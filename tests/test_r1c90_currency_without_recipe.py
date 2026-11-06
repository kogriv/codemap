"""R1-C90 — a graph built elsewhere is checked from its own roots; what cannot be checked is said.

Design `docs/design/currency_without_recipe.md` (pre-registered 3cb2c9c).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from codemap import store
from codemap.cli import main
from codemap.serve.session import Session


def _tree(root: Path):
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "m.py").write_text("def f():\n    return 1\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_m.py").write_text("from pkg.m import f\n\n\ndef test_f():\n    f()\n")


def _break_recipe(g: Path):
    meta = Path(str(g) + ".meta.json")
    m = json.loads(meta.read_text())
    m["cwd"] = "/nonexistent/elsewhere"
    meta.write_text(json.dumps(m))


@pytest.fixture
def built(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    _tree(root)
    monkeypatch.chdir(root)
    g = tmp_path / "g.json"
    assert main(["build", "pkg", "--consumer", "tests", "--mode", "full", "-o", str(g)]) == 0
    _break_recipe(g)
    return root, g


def _currency(g, base=None):
    return Session(store.load(str(g)), graph_path=str(g), currency_ttl=0,
                   source_root=base).handle({"op": "stats"})["currency"]


def test_E1_no_recipe_falls_back_to_the_graphs_roots(built):
    root, g = built
    c = _currency(g)
    assert c["status"] == "current" and c["via"].startswith("provenance roots under")
    (root / "pkg" / "m.py").write_text("def f():\n    return 2\n")
    assert _currency(g)["status"] == "behind"


def test_E2_the_same_tree_elsewhere_is_current(built, tmp_path, monkeypatch):
    root, g = built
    other = tmp_path / "other"
    shutil.copytree(root, other)
    monkeypatch.chdir(tmp_path)               # neither copy is the cwd: base is explicit
    assert _currency(g, base=str(other))["status"] == "current"


def test_D1_the_recipe_path_still_answers_first(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    _tree(root)
    monkeypatch.chdir(root)
    g = tmp_path / "g.json"
    main(["build", "pkg", "--consumer", "tests", "--mode", "full", "-o", str(g)])
    assert _currency(g)["via"] == "recipe"


def test_E4_cannot_check_is_one_note(built, tmp_path, monkeypatch, capsys):
    root, g = built
    monkeypatch.chdir(tmp_path)               # the roots are not under here
    capsys.readouterr()
    assert main(["query", "f", "--graph", str(g)]) == 0
    first = capsys.readouterr()
    notes = [ln for ln in first.err.splitlines() if ln.startswith("[note] could not check")]
    assert len(notes) == 1 and "roots are not under" in notes[0]
    monkeypatch.chdir(root)
    assert main(["query", "f", "--graph", str(g)]) == 0
    second = capsys.readouterr()
    assert second.out == first.out and "[note] could not check" not in second.err
