"""R1-C6 acceptance — relevance ranking + token-budgeted context pack.

Ranking is a pure-Python personalized PageRank over usage edges (no numpy dep);
pack renders the most relevant slice under a token budget. Tests pin determinism,
that importance/seed-bias behave, that the pack never exceeds budget and puts hubs
before leaves, and the serve/MCP surface.
"""

from __future__ import annotations

import pytest

from codemap.model import Edge, Graph, Node
from codemap.query import Query
from codemap.serve.pack import build_pack, estimate_tokens, render_pack


def _fn(nid, **kw):
    return Node(id=nid, kind="function", file="pkg/mod.py", **kw)


@pytest.fixture(scope="module")
def q() -> Query:
    """hub is depended-upon by a/b/c (globally important); unrelated too. seed→tgt is a
    private neighbourhood reachable only from seed (for personalization)."""
    g = Graph(target="pkg")
    g.add_node(Node(id="pkg", kind="module", file="pkg/__init__.py"))
    for name in ("hub", "a", "b", "c", "leaf", "seed", "tgt", "unrelated"):
        g.add_node(_fn(f"pkg.{name}", lineno=1, signature=f"{name}()"))
    for u in ("a", "b", "c"):
        g.add_edge(Edge("calls", f"pkg.{u}", "pkg.hub"))       # hub ← a,b,c
        g.add_edge(Edge("calls", f"pkg.{u}", "pkg.unrelated"))  # unrelated ← a,b,c
    g.add_edge(Edge("calls", "pkg.seed", "pkg.tgt"))            # seed → tgt (only path)
    return Query(g)


# -- ranking ------------------------------------------------------------------

def test_rank_deterministic(q):
    assert q.rank() == q.rank()


def test_rank_importance(q):
    r = q.rank()
    assert r["pkg.hub"] > r["pkg.leaf"]         # depended-upon > isolated
    assert r["pkg.unrelated"] > r["pkg.leaf"]


def test_rank_seed_bias(q):
    seeded = q.rank(seeds=("pkg.seed",))
    # tgt (reachable from the seed) beats unrelated (globally important, but not
    # reachable from the seed) once we personalize on seed
    assert seeded["pkg.tgt"] > seeded["pkg.unrelated"]
    # and seed-bias actually changed the ranking vs global
    assert q.rank()["pkg.unrelated"] > q.rank()["pkg.tgt"]


def test_rank_seed_by_shortname_and_file(q):
    by_name = q.rank(seeds=("seed",))       # short name → resolves to pkg.seed
    by_id = q.rank(seeds=("pkg.seed",))
    assert by_name == by_id
    # a file seed expands to every symbol in that file (non-empty personalization)
    assert q.rank(seeds=("pkg/mod.py",))     # doesn't raise, returns scores
    assert q._expand_seeds(("pkg/mod.py",))  # file path expands to node ids


# -- token estimate + pack budget --------------------------------------------

def test_estimate_tokens():
    assert estimate_tokens("") == 1
    assert estimate_tokens("x" * 40) == 10
    assert estimate_tokens("a" * 8) < estimate_tokens("a" * 80)


def test_pack_never_exceeds_budget(q):
    for budget in (5, 30, 100, 100000):
        p = build_pack(q, budget=budget)
        assert p["used_tokens"] <= budget


def test_pack_hubs_before_leaves(q):
    p = build_pack(q, budget=100000)  # everything fits
    ids = [it["id"] for it in p["items"]]
    assert ids.index("pkg.hub") < ids.index("pkg.leaf")
    # items are strictly rank-ordered (desc), id tiebreak
    ranks = [it["rank"] for it in p["items"]]
    assert ranks == sorted(ranks, reverse=True)


def test_pack_truncation_flags(q):
    big = build_pack(q, budget=100000)
    assert big["truncated"] is False and big["included"] == big["total_ranked"]
    small = build_pack(q, budget=15)
    assert small["truncated"] is True and small["included"] < small["total_ranked"]


def test_pack_seeds_reorder(q):
    glob = [it["id"] for it in build_pack(q, budget=100000)["items"]]
    seeded = [it["id"] for it in build_pack(q, budget=100000, seeds=("pkg.seed",))["items"]]
    assert glob != seeded  # personalization changes what ranks first


def test_render_within_budget_note(q):
    out = render_pack(q, budget=30)
    assert "Context pack" in out and "/ 30 tokens" in out


# -- serve op + MCP surface ---------------------------------------------------

def test_serve_pack_op(q):
    from codemap.serve.session import Session
    sess = Session(q.graph)
    env = sess.handle({"op": "pack", "args": {"budget": 100000}})
    assert env["ok"] and env["result"]["used_tokens"] <= 100000
    assert env["result"]["included"] == env["result"]["total_ranked"]


def test_mcp_lists_pack():
    from codemap.serve.mcp_server import MCP_TOOLS
    assert "pack" in MCP_TOOLS
