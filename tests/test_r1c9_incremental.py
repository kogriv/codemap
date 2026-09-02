"""R1-C9 acceptance — incremental rebuild is byte-identical to a full rebuild.

The whole promise of the incremental path is that recomputing only the affected
modules (and splicing the rest from the old graph) yields *exactly* the graph a full
extract would. These tests pin that across edit / add / remove scenarios on both the
fast and deep tiers, over a small multi-module package with cross-module calls,
inheritance, and attribute access (the relationships the splice must get right).

Deep byte-identity holds here because this fixture's jedi inference is single-hop and
stable. On large packages it does not, and the two reasons are worth keeping apart:

- Two full ``--deep`` builds of an unchanged tree already differ from each other
  (R1-C42), so on that tier there is no fixed artifact to be identical *to*. This was
  attributed to jedi's **cache warmth** until 2026-09-02, when a cold ``XDG_CACHE_HOME``
  per build flipped just as often (5 of 10) and refuted it; the cause is jedi's
  per-script execution budget. That correction reached ``docs/incremental.md`` the same
  day and not this docstring — the copy nobody grepped for.
- The splice adds a divergence of its own (R1-C43): it carries the previous build's
  sample forward, and the rule that would invalidate it reads that same incomplete
  graph. Pinned in ``tests/test_r1c43_incremental_splice.py``.

The splice logic itself is exact, which is what this fixture proves.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codemap import store
from codemap.extract import extract
from codemap.incremental import _path_to_module, update_graph
from codemap.scope import resolve_scope

# -- a small package with the cross-module relationships the splice must preserve ----

BASE = '''\
"""Base module: a class and a dataclass field."""

from dataclasses import dataclass


@dataclass
class Config:
    width: int = 10
    height: int = 20


class Base:
    def run(self) -> int:
        return 1
'''

MID = '''\
"""Mid module: inherits Base, constructs Config, calls across modules."""

from inc_pkg.base import Base, Config


class Mid(Base):
    def run(self) -> int:
        return super().run() + 1


def make() -> Config:
    return Config(width=5, height=6)
'''

LEAF = '''\
"""Leaf module: uses Mid + Config via obj.field (deep tier)."""

from inc_pkg.mid import Mid, make


def go() -> int:
    m = Mid()
    c = make()
    return m.run() + c.width
'''

UTIL = '''\
"""Standalone util, imported by nobody."""


def helper(x: int) -> int:
    return x * 2
'''


def _write_pkg(root: Path) -> Path:
    pkg = root / "inc_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "base.py").write_text(BASE, encoding="utf-8")
    (pkg / "mid.py").write_text(MID, encoding="utf-8")
    (pkg / "leaf.py").write_text(LEAF, encoding="utf-8")
    (pkg / "util.py").write_text(UTIL, encoding="utf-8")
    return pkg


def _scope(pkg: Path) -> dict:
    return resolve_scope(pkg, use_git=False)


def _assert_incremental_matches_full(old_graph, pkg, scope0, *, deep, expect_mode):
    """The splice reproduces a full build's *content* — and says it was not one.

    R1-C43 split what used to be a single `dumps == dumps`. The graphs must agree on
    every node and edge, which is the acceptance bar; they must **disagree** on
    `provenance.incremental`, because an artifact that was partly carried over may not
    present itself as one that was recomputed. Comparing the whole file conflated the
    two, and the field that exists to distinguish them would have read as a regression.
    """
    scope1 = _scope(pkg)
    inc, info = update_graph(old_graph, pkg, scope0, scope1, deep=deep)
    full = extract(pkg, deep=deep)

    def content(g):
        d = json.loads(store.dumps(g))
        d.pop("provenance", None)
        return json.dumps(d, sort_keys=True)

    assert content(inc) == content(full), f"incremental != full ({info})"
    assert full.provenance["incremental"] is False
    # a small toy package trips the full-rebuild fallback easily; the correctness
    # invariant holds either way, so accept a set of allowed modes — but the flag must
    # follow the mode that actually ran, not the one we hoped for.
    assert info["mode"] in expect_mode
    assert inc.provenance["incremental"] is (info["mode"] != "full")
    return inc, info


# -- path → module mapping ----------------------------------------------------

def test_path_to_module():
    assert _path_to_module("inc_pkg/base.py", "inc_pkg") == "inc_pkg.base"
    assert _path_to_module("inc_pkg/__init__.py", "inc_pkg") == "inc_pkg"
    assert _path_to_module("inc_pkg/a/b.py", "inc_pkg") == "inc_pkg.a.b"
    assert _path_to_module("docs/guide.md", "inc_pkg") is None
    assert _path_to_module("other/x.py", "inc_pkg") is None


# -- no change → unchanged (the watcher's hot path) ---------------------------

def test_no_change_returns_unchanged(tmp_path):
    pkg = _write_pkg(tmp_path)
    g0 = extract(pkg, deep=False)
    scope0 = _scope(pkg)
    inc, info = update_graph(g0, pkg, scope0, _scope(pkg), deep=False)
    assert info["mode"] == "unchanged"
    assert inc is g0  # untouched


def test_doc_only_change_is_unchanged(tmp_path):
    pkg = _write_pkg(tmp_path)
    g0 = extract(pkg, deep=False)
    scope0 = _scope(pkg)
    (tmp_path / "inc_pkg" / "README.md").write_text("# hi\n", encoding="utf-8")
    _, info = update_graph(g0, pkg, scope0, _scope(pkg), deep=False)
    assert info["mode"] == "unchanged"


# -- edit a leaf module (fast + deep) -----------------------------------------

@pytest.mark.parametrize("deep", [False, True])
def test_edit_leaf_matches_full(tmp_path, deep):
    pkg = _write_pkg(tmp_path)
    g0 = extract(pkg, deep=deep)
    scope0 = _scope(pkg)
    # add a call inside leaf.go — only leaf's behavioral layer should change.
    (pkg / "leaf.py").write_text(
        LEAF.replace("return m.run() + c.width",
                     "total = m.run() + c.width\n    return total + c.height"),
        encoding="utf-8")
    _, info = _assert_incremental_matches_full(g0, pkg, scope0, deep=deep,
                                               expect_mode={"incremental", "full"})
    assert "inc_pkg.leaf" in info["affected"]


# -- edit a depended-upon module (base) — dependents must re-resolve ----------

@pytest.mark.parametrize("deep", [False, True])
def test_edit_base_matches_full(tmp_path, deep):
    pkg = _write_pkg(tmp_path)
    g0 = extract(pkg, deep=deep)
    scope0 = _scope(pkg)
    # add a new field to Config — construction/obj.field sites in mid/leaf depend on it.
    (pkg / "base.py").write_text(
        BASE.replace("    height: int = 20", "    height: int = 20\n    depth: int = 0"),
        encoding="utf-8")
    _assert_incremental_matches_full(g0, pkg, scope0, deep=deep,
                                     expect_mode={"incremental", "full"})


# -- add a new module ---------------------------------------------------------

@pytest.mark.parametrize("deep", [False, True])
def test_add_module_matches_full(tmp_path, deep):
    pkg = _write_pkg(tmp_path)
    g0 = extract(pkg, deep=deep)
    scope0 = _scope(pkg)
    (pkg / "extra.py").write_text(
        "from inc_pkg.base import Base\n\n\nclass Extra(Base):\n    pass\n",
        encoding="utf-8")
    _assert_incremental_matches_full(g0, pkg, scope0, deep=deep,
                                     expect_mode={"incremental", "full"})


# -- remove a module ----------------------------------------------------------

@pytest.mark.parametrize("deep", [False, True])
def test_remove_module_matches_full(tmp_path, deep):
    pkg = _write_pkg(tmp_path)
    g0 = extract(pkg, deep=deep)
    scope0 = _scope(pkg)
    (pkg / "util.py").unlink()  # imported by nobody — clean removal
    inc, _ = _assert_incremental_matches_full(g0, pkg, scope0, deep=deep,
                                              expect_mode={"incremental", "full"})
    assert "inc_pkg.util" not in {n.id for n in inc.nodes.values()}


# -- full-rebuild fallback when most of the package is affected ---------------

def test_full_fallback_when_widely_affected(tmp_path):
    pkg = _write_pkg(tmp_path)
    g0 = extract(pkg, deep=False)
    scope0 = _scope(pkg)
    # touch 3 of 5 modules at once → ≥50% affected → full-rebuild fallback.
    (pkg / "base.py").write_text(BASE + "\n\ndef a():\n    return 0\n", encoding="utf-8")
    (pkg / "mid.py").write_text(MID + "\n\ndef b():\n    return 0\n", encoding="utf-8")
    (pkg / "util.py").write_text(UTIL + "\n\ndef c():\n    return 0\n", encoding="utf-8")
    inc, info = update_graph(g0, pkg, scope0, _scope(pkg), deep=False)
    assert info["mode"] == "full"
    assert store.dumps(inc) == store.dumps(extract(pkg, deep=False))
