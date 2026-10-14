"""Pack honesty — `pack` says what it did with the seed and what it can never contain.

docs/design/pack_honesty.md. Before this, a seed that resolved to nothing (an unknown
name, a document, an attribute) returned the global pack byte for byte, exit 0, under a
header naming the seed; an ambiguous name was spread over every definition silently; a
seeded budget was topped up with symbols the seed cannot reach; and nothing said that a
seed's callers are never in its pack.

Each guard below was run against the defect it names (the fix reverted) and went red.

Since R1-C66 a seeded pack walks both ways by default; the reachability guards here are
about the one-way walk and ask for it (`direction="uses"`). The two-way walk has its own
guards in `test_r1c66_pack_direction.py`.
"""

from __future__ import annotations

import json

import pytest

from codemap.model import ANSWER_FORMAT, Edge, Graph, Node
from codemap.query import Query
from codemap.serve.pack import build_pack, render_pack

CHAIN = 130  # long enough that the far end of a reachable chain rounds to rank 0.0


def _fn(nid, file="pkg/mod.py"):
    return Node(id=nid, kind="function", file=file, lineno=1, signature=f"{nid.rsplit('.', 1)[-1]}()")


@pytest.fixture(scope="module")
def graph() -> Graph:
    return _build_graph()


def _build_graph() -> Graph:
    """seed → mid → far (reachable); caller → seed (a caller, never reachable from it);
    lonely (unreachable); two functions named `dup` (ambiguous short name); one attribute,
    one column and one document (never rankable); and a reachable chain long enough that
    its tail is reachable while its rounded rank is exactly 0.0."""
    g = Graph(target="pkg")
    g.add_node(Node(id="pkg", kind="module", file="pkg/__init__.py"))
    for nid in ("pkg.seed", "pkg.mid", "pkg.far", "pkg.caller", "pkg.lonely"):
        g.add_node(_fn(nid))
    g.add_node(_fn("pkg.dup"))
    g.add_node(_fn("pkg.sub.dup", file="pkg/sub.py"))
    g.add_node(Node(id="pkg.Thing.size", kind="attribute", file="pkg/mod.py"))
    g.add_node(Node(id="col:price", kind="column", file="pkg/mod.py"))
    g.add_node(Node(id="docs/guide.md", kind="doc", file="docs/guide.md"))
    g.add_edge(Edge("calls", "pkg.seed", "pkg.mid"))
    g.add_edge(Edge("calls", "pkg.mid", "pkg.far"))
    g.add_edge(Edge("calls", "pkg.caller", "pkg.seed"))
    g.add_edge(Edge("calls", "pkg.dup", "pkg.mid"))
    prev = "pkg.chain0"
    g.add_node(_fn(prev, file="pkg/chain.py"))
    g.add_edge(Edge("calls", "pkg.seed", prev))
    for i in range(1, CHAIN):
        cur = f"pkg.chain{i}"
        g.add_node(_fn(cur, file="pkg/chain.py"))
        g.add_edge(Edge("calls", prev, cur))
        prev = cur
    return g


@pytest.fixture(scope="module")
def q(graph) -> Query:
    return Query(graph)


BIG = 10 ** 6  # everything fits: what is left out was left out on purpose


# -- D2: nothing resolved → a refusal, never the global pack -------------------

@pytest.mark.parametrize("seed, kind", [
    ("no_such_symbol", None),       # unknown name
    ("docs/guide.md", "doc"),       # a document: matches, but is never ranked
    ("pkg.Thing.size", "attribute"),
    ("col:price", "column"),
])
def test_unresolved_seed_is_a_refusal_not_the_global_pack(q, seed, kind):
    p = build_pack(q, budget=BIG, seeds=(seed,))
    assert "error" in p and "items" not in p, "fell through to a pack"
    assert p["seeds"]["unresolved"] == [seed]
    got = p["seeds"]["requested"][0]
    assert got["matched"] == []
    if kind is None:
        assert got["via"] == "none" and got["unrankable"] == {}
    else:
        assert got["unrankable"] == {kind: 1}, "what it did match is not said"


def test_cli_refusal_exits_1_and_says_so(graph, tmp_path, capsys):
    from codemap import store
    from codemap.cli import main
    path = tmp_path / "g.json"
    store.save(graph, path)
    assert main(["pack", "--graph", str(path), "--seed", "no_such_symbol"]) == 1
    out = capsys.readouterr().out
    assert "refused" in out and "Unresolved seed `no_such_symbol`" in out
    assert "- pkg." not in out, "a refusal printed pack items"
    # and a seed that does resolve still exits 0 — the refusal is not a blanket error
    assert main(["pack", "--graph", str(path), "--seed", "seed"]) == 0


# -- D1: partially resolved → the resolved part, and the rest named ---------------

def test_partial_seed_set_names_what_it_dropped(q):
    alone = build_pack(q, budget=BIG, seeds=("seed",))
    mixed = build_pack(q, budget=BIG, seeds=("seed", "no_such_symbol"))
    assert mixed["items"] == alone["items"]
    assert mixed["seeds"]["unresolved"] == ["no_such_symbol"]
    md = render_pack(q, budget=BIG, seeds=("seed", "no_such_symbol"))
    assert "Unresolved seed `no_such_symbol`" in md


def test_seed_via_is_reported(q):
    p = build_pack(q, budget=BIG, seeds=("pkg.seed", "seed", "pkg/chain.py"))
    vias = [s["via"] for s in p["seeds"]["requested"]]
    assert vias == ["id", "name", "file"]


