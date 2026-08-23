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

if TYPE_CHECKING:
    from codemap.serve.session import Session

_INSTRUCTIONS = (
    "codemap exposes a static code graph of a package. Start with `search` (find "
    "symbols by substring) or `stats` (graph overview), then `query` a symbol for its "
    "dossier. Use `impact`/`callers`/`callees` for blast radius, `review` to turn a "
    "diff into a change-set review, `architecture` for the system shape, `check` to "
    "enforce the [architecture] contract, `diff` for a two-snapshot API breaking-change "
    "report, `communities` "
    "for module subsystems and `flows` for forward call-flow from an entry. Relational "
    "tools accept a short name or re-export id; when a name is ambiguous the response "
    "carries a `resolved.ambiguous` flag — check it before trusting the answer."
)


def _compact_impact(env: dict, limit: int) -> dict:
    """Shrink an impact envelope for MCP (F22): drop the duplicate markdown and cap
    each entry's flat ref list at ``limit`` — the ``by_root`` counts stay complete."""
    if not env.get("ok"):
        return env
    env = dict(env)
    result = dict(env.get("result") or {})
    result.pop("markdown", None)  # structured refs already carry everything
    entries = []
    for e in result.get("impact", []):
        e = dict(e)
        refs = e.get("refs", [])
        if len(refs) > limit:
            e = {**e, "refs": refs[:limit],
                 "refs_shown": limit, "refs_total": len(refs)}
        entries.append(e)
    result["impact"] = entries
    env["result"] = result
    return env


def _cap_list(env: dict, limit: int) -> dict:
    """Cap a list-valued result at ``limit`` (F22), noting the total when truncated."""
    if not env.get("ok"):
        return env
    res = env.get("result")
    if isinstance(res, list) and len(res) > limit:
        env = {**env, "result": res[:limit], "shown": limit, "total": len(res)}
    return env


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
        """Graph overview: target, schema version, node/edge counts by kind/type."""
        return op("stats")

    @server.tool()
    def search(term: str, kind: str | None = None, limit: int = 50) -> dict:
        """Find symbols whose id contains `term` (case-insensitive). The discovery
        entry point for a cold agent. Optional `kind`: module|class|function|column."""
        return op("search", {"term": term, "kind": kind, "limit": limit})

    @server.tool()
    def query(name: str) -> dict:
        """Full dossier for a symbol name: where defined (file:line), bases/impls for
        classes, callers/callees/columns for functions, registration recipe, column
        dataflow. The main lookup."""
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
    def impact(symbol: str, depth: int = 2, limit: int = 40, full: bool = False) -> dict:
        """Blast radius of changing `symbol`: inbound references up to `depth`, counted
        by provenance root (core/tests/docs/…). Compact by default (F22): omits the
        duplicate markdown and caps the flat ref list at `limit` (by_root counts stay
        complete). Pass full=true for the entire payload including markdown."""
        env = op("impact", {"symbol": symbol, "depth": depth})
        return env if full else _compact_impact(env, limit)

    @server.tool()
    def call_contract(symbol: str, limit: int = 30, full: bool = False) -> dict:
        """Per-caller argument contract of calls into `symbol` (call-sites, posargs,
        kwargs, splat) — for reasoning about a signature change. Capped at `limit`
        entries by default (F22); pass full=true for all of them."""
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
        {resolver, hits:[{symbol, score, file, lines}]}; empty if no adapter is enabled."""
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
    "stats", "search", "query", "resolve", "callers", "callees", "impact",
    "call_contract", "implementers", "family", "families", "column", "columns_of",
    "accessors",
    "locate", "review", "architecture", "check", "diff", "communities", "flows", "source", "report",
    "semantic_search", "pack",
)
