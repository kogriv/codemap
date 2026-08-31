"""MCP adapter — expose the warm serve surface as Model Context Protocol tools.

The `serve` layer is deliberately transport-neutral: ``Session.handle({op, args})``
takes and returns plain dicts. This module is the thin wrapper that maps each op to
one MCP tool, so an MCP client (an AI agent host) can drive codemap directly. No new
logic — every tool just calls ``session.handle`` and returns its envelope
(``{ok, result, resolved?}``), so the caller still sees the ambiguity signal (F14)
and error handling for free.

MCP is an **optional dependency** (`pip install codemap[mcp]`): the import is lazy so
`codemap` works without it; only `codemap serve --mcp` needs it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from codemap.serve.limits import limit_block

if TYPE_CHECKING:
    from codemap.serve.session import Session

_INSTRUCTIONS = (
    "codemap exposes a static code graph of a package. Start with `search` (find "
    "symbols by substring) or `stats` (graph overview), then `query` a symbol for its "
    "dossier. Use `impact`/`callers`/`callees` for blast radius, `review` to turn a "
    "diff into a change-set review, `architecture` for the system shape, `check` to "
    "enforce the [architecture] contract, `diff` for a two-snapshot API breaking-change "
    "report, `communities` "
    "for module subsystems and `flows` for forward call-flow from an entry. `tests` "
    "answers which tests exercise a symbol (and `covers` the inverse) on a repo-scoped "
    "graph. Relational "
    "tools accept a short name or re-export id; when a name is ambiguous the response "
    "carries a `resolved.ambiguous` flag — check it before trusting the answer. "
    "Any tool that takes a `limit` always returns a `limit` block "
    "`{applied, returned, total, truncated}` — read it before concluding a list is "
    "complete; `total: null` means the total was not observable, not that it is zero."
)


def _compact_impact(env: dict, limit: int) -> dict:
    """Shrink an impact envelope for MCP (F22): drop the duplicate markdown and cap
    each entry's flat ref list at ``limit`` — the ``by_root`` counts stay complete.

    R1-C28: the per-entry counts are now emitted on **every** entry, and the envelope
    carries the summed block. The cut is done here, in the transport, so the serve op
    itself has nothing to declare — which is precisely why this layer must.
    """
    if not env.get("ok"):
        return env
    env = dict(env)
    result = dict(env.get("result") or {})
    result.pop("markdown", None)  # structured refs already carry everything
    entries, shown_total, refs_total = [], 0, 0
    for e in result.get("impact", []):
        refs = e.get("refs", [])
        shown = min(limit, len(refs))
        entries.append({**e, "refs": refs[:limit],
                        "refs_shown": shown, "refs_total": len(refs)})
        shown_total += shown
        refs_total += len(refs)
    result["impact"] = entries
    env["result"] = result
    env["limit"] = limit_block(limit, shown_total, refs_total,
                               note="applied per impact entry, not across the answer; "
                                    "the by_root counts are complete regardless")
    return env


def _cap_list(env: dict, limit: int) -> dict:
    """Cap a list-valued result at ``limit`` (F22), declaring the cut either way (R1-C28).

    Was only-on-truncation with its own ``shown``/``total`` vocabulary; both are now the
    shared ``limit`` block, so a client reads one shape across every limited surface.
    """
    if not env.get("ok"):
        return env
    res = env.get("result")
    if not isinstance(res, list):
        return env
    return {**env, "result": res[:limit],
            "limit": limit_block(limit, min(limit, len(res)), len(res))}


def build_mcp_server(session: "Session", name: str = "codemap") -> Any:
    """Build an MCP server exposing the session's ops as tools (lazy mcp import)."""
    try:
        from mcp.server import MCPServer
    except ImportError as exc:  # pragma: no cover - exercised via CLI message
        raise RuntimeError(
            "MCP support requires the optional 'mcp' dependency: "
            "pip install 'codemap[mcp]'"
        ) from exc

    server = MCPServer(name, instructions=_INSTRUCTIONS)

    def op(name: str, args: dict | None = None) -> dict:
        return session.handle({"op": name, "args": args or {}})

    @server.tool()
    def stats() -> dict:
        """Graph overview: target, schema version, node/edge counts by kind/type, and
        `freshness` for the graph ACTUALLY served — `stale: true` (+reason) if the
        on-disk artifact was rebuilt after this server loaded it. Call `reload` then."""
        return op("stats")

    @server.tool()
    def reload() -> dict:
        """Reload the on-disk graph into this server without restarting — pick up an
        external rebuild (e.g. `codemap build --incremental`). Returns before/after
        counts and refreshed freshness. No-op with a reason if started from --build."""
        return op("reload")

    @server.tool()
    def search(term: str, kind: str | None = None, limit: int = 50) -> dict:
        """Find symbols whose id contains `term` (case-insensitive). The discovery
        entry point for a cold agent. Optional `kind`: module|class|function|column.
        The `limit` block reports the true match total — a default page is often a
        small fraction of it, so check `truncated` before concluding a name is rare."""
        return op("search", {"term": term, "kind": kind, "limit": limit})

    @server.tool()
    def query(name: str) -> dict:
        """Full dossier for a symbol name: where defined (file:line) with the declared
        `signature` (a class carries its own `constructor` instead), bases/impls for
        classes, callers/callees/columns for functions, registration recipe, column
        dataflow. The main lookup.

        `signature` is how the symbol is declared; `call_contract` is how it is called
        in fact (posargs / kwargs / splat per call site) — ask that one for the second
        question, not for the first. A missing field means the graph has nothing there,
        never that it was not looked up."""
        return op("query", {"name": name})

    @server.tool()
    def resolve(name: str) -> dict:
        """Resolve a short name / re-export id to the canonical node id, with an
        `ambiguous` flag and `alternatives` when the name maps to several defs."""
        return op("resolve", {"name": name})

    @server.tool()
    def callers(symbol: str) -> dict:
        """Functions that statically call `symbol` (resolved calls only)."""
        return op("callers", {"symbol": symbol})

    @server.tool()
    def callees(symbol: str) -> dict:
        """Internal symbols that `symbol` statically calls."""
        return op("callees", {"symbol": symbol})

    @server.tool()
    def tests(symbol: str, depth: int = 3, cap: int = 25) -> dict:
        """Which tests exercise `symbol` — the NEAREST band of test functions that reach
        it, as runnable pytest node ids. `confidence` is high/medium by distance and
        `unknown` when nothing is found within `depth`: unknown means unknown, never
        "untested". Needs a repo-scoped graph (`--consumer tests --mode full`). Raise
        `depth` above 3 only for low-confidence candidates."""
        return op("tests", {"symbol": symbol, "depth": depth, "cap": cap})

    @server.tool()
    def covers(test: str, depth: int = 3, cap: int = 25) -> dict:
        """The inverse of `tests`: which core symbols this test reaches, by distance.
        Use it to check whether a test exercises what its name claims."""
        return op("covers", {"test": test, "depth": depth, "cap": cap})

    @server.tool()
    def impact(symbol: str, depth: int = 2, limit: int = 40, full: bool = False) -> dict:
        """Blast radius of changing `symbol`: inbound references up to `depth`, counted
        by provenance root (core/tests/docs/…). Compact by default (F22): omits the
        duplicate markdown and caps the flat ref list at `limit` (by_root counts stay
        complete, and every entry carries refs_shown/refs_total). Pass full=true for
        the entire payload including markdown."""
        env = op("impact", {"symbol": symbol, "depth": depth})
        return env if full else _compact_impact(env, limit)

    @server.tool()
    def call_contract(symbol: str, limit: int = 30, full: bool = False) -> dict:
        """Per-caller argument contract of calls into `symbol` (call-sites, posargs,
        kwargs, splat) — for reasoning about a signature change. Capped at `limit`
        entries by default (F22), with the `limit` block giving the true total; pass
        full=true for all of them."""
        env = op("call_contract", {"symbol": symbol})
        return env if full else _cap_list(env, limit)

    @server.tool()
    def implementers(protocol: str) -> dict:
        """Concrete classes that implement `protocol` (registry family)."""
        return op("implementers", {"protocol": protocol})

    @server.tool()
    def family(cls: str) -> dict:
        """The Protocol(s) `cls` satisfies and its sibling implementations."""
        return op("family", {"class": cls})

    @server.tool()
    def families() -> dict:
        """All registry/Protocol families with their registration recipe (decorator +
        key per member) — how to add a new implementation."""
        return op("families")

    @server.tool()
    def column(name: str) -> dict:
        """Producers/consumers of a string-keyed column `name` (dataflow)."""
        return op("column", {"name": name})

    @server.tool()
    def columns_of(symbol: str) -> dict:
        """Which string-key columns a function reads / writes (reverse dataflow)."""
        return op("columns_of", {"symbol": symbol})

    @server.tool()
    def accessors(attribute: str) -> dict:
        """Who reads / writes a class `attribute` (field blast-radius; R1-C20).

        The attribute analog of `column`: `{reads: [funcs], writes: [funcs]}`.
        Lower bound — attribute access is modelled best-effort (self./ClassName./
        construction, and obj.field on the deep tier)."""
        return op("accessors", {"attribute": attribute})

    @server.tool()
    def locate(file: str, line: int | None = None,
               start: int | None = None, end: int | None = None) -> dict:
        """Map a diff location to symbol(s): pass `file` + `line`, or `file` + `start`/
        `end` for a hunk range. Returns the innermost enclosing symbol(s)."""
        if line is not None:
            return op("locate", {"file": file, "line": line})
        return op("locate", {"file": file, "lines": [start, end]})

    @server.tool()
    def review(hunks: list[dict] | None = None, symbols: list[str] | None = None) -> dict:
        """Change-set review: pass `hunks` ([{file, ranges:[[start,end]]}]) and/or
        `symbols`. Returns a risk-sorted dossier per changed symbol + a blast summary."""
        return op("review", {"hunks": hunks, "symbols": symbols})

    @server.tool()
    def architecture() -> dict:
        """Whole-system shape: layers + direction/violations, coupling (Ca/Ce/
        instability), god-objects & call-hubs, import cycles."""
        return op("architecture")

    @server.tool()
    def diff(base: str) -> dict:
        """API diff a baseline graph.json (`base`) → this server's graph. Returns
        {ok, added, removed, changes:[{symbol, kind, severity, detail}], summary} —
        public-API breaking-change detection between two snapshots."""
        return op("diff", {"base": base})

    @server.tool()
    def check(root: str | None = None) -> dict:
        """Architecture-contract gate: does the graph still satisfy the [architecture]
        rules in codemap.toml? Returns {ok, violations:[{rule, summary, edges}]} — the
        'what did I break' check. `root` overrides where codemap.toml is read from."""
        return op("check", {"root": root})

    @server.tool()
    def communities() -> list:
        """Data-driven module subsystems: clusters of modules that import each other
        more than the rest (deterministic greedy modularity), labelled by layer."""
        return op("communities")

    @server.tool()
    def flows(symbol: str | None = None, depth: int = 5) -> dict:
        """Forward call-flow: what calling `symbol` sets in motion (edges by distance,
        the mirror of impact). Omit `symbol` to list entry points with their reach."""
        return op("flows", {"symbol": symbol, "depth": depth})

    @server.tool()
    def source(symbol: str) -> dict:
        """Source span of a symbol: {file, lines, code} (code when readable under the
        server's source-root)."""
        return op("source", {"symbol": symbol})

    @server.tool()
    def report(kind: str) -> dict:
        """Render a markdown report. kind: api-surface | dependencies | dead-code |
        behavior | architecture."""
        return op("report", {"kind": kind})

    @server.tool()
    def semantic_search(query: str, limit: int = 10) -> dict:
        """Concept search → codemap symbols. Routes the natural-language `query` to an
        opt-in semantic-search adapter (cocoindex), then resolves each fuzzy hit to the
        exact codemap symbol at its location — fuzzy retrieval, exact structure. Returns
        {resolver, hits:[{symbol, score, file, lines}]}; empty if no adapter is enabled.
        The adapter applies the limit itself, so a full page comes back with
        `limit.total: null` — unknown, not zero."""
        return op("semantic", {"query": query, "limit": limit})

    @server.tool()
    def pack(budget: int = 2000, seeds: list[str] | None = None) -> dict:
        """Token-budgeted context pack: the most relevant slice of the graph under `budget`
        tokens, ranked by PageRank importance — or by relevance to `seeds` (symbol / file
        ids you're working on). Returns {budget, used_tokens, included, truncated,
        items:[{id, kind, rank, tokens, text}]}, top hubs first."""
        return op("pack", {"budget": budget, "seeds": seeds or []})

    return server


# tool names registered above (kept in sync for tests / introspection)
MCP_TOOLS = (
    "stats", "reload", "search", "query", "resolve", "callers", "callees", "impact",
    "call_contract", "tests", "covers", "implementers", "family", "families",
    "column", "columns_of",
    "accessors",
    "locate", "review", "architecture", "check", "diff", "communities", "flows", "source", "report",
    "semantic_search", "pack",
)
