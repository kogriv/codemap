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
