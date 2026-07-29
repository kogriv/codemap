"""M11 acceptance — call-site argument contract (F7).

`calls` edges are function-granular and previously carried only `resolution`, so
a signature-change refactor could not tell which call-sites break. This captures
the observed argument shape (positional count / kwarg names / splat) and the
collapsed call-site count on each edge.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.extract import extract, extract_repo
from codemap.query import Query
from codemap.serve import render_impact

FIX = Path(__file__).resolve().parent / "fixtures" / "argpkg"
TARGET = "argpkg.api.configure"


@pytest.fixture(scope="module")
def q():
    return Query(extract(FIX))


def test_edges_carry_callsites_and_shape(q):
    contract = {c["caller"].rsplit(".", 1)[-1]: c for c in q.call_contract(TARGET)}
    assert contract["one_positional"]["posargs"] == [1]
    assert contract["one_positional"]["callsites"] == 1


def test_collapsed_sites_stay_visible(q):
    # two_sites_here calls configure twice — the edge must report ×2, not ×1.
    c = {c["caller"].rsplit(".", 1)[-1]: c for c in q.call_contract(TARGET)}["two_sites_here"]
    assert c["callsites"] == 2
    assert "mode" in c["kwargs"]           # kwarg union across the two sites


def test_splat_flagged(q):
    c = {c["caller"].rsplit(".", 1)[-1]: c for c in q.call_contract(TARGET)}["splatted"]
    assert c["splat"] is True              # *args -> arity unknown, honestly flagged


def test_impact_shows_contract_section(q):
    out = render_impact(q, "configure")
    assert "Call-site contract" in out
    assert "positional" in out


def test_deterministic():
    from codemap import store
    assert store.dumps(extract(FIX)) == store.dumps(extract(FIX))
