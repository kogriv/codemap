"""R1-C94 — namespace subdirectories inside a package are read; flat imports name the module they import.

Design `docs/design/root_builds.md` (pre-registered dedb88a).
"""

from __future__ import annotations

import json
import py_compile
from pathlib import Path

import pytest

from codemap.cli import main
from codemap.extract.griffe_extractor import extract


def _write(root: Path, files: dict) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


def _edges(graph, kind):
    return {(e.source, e.target) for e in graph.edges if e.type == kind}


NS = {
    "pkg/__init__.py": "",
    "pkg/layers/act.py": "def act():\n    return 1\n",
    "pkg/layers/more.py": "from .act import act\n\n\ndef twice():\n    return act() + act()\n",
    "pkg/layers/deep/__init__.py": "",
    "pkg/layers/deep/leaf.py": "def leaf():\n    return 2\n",
    "pkg/net.py": ("from pkg.layers.act import act\nfrom pkg.layers.deep.leaf import leaf\n\n\n"
                   "def run():\n    return act() + leaf()\n"),
}


# -- D1 -------------------------------------------------------------------------------------

def test_E1_a_namespace_subdirectory_is_read(tmp_path):
    _write(tmp_path, NS)
    graph = extract(str(tmp_path / "pkg"))
    assert graph.nodes["pkg.layers"].file is None, "a namespace module has no file"
    assert {"pkg.layers.act.act", "pkg.layers.more.twice", "pkg.layers.deep.leaf.leaf"} <= set(graph.nodes)
    calls = _edges(graph, "calls")
    assert ("pkg.net.run", "pkg.layers.act.act") in calls
    assert ("pkg.net.run", "pkg.layers.deep.leaf.leaf") in calls, "a package below a namespace dir"
    assert ("pkg.layers.more.twice", "pkg.layers.act.act") in calls, "relative import inside it"
    assert ("pkg.net", "pkg.layers.act") in _edges(graph, "imports")
    assert "skipped" not in graph.provenance["inputs"]


def test_E3_names_python_cannot_import_stay_unread(tmp_path):
    _write(tmp_path, {"pkg/__init__.py": "", "pkg/my-dir/x.py": "def f():\n    return 1\n",
                      "pkg/ok/a.b.py": "def g():\n    return 1\n", "pkg/ok/fine.py": "Y = 1\n"})
    graph = extract(str(tmp_path / "pkg"))
    skipped = {s["path"] for s in graph.provenance["inputs"].get("skipped", [])}
    assert skipped == {"pkg/my-dir/x.py", "pkg/ok/a.b.py"}
    assert "pkg.ok.fine.Y" in graph.nodes


def test_E3_a_sourceless_pyc_in_a_namespace_dir_is_not_imported(tmp_path):
    _write(tmp_path, {"pkg/__init__.py": "", "pkg/layers/real.py": "Z = 1\n"})
    marker = tmp_path / "MARKER"
    evil = tmp_path / "pkg" / "layers" / "evil.py"
    evil.write_text(f"import pathlib\npathlib.Path({str(marker)!r}).write_text('x')\n")
    py_compile.compile(str(evil), cfile=str(evil.with_suffix(".pyc")), doraise=True)
    evil.unlink()
    graph = extract(str(tmp_path / "pkg"))
    assert not marker.exists()
    assert "pkg.layers.real.Z" in graph.nodes and "pkg.layers.evil" not in graph.nodes
    assert graph.provenance["inputs"]["compiled"] == ["pkg/layers/evil.pyc"]


def test_E1_incremental_equals_full_after_an_edit_in_a_namespace_dir(tmp_path, monkeypatch, capsys):
    root = tmp_path / "t"
    _write(root, NS)
    monkeypatch.chdir(root)
    g, full = tmp_path / "g.json", tmp_path / "full.json"
    assert main(["build", "pkg", "-o", str(g)]) == 0
    _write(root, {"pkg/layers/act.py": "def act():\n    return 11\n\n\ndef extra():\n    return act()\n"})
    assert main(["build", "pkg", "--incremental", "-o", str(g)]) == 0
    assert main(["build", "pkg", "-o", str(full)]) == 0
    a, b = (json.loads(p.read_text()) for p in (g, full))
    for x in (a, b):
        x["provenance"].pop("incremental", None)
    assert a == b
    assert "pkg.layers.act.extra" in {n["id"] for n in a["nodes"]}


