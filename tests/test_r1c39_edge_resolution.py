"""R1-C39 — why an edge exists, and what that route is worth.

From the OntoIndex разбор (`research/tools/ontoindex.md`, «What we'd take», п. 1): every
edge of theirs carries **how** it resolved and **how much to trust it**.

The first thing the measurement produced was a correction to the backlog entry itself.
It claimed codemap's `resolution` says only *whether* a call resolved; it does not — on
`calls` it already names the route, in six distinguishable values. What was actually
missing (design `docs/design/edge_resolution.md`):

1. D1 — the vocabulary was open in practice: six modules emit values and nothing
   enumerated them, so a new or mistyped one shipped in silence. Closed now in
   `model.RESOLUTIONS`, guarded in the R1-C7 shape — **both** directions.
2. D2 — a grade, never a probability: `exact` (a binding read from the source found the
   target) / `inferred` (a type-inference engine did) / `heuristic` (a name match).
3. D3 — derived, not stored: the schema does not move, and no edge grows a field.
4. D4 — the overload is named rather than smoothed: on `references` three values of four
   describe the *site*, not the route.
5. D5 — it is expressible: `callers(min_confidence="exact")`, and `stats` says what the
   whole graph is made of.
"""

from __future__ import annotations

import tempfile
from collections import Counter
from pathlib import Path

import pytest

from codemap.extract import extract, extract_repo
from codemap.model import (CONFIDENCE_ORDER, EDGE_TYPES, RESOLUTIONS,
                           UNKNOWN_CONFIDENCE, UNRESOLVED_EDGE_TYPES, Edge,
                           confidence_of, resolution_of)
from codemap.query import Query
from codemap.serve.audit import render_behavior
from codemap.serve.session import Session

FIX = Path(__file__).resolve().parent / "fixtures"


def _consumer_reference_probe(tmp: Path):
    """A consumer root that *names* a core symbol without calling it.

    The one row of the table that no fixture produced — and finding that out is the
    reason this probe exists rather than a claim that the row is unreachable.
    """
    core = tmp / "core"
    core.mkdir()
    (core / "__init__.py").write_text("from core.engine import Engine\n__all__ = ['Engine']\n")
    (core / "engine.py").write_text("class Engine:\n    def run(self):\n        return 1\n\n\n"
                                    "def helper():\n    return 0\n")
    use = tmp / "usage"
    use.mkdir()
    (use / "script.py").write_text("from core.engine import helper\n\n"
                                   "HANDLERS = {'h': helper}\n")
    return extract_repo(core, consumers=(use,), mode="full")


@pytest.fixture(scope="module")
def builds():
    """Every build the table is measured against — fixtures only, so CI needs no target."""
    tmp = Path(tempfile.mkdtemp(prefix="r1c39-"))
    out = {name: extract(FIX / name) for name in
           ("attrpkg", "dispatchpkg", "flatpkg", "flowpkg", "refpkg", "hardpkg", "tmworld")}
    out["attrpkg-deep"] = extract(FIX / "attrpkg", deep=True)
    out["deeppkg-deep"] = extract(FIX / "deeppkg", deep=True)
    out["reporoot"] = extract_repo(FIX / "reporoot" / "core",
                                   consumers=(FIX / "reporoot" / "usage",),
                                   docs=(FIX / "reporoot" / "docs",), mode="full")
    out["consumer-ref"] = _consumer_reference_probe(tmp)
    return out


def _pairs(graph):
    return {(e.type, e.extras["resolution"]) for e in graph.edges
            if e.extras.get("resolution") is not None}


# -- D1: the vocabulary is closed, in both directions ------------------------------------

def test_no_build_emits_a_pair_the_table_does_not_know(builds):
    for label, graph in builds.items():
        unknown = _pairs(graph) - set(RESOLUTIONS)
        assert not unknown, f"{label} emitted {unknown}"


def test_every_row_of_the_table_is_observed_somewhere(builds):
    """The other direction, and the one that catches a table describing a tool that no
    longer exists — the same shape as the R1-C7 edge-type guard."""
    seen = set().union(*(_pairs(g) for g in builds.values()))
    missing = set(RESOLUTIONS) - seen
    assert not missing, f"declared but never produced: {sorted(missing)}"


def test_every_edge_type_either_has_routes_or_is_declared_routeless(builds):
    typed = {t for t, _ in RESOLUTIONS}
    assert typed | UNRESOLVED_EDGE_TYPES == EDGE_TYPES, "an edge type falls in neither set"
    assert not (typed & UNRESOLVED_EDGE_TYPES), "and none may be in both"
    for label, graph in builds.items():
        for e in graph.edges:
            if e.type in UNRESOLVED_EDGE_TYPES:
                assert "resolution" not in e.extras, (label, e.type, e.extras)


