"""M4 acceptance tests — behavioral layer (call-graph + type-flow) on bquant.

Bounded by design (gaps/ CM-09/10/11): resolves module/self/imported calls,
flags the rest; type-flow is name-based over signatures. See
codemap/gaps/coverage_gap_analysis_2026-07-24.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap import store
from codemap.extract import extract
from codemap.query import Query
from codemap.serve import render_behavior

BQUANT = Path(__file__).resolve().parents[2] / "bquant"
PIPELINE = "bquant.analysis.zones.pipeline"
ANALYZE = f"{PIPELINE}.analyze_zones"
RUN = f"{PIPELINE}.ZoneAnalysisPipeline.run"


@pytest.fixture(scope="module")
def graph():
    if not BQUANT.is_dir():
        pytest.skip(f"bquant package not found at {BQUANT}")
    return extract(BQUANT)


@pytest.fixture(scope="module")
def q(graph):
    return Query(graph)


# -- CM-09: best-effort call-graph -------------------------------------------

def test_calls_edges_present(graph):
    calls = [e for e in graph.edges if e.type == "calls"]
    assert len(calls) > 500
    # every calls edge carries a resolution label
    assert all(e.extras.get("resolution") in {"module", "self", "imported"} for e in calls)


def test_callers_of_flagship(q):
    # presets.analyze_macd_zones calls analyze_zones (module-level import).
    callers = q.callers(ANALYZE)
    assert "bquant.analysis.zones.presets.analyze_macd_zones" in callers


def test_self_call_resolution(q):
    # run() dispatches to its own private helpers via self.* .
    callees = q.callees(RUN)
    assert any(c.endswith("._run_without_cache") for c in callees)


def test_call_coverage_recorded(graph):
    node = graph.nodes[RUN]
    cov = node.extras.get("calls")
    assert cov is not None and cov["out"] >= cov["resolved"] >= 0


# -- CM-11: control skeleton -------------------------------------------------

def test_control_skeleton(graph):
    ctrl = graph.nodes[RUN].extras.get("control")
    assert ctrl is not None
    assert "branches" in ctrl and "loops" in ctrl


# -- CM-10 (type-level) / CM-03: type flow -----------------------------------

def test_return_type_recorded(graph):
    assert graph.nodes[RUN].extras.get("returns") == "ZoneAnalysisResult"


def test_producers_and_consumers(q):
    producers = q.producers("ZoneAnalysisResult")
    assert f"{PIPELINE}.ZoneAnalysisPipeline.run" in producers or producers
    assert any("analyze_zones" in p for p in producers)
    # DataFrame is the pipeline's lifeblood — many consumers.
    assert len(q.consumers("DataFrame")) > 50


# -- CM-12: symbol-level dead code (private, uncalled) -----------------------

def test_dead_symbols_are_private(q):
    dead = q.dead_symbols()
    assert isinstance(dead, list)
    for sid in dead:
        node = q.graph.nodes[sid]
        assert node.visibility == "private"
        assert node.kind == "function"


# -- report + determinism ----------------------------------------------------

def test_behavior_report(q):
    report = render_behavior(q)
    assert report.startswith("# Behavioral layer — `bquant`")
    assert "Call-site resolution" in report


def test_determinism_with_behavior():
    assert store.dumps(extract(BQUANT)) == store.dumps(extract(BQUANT))
