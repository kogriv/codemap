"""R1-C66 — a seeded pack walks both ways by default: what the seeds use, and what uses them.

docs/design/pack_direction.md; measured in research/pack_direction.md. Against git
history the one-way pack never found a co-changed test (recall 0.000 on 53 commits) —
tests use the seed, and the walk ran only from the seed to what it uses. The two-way walk
is personalized PageRank on the symmetric usage graph, cut to the seed's ancestors and
descendants.

The fixture is the pack-honesty one: `caller → seed → mid → far` plus a long chain from
the seed; `dup → mid` is a *sibling* (shares a dependency with the seed, neither uses it
nor is used by it); `lonely` is unconnected. Each guard was run against the change it
names reverted and went red.
"""

from __future__ import annotations

import pytest

from codemap.query import SEED_DIRECTIONS
from codemap.serve.pack import DEFAULT_DIRECTION, build_pack, render_pack

from test_pack_honesty import BIG, CHAIN, _build_graph


@pytest.fixture(scope="module")
def graph():
    return _build_graph()


@pytest.fixture(scope="module")
def q(graph):
    from codemap.query import Query
    return Query(graph)


def _ids(p) -> set[str]:
    return {it["id"] for it in p["items"]}


# -- the default is the two-way walk, and it reaches the seed's callers -------------

def test_default_seeded_walk_is_both_and_reaches_callers(q):
    p = build_pack(q, budget=BIG, seeds=("seed",))
    assert DEFAULT_DIRECTION == "both" and p["coverage"]["walk"] == "both"
    assert "pkg.caller" in _ids(p), "the seed's caller is not in its pack"
    assert {"pkg.seed", "pkg.mid", "pkg.far"} <= _ids(p), "the used side was lost"


def test_uses_walk_is_still_one_way(q):
    p = build_pack(q, budget=BIG, seeds=("seed",), direction="uses")
    assert p["coverage"]["walk"] == "uses"
    assert "pkg.caller" not in _ids(p)


# -- the cut: ancestors ∪ descendants, never a sibling, decided by walking ----------

def test_both_does_not_reach_a_sibling_or_the_unconnected(q):
    """`dup` only shares `mid` with the seed. On the symmetric graph PageRank *does*
    give it mass (seed → mid ← dup), so a cut by `rank > 0` would keep it; the walk over
    ancestors ∪ descendants does not."""
    p = build_pack(q, budget=BIG, seeds=("seed",))
    assert "pkg.dup" not in _ids(p), "a sibling is in the pack"
    assert "pkg.lonely" not in _ids(p)
    reached = 4 + CHAIN  # seed, mid, far, caller + the chain
    assert p["included"] == reached
    assert p["unreachable_from_seeds"] == p["total_ranked"] - reached


def test_reachable_from_both_is_ancestors_and_descendants(q):
    both = q.reachable_from(["pkg.seed"], direction="both")
    uses = q.reachable_from(["pkg.seed"], direction="uses")
    assert both - uses == {"pkg.caller"}


def test_both_rank_is_closeness_either_way(q):
    """The caller is one hop from the seed; the far end of the chain is a hundred. On the
    one-way graph the caller has rank 0 (unreachable); both ways it outranks the tail."""
    both = q.rank(seeds=("seed",), direction="both")
    uses = q.rank(seeds=("seed",), direction="uses")
    tail = f"pkg.chain{CHAIN - 1}"
    assert uses["pkg.caller"] == 0.0
    assert both["pkg.caller"] > both[tail]


# -- the answer says which walk it took -------------------------------------------

def test_direction_text_and_header_name_the_walk(q):
    both = build_pack(q, budget=BIG, seeds=("seed",))["coverage"]["direction"]
    uses = build_pack(q, budget=BIG, seeds=("seed",), direction="uses")["coverage"]["direction"]
    assert both != uses
    assert "what uses them" in both and "callers of a seed are never" in uses
    assert "walk: both" in render_pack(q, budget=BIG, seeds=("seed",))
    assert "walk: uses" in render_pack(q, budget=BIG, seeds=("seed",), direction="uses")


def test_global_pack_has_no_walk(q):
    p = build_pack(q, budget=BIG)
    assert p["coverage"]["walk"] is None


# -- misuse is an error, not a silent default -------------------------------------

def test_direction_without_seeds_is_an_error(q):
    with pytest.raises(ValueError, match="only to a seeded pack"):
        build_pack(q, budget=BIG, direction="both")


@pytest.mark.parametrize("bad", ["up", "used_by", ""])
def test_unknown_direction_is_an_error(q, bad):
    with pytest.raises(ValueError, match="direction"):
        build_pack(q, budget=BIG, seeds=("seed",), direction=bad or "none")
    with pytest.raises(ValueError):
        q.rank(seeds=("seed",), direction=bad or "none")


def test_cli_direction(graph, tmp_path, capsys):
    from codemap import store
    from codemap.cli import main
    path = tmp_path / "g.json"
    store.save(graph, path)
    assert main(["pack", "--graph", str(path), "--direction", "both"]) == 2
    assert "--direction needs --seed" in capsys.readouterr().err
    assert main(["pack", "--graph", str(path), "--seed", "seed", "--direction", "uses"]) == 0
    assert "walk: uses" in capsys.readouterr().out
    assert main(["pack", "--graph", str(path), "--seed", "seed"]) == 0
    assert "walk: both" in capsys.readouterr().out


def test_serve_passes_direction(q):
    from codemap.serve.session import Session
    sess = Session(q.graph)
    one = sess.handle({"op": "pack", "args": {"budget": BIG, "seeds": ["seed"],
                                              "direction": "uses"}})
    assert one["ok"] and one["result"]["coverage"]["walk"] == "uses"
    dflt = sess.handle({"op": "pack", "args": {"budget": BIG, "seeds": ["seed"]}})
    assert dflt["result"]["coverage"]["walk"] == "both"
    bad = sess.handle({"op": "pack", "args": {"budget": BIG, "direction": "both"}})
    assert bad["ok"] is False and "seeded pack" in bad["error"]


def test_mcp_pack_takes_direction():
    import inspect
    pytest.importorskip("mcp")
    from codemap.serve import mcp_server
    src = inspect.getsource(mcp_server)
    assert "direction: str | None = None" in src and 'args["direction"] = direction' in src


def test_directions_are_closed():
    assert SEED_DIRECTIONS == ("uses", "both")