# -- D5: an ambiguous name is declared, not resolved arbitrarily -------------------

def test_ambiguous_name_is_flagged_with_every_definition(q):
    p = build_pack(q, budget=BIG, seeds=("dup",))
    s = p["seeds"]["requested"][0]
    assert s["ambiguous"] is True
    assert s["matched"] == ["pkg.dup", "pkg.sub.dup"]
    assert "Ambiguous seed `dup`" in render_pack(q, budget=BIG, seeds=("dup",))


def test_unambiguous_name_is_not_flagged(q):
    assert build_pack(q, budget=BIG, seeds=("seed",))["seeds"]["requested"][0]["ambiguous"] is False


# -- D3: a seeded pack holds only what the seed reaches, decided by walking ---------

def test_seeded_pack_holds_only_what_the_seed_reaches(q):
    p = build_pack(q, budget=BIG, seeds=("seed",), direction="uses")
    ids = {it["id"] for it in p["items"]}
    assert {"pkg.seed", "pkg.mid", "pkg.far"} <= ids
    assert "pkg.caller" not in ids, "a caller of the seed is in its pack"
    assert "pkg.lonely" not in ids and "pkg" not in ids, "unreachable filler"
    reachable = 3 + CHAIN  # seed, mid, far + the whole chain
    assert p["unreachable_from_seeds"] == p["total_ranked"] - reachable
    assert p["included"] == reachable


def test_reachability_is_walked_not_read_off_a_rounded_rank(q):
    """The far end of the chain is reachable and its rounded rank is exactly 0.0. A cut
    by `rank == 0` would drop it; the walk keeps it."""
    tail = f"pkg.chain{CHAIN - 1}"
    p = build_pack(q, budget=BIG, seeds=("seed",), direction="uses")
    got = {it["id"]: it["rank"] for it in p["items"]}
    assert tail in got, "a reachable symbol was cut"
    assert got[tail] == 0.0, "fixture no longer exercises rounding — lengthen CHAIN"


# -- D4: coverage is declared on every answer ------------------------------------

def test_coverage_names_what_can_never_be_in_a_pack(q):
    for p in (build_pack(q, budget=BIG),
              build_pack(q, budget=BIG, seeds=("seed",)),
              build_pack(q, budget=BIG, seeds=("no_such_symbol",))):
        cov = p["coverage"]
        assert cov["ranked_kinds"] == ["class", "function", "module"]
        assert cov["never_in_pack"] == {"attribute": 1, "column": 1, "doc": 1}


def test_direction_is_stated_and_differs_with_seeds(q):
    glob = build_pack(q, budget=BIG)["coverage"]["direction"]
    seeded = build_pack(q, budget=BIG, seeds=("seed",), direction="uses")["coverage"]["direction"]
    assert "callers of a seed are never" in seeded
    assert glob != seeded


def test_global_pack_fields_are_present_and_null(q):
    """R1-C28: the fields exist on every answer; without seeds they are null — the notion
    does not apply — not missing, and not zero."""
    p = build_pack(q, budget=BIG)
    assert p["seeds"] is None and p["unreachable_from_seeds"] is None
    assert p["included"] == p["total_ranked"]  # global: nothing is unreachable


# -- serve / MCP: the same answer, a new format ---------------------------------

def test_serve_carries_the_same_blocks_and_format_2(q):
    from codemap.serve.session import Session
    sess = Session(q.graph)
    env = sess.handle({"op": "pack", "args": {"budget": BIG, "seeds": ["seed"]}})
    assert env["ok"] and env["answer_format"] == ANSWER_FORMAT == 2
    assert env["result"] == build_pack(q, budget=BIG, seeds=("seed",))
    refused = sess.handle({"op": "pack", "args": {"budget": BIG, "seeds": ["no_such_symbol"]}})
    assert refused["ok"] is True and "error" in refused["result"]


def test_json_is_deterministic(q):
    a = json.dumps(build_pack(q, budget=BIG, seeds=("dup", "no_such_symbol")), sort_keys=True)
    b = json.dumps(build_pack(q, budget=BIG, seeds=("dup", "no_such_symbol")), sort_keys=True)
    assert a == b


# -- the rendered pack is pinned, so its shape cannot move silently ---------------
# `pack` was not among the six surfaces `test_r1c63_answer_format` pins, so the structure
# of its answer could change without anyone deciding it. Bump together with
# ANSWER_FORMAT when a change of structure is intended; checked under PYTHONHASHSEED
# 0, 1, 7, 42 and 99 before pinning.
#
# Re-pinned for R1-C66 (a seeded pack walks both ways by default; the header names the
# walk). A change of meaning, not only of wording — but ANSWER_FORMAT stays 2: format 2
# has never been released (0.0.21 answers format 1), so it describes 0.0.22's answer
# whole (docs/design/pack_direction.md D3). Checked under the same five hash seeds.
PACK_RENDERED_SHA = "5d4dc2677ad10fab35ae427ae28551132bdcb09dcacf7112f13d592547f157e1"


def test_rendered_pack_matches_the_pin(q):
    import hashlib
    out = "".join(render_pack(q, budget=b, seeds=s) for b, s in
                  ((60, ()), (80, ("seed",)), (BIG, ("dup", "no_such_symbol")),
                   (BIG, ("no_such_symbol",))))
    got = hashlib.sha256(out.encode()).hexdigest()
    assert got == PACK_RENDERED_SHA, (
        "the rendered pack changed — intended change of structure? bump ANSWER_FORMAT "
        f"and this pin together; wording only? this pin alone.\n  got {got}")
