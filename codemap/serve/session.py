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
from codemap.serve.architecture import build_architecture, render_architecture
from codemap.serve.audit import render_behavior, render_dead_code, render_dependencies
from codemap.serve.impact import render_impact
from codemap.serve.limits import limit_block
from codemap.serve.mermaid import render_mermaid
from codemap.serve.rag import build_chunks
from codemap.serve.review import build_review, render_review
from codemap.serve.vault import build_vault

_REPORTS = {
    "api-surface": lambda q: render_api_surface(q.graph),
    "dependencies": render_dependencies,
    "dead-code": render_dead_code,
    "behavior": render_behavior,
    "architecture": render_architecture,
}

# R1-C13: ops whose answer leans on the partial static call graph (Python call
# resolution is incomplete — gaps/ CM-09) → the answer is a lower bound. We stamp
# them with a machine-readable epistemic label (the structured twin of the prose
# disclaimers). Absence of the label = structural/complete (imports, contains,
# inherits, exports — exact). One label per answer (no per-edge confidence: edges
# already carry `resolution`). From the GitNexus разбор, built natively.
_PARTIAL_OPS = frozenset({"callers", "callees", "impact", "flows", "call_contract",
                          "tests", "covers"})
_EPISTEMIC_PARTIAL = {
    "epistemic": "partial",
    "reason": "leans on static call resolution (partial for Python) — a lower "
              "bound; pair with grep/tests before acting.",
}

# R1-C28: ops that cut a computed answer down to a limit. Orthogonal to _PARTIAL_OPS
# — that one is about how well calls *resolve*; this one is about how much of the
# resolved answer survived. An answer can be both, and the two say different things.
# Each of these sets ``self._limit`` (see `limits.limit_block`); `handle` lifts it into
# the envelope, always — including when nothing was cut.
_LIMITED_OPS = frozenset({"search", "semantic", "tests", "covers"})

# Ops bounded by something that is *not* a cut of a computed list. Written down rather
# than left implicit so the guard test can tell "exempt, deliberately" from "forgotten"
# — the rule outlives this fix only if something enforces it.
_UNLIMITED_BY_DESIGN = {
    "pack": "budget is a token budget the caller sets on purpose, and the result is "
            "explicitly a *pack* — self-describing by construction",
    "impact": "depth bounds the walk, it does not slice a computed list; the reach is "
              "already echoed back as by_distance / max_distance",
    "flows": "depth likewise bounds the walk, and the answer carries its own depth",
}


def _match(q: Query, n) -> dict:
    """One entry of the ``matches`` list: where the symbol is, and how it is declared.

    R1-C33. The question after "where is it" is "how is it called", and the declared
    signature was already on the node — asking ``call_contract`` for it was a second
    round-trip for something the graph carried all along. Fields that would say nothing
    are omitted rather than emitted as ``null``: a caller can tell "no signature here"
    from "a signature we did not look up" only if the absent case is absent.

    Note the two are different questions and keep different names. ``signature`` is how
    the symbol is *declared*; ``call_contract`` answers how it is *called in fact*
    (posargs / kwargs / splat per call site), which no node field can know.
    """
    e = {"id": n.id, "kind": n.kind, "file": n.file, "lines": [n.lineno, n.endlineno]}
    if n.signature:
        e["signature"] = n.signature
    elif n.kind == "class":
        # A class has no signature of its own in the model (only functions get one).
        # Its constructor answers what a caller standing on the class actually wants,
        # so it travels under its own name — never dressed up as the class's signature.
        # Only the class's *own* __init__: an inherited one is not resolved here, and
        # for that case saying nothing is the honest answer (unknown != none).
        init = q.graph.nodes.get(f"{n.id}.__init__")
        if init is not None and init.signature:
            e["constructor"] = init.signature
    if n.is_deprecated:
        e["deprecated"] = True
    return e


def tool_drift(running: str | None, installed: str | None) -> dict | None:
    """Say when this process is running code the installed distribution has moved past.

    R1-C38. A warm server holds two things that go stale independently: the graph and the
    **code**. `reload` refreshes the graph, and nothing refreshes the code — a process
    started before an upgrade keeps answering in the shape it was born with, over a graph
    that carries everything the new shape needs. Measured, not imagined: a server started
    before R1-C33 served a freshly rebuilt 0.13 graph and returned dossiers without the
    `signature` the artifact contained, with nothing in the answer to say why.

    `stats` already separates the graph's schema from the running tool's. This is the same
    separation one level up, and it is only visible because the version is read from the
    installed metadata at call time while the code was loaded at import.
    """
    if not running or not installed or running == installed:
        return None
    return {
        "code": "tool_restart_needed",
        "severity": "warning",
        "running": running,
        "installed": installed,
        "consequence": "Answers keep the shape of the running code; `reload` refreshes the "
                       "graph, never the code.",
        "message": f"this server is running codemap {running} while {installed} is installed — "
                   "restart it to serve the installed version.",
    }


