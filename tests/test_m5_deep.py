"""M5 acceptance tests — deep call resolution (jedi tier).

The deep tier cracks the local-variable call tail that the fast (ast) tier leaves
unresolved. Tested on a tiny synthetic fixture so the suite stays fast and
deterministic; the real-bquant lift (18.6% -> 25.7%) is documented in
gaps/call_resolution_spike_2026-07-26.md.
"""

from __future__ import annotations

from pathlib import Path

from codemap import store
from codemap.extract import extract

FIX = Path(__file__).resolve().parent / "fixtures" / "deeppkg"


def _calls(graph):
    return {
        (e.source, e.target, e.extras.get("resolution"))
        for e in graph.edges
        if e.type == "calls"
    }


def test_deep_cracks_local_variable_call():
    # app.main(): `e = Engine(); e.run()` — e.run() is a call on a local variable.
    deep = _calls(extract(FIX, deep=True))
    assert ("deeppkg.app.main", "deeppkg.core.Engine.run", "deep") in deep


def test_fast_tier_misses_the_tail():
    fast = _calls(extract(FIX))
    # the fast tier resolves the constructor (imported) but not the method on the local
    assert not any(
        src == "deeppkg.app.main" and tgt == "deeppkg.core.Engine.run"
        for src, tgt, _ in fast
    )


def test_deep_still_resolves_self_calls():
    # Engine.run() calls self._step() — both tiers get this; deep labels it "deep".
    deep = _calls(extract(FIX, deep=True))
    assert ("deeppkg.core.Engine.run", "deeppkg.core.Engine._step", "deep") in deep


def test_deep_is_deterministic():
    assert store.dumps(extract(FIX, deep=True)) == store.dumps(extract(FIX, deep=True))


def test_deep_superset_of_fast_on_fixture():
    fast_targets = {(s, t) for s, t, _ in _calls(extract(FIX))}
    deep_targets = {(s, t) for s, t, _ in _calls(extract(FIX, deep=True))}
    # deep resolves at least everything fast did, plus the tail
    assert len(deep_targets) > len(fast_targets)
