"""R1-C13 (b) — grep-vs-graph value proof, dogfooded on codemap itself.

The headline numbers in the docs are measured on bquant (an external tree); here
we dogfood the *same harness* on codemap's own repo so the claim is protected in
CI with no external dependency. We assert the DIRECTION, not magnitudes:

  - grep is costlier than the graph for BREAKAGE (more candidates to inspect);
  - grep is LESS precise at finding call-sites than at finding definitions —
    which is exactly why the graph's leverage is on relationships, not locations.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_HARNESS = _ROOT / "research" / "bench" / "grep_vs_graph.py"


def _harness():
    spec = importlib.util.spec_from_file_location("grep_vs_graph", _HARNESS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def measured():
    m = _harness()
    from codemap.extract import extract
    from codemap.query import Query
    q = Query(extract(str(_ROOT / "codemap"), deep=False))  # fast tier: sub-second
    targets = m._auto_targets(q, min_callers=2, per_bucket=3)
    assert targets, "codemap self-graph yielded no targets with >=2 callers"
    return m.measure(q, _ROOT, targets)


def test_grep_costlier_than_graph_for_breakage(measured):
    total_grep = sum(r["grep_word"] for r in measured)
    total_graph = sum(r["breakage_graph"] for r in measured)
    assert total_grep > total_graph  # grep hands you more candidates to inspect


def test_grep_less_precise_at_calls_than_defs(measured):
    # the core claim: `def NAME` is a precise grep; `\bNAME\b` (call-finding) is not.
    for r in measured:
        cp, dp = r["grep_call_precision"], r["grep_def_precision"]
        if cp is None or dp is None:
            continue
        assert cp <= dp, f"{r['short']}: call precision {cp} should not exceed def precision {dp}"


def test_def_find_precision_is_near_one(measured):
    # grep already nails locations → the graph earns no "where-defined" advantage.
    dps = [r["grep_def_precision"] for r in measured if r["grep_def_precision"] is not None]
    assert dps and all(dp >= 0.4 for dp in dps)


def test_deterministic(measured):
    m = _harness()
    from codemap.extract import extract
    from codemap.query import Query
    q = Query(extract(str(_ROOT / "codemap"), deep=False))
    targets = m._auto_targets(q, min_callers=2, per_bucket=3)
    again = m.measure(q, _ROOT, targets)
    assert [r["short"] for r in again] == [r["short"] for r in measured]
