"""M9 acceptance — registry-family Protocol links (F4).

Concrete impls satisfy their Protocol *structurally* (never inherit it), so the
family is invisible to inheritance-based queries/diagrams. M9 synthesises
``implements`` edges from the registry family. Fixture ``dispatchpkg`` has a
``ThingProtocol`` that ``Alpha``/``Beta`` satisfy without inheriting.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.extract import extract
from codemap.query import Query
from codemap.serve.mermaid import render_class_diagram

FIX = Path(__file__).resolve().parent / "fixtures" / "dispatchpkg"
PROTO = "dispatchpkg.base.ThingProtocol"
ALPHA = "dispatchpkg.impls.Alpha"
BETA = "dispatchpkg.impls.Beta"


@pytest.fixture(scope="module")
def q():
    return Query(extract(FIX))


def test_implements_edges_synthesised(q):
    # impls link to the Protocol though they never inherit it.
    assert q.bases(ALPHA) == []            # structural typing — no inheritance
    assert PROTO in q.implements(ALPHA)
    assert PROTO in q.implements(BETA)


def test_protocol_lists_implementers(q):
    impls = q.implementers(PROTO)
    assert ALPHA in impls and BETA in impls


def test_family_siblings(q):
    assert q.family_siblings(ALPHA) == [BETA]


def test_class_diagram_non_empty_for_family(q):
    out = render_class_diagram(q, scope="dispatchpkg.impls")
    assert "<|.." in out                   # realization edge rendered
    assert "ThingProtocol" in out


def test_rag_chunk_carries_family(q):
    from codemap.serve.rag import build_chunks
    chunks = {c["id"]: c for c in build_chunks(q)}
    assert PROTO in chunks[ALPHA]["neighbors"].get("implements", [])
    assert "Implements" in chunks[ALPHA]["text"]


def test_deterministic():
    from codemap import store
    assert store.dumps(extract(FIX)) == store.dumps(extract(FIX))