def test_an_unknown_value_raises_where_it_must_and_degrades_where_it_should():
    """R1-C37: the guard has been shown what it must reject. Strict is what the guard and
    the extractor use; a *foreign* artifact is read leniently and its ungradable part is
    reported as `unknown` — refusing to open another version's graph is a worse answer."""
    bogus = Edge("calls", "a", "b", extras={"resolution": "global"})
    with pytest.raises(KeyError, match="unknown resolution"):
        resolution_of(bogus)
    assert confidence_of(bogus, strict=False) == UNKNOWN_CONFIDENCE
    assert resolution_of(Edge("contains", "a", "b")) is None, "no route is not an unknown one"


# -- D2: a grade, not a probability -------------------------------------------------------

def test_every_row_carries_a_grade_from_the_closed_set_and_a_meaning():
    for key, row in RESOLUTIONS.items():
        assert row["confidence"] in CONFIDENCE_ORDER, key
        assert row["means"] in ("route", "site"), key
        assert len(row["how"]) > 20, f"{key} has no explanation"


def test_no_grade_is_a_number():
    """Their `EXTENDS` carries 0.9246621004453465 — a computed probability read as a
    precision that is not there. Ours is an ordinal, and stays one."""
    for row in RESOLUTIONS.values():
        assert isinstance(row["confidence"], str)
        with pytest.raises(ValueError):
            float(row["confidence"])


def test_the_over_approximation_is_the_only_heuristic(builds):
    """A factory fanned out across a registry family is the one route that did not find
    a target — everything else was a binding or an inference."""
    heuristic = {k for k, v in RESOLUTIONS.items() if v["confidence"] == "heuristic"}
    assert heuristic == {("calls", "registry-candidate")}
    inferred = {k for k, v in RESOLUTIONS.items() if v["confidence"] == "inferred"}
    assert inferred == {("calls", "deep"), ("accesses", "deep")}


# -- D3: nothing is stored, the schema does not move --------------------------------------

def test_no_edge_grows_a_confidence_field(builds):
    for label, graph in builds.items():
        for e in graph.edges:
            assert "confidence" not in e.extras, (label, e.source, e.target)


# -- D4: the overload is named ------------------------------------------------------------

def test_references_carries_both_meanings_and_says_which(builds):
    means = {v: RESOLUTIONS[("references", v)]["means"]
             for v in ("annotation", "name", "doc", "imported")}
    assert means == {"annotation": "site", "name": "site", "doc": "site",
                     "imported": "route"}, "one field, two questions — stated, not smoothed"
    assert ("references", "imported") in _pairs(builds["consumer-ref"])
    assert ("references", "doc") in _pairs(builds["reporoot"])


# -- D5: it is expressible ----------------------------------------------------------------

def test_min_confidence_drops_exactly_the_heuristic_edges(builds):
    q = Query(builds["dispatchpkg"])
    fanned = {(e.source, e.target) for e in builds["dispatchpkg"].edges
              if e.extras.get("resolution") == "registry-candidate"}
    assert fanned, "the fixture must contain the thing being filtered"
    dropped = set()
    for target in {t for _, t in fanned}:
        every = set(q.callers(target))
        exact = set(q.callers(target, min_confidence="exact"))
        assert exact <= every
        dropped |= {(src, target) for src in every - exact}
    assert dropped == {p for p in fanned if p[0] in set(q.graph.nodes)}


def test_a_pair_reached_both_ways_keeps_the_stronger_grade(builds):
    """Two edges may collapse onto one caller→callee pair — resolved exactly at one site,
    fanned out from a registry at another. The pair *is* connected by a binding, so the
    filter must keep it."""
    from codemap.model import Edge as E
    g = builds["dispatchpkg"]
    src, tgt = next(iter({(e.source, e.target) for e in g.edges
                          if e.extras.get("resolution") == "registry-candidate"}))
    q = Query(g)
    assert src not in q.callers(tgt, min_confidence="exact")
    g2 = extract(FIX / "dispatchpkg")
    g2.add_edge(E("calls", src, tgt, extras={"resolution": "imported"}))
    assert src in Query(g2).callers(tgt, min_confidence="exact")


def test_an_unknown_grade_is_refused_rather_than_ignored(builds):
    q = Query(builds["dispatchpkg"])
    with pytest.raises(ValueError, match="min_confidence"):
        q.callers("whatever", min_confidence="0.9")


def test_stats_says_what_the_graph_is_made_of(builds):
    env = Session(builds["dispatchpkg"]).handle({"op": "stats", "args": {}})
    conf = env["result"]["confidence"]
    counted = Counter(f"{e.type}:{e.extras['resolution']}"
                      for e in builds["dispatchpkg"].edges
                      if e.extras.get("resolution") is not None)
    assert conf["by_pair"] == dict(sorted(counted.items())), "the map is the graph, recounted"
    assert sum(conf["by_grade"].values()) == len(builds["dispatchpkg"].edges)
    assert conf["by_grade"]["heuristic"] == counted["calls:registry-candidate"]
    assert conf["by_grade"]["none"] > 0, "edges with no route are counted, not dropped"


def test_the_behavior_report_grades_the_call_edges(builds):
    md = render_behavior(Query(builds["dispatchpkg"]))
    assert "by route grade:" in md and "**exact**" in md and "**heuristic**" in md
    assert "a name match, not a binding" in md
