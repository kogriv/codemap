"""R1-C13 acceptance — machine-readable epistemic label on call-graph answers.

One label per answer (variant 1): ops that lean on the partial static call graph
carry ``epistemic: "partial"``; structural ops (imports/contains/…) don't. The
label is the structured twin of the prose disclaimers. From the GitNexus разбор,
built natively. No per-edge confidence — edges already carry ``resolution``.
"""

from __future__ import annotations

from codemap.model import Edge, Graph, Node
from codemap.serve.mcp_server import _cap_list, _compact_impact
from codemap.serve.session import Session


def _graph() -> Graph:
    g = Graph(target="pkg")
    for n in ("E", "F"):
        g.add_node(Node(id=f"pkg.{n}", kind="function", extras={"root": "core"}))
    g.add_node(Node(id="pkg.m", kind="module", extras={"root": "core"}))
    g.add_edge(Edge(type="calls", source="pkg.E", target="pkg.F"))
    return g


def _handle(op, args=None):
    return Session(_graph()).handle({"op": op, "args": args or {}})


# -- partial ops carry the label ---------------------------------------------

def test_callers_partial():
    env = _handle("callers", {"symbol": "F"})
    assert env["ok"] and env["epistemic"]["epistemic"] == "partial"
    assert "lower bound" in env["epistemic"]["reason"]


def test_callees_impact_flows_call_contract_partial():
    for op, args in [("callees", {"symbol": "E"}),
                     ("impact", {"symbol": "F"}),
                     ("flows", {"symbol": "E"}),
                     ("flows", {}),                 # entry-point listing is call-based too
                     ("call_contract", {"symbol": "F"})]:
        env = _handle(op, args)
        assert env["ok"], (op, env)
        assert env.get("epistemic", {}).get("epistemic") == "partial", op


# -- structural ops do NOT (absence = exact/complete) ------------------------

def test_structural_ops_have_no_label():
    for op, args in [("query", {"name": "E"}),
                     ("communities", {}),
                     ("search", {"term": "E"}),
                     ("stats", {})]:
        assert "epistemic" not in _handle(op, args), op


# -- label survives MCP compaction -------------------------------------------

def test_epistemic_survives_impact_compaction():
    env = {"ok": True, "epistemic": {"epistemic": "partial"},
           "result": {"symbol": "F", "markdown": "…",
                      "impact": [{"refs": [], "by_root": {}}]}}
    assert _compact_impact(env, 40)["epistemic"] == {"epistemic": "partial"}


def test_epistemic_survives_list_cap():
    env = {"ok": True, "epistemic": {"epistemic": "partial"},
           "result": [{"caller": f"c{i}"} for i in range(50)]}
    assert _cap_list(env, 10)["epistemic"] == {"epistemic": "partial"}
