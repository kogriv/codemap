"""R1-C134 — `refresh` checks the recorded recipe the way `build` will read it.

Follow-up audit FU-02, plus two more shapes found here. Expectations E1–E7 are in BACKLOG.md (R1-C134), written
before the change; on 0.0.46 a repeated `-o`, an abbreviated `--ou`, an attached `-oX` and a recorded working
directory that is not there each made `codemap refresh` write a graph somewhere else.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from codemap.cli import _recipe_problem


@pytest.fixture()
def built(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/__init__.py").write_text("def f():\n    return 1\n")
    subprocess.run([sys.executable, "-m", "codemap", "build", "pkg", "-o", "graph.json"], cwd=tmp_path, check=True,
                   capture_output=True)
    (tmp_path / "sentinel.json").write_text('{"keep": true}\n')
    (tmp_path / "run").mkdir()                           # refresh is run from elsewhere
    return tmp_path


def _refresh(root: Path, argv: list[str], cwd: str | None) -> tuple[subprocess.CompletedProcess, set[str], bytes]:
    sidecar = root / "graph.json.meta.json"
    meta = json.loads(sidecar.read_text())
    meta["argv"], meta["cwd"] = argv, cwd
    sidecar.write_text(json.dumps(meta))
    graph = (root / "graph.json").read_bytes()
    before = {str(p) for p in root.rglob("*")}
    r = subprocess.run([sys.executable, "-m", "codemap", "refresh", str(root / "graph.json")], cwd=root / "run",
                       capture_output=True, text=True)
    new = {str(p) for p in root.rglob("*")} - before
    assert (root / "sentinel.json").read_text() == '{"keep": true}\n'
    return r, new, graph


@pytest.mark.parametrize("label, tail", [
    ("E1 repeated -o", ["-o", "graph.json", "-o", "sentinel.json"]),
    ("E2 repeated --out=", ["--out=graph.json", "--out=sentinel.json"]),
    ("E3 abbreviated --ou", ["-o", "graph.json", "--ou", "sentinel.json"]),
    ("E3 attached -oX", ["-o", "graph.json", "-osentinel.json"]),
    ("E3 mixed", ["--out=graph.json", "-o", "other.json"]),
])
def test_e1_e3_the_check_reads_the_output_build_would_write(built, label, tail):
    r, new, _ = _refresh(built, ["build", "pkg", *tail], str(built))
    assert r.returncode != 0 and "not repeated" in r.stderr and "not this graph" in r.stderr, (label, r.stderr)
    assert new == set(), (label, new)


def test_e4_a_recorded_working_directory_that_is_not_there_is_refused(built, tmp_path):
    out = "../.." + str(built / "graph.json")           # right only when counted from /nonexistent/cwd
    r, new, _ = _refresh(built, ["build", str(built / "pkg"), "-o", out], "/nonexistent/cwd")
    assert r.returncode != 0 and "is not a directory here" in r.stderr, r.stderr
    assert new == set()


@pytest.mark.parametrize("tail", [["-o", "graph.json"], ["--out=graph.json"], ["--out", "graph.json"]])
def test_e5_an_ordinary_recipe_still_rebuilds(built, tail):
    r, new, _ = _refresh(built, ["build", "pkg", *tail], str(built))
    assert r.returncode == 0, r.stderr
    assert new == set() and json.loads((built / "graph.json").read_text())["nodes"]


def test_e7_a_recipe_build_does_not_take_is_refused_by_name(tmp_path):
    g = str(tmp_path / "g.json")
    problem = _recipe_problem({"argv": ["build", "pkg", "-o", "g.json", "--bogus"], "cwd": str(tmp_path)}, g)
    assert problem and problem.startswith("`build` does not take it") and "--bogus" in problem, problem
    assert "usage:" not in problem
    assert "no graph file" in _recipe_problem({"argv": ["build", "pkg"], "cwd": str(tmp_path)}, g)
