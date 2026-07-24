"""M1 acceptance tests — queryable graph on bquant.

DoD (BACKLOG M1): answers the §1 catalog; import + re-export resolution correct.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap import store
from codemap.extract import extract
from codemap.query import Query

BQUANT = Path(__file__).resolve().parents[2] / "bquant"
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
    cycles = q.import_cycles()
    # bquant has a real pipeline<->cache circular dependency.
    flat = {frozenset(c) for c in cycles}
    assert frozenset({PIPELINE, "bquant.analysis.zones.cache"}) in flat


def test_orphan_modules(q):
    orphans = q.orphan_modules()
    assert isinstance(orphans, list)
    assert "bquant.cli" in orphans  # entry point, imported by nothing internally


def test_determinism_with_edges():
    assert store.dumps(extract(BQUANT)) == store.dumps(extract(BQUANT))