# -- D2 -------------------------------------------------------------------------------------

ROOT = {
    "repo/engine/dataset.py": "def get():\n    return 1\n",
    "repo/engine/util/io.py": "def load():\n    return 2\n",
    "repo/main.py": ("from engine.dataset import get\nimport engine.util.io\n\n\n"
                     "def main():\n    return get() + engine.util.io.load()\n"),
    "repo/helper.py": "X = 1\n",
    "repo/tool.py": "from helper import X\n",
}


def test_E2_a_dotted_flat_import_points_at_the_module_it_imports(tmp_path):
    _write(tmp_path, ROOT)
    graph = extract(str(tmp_path / "repo"))
    flat = {(e.source, e.target) for e in graph.edges
            if e.type == "imports" and e.extras.get("resolution") == "flat"}
    assert ("repo.main", "repo.engine.dataset") in flat
    assert ("repo.main", "repo.engine.util.io") in flat
    assert ("repo.main", "repo.engine") not in flat, "not the head any more"
    assert ("repo.tool", "repo.helper") in flat, "a bare sibling import is unchanged"


def test_a_dotted_path_past_the_last_module_stops_at_the_module(tmp_path):
    _write(tmp_path, {"repo/engine/dataset.py": "def get():\n    return 1\n",
                      "repo/main.py": "from engine.dataset.get import nothing\n"})
    graph = extract(str(tmp_path / "repo"))
    assert ("repo.main", "repo.engine.dataset") in _edges(graph, "imports")


@pytest.mark.parametrize("target", ["engine.missing", "engine"])
def test_an_unknown_tail_falls_back_to_the_deepest_known_module(tmp_path, target):
    _write(tmp_path, {"repo/engine/__init__.py": "", "repo/engine/dataset.py": "V = 1\n",
                      "repo/main.py": f"import {target}\n"})
    graph = extract(str(tmp_path / "repo"))
    assert ("repo.main", "repo.engine") in _edges(graph, "imports")


# -- D3 (amendment): imports anchored at a namespace root ------------------------------------

ANCHORED = {
    "repo/python/net.py": "def f():\n    return 1\n",
    "repo/teeslice/model.py": "from python.net import f\n\n\ndef model():\n    return f()\n",
    "repo/other/python.py": "def g():\n    return 2\n",
    "repo/other/user.py": "from python import g\n\n\ndef use():\n    return g()\n",
}


def test_E4b_a_nested_module_importing_from_the_root_resolves(tmp_path):
    _write(tmp_path, ANCHORED)
    graph = extract(str(tmp_path / "repo"))
    flat = {(e.source, e.target) for e in graph.edges
            if e.type == "imports" and e.extras.get("resolution") == "flat"}
    assert ("repo.teeslice.model", "repo.python.net") in flat
    assert ("repo.teeslice.model.model", "repo.python.net.f") in _edges(graph, "calls"), "E4‴"


def test_E4b_a_sibling_with_the_same_head_wins_over_the_root(tmp_path):
    _write(tmp_path, ANCHORED)
    graph = extract(str(tmp_path / "repo"))
    assert ("repo.other.user", "repo.other.python") in _edges(graph, "imports")
    assert ("repo.other.user", "repo.python") not in _edges(graph, "imports")
    assert ("repo.other.user.use", "repo.other.python.g") in _edges(graph, "calls")


def test_a_regular_package_target_is_not_root_anchored(tmp_path):
    files = {k.replace("repo/", "pkg/"): v for k, v in ANCHORED.items()}
    files["pkg/__init__.py"] = ""
    for d in ("python", "teeslice", "other"):
        files[f"pkg/{d}/__init__.py"] = ""
    _write(tmp_path, files)
    graph = extract(str(tmp_path / "pkg"))
    assert not any(t.startswith("pkg.python") for s, t in _edges(graph, "imports")
                   if s == "pkg.teeslice.model"), "`python` is not on sys.path for a package"
