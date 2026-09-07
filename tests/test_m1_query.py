"""M1 acceptance tests — queryable graph on bquant.

DoD (BACKLOG M1): answers the §1 catalog; import + re-export resolution correct.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap import store
from codemap.extract import extract
from codemap.query import Query
from tests.frozen import frozen

# Real-bquant acceptance target: the bquant repo checked out as a sibling
# (../bquant/bquant is the package). Whole module skips when absent (FOSS CI).
BQUANT = Path(__file__).resolve().parents[2] / "bquant" / "bquant"
pytestmark = pytest.mark.skipif(not BQUANT.is_dir(), reason="bquant sibling repo not present")
PIPELINE = "bquant.analysis.zones.pipeline"
MODELS = "bquant.analysis.zones.models"


@pytest.fixture(scope="module")
def graph():
    if not BQUANT.is_dir():
        pytest.skip(f"bquant package not found at {BQUANT}")
    return extract(BQUANT)


@pytest.fixture(scope="module")
def q(graph):
    return Query(graph)


def test_export_edge_reexport(graph):
    # bquant.analysis.zones re-exports analyze_zones from pipeline (§2.1).
    exports = [
        e for e in graph.edges
        if e.type == "export"
        and e.source == "bquant.analysis.zones"
        and e.extras.get("as") == "analyze_zones"
    ]
    assert exports, "expected an export edge for analyze_zones on the zones package"
    assert exports[0].target == f"{PIPELINE}.analyze_zones"


def test_import_edges_resolved(graph):
    # Deep relative import resolved to an absolute module→module edge (§3.1).
    imports = {(e.source, e.target) for e in graph.edges if e.type == "imports"}
    assert (PIPELINE, MODELS) in imports


def test_where_defined_resolves_reexport(q):
    defined = q.where_defined("analyze_zones")
    assert f"{PIPELINE}.analyze_zones" in defined


def test_dependencies_both_ways(q):
    assert MODELS in q.dependencies(PIPELINE)
    assert PIPELINE in q.dependents(MODELS)


def test_cycle_detection(q):
    # bquant's pipeline<->cache pair is mutually dependent, and the cache side reaches
    # pipeline only through an import under `if TYPE_CHECKING:` — which never runs. Until
    # R1-C48 (issue #18) that edge was counted as eager and this test pinned the defect:
    # the pair is a *dependency* cycle, and not an import-time one.
    pair = frozenset({PIPELINE, "bquant.analysis.zones.cache"})
    assert pair not in {frozenset(c) for c in q.import_cycles()}, \
        "an import under TYPE_CHECKING must not close an eager cycle"
    assert pair not in {frozenset(c) for c in q.lazy_import_cycles()}, \
        "nor a runtime one: R1-C49, the pair has no runtime dependency at all"
    assert pair in {frozenset(c) for c in q.type_only_import_cycles()}
    assert q.import_map()["type_checking"] >= 1


def test_orphan_modules(q):
    orphans = q.orphan_modules()
    assert isinstance(orphans, list)
    assert "bquant.cli" in orphans  # entry point, imported by nothing internally


def test_determinism_with_edges():
    """On a **frozen** snapshot: a moving target makes this test measure the target
    (R1-C25 — see tests/frozen.py)."""
    src = frozen(BQUANT)
    assert store.dumps(extract(src)) == store.dumps(extract(src))
