"""R1-C16 acceptance — adapter layer + semantic search enriched to codemap symbols.

The router half (GitNexus passthrough) shipped earlier; this covers the **adapter**
half: a permissive-licensed retrieval tool whose fuzzy hits codemap resolves to
exact symbols via its own graph. Tests use a FakeAdapter (so no external tool is
needed and the *generalized* mechanism is exercised, not just cocoindex), plus a
monkeypatched-transport check of the real cocoindex argv/parse, plus a skipped live
test when `ccc` is installed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from codemap.extract import extract
from codemap.integrations import (
    IntegrationMode, all_integrations, register, resolve, unregister,
)
from codemap.integrations.base import Integration
from codemap.integrations.gate import IntegrationConfig
from codemap.query import Query
from codemap.serve.semantic import semantic_search

CORE = Path(__file__).resolve().parent / "fixtures" / "reporoot" / "core"
# Enrichment tests enable ONLY the FakeAdapter, so resolve() picks it deterministically
# (it wouldn't if the real cocoindex were also enabled — 'cocoindex' sorts first).
ENABLE = IntegrationConfig(enabled=frozenset({"fake-sem"}))


class FakeAdapter(Integration):
    """A permissive retrieval adapter returning canned hits — the generalized path."""

    name = "fake-sem"
    mode = IntegrationMode.ADAPTER
    license = "MIT"
    capabilities = ("semantic-search",)

    def __init__(self, hits):
        self._hits = hits

    def is_available(self) -> bool:
        return True

    def search(self, capability, query, **kw):
        return list(self._hits)


@pytest.fixture
def core_q() -> Query:
    return Query(extract(CORE))


@pytest.fixture
def fake(request):
    """Register a FakeAdapter with the given hits for one test; auto-unregister."""
    hits = getattr(request, "param", [])
    register(FakeAdapter(hits))
    yield
    unregister("fake-sem")


# -- registration + license policy -------------------------------------------

def test_cocoindex_registered_as_permissive_adapter():
    names = {i.name: i for i in all_integrations()}
    ccc = names["cocoindex"]
    assert ccc.mode is IntegrationMode.ADAPTER
    assert ccc.license.lower() == "apache-2.0"


def test_adapter_must_be_permissive():
    class BadAdapter(Integration):
        name = "bad-nc"
        mode = IntegrationMode.ADAPTER
        license = "PolyForm-Noncommercial-1.0.0"
        capabilities = ("semantic-search",)
        def is_available(self): return True
    with pytest.raises(ValueError, match="non-permissive"):
        register(BadAdapter())


# -- resolution: adapter-mode picks the adapter, never the router -------------

def test_resolve_adapter_mode_skips_router(monkeypatch):
    # gitnexus (router) also provides semantic-search; mode=ADAPTER must skip it.
    #
    # `resolve` also gates on `is_available()`, which for cocoindex means the `ccc` binary
    # being on PATH — irrelevant to the dispatch rule under test, and the reason this test
    # passed on a developer machine that happened to have `ccc` and failed the moment it
    # first ran anywhere else (M20). Stub availability, in keeping with this module's
    # stated design: no external tool is needed to exercise the mechanism.
    from codemap.integrations.cocoindex import CocoIndexAdapter
    monkeypatch.setattr(CocoIndexAdapter, "is_available", lambda self: True)

    cfg = IntegrationConfig(enabled=frozenset({"gitnexus", "cocoindex"}))
    got = resolve("semantic-search", config=cfg, mode=IntegrationMode.ADAPTER)
    assert got is not None and got.mode is IntegrationMode.ADAPTER
    assert got.name == "cocoindex"


# -- enrichment: fuzzy (file, line) → exact codemap symbol -------------------

def test_semantic_enriches_hits_to_symbols(core_q):
    run = core_q.graph.nodes["core.engine.Engine.run"]
    helper = core_q.graph.nodes["core.engine.helper"]
    hits = [
        {"file": "core/engine.py", "start_line": run.lineno, "end_line": run.endlineno,
         "score": 0.6},
        {"file": "core/engine.py", "start_line": helper.lineno, "end_line": helper.endlineno,
         "score": 0.9},
    ]
    register(FakeAdapter(hits))
    try:
        out = semantic_search(core_q, "anything", config=ENABLE)
    finally:
        unregister("fake-sem")
    assert out["resolver"] == "fake-sem"
    syms = [(h["symbol"], h["score"]) for h in out["hits"]]
    # sorted by score desc → helper (0.9) before run (0.6); both resolved to symbols
    assert syms == [("core.engine.helper", 0.9), ("core.engine.Engine.run", 0.6)]
    assert all(h["resolution"] == "symbol" for h in out["hits"])


def test_semantic_dedups_same_symbol_keeps_best(core_q):
    run = core_q.graph.nodes["core.engine.Engine.run"]
    hits = [
        {"file": "core/engine.py", "start_line": run.lineno, "end_line": run.endlineno, "score": 0.5},
        {"file": "core/engine.py", "start_line": run.lineno, "end_line": run.endlineno, "score": 0.8},
    ]
    register(FakeAdapter(hits))
    try:
        out = semantic_search(core_q, "x", config=ENABLE)
    finally:
        unregister("fake-sem")
    resolved = [h for h in out["hits"] if h["symbol"] == "core.engine.Engine.run"]
    assert len(resolved) == 1 and resolved[0]["score"] == 0.8  # deduped, best kept


def test_semantic_unresolved_hit_kept_honestly(core_q):
    hits = [{"file": "core/nope.py", "start_line": 3, "end_line": 4, "score": 0.7}]
    register(FakeAdapter(hits))
    try:
        out = semantic_search(core_q, "x", config=ENABLE)
    finally:
        unregister("fake-sem")
    assert out["hits"][0]["symbol"] is None
    assert out["hits"][0]["resolution"] == "unresolved"


def test_semantic_no_adapter_degrades(core_q):
    # nothing enabled → clean empty result, never an error
    out = semantic_search(core_q, "x", config=IntegrationConfig())
    assert out == {"resolver": None, "disclaimer": None, "hits": []}


# -- real cocoindex adapter: argv + parse (transport monkeypatched) ----------

def test_cocoindex_argv_and_parse(monkeypatch):
    from codemap.integrations import cocoindex
    captured = {}

    def fake_run_json(cmd, *, timeout=120.0, input_text=None, cwd=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return {"type": "search", "success": True, "results": [
            {"file_path": "bquant/a.py", "start_line": 10, "end_line": 20, "score": 0.71},
            {"file_path": None, "start_line": 5, "score": 0.4},  # unanchorable → dropped
        ]}

    monkeypatch.setattr(cocoindex, "run_json", fake_run_json)
    monkeypatch.setattr(cocoindex, "which", lambda b: "/usr/bin/ccc")
    adapter = cocoindex.CocoIndexAdapter()
    hits = adapter.search("semantic-search", "swing pivots", root="/repo", limit=7)
    assert captured["cmd"] == ["ccc", "search", "swing pivots", "--limit", "7", "--json"]
    assert captured["cwd"] == "/repo"
    assert hits == [{"file": "bquant/a.py", "start_line": 10, "end_line": 20, "score": 0.71}]


def test_cocoindex_bad_payload_yields_no_hits(monkeypatch):
    from codemap.integrations import cocoindex
    monkeypatch.setattr(cocoindex, "which", lambda b: "/usr/bin/ccc")
    monkeypatch.setattr(cocoindex, "run_json", lambda *a, **k: None)  # tool couldn't answer
    assert cocoindex.CocoIndexAdapter().search("semantic-search", "q", root=".") == []


# -- serve op + MCP surface --------------------------------------------------

def test_serve_semantic_op(core_q, monkeypatch):
    from codemap.serve.session import Session
    import codemap.serve.semantic as sem
    run = core_q.graph.nodes["core.engine.Engine.run"]
    monkeypatch.setattr(sem, "semantic_search", lambda q, text, **kw: {
        "resolver": "fake", "disclaimer": None,
        "hits": [{"symbol": "core.engine.Engine.run", "score": 0.9,
                  "file": "core/engine.py", "lines": [run.lineno, run.endlineno],
                  "resolution": "symbol"}]})
    sess = Session(core_q.graph)
    env = sess.handle({"op": "semantic", "args": {"query": "run engine"}})
    assert env["ok"] and env["result"]["hits"][0]["symbol"] == "core.engine.Engine.run"


def test_mcp_lists_semantic_search():
    from codemap.serve.mcp_server import MCP_TOOLS
    assert "semantic_search" in MCP_TOOLS


# -- optional live check (only when ccc is installed) -------------------------

def test_live_cocoindex_available():
    if shutil.which("ccc") is None:
        pytest.skip("ccc not on PATH")
    from codemap.integrations.cocoindex import CocoIndexAdapter
    assert CocoIndexAdapter().is_available() is True
