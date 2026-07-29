"""M3.1 acceptance — warm serve session + stdio loop (DESIGN §14.4).

The resident process holds the graph in memory and answers JSON requests by
dispatching to the existing services — zero per-call startup, no new logic.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from codemap.extract import extract
from codemap.serve.server import serve_stdio
from codemap.serve.session import Session

FIX = Path(__file__).resolve().parent / "fixtures" / "flowpkg"
DISPATCH = Path(__file__).resolve().parent / "fixtures" / "dispatchpkg"


@pytest.fixture(scope="module")
def session():
    return Session(extract(FIX))


def test_ping(session):
    assert session.handle({"op": "ping"})["result"] == "pong"


def test_stats(session):
    r = session.handle({"op": "stats"})
    assert r["ok"]
    assert r["result"]["nodes"] > 0
    assert "column" in r["result"]["node_kinds"]


def test_column_op(session):
    r = session.handle({"op": "column", "args": {"name": "signal"}})
    assert r["ok"]
    assert r["result"]["writes"] == ["flowpkg.produce.compute"]


def test_query_op(session):
    r = session.handle({"op": "query", "args": {"name": "compute"}})
    assert r["ok"]
    assert any(m["id"] == "flowpkg.produce.compute" for m in r["result"]["matches"])


def test_unknown_op_is_error_not_crash(session):
    r = session.handle({"op": "nope"})
    assert r["ok"] is False
    assert "unknown op" in r["error"]
    assert "query" in r["ops"]


def test_bad_args_do_not_crash(session):
    # missing required arg -> error response, process stays alive.
    r = session.handle({"op": "column", "args": {}})
    assert r["ok"] is False


def test_family_op_on_dispatch_fixture():
    s = Session(extract(DISPATCH))
    r = s.handle({"op": "implementers", "args": {"protocol": "dispatchpkg.base.ThingProtocol"}})
    assert r["ok"]
    assert "dispatchpkg.impls.Alpha" in r["result"]


def test_stdio_loop_roundtrip(session):
    inp = io.StringIO(
        '{"op":"ping"}\n'
        "\n"                       # blank line skipped
        '{"op":"column","args":{"name":"signal"}}\n'
        "not json\n"               # malformed -> error, loop survives
    )
    out = io.StringIO()
    rc = serve_stdio(session, stdin=inp, stdout=out)
    assert rc == 0
    lines = [json.loads(x) for x in out.getvalue().splitlines()]
    assert lines[0]["result"] == "pong"
    assert lines[1]["result"]["writes"] == ["flowpkg.produce.compute"]
    assert lines[2]["ok"] is False and "invalid JSON" in lines[2]["error"]


# -- serve ergonomics fixes from agent-workflow dogfood (F9-F13) ---------------

def test_search_finds_by_substring(session):
    # F9: cold discovery — the agent doesn't know exact names.
    r = session.handle({"op": "search", "args": {"term": "compute"}})
    assert r["ok"]
    assert any(x["id"] == "flowpkg.produce.compute" for x in r["result"])


def test_search_kind_filter(session):
    r = session.handle({"op": "search", "args": {"term": "flowpkg", "kind": "module"}})
    assert all(x["kind"] == "module" for x in r["result"])


def test_query_match_carries_file_and_lines(session):
    # F12: an agent must be able to jump to source.
    r = session.handle({"op": "query", "args": {"name": "compute"}})
    m = [x for x in r["result"]["matches"] if x["id"] == "flowpkg.produce.compute"][0]
    assert m["file"] and m["lines"][0]


def test_source_op_returns_code(session):
    # F12: the source op reads the span (source_root wired below in dispatch test).
    from pathlib import Path
    s = Session(extract(FIX), source_root=str(FIX.parent))
    r = s.handle({"op": "source", "args": {"symbol": "flowpkg.produce.compute"}})
    assert r["ok"]
    assert "def compute" in (r["result"]["code"] or "")


def test_columns_of_reverse_dataflow(session):
    # F11: which columns does this function touch.
    r = session.handle({"op": "columns_of",
                        "args": {"symbol": "flowpkg.produce.compute"}})
    assert r["ok"]
    assert "flag" in r["result"]["writes"]
    r2 = session.handle({"op": "columns_of", "args": {"symbol": "flowpkg.consume.plot"}})
    assert "signal" in r2["result"]["reads"]


def test_canonical_resolves_short_name():
    # F13: relational ops accept a short name / re-export id, not only the full id.
    s = Session(extract(DISPATCH))
    assert s.query.canonical("ThingProtocol") == "dispatchpkg.base.ThingProtocol"
    r = s.handle({"op": "implementers", "args": {"protocol": "ThingProtocol"}})
    assert "dispatchpkg.impls.Alpha" in r["result"]


def test_families_lists_registration_recipe():
    # F10: how to plug in — decorator + key per member.
    s = Session(extract(DISPATCH))
    fams = s.handle({"op": "families"})["result"]
    fam = [f for f in fams if f["protocol"] == "dispatchpkg.base.ThingProtocol"][0]
    alpha = [m for m in fam["members"] if m["class"].endswith("Alpha")][0]
    assert alpha["key"] == "alpha"
    assert "register_thing" in (alpha["decorator"] or "")