def build_query_result(q: Query, name: str) -> dict:
    """The full symbol dossier — shared by ``codemap query`` and warm serve."""
    matches = q.find(name)
    result: dict = {
        "name": name,
        "defined_at": q.where_defined(name),
        # F12: carry file:line so an agent can jump to source; the id here is the
        # canonical node (not a re-export), so it also chains into relational ops.
        "matches": [_match(q, n) for n in matches],
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
                "columns": _nonempty(q.columns_of(f)),
                # R1-C4: per-symbol complexity (cc / mi / volume / sloc), when known.
                "complexity": q.graph.nodes[f].extras.get("complexity")}
            for f in funcs
        }
    attrs = [n.id for n in matches if n.kind == "attribute"]
    if attrs:
        # R1-C20: standing on a field, who reads/writes it (accesses edges, issue #1).
        accessed = {
            a: acc for a in attrs
            if (acc := _nonempty({"reads": q.readers(a), "writes": q.writers(a)}))
        }
        if accessed:
            result["attributes"] = accessed
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

    def __init__(self, graph: Graph, source_root: str | None = None,
                 graph_path: str | None = None) -> None:
        self.graph = graph
        self.query = Query(graph)
        # F12: base dir to resolve node.file for the `source` op (node paths are
        # repo-relative, e.g. `bquant/…`). Defaults to cwd; best-effort.
        self.source_root = source_root
        # M18: path of the loaded graph file, if any — lets `stats` report the map's
        # age so a caller knows it may be stale. None for an in-memory graph.
        self.graph_path = graph_path
        # #3: the mtime of the artifact WHEN WE LOADED IT — so `stats` describes the
        # graph actually being served, not the file on disk (which may have been
        # rebuilt out from under a long-lived server). None for an in-memory graph.
        self._served_mtime = self._current_mtime()
        # R1-C28: the limit block of the op currently being handled (set by the op,
        # lifted into the envelope by `handle`) — same one-shot channel as _resolution.
        self._limit: dict | None = None

    def _current_mtime(self) -> float | None:
        import os
        if not self.graph_path:
            return None
        try:
            return os.path.getmtime(self.graph_path)
        except OSError:
            return None

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

        When the op accepts a limit, the envelope carries a ``limit`` block (R1-C28)
        **whether or not anything was cut** — see ``serve/limits.py`` for why the
        only-on-truncation variant is not honest enough.
        """
        op = request.get("op")
        args = request.get("args") or {}
        fn = _OPS.get(op)
        if fn is None:
            return {"ok": False, "error": f"unknown op: {op!r}",
                    "ops": sorted(_OPS)}
        self._resolution = None
        self._limit = None
        try:
            env = {"ok": True, "result": fn(self, args)}
        except Exception as exc:  # a bad arg must not kill the resident process
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        r = self._resolution
        if r and (r["ambiguous"] or r["input"] != r["id"]):
            env["resolved"] = r
        if op in _PARTIAL_OPS:  # R1-C13: machine-readable "this is a lower bound"
            env["epistemic"] = _EPISTEMIC_PARTIAL
        if self._limit is not None:  # R1-C28: how much of the answer survived the cut
            env["limit"] = self._limit
        return env

    # -- ops (each takes an args dict) ---------------------------------------

    def _op_ping(self, args) -> str:
        return "pong"

    def _op_stats(self, args) -> dict:
        out = {
            "target": self.graph.target,
            # R1-C25: two different facts that used to share one field. `schema` was the
            # *running tool's* version reported over a graph that might declare another.
            "schema": self.graph.loaded_schema or SCHEMA_VERSION,
            "tool_schema": SCHEMA_VERSION,
            "provenance": self.graph.provenance or None,
            "nodes": len(self.graph.nodes),
            "edges": len(self.graph.edges),
            "node_kinds": dict(Counter(n.kind for n in self.graph.nodes.values())),
            "edge_types": dict(Counter(e.type for e in self.graph.edges)),
        }
        # M18 + #3: age of the graph WE SERVE (not the on-disk file), with an explicit
        # stale flag when the artifact was rebuilt after we loaded it.
        from codemap.freshness import freshness
        fr = freshness(self.graph_path, served_mtime=self._served_mtime)
        if fr is not None:
            out["freshness"] = fr
        # R1-C21: same spirit as freshness — say when the graph may be *vacuous* (0 import
        # edges from a layout the extractor didn't understand), rather than letting every
        # downstream conclusion silently inherit the emptiness.
        from codemap.diagnostics import diagnostics
        diags = list(diagnostics(self.graph))
        # R1-C38: the graph is not the only thing that goes stale in a warm server.
        drift = self._tool_drift()
        if drift:
            diags.append(drift)
        if diags:
            out["diagnostics"] = diags
        return out

    @staticmethod
    def _tool_drift() -> dict | None:
        import codemap
        from codemap.provenance import tool_version
        return tool_drift(getattr(codemap, "__version__", None), tool_version())

    def _op_reload(self, args) -> dict:
        """Reload the on-disk artifact into the served graph, without a restart (#3).

        Picks up an external rebuild (e.g. ``codemap build --incremental``) so the
        server stops answering from its startup snapshot. Returns what changed and the
        refreshed freshness. A no-op-with-reason when the server has no on-disk graph
        (started from ``--build``) — restart to refresh those.
        """
        from codemap.freshness import freshness
        from codemap import store
        if not self.graph_path:
            return {"reloaded": False,
                    "reason": "server was started from an in-memory build; "
                              "restart to refresh"}
        before = {"nodes": len(self.graph.nodes), "edges": len(self.graph.edges)}
        try:
            graph = store.load(self.graph_path)
        except (OSError, ValueError) as exc:
            return {"reloaded": False,
                    "reason": f"could not read {self.graph_path}: "
                              f"{type(exc).__name__}: {exc}"}
        self.graph = graph
        self.query = Query(graph)
        self._served_mtime = self._current_mtime()
        after = {"nodes": len(graph.nodes), "edges": len(graph.edges)}
        out = {"reloaded": True, "before": before, "after": after,
               "changed": before != after,
               "freshness": freshness(self.graph_path,
                                      served_mtime=self._served_mtime)}
        # R1-C38: this is the op whose name promises freshness, so it is the op that owes
        # the caller the half it cannot deliver — the code, which only a restart replaces.
        drift = self._tool_drift()
        if drift:
            out["diagnostics"] = [drift]
        return out

    def _op_query(self, args) -> dict:
        return build_query_result(self.query, args["name"])

    def _op_impact(self, args) -> dict:
        sym = args["symbol"]
        depth = int(args.get("depth", 2))
        ids = self.query.impact_targets(sym)  # F23: accept full id / re-export too
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
        # R1-C28: count the whole match set, then slice — this op is the *discovery*
        # entry point (F9), the one an agent uses precisely because it does not yet
        # know what exists, so a silent 50-of-1259 is the worst place to be quiet.
        # The full list is already materialised inside `search`; counting is free.
        limit = int(args.get("limit", 50))
        hits = self.query.search(args["term"], kind=args.get("kind"), limit=None)
        self._limit = limit_block(limit, min(limit, len(hits)), len(hits))
        return hits[:limit]

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

    def _op_accessors(self, args) -> dict:
        # R1-C20: who reads/writes a class attribute (accesses edges, issue #1).
        aid = self._canon(args["attribute"])
        return {"reads": self.query.readers(aid), "writes": self.query.writers(aid)}

    def _op_tests(self, args) -> dict:
        """R1-C24: which tests exercise a symbol, nearest band first, honestly labelled."""
        cap = int(args.get("cap", 25))
        res = self.query.tests_for(
            self._canon(args["symbol"]), depth=int(args.get("depth", 3)), cap=cap)
        # These two already say it in their own body (`total_at_distance` + a caveat
        # line). The envelope block is added anyway: a machine consumer should read one
        # vocabulary across every limited op, not learn a per-op dialect.
        self._limit = limit_block(cap, len(res["tests"]), res["total_at_distance"])
        return res

    def _op_covers(self, args) -> dict:
        """The inverse — what a test actually reaches (same index, read forward)."""
        cap = int(args.get("cap", 25))
        res = self.query.covers(
            self._canon(args["test"]), depth=int(args.get("depth", 3)), cap=cap)
        self._limit = limit_block(cap, len(res["symbols"]), res["total"])
        return res

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

    def _op_architecture(self, args) -> dict:
        """F21: whole-system shape — cycles + layers + coupling + hotspots."""
        return build_architecture(self.query)

    def _op_diff(self, args) -> dict:
        """R1-C5: API diff a baseline graph → this session's graph.

        ``base`` is the path to the 'before' graph.json; the session graph is the
        'after'. Returns {ok, added, removed, changes, summary} — breaking-change
        classification on the public API surface.
        """
        from codemap import store
        from codemap.serve.apidiff import build_apidiff
        base_path = args.get("base")
        if not base_path:
            return {"error": "diff needs args.base = path to the baseline graph.json"}
        return build_apidiff(store.load(base_path), self.graph)

    def _op_check(self, args) -> dict:
        """R1-C3: evaluate the [architecture] contract → {ok, violations}.

        The 'what did I break' surface: an agent (or CI) asks whether the current
        graph still satisfies the declared architecture. The contract is read from
        codemap.toml under ``root`` (arg, else ``source_root``, else cwd).
        """
        from codemap.arch import check_contract, load_contract
        from codemap.serve.check import build_check
        root = args.get("root") or self.source_root or "."
        contract = load_contract(root)
        return build_check(self.query, contract, check_contract(self.query, contract))

    def _op_communities(self, args) -> list:
        """R1-C18: data-driven module subsystems (greedy modularity)."""
        return self.query.communities()

    def _op_flows(self, args) -> dict:
        """R1-C18: forward call-flow from a symbol, or entry points if none given."""
        sym = args.get("symbol")
        if not sym:
            return {"entry_points": self.query.entry_points()}
        return self.query.flow(self._canon(sym), max_depth=int(args.get("depth", 5)))

    def _op_semantic(self, args) -> dict:
        """R1-C16: semantic search via an opt-in adapter, enriched to codemap symbols.

        Resolves an ADAPTER providing ``semantic-search`` (opt-in via codemap.toml +
        installed), asks it for fuzzy hits, and resolves each to the exact symbol via
        the graph. ``root`` (arg, else ``source_root``, else cwd) is both the repo the
        tool's index lives in and where file paths resolve. No adapter → empty hits.
        """
        from codemap.serve.semantic import semantic_search
        root = args.get("root") or self.source_root or "."
        res = semantic_search(self.query, args["query"], root=root,
                              limit=int(args.get("limit", 10)))
        # R1-C28: here the cut happens *upstream*, inside the adapter, so the pre-limit
        # total is genuinely unobservable when it returns a full page — `total: null` is
        # the true answer, and it is stated rather than omitted.
        self._limit = res.pop("limit")
        return res

    def _op_pack(self, args) -> dict:
        """R1-C6: token-budgeted context pack — most relevant graph slice under N tokens."""
        from codemap.serve.pack import build_pack
        return build_pack(self.query, budget=int(args.get("budget", 2000)),
                          seeds=tuple(args.get("seeds") or ()))

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
            return {"kind": kind, "markdown": render_impact(
                self.query, args["symbol"], depth=int(args.get("depth", 2)))}
        if kind == "dead-code":  # R1-C8: confidence + whitelist from [dead_code]
            from codemap.serve.audit import load_dead_code_whitelist
            wl, wl_error = load_dead_code_whitelist(args.get("root") or self.source_root)
            return {"kind": kind, "markdown": render_dead_code(
                self.query, whitelist=wl, min_confidence=args.get("min_confidence"),
                whitelist_error=wl_error)}
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
        if view == "docs":
            from codemap.serve.livingdocs import render_docs
            return {"view": view, "markdown": render_docs(self.query)}
        raise ValueError(f"unknown export view: {view!r}")


_OPS = {
    "ping": Session._op_ping,
    "stats": Session._op_stats,
    "reload": Session._op_reload,
    "query": Session._op_query,
    "impact": Session._op_impact,
    "resolve": Session._op_resolve,
    "search": Session._op_search,
    "families": Session._op_families,
    "column": Session._op_column,
    "columns": Session._op_columns,
    "columns_of": Session._op_columns_of,
    "accessors": Session._op_accessors,
    "tests": Session._op_tests,
    "covers": Session._op_covers,
    "callers": Session._op_callers,
    "callees": Session._op_callees,
    "implementers": Session._op_implementers,
    "family": Session._op_family,
    "call_contract": Session._op_call_contract,
    "locate": Session._op_locate,
    "review": Session._op_review,
    "architecture": Session._op_architecture,
    "check": Session._op_check,
    "diff": Session._op_diff,
    "communities": Session._op_communities,
    "flows": Session._op_flows,
    "semantic": Session._op_semantic,
    "pack": Session._op_pack,
    "source": Session._op_source,
    "report": Session._op_report,
    "export": Session._op_export,
}
