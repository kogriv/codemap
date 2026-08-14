"""R1-C13 (a) — call-graph accuracy against hand-labeled ground truth.

Guards the honest-ceiling story so a regression in the extractor (or the labels)
trips the suite. The harness lives in research/bench/callgraph_accuracy.py; here
we import it and assert the invariants the accuracy claims rest on.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parent.parent / "research" / "bench" / "callgraph_accuracy.py"


def _load():
    spec = importlib.util.spec_from_file_location("callgraph_accuracy", _HARNESS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def result():
    return _load().run()


def test_deep_precision_perfect_on_real_relationships(result):
    # every deep-tier calls edge is a true relationship (phantom closure excluded
    # as a documented limitation, not counted here — see test_deep_phantom).
    assert result["aggregate"]["deep"]["precision"] == 1.0


def test_deep_recall_perfect_on_decidable(result):
    # no statically-decidable edge is missed by the deep tier — the "bug" metric.
    assert result["aggregate"]["deep"]["recall_decidable"] == 1.0


def test_honest_ceiling_below_one(result):
    # the whole point: over ALL true edges (incl. undecidable ones) recall is < 100%.
    # Python dynamism is not fully statically resolvable — we state this, not hide it.
    assert result["aggregate"]["deep"]["recall_overall"] < 1.0


def test_fast_tier_has_the_documented_inheritance_phantom(result):
    # fast tier over-approximates self.<inherited> to a same-class phantom id; the
    # suite surfaces it rather than hiding it. Deep resolves it correctly.
    c06_fast = next(r for r in result["rows"]
                    if r["case"] == "c06_inheritance" and r["tier"] == "fast")
    assert c06_fast["phantom"] == 1
    assert c06_fast["fp"] == 1


def test_deep_phantom_is_only_the_closure_case(result):
    # exactly one phantom edge on the deep tier — the c10 closure limitation.
    assert result["aggregate"]["deep"]["phantom"] == 1
    c10 = next(r for r in result["rows"]
               if r["case"] == "c10_closure" and r["tier"] == "deep")
    assert c10["phantom"] == 1


def test_registry_dispatch_not_a_call_edge(result):
    # design boundary: string-keyed dict dispatch is not emitted as a calls edge.
    c09 = next(r for r in result["rows"]
               if r["case"] == "c09_registry_dispatch" and r["tier"] == "deep")
    assert c09["tp"] == 0 and c09["fp"] == 0


def test_deterministic(result):
    assert _load().run()["aggregate"] == result["aggregate"]
