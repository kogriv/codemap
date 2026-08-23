"""R1-C7 acceptance — closed edge-type vocabulary.

Node ``kind`` is an open set by design, but edges are typed: every relationship
codemap emits must be one of ``model.EDGE_TYPES``. These tests pin that set and
fail if a real graph carries a type not declared in it (a new edge type must be
added to the vocabulary + documented, never emitted silently) — or if a declared
type stops appearing on the comprehensive dogfood target (no dead vocabulary).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.extract import extract_repo
from codemap.model import EDGE_TYPES

BQUANT = Path(__file__).resolve().parents[2] / "bquant" / "bquant"
_REPO = BQUANT.parent  # sibling checkout root (has tests/ and docs/)


def test_edge_types_pinned():
    # The closed vocabulary, spelled out — changing it is a deliberate act that
    # updates this test too (guards accidental drift in the constant).
    assert EDGE_TYPES == {
        "contains", "imports", "export", "inherits", "decorated_by",
        "calls", "references", "implements", "reads", "writes", "accesses",
    }


@pytest.fixture(scope="module")
def comprehensive_edge_types() -> set[str]:
    """Every edge type a rich (repo-scoped) extraction of bquant emits."""
    if not BQUANT.is_dir():
        pytest.skip("bquant sibling checkout not present")
    consumers = [str(_REPO / "tests")] if (_REPO / "tests").is_dir() else []
    docs = [str(_REPO / "docs")] if (_REPO / "docs").is_dir() else []
    g = extract_repo(str(BQUANT), consumers=consumers, docs=docs, mode="thin")
    return {e.type for e in g.edges}


def test_no_undeclared_edge_type(comprehensive_edge_types):
    # code must not emit a type outside the declared vocabulary
    undeclared = comprehensive_edge_types - EDGE_TYPES
    assert not undeclared, f"graph emits undeclared edge type(s): {sorted(undeclared)}"


def test_no_dead_vocabulary(comprehensive_edge_types):
    # every declared type actually appears on the comprehensive target (no cruft)
    missing = EDGE_TYPES - comprehensive_edge_types
    assert not missing, f"declared edge type(s) never emitted: {sorted(missing)}"
