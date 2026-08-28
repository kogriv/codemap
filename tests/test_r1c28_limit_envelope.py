"""R1-C28 acceptance — a result limit is partiality, and every limited op says so.

Found by measuring CodeGraph (research/tools/codegraph.md, T2): its `callers` defaults
to `--limit 20` and reports nothing about the cut, which made a 79-entry answer read as
a 20-entry one of a different shape. Asking the same question of ourselves:
`search "zone"` returned **50 of 1259** under an envelope that said `{"ok": true}`.

Gap: gaps/limit_truncation_2026-08-28.md. The rule: whenever an op accepts a limit, the
envelope carries `limit {applied, returned, total, truncated}` — *always*, because an
only-on-truncation field forces a caller to distinguish "nothing was cut" from "this
build does not report cuts", and it cannot.

The last test in this file is the one that matters in a year: it fails if a new op
learns a limit without declaring it.
"""

from __future__ import annotations

import inspect
import re

from codemap.model import Edge, Graph, Node
from codemap.serve.limits import limit_block, limit_footer
from codemap.serve.mcp_server import _cap_list, _compact_impact
from codemap.serve import session as session_mod
from codemap.serve.session import _LIMITED_OPS, _UNLIMITED_BY_DESIGN, Session

_BLOCK_KEYS = {"applied", "returned", "total", "truncated"}


def _graph(n_zones: int = 120) -> Graph:
    """A graph with many `zone`-ish names — enough to overflow any sane default."""
    g = Graph(target="pkg")
    g.add_node(Node(id="pkg.m", kind="module", file="pkg/m.py", extras={"root": "core"}))
    for i in range(n_zones):
        g.add_node(Node(id=f"pkg.m.zone_{i:03d}", kind="function", file="pkg/m.py",
                        lineno=i + 1, endlineno=i + 1, extras={"root": "core"}))
    g.add_node(Node(id="pkg.m.other", kind="function", file="pkg/m.py",
                    extras={"root": "core"}))
    g.add_edge(Edge(type="contains", source="pkg.m", target="pkg.m.other"))
    return g


def _handle(op, args=None, graph=None):
    return Session(graph or _graph()).handle({"op": op, "args": args or {}})


# -- the block is present, and it is true ------------------------------------

def test_search_declares_the_cut():
    env = _handle("search", {"term": "zone"})
    assert env["ok"] and len(env["result"]) == 50
    assert env["limit"] == {"applied": 50, "returned": 50,
                            "total": 120, "truncated": True}


def test_search_declares_the_absence_of_a_cut():
    """The half that is easy to skip: `truncated: false` must be stated, not implied.

    A consumer reading an answer with no block cannot tell a complete answer from an
    old build — which is the same confident-partial failure one level up.
    """
    env = _handle("search", {"term": "other"})
    assert env["limit"] == {"applied": 50, "returned": 1,
                            "total": 1, "truncated": False}


def test_search_total_is_the_true_total_not_the_page():
    """Regression on the actual defect: 50 of 1259 used to be indistinguishable from 50."""
    env = _handle("search", {"term": "zone", "limit": 5})
    assert len(env["result"]) == 5
    assert env["limit"]["total"] == 120 and env["limit"]["truncated"] is True


def test_search_kind_filter_counts_after_filtering():
    env = _handle("search", {"term": "zone", "kind": "module", "limit": 10})
    assert env["result"] == [] and env["limit"]["total"] == 0
    assert env["limit"]["truncated"] is False


def test_widening_the_limit_reaches_the_declared_total():
    """The block has to be actionable: the number it promises must be gettable."""
    total = _handle("search", {"term": "zone"})["limit"]["total"]
    env = _handle("search", {"term": "zone", "limit": total})
    assert len(env["result"]) == total and env["limit"]["truncated"] is False


def test_unlimited_ops_carry_no_block():
    """Absence is meaningful too: no block = this op has no limit to declare."""
    for op, args in [("stats", {}), ("families", {}), ("architecture", {}),
                     ("callers", {"symbol": "pkg.m.other"})]:
        assert "limit" not in _handle(op, args), op


# -- tests / covers: one vocabulary across ops -------------------------------

