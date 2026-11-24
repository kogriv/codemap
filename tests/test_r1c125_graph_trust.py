"""R1-C125 — a graph file and its sidecar are artifacts anyone can hand over: what they say is checked.

Expectations E1–E4 are in BACKLOG.md (R1-C125), written before the change (external audit F-03, F-06, F-14).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from codemap import store
from codemap.cli import _recipe_problem, _write_vault
from codemap.extract import extract
from codemap.model import Graph, GraphFormatError
from codemap.serve.session import Session


def _graph(tmp_path: Path) -> Path:
    (tmp_path / "src/pkg").mkdir(parents=True)
    (tmp_path / "src/pkg/__init__.py").write_text("def f():\n    return 1\n")
    path = tmp_path / "g.json"
    store.save(extract(str(tmp_path / "src/pkg")), path)
    return path


def _with_file(path: Path, file: str) -> dict:
    d = json.loads(path.read_text())
    for n in d["nodes"]:
        if n["id"] == "pkg.f":
            n["file"] = file
    return d


def test_e1_source_does_not_read_outside_the_source_root(tmp_path):
    from codemap.cli import main
    path = _graph(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET\n")
    root = tmp_path / "src"
    assert main(["build", str(root / "pkg"), "-o", str(path)]) == 0
    good = Session(store.load(path), source_root=str(root), graph_path=str(path)).handle(
        {"op": "source", "args": {"symbol": "pkg.f"}})
    assert "def f" in good["result"]["code"]                          # control
    (root / "link.py").symlink_to(secret)
    g = Graph.from_dict(_with_file(path, "link.py"))
    out = Session(g, source_root=str(root)).handle({"op": "source", "args": {"symbol": "pkg.f"}})["result"]
    assert out["code"] is None and "outside the source root" in out["note"]


@pytest.mark.parametrize("file", ["../secret.txt", "/etc/hostname", "a/../../secret.txt", "C:/x.py", "\\\\srv\\x"])
def test_e3_a_graph_with_an_escaping_file_is_refused_at_load(tmp_path, file):
    d = _with_file(_graph(tmp_path), file)
    with pytest.raises(GraphFormatError, match=r"nodes\[\d+\]\.file"):
        Graph.from_dict(d)


@pytest.mark.parametrize("mutate, field", [
    (lambda d: d.__setitem__("nodes", {}), "`nodes`"),
    (lambda d: d["nodes"][0].__setitem__("lineno", "3"), ".lineno"),
    (lambda d: d["nodes"][0].__setitem__("lineno", True), ".lineno"),
    (lambda d: d["nodes"][0].__setitem__("evil", 1), "unknown field"),
    (lambda d: d["edges"][0].__setitem__("source", 5), ".source"),
    (lambda d: d["nodes"][0].__setitem__("extras", []), ".extras"),
])
def test_e3_structure_is_checked_and_named(tmp_path, mutate, field):
    d = json.loads(_graph(tmp_path).read_text())
    mutate(d)
    with pytest.raises(GraphFormatError) as exc:
        Graph.from_dict(d)
    assert field in str(exc.value)


def test_e3_a_newer_vocabulary_still_loads(tmp_path):
    d = json.loads(_graph(tmp_path).read_text())
    d["edges"].append({"type": "a_future_edge", "source": "pkg", "target": "pkg.f"})
    d["nodes"].append({"id": "pkg.thing", "kind": "a_future_kind"})
    assert len(Graph.from_dict(d).nodes) == len(d["nodes"])            # degrades, as R1-C37 decided


def test_e2_the_vault_writes_nothing_outside_its_directory(tmp_path):
    out = tmp_path / "vault"
    with pytest.raises(SystemExit, match="outside"):
        _write_vault({"ok.md": "x", "../escaped.md": "y"}, str(out))
    assert not (tmp_path / "escaped.md").exists() and not (out / "ok.md").exists()


def test_e4_refresh_repeats_only_a_build_of_this_graph(tmp_path):
    g = str(tmp_path / "g.json")
    ok = {"argv": ["build", "pkg", "-o", "g.json"], "cwd": str(tmp_path)}
    assert _recipe_problem(ok, g) is None
    assert "not `build`" in _recipe_problem({**ok, "argv": ["devkit", "init", "--package", "pkg"]}, g)
    assert "not this graph" in _recipe_problem({**ok, "argv": ["build", "pkg", "-o", "../elsewhere.json"]}, g)
    assert "no graph file" in _recipe_problem({**ok, "argv": ["build", "pkg"]}, g)
    meta = Path(g + ".meta.json")
    Path(g).write_text("{}")
    meta.write_text(json.dumps({"argv": ["export", "vault", "-o", "/tmp/x"], "cwd": str(tmp_path)}))
    r = subprocess.run([sys.executable, "-m", "codemap", "refresh", g], capture_output=True, text=True)
    assert r.returncode != 0 and "not repeated" in r.stderr and "`export`" in r.stderr
