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
    "diff into a change-set review, `architecture` for the system shape. Relational "
    "tools accept a short name or re-export id; when a name is ambiguous the response "
    "carries a `resolved.ambiguous` flag — check it before trusting the answer."
)


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
    def impact(symbol: str, depth: int = 2) -> dict:
        """Blast radius of changing `symbol`: inbound references up to `depth`, counted
        by provenance root (core/tests/docs/…), plus a markdown summary."""
        return op("impact", {"symbol": symbol, "depth": depth})

    @server.tool()
    def call_contract(symbol: str) -> dict:
        """Per-caller argument contract of calls into `symbol` (call-sites, posargs,
        kwargs, splat) — for reasoning about a signature change."""
        return op("call_contract", {"symbol": symbol})

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
    def source(symbol: str) -> dict:
        """Source span of a symbol: {file, lines, code} (code when readable under the
        server's source-root)."""
        return op("source", {"symbol": symbol})

    @server.tool()
    def report(kind: str) -> dict:
        """Render a markdown report. kind: api-surface | dependencies | dead-code |
        behavior | architecture."""
        return op("report", {"kind": kind})

    return server


# tool names registered above (kept in sync for tests / introspection)
MCP_TOOLS = (
    "stats", "search", "query", "resolve", "callers", "callees", "impact",
    "call_contract", "implementers", "family", "families", "column", "columns_of",
    "locate", "review", "architecture", "source", "report",
)
