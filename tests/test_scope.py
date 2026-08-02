"""M19.A acceptance — input scope manifest.

Self-contained: builds temp trees (fs + a real git repo) rather than depending on a
sibling checkout. Pins the model's guarantees: deterministic content-addressed
scope_id, git-mode enumeration (gitignore-correct, dirty-aware), profile, and diff.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from codemap.scope import diff_scopes, resolve_scope


def _tree(base: Path) -> None:
    """A package + tests + docs + a non-standard venv and caches to be excluded."""
    (base / "pkg").mkdir()
    (base / "pkg" / "__init__.py").write_text("x = 1\n")
    (base / "pkg" / "core.py").write_text("def f():\n    return 1\n")
    (base / "tests").mkdir()
    (base / "tests" / "test_core.py").write_text("from pkg.core import f\n")
    (base / "docs").mkdir()
    (base / "docs" / "guide.md").write_text("# Guide\n`pkg.core.f`\n")
    # noise that must NOT enter the scope:
    (base / "venv_x" / "lib").mkdir(parents=True)
    (base / "venv_x" / "lib" / "junk.py").write_text("import numpy\n")
    (base / "pkg" / "__pycache__").mkdir()
    (base / "pkg" / "__pycache__" / "core.pyc").write_text("bytecode\n")


@pytest.fixture
def tree(tmp_path) -> Path:
    _tree(tmp_path)
    return tmp_path


def _resolve(base: Path, **kw):
    return resolve_scope(base / "pkg", consumers=(base / "tests",),
                         docs=(base / "docs",), **kw)


# -- fs mode ------------------------------------------------------------------

def test_fs_resolves_and_excludes(tree):
    s = _resolve(tree, use_git=False)
    paths = {f["path"] for f in s["files"]}
    assert paths == {"pkg/__init__.py", "pkg/core.py", "tests/test_core.py", "docs/guide.md"}
    assert not any("venv_x" in p or ".pyc" in p for p in paths)   # excludes work
    assert s["git"] == {"mode": "fs"}
    assert s["scope_id"].startswith("sha256:")


def test_fs_deterministic(tree):
    assert _resolve(tree, use_git=False)["scope_id"] == _resolve(tree, use_git=False)["scope_id"]


def test_profile(tree):
    p = _resolve(tree, use_git=False)["profile"]
    assert p["file_count"] == 4
    assert p["by_role"]["core"]["files"] == 2
    assert p["by_role"]["tests"]["files"] == 1
    assert p["by_role"]["docs"]["files"] == 1
    assert p["by_ext"][".py"]["files"] == 3
    assert p["by_ext"][".md"]["files"] == 1
    assert p["loc_total"] > 0
    assert p["largest"][0]["bytes"] >= p["largest"][-1]["bytes"]


def test_content_change_flips_scope_id_and_diff(tree):
    a = _resolve(tree, use_git=False)
    (tree / "pkg" / "core.py").write_text("def f():\n    return 2  # changed\n")
    b = _resolve(tree, use_git=False)
    assert a["scope_id"] != b["scope_id"]
    d = diff_scopes(a, b)
    assert d["changed"] == ["pkg/core.py"]
    assert d["added"] == [] and d["removed"] == []
    assert d["same_scope_id"] is False


def test_diff_add_remove(tree):
    a = _resolve(tree, use_git=False)
    (tree / "pkg" / "extra.py").write_text("y = 2\n")
    b = _resolve(tree, use_git=False)
    d = diff_scopes(a, b)
    assert d["added"] == ["pkg/extra.py"] and d["removed"] == [] and d["changed"] == []


# -- git mode -----------------------------------------------------------------

def _git(base: Path, *args: str) -> None:
    subprocess.run(("git", "-C", str(base), *args), check=True,
                   capture_output=True, text=True)


@pytest.fixture
def git_tree(tmp_path) -> Path:
    if not shutil.which("git"):
        pytest.skip("git not available")
    _tree(tmp_path)
    (tmp_path / ".gitignore").write_text("venv_*/\n__pycache__/\n*.pyc\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def test_git_mode_excludes_venv_via_gitignore(git_tree):
    s = _resolve(git_tree)                       # use_git=True (default)
    paths = {f["path"] for f in s["files"]}
    assert "venv_x/lib/junk.py" not in paths     # gitignored → never enumerated
    assert "pkg/core.py" in paths
    assert s["git"]["mode"] == "git"
    assert s["git"]["dirty"] is False
    assert s["git"]["commit"] and s["git"]["ref"]
    # git blob hashes recorded for free
    assert all("git_blob" in f for f in s["files"])


def test_git_mode_dirty_tracking(git_tree):
    (git_tree / "pkg" / "core.py").write_text("def f():\n    return 99\n")  # uncommitted
    s = _resolve(git_tree)
    assert s["git"]["dirty"] is True
    assert "pkg/core.py" in s["git"]["dirty_files"]
    # identity still reflects the actual working-tree bytes (not HEAD)
    assert s["scope_id"] != _resolve_committed_id(git_tree)


def _resolve_committed_id(base: Path) -> str:
    # scope_id of the committed content == fs of HEAD; here we just recompute after revert
    subprocess.run(("git", "-C", str(base), "checkout", "--", "pkg/core.py"),
                   check=True, capture_output=True, text=True)
    sid = _resolve(base)["scope_id"]
    return sid
