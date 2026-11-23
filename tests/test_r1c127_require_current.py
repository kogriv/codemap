"""R1-C127 — `check --require-current` refuses a graph whose currency is unknown. E1–E3 in BACKLOG.md."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _run(cwd: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "codemap", *argv], cwd=cwd, capture_output=True, text=True)


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/__init__.py").write_text("def f():\n    return 1\n")
    (tmp_path / "codemap.toml").write_text("[architecture]\nno_cycles = true\n")
    assert _run(tmp_path, "build", "pkg", "-o", "g.json").returncode == 0
    return tmp_path


def _unknown(tree: Path) -> None:
    """A graph handed over without its provenance: currency cannot be checked."""
    d = json.loads((tree / "g.json").read_text())
    d["provenance"].pop("scope_id", None)
    (tree / "g.json").write_text(json.dumps(d))
    (tree / "g.json.meta.json").unlink()


def test_e1_unknown_currency_fails_only_with_the_flag(tree):
    _unknown(tree)
    assert _run(tree, "check", "--graph", "g.json", "--root", ".").returncode == 0          # E3: as before
    r = _run(tree, "check", "--graph", "g.json", "--root", ".", "--require-current")
    assert r.returncode == 2 and "not known to match its source tree" in r.stderr, r.stderr


def test_e2_a_current_or_freshly_built_graph_passes(tree):
    assert _run(tree, "check", "--graph", "g.json", "--root", ".", "--require-current").returncode == 0
    assert _run(tree, "check", "--build", "pkg", "--root", ".", "--require-current").returncode == 0


def test_the_flag_and_allow_stale_exclude_each_other(tree):
    r = _run(tree, "check", "--graph", "g.json", "--require-current", "--allow-stale")
    assert r.returncode == 2 and "not allowed with" in r.stderr
