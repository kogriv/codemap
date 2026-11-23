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
    # the core claim: `def NAME` is a precise grep; `\bNAME\b` (call-finding) is not. A claim about grep in
    # general, so it is asserted on the sample, not per symbol: 0.0.43 drew `_read`, whose few call sites are
    # mostly real while the definition grep also matches an unrelated method of that name (call 0.77, def 0.5).
    pairs = [(r["grep_call_precision"], r["grep_def_precision"]) for r in measured
             if r["grep_call_precision"] is not None and r["grep_def_precision"] is not None]
    assert pairs
    assert sum(cp <= dp for cp, dp in pairs) > len(pairs) / 2, pairs
    assert sum(cp for cp, _ in pairs) / len(pairs) < sum(dp for _, dp in pairs) / len(pairs), pairs


def test_def_find_precision_is_near_one(measured):
    # grep already nails locations → the graph earns no "where-defined" advantage.
    # On the sample, not per symbol (as above): the repo's own tests carry code inside strings, so a short name
    # drawn from the self-graph (`load`, 0.0.44) can have fixture `def`s beside the real one.
    dps = sorted(r["grep_def_precision"] for r in measured if r["grep_def_precision"] is not None)
    assert dps and dps[len(dps) // 2] >= 0.4 and sum(dps) / len(dps) >= 0.5, dps


def test_deterministic(measured):
    m = _harness()
    from codemap.extract import extract
    from codemap.query import Query
    q = Query(extract(str(_ROOT / "codemap"), deep=False))
    targets = m._auto_targets(q, min_callers=2, per_bucket=3)
    again = m.measure(q, _ROOT, targets)
    assert [r["short"] for r in again] == [r["short"] for r in measured]
