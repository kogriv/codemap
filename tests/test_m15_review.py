"""M15 acceptance — diff / change-review (A11 dogfood F16 + F17).

A reviewer's input is a diff (file + changed line ranges), not a symbol name. F16
adds location→symbol resolution over existing lineno/endlineno; F17 aggregates a
change-set into one risk-sorted review dossier. Fixtures: flowpkg (known spans).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.extract import extract
from codemap.query import Query
from codemap.serve.review import build_review, parse_unified_diff, render_review
from codemap.serve.session import Session

FIX = Path(__file__).resolve().parent / "fixtures" / "flowpkg"


@pytest.fixture(scope="module")
def q():
    return Query(extract(FIX))


# -- F16: location → symbol --------------------------------------------------

def test_symbol_at_finds_enclosing_function(q):
    # compute() spans flowpkg/produce.py:4-6.
    assert q.symbol_at("flowpkg/produce.py", 5) == "flowpkg.produce.compute"


def test_symbol_at_module_fallback(q):
    # line 1 (module docstring) is outside any def → falls back to the module.
    assert q.symbol_at("flowpkg/produce.py", 1) == "flowpkg.produce"


def test_symbol_at_unknown_file_is_none(q):
    assert q.symbol_at("flowpkg/nope.py", 3) is None


def test_symbols_in_range_dedupes(q):
    got = q.symbols_in_range("flowpkg/produce.py", 4, 6)
    assert got == ["flowpkg.produce.compute"]


# -- F17: change-set review --------------------------------------------------

def test_build_review_resolves_hunks_to_dossiers(q):
    rv = build_review(q, hunks=[{"file": "flowpkg/produce.py", "ranges": [[4, 6]]}])
    ids = [d["symbol"] for d in rv["changed"]]
    assert "flowpkg.produce.compute" in ids
    d = next(d for d in rv["changed"] if d["symbol"] == "flowpkg.produce.compute")
    # compute writes the 'flag' column by subscript — dataflow contact surfaces.
    assert "flag" in d["columns"]["writes"]
    assert d["risk"] in ("low", "medium", "high")


def test_review_summary_counts_and_sorts(q):
    rv = build_review(q, symbols=["flowpkg.produce.compute", "flowpkg.consume.plot"])
    assert rv["summary"]["changed_symbols"] == 2
    scores = [d["risk_score"] for d in rv["changed"]]
    assert scores == sorted(scores, reverse=True)  # highest risk first


def test_review_reports_unresolved_hunks(q):
    rv = build_review(q, hunks=[{"file": "flowpkg/nope.py", "ranges": [[1, 9]]}])
    assert rv["summary"]["unresolved_hunks"] == [{"file": "flowpkg/nope.py", "range": [1, 9]}]
    assert rv["summary"]["changed_symbols"] == 0


def test_render_review_markdown(q):
    md = render_review(q, hunks=[{"file": "flowpkg/produce.py", "ranges": [[4, 6]]}])
    assert "# Change-set review" in md
    assert "flowpkg.produce.compute" in md


# -- unified-diff parsing ----------------------------------------------------

def test_parse_unified_diff_new_side_ranges():
    diff = (
        "diff --git a/flowpkg/produce.py b/flowpkg/produce.py\n"
        "--- a/flowpkg/produce.py\n"
        "+++ b/flowpkg/produce.py\n"
        "@@ -4,2 +4,3 @@ def compute(df):\n"
        " ctx\n+added\n"
    )
    hunks = parse_unified_diff(diff)
    assert hunks == [{"file": "flowpkg/produce.py", "ranges": [[4, 6]]}]


def test_parse_diff_then_review_end_to_end(q):
    diff = (
        "+++ b/flowpkg/produce.py\n"
        "@@ -4,2 +4,3 @@\n"
    )
    rv = build_review(q, hunks=parse_unified_diff(diff))
    assert any(d["symbol"] == "flowpkg.produce.compute" for d in rv["changed"])


# -- serve ops ---------------------------------------------------------------

def test_locate_op_line():
    s = Session(extract(FIX))
    r = s.handle({"op": "locate", "args": {"file": "flowpkg/produce.py", "line": 5}})
    assert r["ok"]
    assert r["result"]["symbol"] == "flowpkg.produce.compute"


def test_locate_op_range():
    s = Session(extract(FIX))
    r = s.handle({"op": "locate",
                  "args": {"file": "flowpkg/produce.py", "lines": [4, 6]}})
    assert r["result"]["symbols"] == ["flowpkg.produce.compute"]


def test_review_op():
    s = Session(extract(FIX))
    r = s.handle({"op": "review",
                  "args": {"hunks": [{"file": "flowpkg/produce.py", "ranges": [[4, 6]]}]}})
    assert r["ok"]
    assert r["result"]["summary"]["changed_symbols"] >= 1
