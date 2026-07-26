"""M1.5 acceptance tests — semantic edges + extras on bquant.

Closes gap-doc CM-01/02/06/07/08: inherits + decorated_by edges, attribute
annotations, dataclass flag, dynamic-registration key. See
codemap/gaps/coverage_gap_analysis_2026-07-24.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap import store
from codemap.extract import extract
from codemap.query import Query

BQUANT = Path(__file__).resolve().parents[2] / "bquant"
BASE = "bquant.indicators.base.BaseIndicator"
RESULT = "bquant.analysis.zones.models.ZoneAnalysisResult"


@pytest.fixture(scope="module")
def graph():
    if not BQUANT.is_dir():
        pytest.skip(f"bquant package not found at {BQUANT}")
    return extract(BQUANT)


@pytest.fixture(scope="module")
def q(graph):
    return Query(graph)


# -- CM-08: inherits ---------------------------------------------------------

def test_inherits_internal_edge(graph):
    inh = {(e.source, e.target) for e in graph.edges if e.type == "inherits"}
    assert ("bquant.indicators.base.CustomIndicator", BASE) in inh


def test_inherits_external_flagged(graph):
    # BaseIndicator(ABC) — external base resolved to abc.ABC and flagged.
    ext = [
        e for e in graph.edges
        if e.type == "inherits" and e.source == BASE
    ]
    assert ext and ext[0].target == "abc.ABC"
    assert ext[0].extras.get("external") is True


def test_subclasses_query(q):
    subs = q.subclasses(BASE)
    assert {"bquant.indicators.base.CustomIndicator",
            "bquant.indicators.base.LibraryIndicator",
            "bquant.indicators.base.PreloadedIndicator"} <= set(subs)
    assert q.bases("bquant.indicators.base.CustomIndicator") == [BASE]


# -- CM-06: decorated_by -----------------------------------------------------

def test_decorated_by_deprecated(q):
    decorated = q.decorated_with("deprecated")
    assert "bquant.indicators.macd.MACDZoneAnalyzer" in decorated


def test_decorated_by_edge_present(graph):
    edges = {(e.source, e.target) for e in graph.edges if e.type == "decorated_by"}
    assert (RESULT, "dataclasses.dataclass") in edges


# -- CM-01 / CM-02: attribute annotation + dataclass flag --------------------

def test_attribute_annotation(graph):
    field = graph.nodes[f"{RESULT}.zones"]
    assert field.extras.get("annotation") == "List[ZoneInfo]"


def test_dataclass_flag(graph):
    assert graph.nodes[RESULT].extras.get("is_dataclass") is True


# -- CM-07: dynamic-registration key -----------------------------------------

def test_registry_binding(graph):
    node = graph.nodes["bquant.analysis.zones.detection.zero_crossing.ZeroCrossingDetection"]
    binding = node.extras.get("registry")
    assert binding is not None
    assert binding["key"] == "zero_crossing"
    assert binding["decorator"].endswith("ZoneDetectionRegistry.register")


# -- determinism holds with the richer graph ---------------------------------

def test_determinism_with_semantics():
    assert store.dumps(extract(BQUANT)) == store.dumps(extract(BQUANT))


def test_schema_bumped(graph):
    assert graph.to_dict()["codemap_schema"] == "0.2"
