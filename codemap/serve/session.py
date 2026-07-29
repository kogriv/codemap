"""Warm serve session — graph held in memory, many queries, zero per-call startup.

DESIGN §14.4 (M3.1): the AI-hot path is served by a *resident process* holding the
graph in memory, not by rebuilding on every call. A ``Session`` loads the graph
once and answers request dicts (``{op, args}``) by dispatching to the existing
Serve/Query services — no new logic, just the warm surface.

The protocol is deliberately transport-neutral JSON (``handle`` takes/returns
dicts): ``server.serve_stdio`` wraps it as a line-delimited stdio loop, and a thin
MCP adapter can wrap the same ``handle`` later (each ``op`` maps to one MCP tool).
"""

from __future__ import annotations

from collections import Counter

from codemap.model import SCHEMA_VERSION, Graph
from codemap.query import Query
from codemap.serve.api_surface import render_api_surface
from codemap.serve.audit import render_behavior, render_dead_code, render_dependencies
from codemap.serve.impact import render_impact
from codemap.serve.mermaid import render_mermaid
from codemap.serve.rag import build_chunks
from codemap.serve.vault import build_vault

_REPORTS = {
    "api-surface": lambda q: render_api_surface(q.graph),
    "dependencies": render_dependencies,
    "dead-code": render_dead_code,
    "behavior": render_behavior,
}


def build_query_result(q: Query, name: str) -> dict:
    """The full symbol dossier — shared by ``codemap query`` and warm serve."""
    matches = q.find(name)
    result: dict = {
        "name": name,
        "defined_at": q.where_defined(name),
        "matches": [{"id": n.id, "kind": n.kind} for n in matches],
    }
    modules = [n.id for n in matches if n.kind == "module"]
    if modules:
        result["modules"] = {
            m: {"dependencies": q.dependencies(m), "dependents": q.dependents(m)}
            for m in modules
        }
    classes = [n.id for n in matches if n.kind == "class"]
    if classes:
        result["classes"] = {
            c: {"bases": q.bases(c), "subclasses": q.subclasses(c),
                "implements": q.implements(c), "implementers": q.implementers(c),
                "family": q.family_siblings(c)}
            for c in classes
        }
    funcs = [n.id for n in matches if n.kind == "function"]
    if funcs:
        result["functions"] = {
            f: {"callers": q.callers(f), "callees": q.callees(f)} for f in funcs
        }
    if matches:
        used_by = {}
        for n in matches:
            if n.kind in ("class", "function"):
                by_root: dict[str, int] = {}
                for ref in q.references_to(n.id):
                    by_root[ref["root"]] = by_root.get(ref["root"], 0) + 1
                if by_root:
                    used_by[n.id] = by_root
        if used_by:
            result["used_by"] = used_by
    col = q.column(name)
    if col and (col["writes"] or col["reads"]):
        result["column"] = col
    return result


class Session:
    """A warm, in-memory query surface over one graph."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self.query = Query(graph)

    # -- dispatch ------------------------------------------------------------

    def handle(self, request: dict) -> dict:
        """Route one ``{op, args}`` request to a service; never raises."""
        op = request.get("op")
        args = request.get("args") or {}
        fn = _OPS.get(op)
        if fn is None:
            return {"ok": False, "error": f"unknown op: {op!r}",
                    "ops": sorted(_OPS)}
        try:
            return {"ok": True, "result": fn(self, args)}
        except Exception as exc:  # a bad arg must not kill the resident process
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # -- ops (each takes an args dict) ---------------------------------------

    def _op_ping(self, args) -> str:
        return "pong"

    def _op_stats(self, args) -> dict:
        return {
            "target": self.graph.target,
            "schema": SCHEMA_VERSION,
            "nodes": len(self.graph.nodes),
            "edges": len(self.graph.edges),
            "node_kinds": dict(Counter(n.kind for n in self.graph.nodes.values())),
            "edge_types": dict(Counter(e.type for e in self.graph.edges)),
        }

    def _op_query(self, args) -> dict:
        return build_query_result(self.query, args["name"])

    def _op_impact(self, args) -> dict:
        sym = args["symbol"]
        depth = int(args.get("depth", 2))
        ids = [n.id for n in self.query.find(sym)] or self.query.where_defined(sym)
        return {
            "symbol": sym,
            "impact": [self.query.impact(sid, depth=depth) for sid in ids],
            "markdown": render_impact(self.query, sym, depth=depth),
        }

    def _op_column(self, args) -> dict | None:
        return self.query.column(args["name"])

    def _op_columns(self, args) -> list:
        return self.query.columns()

    def _op_callers(self, args) -> list:
        return self.query.callers(args["symbol"])

    def _op_callees(self, args) -> list:
        return self.query.callees(args["symbol"])

    def _op_implementers(self, args) -> list:
        return self.query.implementers(args["protocol"])

    def _op_family(self, args) -> dict:
        cid = args["class"]
        return {"implements": self.query.implements(cid),
                "siblings": self.query.family_siblings(cid)}

    def _op_call_contract(self, args) -> list:
        return self.query.call_contract(args["symbol"])

    def _op_report(self, args) -> dict:
        kind = args["kind"]
        if kind == "impact":
            return {"kind": kind, "markdown": render_impact(self.query, args["symbol"])}
        renderer = _REPORTS.get(kind)
        if renderer is None:
            raise ValueError(f"unknown report kind: {kind!r}")
        return {"kind": kind, "markdown": renderer(self.query)}

    def _op_export(self, args) -> dict:
        view = args["view"]
        if view == "rag":
            return {"view": view, "chunks": build_chunks(self.query)}
        if view == "mermaid":
            return {"view": view, "diagram": render_mermaid(
                self.query, args.get("mkind", "class"),
                scope=args.get("scope"), root=args.get("root"),
                depth=int(args.get("depth", 2)))}
        if view == "vault":
            return {"view": view, "files": build_vault(self.query)}
        raise ValueError(f"unknown export view: {view!r}")


_OPS = {
    "ping": Session._op_ping,
    "stats": Session._op_stats,
    "query": Session._op_query,
    "impact": Session._op_impact,
    "column": Session._op_column,
    "columns": Session._op_columns,
    "callers": Session._op_callers,
    "callees": Session._op_callees,
    "implementers": Session._op_implementers,
    "family": Session._op_family,
    "call_contract": Session._op_call_contract,
    "report": Session._op_report,
    "export": Session._op_export,
}
