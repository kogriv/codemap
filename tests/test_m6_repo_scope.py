"""M6 acceptance tests — repo scope / impact (multi-root).

Synthetic ``reporoot`` fixture: a core package + a loose consumer script + a doc,
all naming the core (incl. a re-export) so we can assert the blast radius reaches
beyond the package. Plus real-bquant sanity on the MACDZoneAnalyzer case (F1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.extract import extract, extract_repo
from codemap.query import Query
from codemap.serve import render_impact

FIX = Path(__file__).resolve().parent / "fixtures" / "reporoot"
CORE = FIX / "core"
USAGE = FIX / "usage"
DOCS = FIX / "docs"
REPO = Path(__file__).resolve().parents[2]  # /data/pro/bquant
BQUANT = REPO / "bquant"


@pytest.fixture(scope="module")
def thin():
    return extract_repo(CORE, consumers=(USAGE,), docs=(DOCS,), mode="thin")


@pytest.fixture(scope="module")
def full():
    return extract_repo(CORE, consumers=(USAGE,), docs=(DOCS,), mode="full")


# -- M6.1 roots + provenance --------------------------------------------------

def test_provenance_tags(thin):
    roots = {n.id: n.extras.get("root") for n in thin.nodes.values()}
    assert roots["core.engine.Engine"] == "core"
    assert roots["usage.use_engine"] == "usage"
    assert roots["docs/guide.md"] == "docs"


def test_single_package_still_core(thin):
    # a plain single-package extract has no consumers; everything reads as core.
    q = Query(extract(CORE))
    assert q.root_of("core.engine.Engine") == "core"


# -- M6.2 consumer references reach core (thin) + re-export resolution ---------

def test_consumer_call_edge_to_core(thin):
    # `from core import Engine` (re-export) + `Engine()` -> edge to the CANONICAL
    # def, not the re-export path core.Engine.
    edges = [
        e for e in thin.edges
        if e.source == "usage.use_engine" and e.target == "core.engine.Engine"
    ]
    assert edges, "consumer -> core edge missing"
    assert any(e.type == "calls" for e in edges)
    assert "core.Engine" not in {n.id for n in thin.nodes.values()}  # not materialised


def test_consumer_import_edge(thin):
    assert any(
        e.type == "imports" and e.source == "usage.use_engine"
        and e.target in ("core", "core.engine")
        for e in thin.edges
    )


# -- M6.3 thin vs full granularity --------------------------------------------

def test_full_sources_use_from_function(thin, full):
    assert "usage.use_engine.scenario" in full.nodes
    assert "usage.use_engine.scenario" not in thin.nodes
    # in full the Engine() call is attributed to the enclosing function.
    assert any(
        e.type == "calls" and e.source == "usage.use_engine.scenario"
        and e.target == "core.engine.Engine"
        for e in full.edges
    )


# -- M6.4 doc references ------------------------------------------------------

def test_doc_references(thin):
    refs = {
        e.target for e in thin.edges
        if e.type == "references" and e.source == "docs/guide.md"
    }
    assert "core.engine.Engine" in refs      # from-import + dotted mention
    assert "core.engine.helper" in refs      # dotted mention resolves to a node


# -- M6.5/6.6 query impact + inbound ------------------------------------------

def test_impact_spans_roots(thin):
    q = Query(thin)
    rep = q.impact("core.engine.Engine")
    assert "usage" in rep["by_root"]
    assert "docs" in rep["by_root"]


def test_references_to_reaches_consumers(thin):
    q = Query(thin)
    roots = {r["root"] for r in q.references_to("core.engine.Engine")}
    assert {"usage", "docs"} <= roots


def test_render_impact_markdown(thin):
    out = render_impact(Query(thin), "Engine")
    assert "# Impact" in out
    assert "usage" in out and "docs" in out
    assert "lower bound" in out  # honesty disclaimer present


# -- determinism --------------------------------------------------------------

def test_repo_scope_deterministic():
    a = extract_repo(CORE, consumers=(USAGE,), docs=(DOCS,), mode="thin").to_dict()
    b = extract_repo(CORE, consumers=(USAGE,), docs=(DOCS,), mode="thin").to_dict()
    assert a == b


# -- real bquant: F1 blast radius now visible ---------------------------------

def test_bquant_macd_blast_radius():
    if not BQUANT.is_dir():
        pytest.skip("bquant not found")
    g = extract_repo(BQUANT, consumers=(REPO / "tests",), mode="thin")
    q = Query(g)
    rep = q.impact("bquant.indicators.macd.MACDZoneAnalyzer")
    # the backward-compat test suite must now show up as inbound refs.
    assert "tests" in rep["by_root"]
    assert sum(rep["by_root"]["tests"].values()) >= 10


# -- F8: provenance-aware dead-code (deep dogfood 2026-07-29) ------------------

def test_orphan_modules_provenance_aware(full):
    q = Query(full)
    grouped = q.orphan_modules_by_root()
    # the loose consumer script is orphan by nature — under its own root, not core.
    assert "usage" in grouped
    assert "usage" not in q.orphan_modules(root="core")
    # core-scoped orphans never include a consumer module.
    assert all(q.root_of(m) == "core" for m in q.orphan_modules(root="core"))


def test_dead_code_report_separates_consumers(full):
    from codemap.serve.audit import render_dead_code
    out = render_dead_code(Query(full))
    assert "core (no incoming imports)" in out
    assert "orphan by nature, not dead code" in out
