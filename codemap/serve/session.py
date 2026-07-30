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
from codemap.serve.review import build_review, render_review
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
        # F12: carry file:line so an agent can jump to source; the id here is the
        # canonical node (not a re-export), so it also chains into relational ops.
        "matches": [{"id": n.id, "kind": n.kind, "file": n.file,
                     "lines": [n.lineno, n.endlineno]} for n in matches],
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
                "family": q.family_siblings(c),
                # F10: how to register a sibling — the extension recipe.
                "registered_as": q.graph.nodes[c].extras.get("registry")}
            for c in classes
        }
    funcs = [n.id for n in matches if n.kind == "function"]
    if funcs:
        result["functions"] = {
            f: {"callers": q.callers(f), "callees": q.callees(f),
                # F11: which columns this function reads/writes (reverse dataflow).
                "columns": _nonempty(q.columns_of(f))}
            for f in funcs
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


def _nonempty(d: dict) -> dict | None:
    """Drop a reads/writes dict that has nothing on either side."""
    return d if (d.get("reads") or d.get("writes")) else None


class Session:
    """A warm, in-memory query surface over one graph."""

    def __init__(self, graph: Graph, source_root: str | None = None) -> None:
        self.graph = graph
        self.query = Query(graph)
        # F12: base dir to resolve node.file for the `source` op (node paths are
        # repo-relative, e.g. `bquant/…`). Defaults to cwd; best-effort.
        self.source_root = source_root

    def _canon(self, name_or_id: str) -> str:
        """Resolve a name / re-export id to the canonical node id (F13).

        Records the resolution (F14) so ``handle`` can surface an ``ambiguous``
        warning when a bare short name resolved to one of many defs arbitrarily.
        """
        info = self.query.canonical_info(name_or_id)
        self._resolution = info
        return info["id"] if info else name_or_id

    # -- dispatch ------------------------------------------------------------

    def handle(self, request: dict) -> dict:
        """Route one ``{op, args}`` request to a service; never raises.

        When an op resolved its input through ``_canon`` and that resolution either
        was **ambiguous** (M14/F14 — arbitrary pick among equals) or rewrote the
        input (F13 — re-export → canonical), the envelope carries a ``resolved``
        block so a caller never acts on a silently-wrong symbol.
        """
        op = request.get("op")
        args = request.get("args") or {}
        fn = _OPS.get(op)
        if fn is None:
            return {"ok": False, "error": f"unknown op: {op!r}",
                    "ops": sorted(_OPS)}
        self._resolution = None
        try:
            env = {"ok": True, "result": fn(self, args)}
        except Exception as exc:  # a bad arg must not kill the resident process
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        r = self._resolution
        if r and (r["ambiguous"] or r["input"] != r["id"]):
            env["resolved"] = r
        return env

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

    def _op_resolve(self, args) -> dict | None:
        # F14: full resolution — {input, id, ambiguous, alternatives} — so a cold
        # agent can check for ambiguity before chaining into a relational op.
        return self.query.canonical_info(args["name"])

    def _op_search(self, args) -> list:
        return self.query.search(args["term"], kind=args.get("kind"),
                                 limit=int(args.get("limit", 50)))

    def _op_families(self, args) -> list:
        return self.query.families()

    def _op_column(self, args) -> dict | None:
        return self.query.column(args["name"])

    def _op_columns(self, args) -> list:
        # F15: default to subscript-accessed keys (the real column-like set);
        # pass all=true for the full over-set incl. dict-literal payload keys.
        return self.query.columns(subscripted_only=not args.get("all", False))

    def _op_columns_of(self, args) -> dict:
        return self.query.columns_of(self._canon(args["symbol"]))

    def _op_callers(self, args) -> list:
        return self.query.callers(self._canon(args["symbol"]))

    def _op_callees(self, args) -> list:
        return self.query.callees(self._canon(args["symbol"]))

    def _op_implementers(self, args) -> list:
        return self.query.implementers(self._canon(args["protocol"]))

    def _op_family(self, args) -> dict:
        cid = self._canon(args["class"])
        return {"implements": self.query.implements(cid),
                "siblings": self.query.family_siblings(cid)}

    def _op_call_contract(self, args) -> list:
        return self.query.call_contract(self._canon(args["symbol"]))

    def _op_locate(self, args) -> dict:
        """F16: (file, line) or (file, lines:[start,end]) → containing symbol(s)."""
        file = args["file"]
        if "line" in args:
            return {"file": file, "line": int(args["line"]),
                    "symbol": self.query.symbol_at(file, int(args["line"]))}
        lo, hi = args["lines"]
        return {"file": file, "lines": [int(lo), int(hi)],
                "symbols": self.query.symbols_in_range(file, int(lo), int(hi))}

    def _op_review(self, args) -> dict:
        """F17: change-set review from diff hunks and/or explicit symbols."""
        return build_review(self.query, hunks=args.get("hunks"),
                            symbols=args.get("symbols"))

    def _op_source(self, args) -> dict:
        """Return the source span of a symbol (F12): {file, lines, code?}.

        ``code`` is included when the file is readable under ``source_root`` (or
        cwd); otherwise only the location is returned so the caller can read it.
        """
        from pathlib import Path
        cid = self._canon(args["symbol"])
        node = self.graph.nodes.get(cid)
        if node is None:
            return {"error": f"unknown symbol: {args['symbol']!r}"}
        loc = {"id": cid, "file": node.file, "lines": [node.lineno, node.endlineno]}
        if not node.file or node.lineno is None:
            return {**loc, "code": None, "note": "no location (overlay node)"}
        base = Path(self.source_root) if self.source_root else Path(".")
        path = base / node.file
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            loc["code"] = "\n".join(lines[node.lineno - 1:(node.endlineno or node.lineno)])
        except OSError:
            loc["code"] = None
            loc["note"] = f"source unreadable at {path} — set source_root"
        return loc

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
    "resolve": Session._op_resolve,
    "search": Session._op_search,
    "families": Session._op_families,
    "column": Session._op_column,
    "columns": Session._op_columns,
    "columns_of": Session._op_columns_of,
    "callers": Session._op_callers,
    "callees": Session._op_callees,
    "implementers": Session._op_implementers,
    "family": Session._op_family,
    "call_contract": Session._op_call_contract,
    "locate": Session._op_locate,
    "review": Session._op_review,
    "source": Session._op_source,
    "report": Session._op_report,
    "export": Session._op_export,
}
