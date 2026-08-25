"""R1-C24 acceptance — "which tests exercise this symbol?" (axis A10).

The measurement that shaped the design, on codemap's own repo against **coverage.py**
ground truth (`dynamic_context = test_function`, 484 tests):

- The direct answer — what `callers`/`references_to` return today — is empty for **82%**
  of core symbols. A test calls `extract()`; `extract()` calls two hundred things.
- "Everything reachable" is not the answer either: median 21 tests, max 126 of 416.
- Precision by nearest hop, measured, is a cliff:

      hop 1: median precision 1.00, 2 tests      hop 4: 0.67, 78 tests
      hop 2: 1.00, 4 tests                       hop 5: 0.33, 78 tests
      hop 3: 1.00, 8 tests                       hop 6: 0.23, 78 tests

  By the fourth hop the walk has reached shared test infrastructure and is answering
  "most of the suite". Hence a default cutoff of **3**, chosen from that table and not
  from taste, with deeper walks available on request and labelled `low`.
- At that cutoff: **57%** of exercised symbols get an answer (deep tier; 43% fast),
  median precision **1.00**, and **93%** of answers contain at least one test that
  coverage.py confirms executes the symbol. Recall against the executed-set is 0.43
  median and deliberately not the target — for a central symbol that set is most of the
  suite. Re-runnable: ``research/bench/test_mapping_accuracy.py``.
- The remaining **16%** get `unknown` — never "no tests cover this".

The fixture is a hand-built world with known distances, because an acceptance that
depends on codemap's own suite would move every time the suite does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.extract import extract_repo
from codemap.query import Query

W = Path(__file__).resolve().parent / "fixtures" / "tmworld"


@pytest.fixture(scope="module")
def q():
    return Query(extract_repo(W / "tmpkg", consumers=(W / "tests",), mode="full"))


def _row(q, sym, **kw):
    return q.tests_for(f"tmpkg.core.{sym}", **kw)


# -- D1: what counts as a test is derived, not stored ----------------------------

def test_only_real_pytest_tests_are_tests(q):
    assert q._test_ids == {
        "tests.test_world.test_entry",
        "tests.test_world.test_entry_again",
        "tests.test_world.TestEngine.test_run",
    }


def test_a_test_named_function_outside_a_test_file_is_not_a_test(q):
    """`helpers.py::test_looking_but_not_collected` — pytest would not collect it, so
    neither may we. This rule is what keeps helper packages under `tests/fixtures/` out."""
    assert "tests.helpers.test_looking_but_not_collected" not in q._test_ids


def test_a_helper_inside_a_test_file_is_not_a_test(q):
    assert "tests.test_world.helper_not_a_test" not in q._test_ids


def test_nothing_was_stamped_on_the_graph(q):
    """Derived at query time: no node carries a `test` marker, so an existing graph gains
    the feature on upgrade and the artifact stays free of one framework's conventions."""
    assert not [n for n in q.graph.nodes.values() if "test" in n.extras]


# -- D5: the answer is a command, not a reading exercise -------------------------

def test_ids_are_translated_to_pytest_node_ids(q):
    assert q.pytest_nodeid("tests.test_world.test_entry") == \
        "tests/test_world.py::test_entry"


def test_a_test_method_keeps_its_class(q):
    assert q.pytest_nodeid("tests.test_world.TestEngine.test_run") == \
        "tests/test_world.py::TestEngine::test_run"


# -- D2: nearest band, and the distance is the ranking ---------------------------

@pytest.mark.parametrize("sym,dist,conf", [
    ("entry", 1, "high"),     # called directly by two tests
    ("_mid", 2, "high"),      # entry -> _mid
    ("_leaf", 3, "medium"),   # entry -> _mid -> _leaf
])
def test_the_nearest_band_is_returned_with_its_confidence(q, sym, dist, conf):
    r = _row(q, sym)
    assert r["distance"] == dist and r["confidence"] == conf
    assert {t["node_id"] for t in r["tests"]} == {
        "tests/test_world.py::test_entry", "tests/test_world.py::test_entry_again"}


def test_beyond_the_measured_cutoff_the_default_answer_is_unknown(q):
    """`_beyond` is four hops away — where measured precision falls to 0.67 and the
    answer size explodes to 78. Not returned by default."""
    assert _row(q, "_beyond")["confidence"] == "unknown"


def test_a_deeper_walk_is_available_and_labelled_low(q):
    r = _row(q, "_beyond", depth=6)
    assert r["distance"] == 4 and r["confidence"] == "low"


def test_the_cap_is_stated_never_silent(q):
    r = _row(q, "entry", cap=1)
    assert len(r["tests"]) == 1 and r["truncated"] == 1
    assert any("not listed" in c for c in r["caveats"])


# -- the honesty rule this project keeps having to re-learn ----------------------

def test_no_answer_is_unknown_never_none(q):
    """A confident empty is the failure behind #1 (`risk:"none"`), #3, #5, #7 and #23.
    16% of symbols coverage.py proves are exercised produce no answer here."""
    r = _row(q, "orphan")
    assert r["confidence"] == "unknown" and r["tests"] == []
    assert any("unknown, not none" in c for c in r["caveats"])


def test_every_answer_carries_both_epistemic_labels(q):
    caveats = " ".join(_row(q, "entry")["caveats"])
    assert "over-set" in caveats and "lower bound" in caveats


def test_the_tier_is_part_of_the_answer(q):
    """21% of methods resolve on the fast tier against 56% on deep, and test suites call
    methods on objects — so a fast-tier answer is not a slightly worse answer."""
    r = _row(q, "entry")
    assert r["tier"] == "fast"
    assert any("fast tier" in c for c in r["caveats"])


def test_a_method_on_a_constructed_object_is_a_known_limit(q):
    """`Engine().run()` in a test resolves to no edge: consumer-root call resolution is
    name-based. Stated as `unknown` rather than answered wrongly — and it is the dominant
    residual cause of the 16%."""
    assert _row(q, "Engine.run")["confidence"] == "unknown"


# -- D5 inverse: what does this test reach ---------------------------------------

def test_covers_walks_the_other_way(q):
    c = q.covers("tests.test_world.test_entry")
    got = {s["id"]: s["distance"] for s in c["symbols"]}
    assert got["tmpkg.core.entry"] == 1
    assert got["tmpkg.core._mid"] == 2
    assert got["tmpkg.core._leaf"] == 3


def test_covers_names_the_test_it_is_about(q):
    assert q.covers("tests.test_world.test_entry")["node_id"] == \
        "tests/test_world.py::test_entry"


# -- the serve surface ------------------------------------------------------------

def test_the_ops_are_served(q):
    from codemap.serve.session import Session
    s = Session(q.graph)
    env = s.handle({"op": "tests", "args": {"symbol": "tmpkg.core.entry"}})
    assert env["ok"] and env["result"]["confidence"] == "high"
    assert env["epistemic"]["epistemic"] == "partial"
    inv = s.handle({"op": "covers", "args": {"test": "tests.test_world.test_entry"}})
    assert inv["ok"] and inv["result"]["total"] >= 3