def _test_graph() -> Graph:
    """A core function called by nine real (pytest-collectable) tests, plus the `zone`
    names from `_graph` so one fixture serves every limited op."""
    g = _graph()
    g.provenance = {"tier": "ast"}
    g.add_node(Node(id="pkg.core", kind="module", file="pkg/core.py",
                    extras={"root": "core"}))
    g.add_node(Node(id="pkg.core.f", kind="function", file="pkg/core.py",
                    extras={"root": "core"}))
    g.add_edge(Edge(type="contains", source="pkg.core", target="pkg.core.f"))
    g.add_node(Node(id="tests.test_m", kind="module", file="tests/test_m.py",
                    extras={"root": "tests"}))
    for i in range(9):
        tid = f"tests.test_m.test_{i}"
        g.add_node(Node(id=tid, kind="function", file="tests/test_m.py",
                        lineno=i + 1, extras={"root": "tests"}))
        g.add_edge(Edge(type="contains", source="tests.test_m", target=tid))
        g.add_edge(Edge(type="calls", source=tid, target="pkg.core.f"))
    return g


def test_tests_op_declares_its_cap():
    env = _handle("tests", {"symbol": "pkg.core.f", "cap": 4}, graph=_test_graph())
    assert env["limit"] == {"applied": 4, "returned": 4, "total": 9, "truncated": True}
    # …without losing what the result already said in its own body (R1-C24).
    assert env["result"]["total_at_distance"] == 9 and env["result"]["truncated"] == 5


def test_covers_op_declares_its_cap():
    env = _handle("covers", {"test": "tests.test_m.test_0", "cap": 1},
                  graph=_test_graph())
    assert env["limit"]["applied"] == 1 and env["limit"]["total"] == 1
    assert env["limit"]["truncated"] is False


def test_limit_and_epistemic_are_orthogonal():
    """An answer can be resolution-partial *and* limit-truncated; both belong.

    This is the whole point of not folding the limit into `_PARTIAL_OPS`: they are two
    independent sources of lower-boundness, and collapsing them loses which one bit.
    """
    env = _handle("tests", {"symbol": "pkg.core.f", "cap": 2}, graph=_test_graph())
    assert env["epistemic"]["epistemic"] == "partial"
    assert env["limit"]["truncated"] is True
    # search is limited but structurally exact — limit without epistemic.
    s = _handle("search", {"term": "zone"})
    assert "epistemic" not in s and s["limit"]["truncated"] is True


# -- semantic: the cut happens upstream, so the total is honestly unknown ----

def test_semantic_without_adapter_still_declares_a_limit():
    """No adapter is not an excuse to skip the block — the op still took a limit."""
    env = _handle("semantic", {"query": "swing pivots", "root": "."})
    assert env["result"]["resolver"] is None
    assert env["limit"] == {"applied": 10, "returned": 0,
                            "total": 0, "truncated": False}
    assert "limit" not in env["result"]  # lifted to the envelope, not duplicated


def test_semantic_full_page_reports_unknown_total(monkeypatch):
    """`total: null` — an unobserved total is a fact, not a field to omit."""
    from codemap.serve import semantic as sem

    class _Adapter:
        name, license = "fake", "MIT"

        def search(self, capability, text, *, root=".", limit=10):
            return [{"file": "pkg/m.py", "start_line": i + 1, "end_line": i + 1,
                     "score": 1.0 - i / 100} for i in range(limit)]

    monkeypatch.setattr(sem, "resolve", lambda *a, **k: _Adapter())
    res = sem.semantic_search(__import__("codemap.query", fromlist=["Query"])
                              .Query(_graph()), "zones", root=".", limit=3)
    assert res["limit"]["applied"] == 3 and res["limit"]["total"] is None
    assert res["limit"]["truncated"] is None
    assert "not observable" in res["limit"]["note"]


def test_semantic_short_page_proves_nothing_was_cut(monkeypatch):
    from codemap.serve import semantic as sem

    class _Adapter:
        name, license = "fake", "MIT"

        def search(self, capability, text, *, root=".", limit=10):
            return [{"file": "pkg/m.py", "start_line": 1, "end_line": 1, "score": 0.9}]

    monkeypatch.setattr(sem, "resolve", lambda *a, **k: _Adapter())
    res = sem.semantic_search(__import__("codemap.query", fromlist=["Query"])
                              .Query(_graph()), "zones", root=".", limit=5)
    assert res["limit"]["truncated"] is False and res["limit"]["total"] == 1


# -- the MCP transport caps too, and now in the same words -------------------

