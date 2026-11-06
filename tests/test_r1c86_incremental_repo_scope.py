"""R1-C86 — incremental builds for repo-scoped graphs, and for a package that is not at the git root.

Design `docs/design/incremental_repo_scope.md` (pre-registered 3cb2c9c).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from codemap.cli import main

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _git_repo(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "a"],
                   cwd=root, check=True)
    return root


def _modules(prefix: str, n: int = 6) -> dict[str, str]:
    out = {f"{prefix}/__init__.py": ""}
    for i in range(1, n + 1):
        out[f"{prefix}/m{i}.py"] = f"def f{i}():\n    return {i}\n\n\ndef g{i}():\n    return f{i}()\n"
    return out


def _same(a: Path, b: Path) -> bool:
    x, y = json.loads(a.read_text()), json.loads(b.read_text())
    for g in (x, y):
        g["provenance"].pop("incremental", None)
    return x == y


def _mode(capsys) -> str:
    err = capsys.readouterr().err
    line = next((ln for ln in err.splitlines() if ln.startswith("[incremental]")), "")
    return line.split()[1].rstrip(":") if line else ""


# -- D0 ----------------------------------------------------------------------

@pytest.mark.parametrize("prefix", ["research/shared", "src/shared"])
def test_D0_a_package_below_the_git_root_sees_its_edit(tmp_path, monkeypatch, capsys, prefix):
    root = _git_repo(tmp_path, _modules(prefix))
    monkeypatch.chdir(root)
    pkg = prefix
    assert main(["build", pkg, "-o", "i.json"]) == 0
    (root / prefix / "m3.py").write_text("def f3():\n    return 33\n\n\ndef g3():\n    return f3()\n")
    capsys.readouterr()
    assert main(["build", pkg, "--incremental", "-o", "i.json"]) == 0
    assert _mode(capsys) == "incremental"          # 0.0.33: "unchanged" — the edit was not seen
    assert main(["build", pkg, "-o", "f.json"]) == 0
    assert _same(root / "i.json", root / "f.json")


# -- D1 ----------------------------------------------------------------------

REPO = {**_modules("src/pkg"),
        "tests/test_m1.py": "from pkg.m1 import f1\n\n\ndef test_f1():\n    assert f1() == 1\n",
        "docs/m1.md": "# m1\n\nUse `pkg.m1.f1`.\n"}
BUILD = ["build", "src/pkg", "--consumer", "tests", "--docs", "docs", "--mode", "full"]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = _git_repo(tmp_path, REPO)
    monkeypatch.chdir(root)
    assert main(BUILD + ["-o", "i.json"]) == 0
    return root


EDITS = {
    "core-edit": (lambda r: (r / "src/pkg/m3.py").write_text("def f3():\n    return 9\n"), "incremental"),
    "consumer-edit": (lambda r: (r / "tests/test_m1.py").open("a").write(
        "\n\ndef test_again():\n    assert f1()\n"), "unchanged"),
    "doc-edit": (lambda r: (r / "docs/m1.md").open("a").write("\nAlso `pkg.m2.f2`.\n"), "unchanged"),
    "core-add": (lambda r: (r / "src/pkg/m7.py").write_text(
        "from pkg.m1 import f1\n\n\ndef k():\n    return f1()\n"), "incremental"),
    "core-remove": (lambda r: (r / "src/pkg/m6.py").unlink(), "incremental"),
}


@pytest.mark.parametrize("case", sorted(EDITS))
def test_E2_a_repo_scoped_incremental_build_equals_a_full_one(repo, capsys, case):
    edit, mode = EDITS[case]
    edit(repo)
    capsys.readouterr()
    assert main(BUILD + ["--incremental", "-o", "i.json"]) == 0
    err_mode = _mode(capsys)
    assert err_mode == mode, case
    assert main(BUILD + ["-o", "f.json"]) == 0
    assert _same(repo / "i.json", repo / "f.json"), case
    assert json.loads((repo / "i.json").read_text())["provenance"].get("incremental") is True


def test_D1_the_old_note_is_gone(repo, capsys):
    capsys.readouterr()
    main(BUILD + ["--incremental", "-o", "i.json"])
    assert "--incremental was not applied" not in capsys.readouterr().err


# -- D2 ----------------------------------------------------------------------

MENU = '''from typing import Protocol


class P(Protocol):
    def band(self, k): ...


class A:
    def band(self, k):
        return k


class B:
    def band(self, k):
        return -k


class Spec:
    def build(self) -> P:
        return A()
'''


def test_D2_spliced_deep_callers_keep_their_protocol_fan_out(tmp_path, monkeypatch, capsys):
    files = {"pkg/__init__.py": "", "pkg/menu.py": MENU,
             "pkg/use.py": "from pkg.menu import Spec\n\n\ndef run(spec: Spec):\n    return spec.build().band(1)\n"}
    files.update({f"pkg/x{i}.py": f"def x{i}():\n    return {i}\n" for i in range(1, 6)})
    root = _git_repo(tmp_path, files)
    monkeypatch.chdir(root)
    assert main(["build", "pkg", "--deep", "-o", "g.json"]) == 0
    fan = lambda: {(e["source"], e["target"]) for e in json.loads((root / "g.json").read_text())["edges"]
                   if e["type"] == "calls" and e.get("extras", {}).get("resolution") == "protocol"}
    before = fan()
    assert ("pkg.use.run", "pkg.menu.B.band") in before
    (root / "pkg" / "x3.py").write_text("def x3():\n    return 33\n")     # pkg.use untouched
    capsys.readouterr()
    assert main(["build", "pkg", "--deep", "--incremental", "-o", "g.json"]) == 0
    assert _mode(capsys) == "incremental"
    assert ("pkg.use.run", "pkg.menu.B.band") in fan()


# -- found by the bquant replay (E3): node extras the splice did not carry ---------

def test_every_extras_key_the_jedi_passes_stamp_is_spliced(tmp_path):
    """Derived, not listed: whatever add_behavior / add_attrflow add to node extras must be
    in the splice set, or an unaffected module silently loses it (R1-C86 E3)."""
    from codemap.extract.attrflow import add_attrflow
    from codemap.extract.behavior import add_behavior
    from codemap.extract.griffe_extractor import build_structural
    from codemap.incremental import _BEHAVIORAL_EXTRAS
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text(
        "import os\n\n\nclass C:\n    size = 1\n\n    def go(self):\n        return self.size\n\n\n"
        "def outer():\n    def inner():\n        return os.getcwd()\n    return inner()\n\n\n"
        "def twice():\n    return len([1])\n\n\ndef twice():\n    return 2\n\n\n"
        "if True:\n    print(len([]))\n")
    graph, root, name, sp = build_structural(str(pkg))
    before = {nid: set(n.extras) for nid, n in graph.nodes.items()}
    add_behavior(graph, root, name, deep=False, search_path=sp)
    add_attrflow(graph, root, name, deep=False, search_path=sp)
    stamped = set().union(*(set(n.extras) - before.get(nid, set()) for nid, n in graph.nodes.items()))
    assert {"calls_nested", "calls_shadowed", "calls"} <= stamped   # the fixture exercises them
    assert stamped <= set(_BEHAVIORAL_EXTRAS), stamped - set(_BEHAVIORAL_EXTRAS)


def test_an_unaffected_module_with_a_nested_def_survives_an_incremental_build(tmp_path, monkeypatch, capsys):
    files = _modules("pkg")
    files["pkg/nested.py"] = ("import os\n\n\ndef outer():\n    def inner():\n        return os.getcwd()\n"
                              "    return inner()\n")
    root = _git_repo(tmp_path, files)
    monkeypatch.chdir(root)
    assert main(["build", "pkg", "-o", "i.json"]) == 0
    (root / "pkg" / "m2.py").write_text("def f2():\n    return 22\n")
    capsys.readouterr()
    assert main(["build", "pkg", "--incremental", "-o", "i.json"]) == 0
    assert _mode(capsys) == "incremental"
    assert main(["build", "pkg", "-o", "f.json"]) == 0
    assert _same(root / "i.json", root / "f.json")
