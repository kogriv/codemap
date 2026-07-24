"""M0 acceptance tests — API-surface slice end-to-end on the bquant package.

DoD (BACKLOG M0): correct + deterministic API-surface report on bquant.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap import store
from codemap.extract import extract
from codemap.serve import render_api_surface

# codemap/ lives at the repo root next to bquant/; tests/ is one level down.
BQUANT = Path(__file__).resolve().parents[2] / "bquant"


@pytest.fixture(scope="module")
def graph():
    if not BQUANT.is_dir():
        pytest.skip(f"bquant package not found at {BQUANT}")
    return extract(BQUANT)


def test_graph_is_populated(graph):
    assert graph.target == "bquant"
    kinds = {k: 0 for k in ("module", "class", "function", "attribute")}
    for n in graph.nodes.values():
        kinds[n.kind] = kinds.get(n.kind, 0) + 1
    assert kinds["module"] > 50
    assert kinds["class"] > 50
    assert kinds["function"] > 100
    # contains-edges form a tree over the nodes (root has no parent).
    contains = [e for e in graph.edges if e.type == "contains"]
    assert len(contains) == len(graph.nodes) - 1


def test_flagship_symbol_signature(graph):
    node = graph.nodes["bquant.analysis.zones.pipeline.analyze_zones"]
    assert node.kind == "function"
    assert node.visibility == "public"
    assert node.signature == "analyze_zones(df: pd.DataFrame) -> ZoneAnalysisBuilder"
    assert not node.is_deprecated


def test_deprecated_detection(graph):
    node = graph.nodes["bquant.indicators.macd.MACDZoneAnalyzer"]
    assert node.kind == "class"
    assert node.is_deprecated is True


def test_determinism(graph):
    assert store.dumps(extract(BQUANT)) == store.dumps(extract(BQUANT))


def test_roundtrip(graph, tmp_path):
    p = tmp_path / "graph.json"
    store.save(graph, p)
    reloaded = store.load(p)
    assert store.dumps(reloaded) == store.dumps(graph)


def test_api_surface_report(graph):
    report = render_api_surface(graph)
    assert report.startswith("# API surface — `bquant`")
    assert "analyze_zones(df: pd.DataFrame) -> ZoneAnalysisBuilder" in report
    # deprecated marker rendered for MACDZoneAnalyzer
    assert "**⚠ deprecated**" in report
    lines = [l for l in report.splitlines() if "MACDZoneAnalyzer" in l]
    assert lines and "deprecated" in lines[0]