def test_mcp_cap_list_uses_the_shared_block():
    env = {"ok": True, "result": [{"caller": f"c{i}"} for i in range(50)]}
    out = _cap_list(env, 10)
    assert len(out["result"]) == 10
    assert out["limit"] == {"applied": 10, "returned": 10,
                            "total": 50, "truncated": True}


def test_mcp_cap_list_declares_an_uncut_list():
    out = _cap_list({"ok": True, "result": [1, 2]}, 10)
    assert out["limit"] == {"applied": 10, "returned": 2,
                            "total": 2, "truncated": False}


def test_mcp_compact_impact_declares_per_entry_and_in_total():
    env = {"ok": True, "result": {"markdown": "…", "impact": [
        {"symbol": "a", "refs": [f"r{i}" for i in range(30)]},
        {"symbol": "b", "refs": ["r0"]},
    ]}}
    out = _compact_impact(env, 5)
    entries = out["result"]["impact"]
    assert [e["refs_shown"] for e in entries] == [5, 1]
    assert [e["refs_total"] for e in entries] == [30, 1]
    assert out["limit"]["returned"] == 6 and out["limit"]["total"] == 31
    assert out["limit"]["truncated"] is True and "per impact entry" in out["limit"]["note"]


def test_mcp_helpers_leave_failed_envelopes_alone():
    err = {"ok": False, "error": "boom"}
    assert _cap_list(err, 10) == err and _compact_impact(err, 10) == err


# -- the footer is for humans, so it stays quiet when there is nothing to say -

def test_footer_only_speaks_on_a_cut():
    assert limit_footer(limit_block(50, 50, 1259)) == \
        "_50 of 1259 shown — pass --limit to widen._"
    assert limit_footer(limit_block(50, 3, 3)) is None
    assert limit_footer(None) is None
    unknown = limit_footer(limit_block(10, 10, None, truncated=None))
    assert "pre-limit total is unknown" in unknown


def test_block_derives_truncated_when_not_given():
    assert limit_block(10, 10, 40)["truncated"] is True
    assert limit_block(10, 4, 4)["truncated"] is False
    # Fewer than asked for, unknown total → still provably uncut.
    assert limit_block(10, 4, None)["truncated"] is False
    # Exactly full, unknown total → the one honest `None` in the vocabulary.
    assert limit_block(10, 10, None)["truncated"] is None


# -- the guard: this rule outlives the fix only if something enforces it -----

_LIMIT_ARG = re.compile(r"""args\.get\(\s*["'](limit|cap|budget|max|top)["']""")


def test_every_op_that_reads_a_limit_arg_is_accounted_for():
    """Fails when a new op learns a limit without joining the convention.

    Reads the ops' own source rather than a hand-kept list, because a hand-kept list is
    exactly what gets forgotten. An op that takes a limit-ish argument must either be in
    `_LIMITED_OPS` (and therefore emit the block) or be written down in
    `_UNLIMITED_BY_DESIGN` with the reason it is not a cut of a computed list.
    """
    for op, fn in session_mod._OPS.items():
        if not _LIMIT_ARG.search(inspect.getsource(fn)):
            continue
        assert op in _LIMITED_OPS or op in _UNLIMITED_BY_DESIGN, (
            f"op {op!r} reads a limit-like argument but neither declares a limit block "
            f"(_LIMITED_OPS) nor records why it does not (_UNLIMITED_BY_DESIGN)")


def test_declared_limited_ops_actually_emit_the_block():
    """The other direction: being in the set is a promise, so it is checked."""
    calls = {
        "search": {"term": "zone"},
        "semantic": {"query": "zones", "root": "."},
        "tests": {"symbol": "pkg.core.f"},
        "covers": {"test": "tests.test_m.test_0"},
    }
    assert set(calls) == set(_LIMITED_OPS), "a limited op has no coverage here"
    for op, args in calls.items():
        env = _handle(op, args, graph=_test_graph())
        assert env["ok"], (op, env)
        block = env.get("limit")
        assert block and _BLOCK_KEYS <= set(block), f"{op} emitted {block!r}"
        assert isinstance(block["applied"], int) and isinstance(block["returned"], int)


def test_exemptions_carry_a_reason_not_just_a_name():
    for op, reason in _UNLIMITED_BY_DESIGN.items():
        assert op in session_mod._OPS and len(reason) > 40, op
