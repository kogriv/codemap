"""R1-C119 — the first build in a fresh clone: no graph directory yet. E1–E4 in BACKLOG.md (R1-C119)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from codemap.cli import main
from codemap.devkit.hooks import currency_line


def _pkg(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/__init__.py").write_text("def f():\n    return 1\n")
    return tmp_path


def test_e1_build_creates_the_graph_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(_pkg(tmp_path))
    assert main(["build", "pkg", "-o", ".codemap/deep/graph.json"]) == 0
    assert (tmp_path / ".codemap/deep/graph.json").is_file()


@pytest.mark.parametrize("argv", [["check", "--graph", "{g}"], ["query", "f", "--graph", "{g}"],
                                  ["report", "dead-code", "--graph", "{g}"]])
def test_e2_a_missing_graph_is_refused_with_the_command(tmp_path, argv):
    g = str(tmp_path / ".codemap/graph.json")
    r = subprocess.run([sys.executable, "-m", "codemap", *[a.replace("{g}", g) for a in argv]],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert f"no graph at {g}" in r.stderr and "codemap build <package> -o" in r.stderr, r.stderr
    assert "Errno" not in r.stderr


def test_e3_refresh_names_the_real_path(tmp_path):
    g = str(tmp_path / "nowhere/graph.json")
    r = subprocess.run([sys.executable, "-m", "codemap", "refresh", g], capture_output=True, text=True)
    assert r.returncode != 0 and f"no graph at {g}" in r.stderr and "{graph}" not in r.stderr, r.stderr


def test_e4_status_gives_the_first_build_command(tmp_path):
    st = {"package": "src/pkg", "consumers": ["tests"], "docs": ["docs"], "graph": ".codemap/graph.json"}
    line = currency_line(tmp_path, st)
    assert ("`codemap build src/pkg --consumer tests --docs docs --mode full -o .codemap/graph.json`" in line), line



def test_status_does_not_promise_a_hook_that_is_off(tmp_path):
    """tgsh-26, 23.11: with `hook: false` the absent-graph line must not say the hook keeps the graph."""
    st = {"package": "pkg", "consumers": [], "docs": [], "graph": ".codemap/graph.json", "options": {"hook": False}}
    line = currency_line(tmp_path, st)
    assert "post-commit hook keeps it" not in line and "`codemap refresh .codemap/graph.json`" in line
    st["options"]["hook"] = True
    assert "post-commit hook keeps it" in currency_line(tmp_path, st)
