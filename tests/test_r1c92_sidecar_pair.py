"""R1-C92 — a graph and its sidecar must describe one build, or the sidecar is not used.

Design `docs/design/sidecar_pair.md` (pre-registered 8f525ea).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from codemap import store
from codemap.cli import main
from codemap.serve.session import Session


def _write(root: Path, files: dict):
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


BASE = {"pkg/__init__.py": "", **{f"pkg/m{i}.py": f"def f{i}():\n    return {i}\n" for i in range(1, 7)}}
STATE1 = {"pkg/m1.py": "from pkg.m3 import f3\n\n\ndef f1():\n    return f3()\n"}
EDIT = {"pkg/m2.py": "def f2():\n    return 22\n"}
CALL = ("calls", "pkg.m1.f1", "pkg.m3.f3")


def _build(out: Path, *extra) -> str:
    return main(["build", "pkg", "-o", str(out), *extra])


def _pair(dst: Path, graph: Path, meta_of: Path):
    shutil.copy(graph, dst)
    shutil.copy(str(meta_of) + ".meta.json", str(dst) + ".meta.json")


def _edges(path: Path):
    return {(e["type"], e["source"], e["target"]) for e in json.loads(path.read_text())["edges"]}


def _same(a: Path, b: Path) -> bool:
    x, y = json.loads(a.read_text()), json.loads(b.read_text())
    for g in (x, y):
        g["provenance"].pop("incremental", None)
    return x == y


@pytest.fixture
def tree(tmp_path, monkeypatch):
    root = tmp_path / "t"
    _write(root, BASE)
    monkeypatch.chdir(root)
    g0, g1 = tmp_path / "g0.json", tmp_path / "g1.json"
    assert _build(g0) == 0
    _write(root, STATE1)
    assert _build(g1) == 0
    return root, tmp_path, g0, g1


def test_E1_graph_older_than_its_sidecar_is_rebuilt_in_full(tree, capsys):
    root, tmp, g0, g1 = tree
    g = tmp / "g.json"
    _pair(g, g0, g1)
    _write(root, EDIT)
    capsys.readouterr()
    assert _build(g, "--incremental") == 0
    err = capsys.readouterr().err
    assert "[incremental] full" in err and "the sidecar describes another build" in err
    full = tmp / "full.json"
    assert _build(full) == 0
    assert CALL in _edges(g), "the edit between graph and sidecar must not be lost"
    assert _same(g, full)


def test_E2_graph_newer_than_its_sidecar_is_rebuilt_in_full(tree, capsys):
    root, tmp, g0, g1 = tree
    g = tmp / "g.json"
    _pair(g, g1, g0)
    _write(root, EDIT)
    capsys.readouterr()
    assert _build(g, "--incremental") == 0
    assert "the sidecar describes another build" in capsys.readouterr().err


def test_E3_a_matched_pair_stays_incremental(tree, capsys):
    root, tmp, g0, g1 = tree
    _write(root, EDIT)
    capsys.readouterr()
    assert _build(g1, "--incremental") == 0
    err = capsys.readouterr().err
    assert "[incremental] incremental: 1 module(s) recomputed\n" in err
    full = tmp / "full.json"
    assert _build(full) == 0
    assert _same(g1, full)


def test_E4_repo_scoped_mismatch_is_rebuilt_in_full(tmp_path, monkeypatch, capsys):
    root = tmp_path / "t"
    _write(root, {**BASE, "tests/test_m.py": "from pkg.m1 import f1\n\n\ndef test_f1():\n    f1()\n"})
    monkeypatch.chdir(root)
    flags = ("--consumer", "tests", "--mode", "full")
    g0, g1, g = tmp_path / "g0.json", tmp_path / "g1.json", tmp_path / "g.json"
    assert _build(g0, *flags) == 0
    _write(root, STATE1)
    assert _build(g1, *flags) == 0
    _pair(g, g0, g1)
    _write(root, EDIT)
    capsys.readouterr()
    assert _build(g, *flags, "--incremental") == 0
    assert "the sidecar describes another build" in capsys.readouterr().err
    assert CALL in _edges(g)


def test_E5_currency_does_not_use_a_foreign_sidecar(tree):
    root, tmp, g0, g1 = tree
    g = tmp / "g.json"
    _pair(g, g0, g1)
    c = Session(store.load(str(g)), graph_path=str(g), currency_ttl=0,
                source_root=str(root)).handle({"op": "stats"})["currency"]
    assert c["status"] == "behind"
    assert c["via"].startswith("provenance roots under"), c
    assert "changed" not in c, "no counts from another build's baseline"
