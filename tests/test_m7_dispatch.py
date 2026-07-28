"""M7 acceptance tests — registry-aware call bridging (dispatch seams, F5).

Synthetic ``dispatchpkg`` mirrors bquant's plugin wiring: a keyed registry, two
impls with no shared base, a factory, and a consumer that binds the strategy on
``self`` and calls it in another method. Plus a real-bquant sanity check that the
``analyze_zones`` chain now reaches the swing/detection strategies.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.extract import extract
from codemap.query import Query

FIX = Path(__file__).resolve().parent / "fixtures" / "dispatchpkg"
BQUANT = Path(__file__).resolve().parents[2] / "bquant"


@pytest.fixture(scope="module")
def g():
    return extract(FIX)


def _calls(graph, src):
    return {
        (e["target"] if isinstance(e, dict) else e.target): (
            e["extras"].get("resolution") if isinstance(e, dict) else e.extras.get("resolution")
        )
        for e in graph.edges
        if (e.type == "calls" and e.source == src)
    }


# -- self.attr.method() bridged to all family impls ---------------------------

def test_self_attr_dispatch_bridged(g):
    edges = _calls(g, "dispatchpkg.user.Worker.work")
    assert edges.get("dispatchpkg.impls.Alpha.run") == "registry-candidate"
    assert edges.get("dispatchpkg.impls.Beta.run") == "registry-candidate"


# -- literal key resolves to the single exact impl ----------------------------

def test_literal_key_exact(g):
    edges = _calls(g, "dispatchpkg.user.direct_literal")
    assert edges.get("dispatchpkg.impls.Alpha") == "registry"
    assert "dispatchpkg.impls.Beta" not in edges  # literal 'alpha' — Beta excluded


# -- the registry table was actually read (M1.5 dependency) -------------------

def test_family_members_present(g):
    reg = {n.id: n.extras.get("registry") for n in g.nodes.values() if n.extras.get("registry")}
    keys = {r["key"] for r in reg.values() if r}
    assert {"alpha", "beta"} <= keys


# -- query picks the bridges up (callers/impact benefit) ----------------------

def test_callers_include_bridge(g):
    q = Query(g)
    callers = q.callers("dispatchpkg.impls.Alpha.run")
    assert "dispatchpkg.user.Worker.work" in callers


def test_deterministic():
    a = extract(FIX).to_dict()
    b = extract(FIX).to_dict()
    assert a == b


# -- real bquant: the flagship chain reconnects at the seams ------------------

def test_bquant_chain_reaches_strategies():
    if not BQUANT.is_dir():
        pytest.skip("bquant not found")
    q = Query(extract(BQUANT))  # fast tier is enough — bridging is tier-independent
    # detection seam: the pipeline detector dispatch reaches concrete detectors.
    detect = q.callees("bquant.analysis.zones.pipeline.ZoneAnalysisPipeline._detect_zones")
    assert any("detection.zero_crossing" in c for c in detect)
    # feature seam: extract_zone_features reaches a concrete swing strategy method.
    feats = q.callees("bquant.analysis.zones.zone_features.ZoneFeaturesAnalyzer.extract_zone_features")
    assert any("swing" in c and c.endswith(".calculate") for c in feats)
