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

import json
from typing import TYPE_CHECKING, Annotated, Any, Literal

from codemap.serve.limits import cap_list as _cap_list, compact_impact as _compact_impact

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
    "Limited answers carry a `limit` block "
    "`{applied, returned, total, truncated}` — read it before concluding a list is "
    "complete; `total: null` means the total was not observable, and "
    "`applied: null` means the result is uncapped. "
    "Every response carries `currency`: `behind` means the source tree changed since the "
    "graph was built, so the answer describes the older tree — say so, or rebuild and "
    "`reload` before relying on it. codemap reads Python only: for other languages and for "
    "needs it does not cover (duplicates, security patterns, DB query counts, …) call "
    "`advise` — the lab's measured and read-only knowledge of other tools, never a guess. "
    "A not-found answer with `outside_graph` names a file codemap does not read."
)




def build_mcp_server(session: "Session", name: str = "codemap") -> Any:
    """Build an MCP server exposing the session's ops as tools (lazy mcp import)."""
    try:
        from mcp.server import MCPServer
        from mcp.types import CallToolResult, TextContent, ToolAnnotations
        from pydantic import Field, ValidationError
        from typing_extensions import NotRequired, TypedDict
    except ImportError as exc:  # pragma: no cover - exercised via CLI message
        raise RuntimeError(
            "MCP support requires the optional 'mcp' dependency: "
            "pip install 'codemap[mcp]'"
        ) from exc

    envelope = TypedDict("CodemapEnvelope", {
        "answer_format": int,
        "ok": bool,
        "outcome": Literal["ok", "error", "not_found", "refused", "verdict"],
        "currency": dict[str, Any],
        "result": NotRequired[Any],
        "error": NotRequired[str],
        "error_kind": NotRequired[str],
        "resolved": NotRequired[dict[str, Any]],
        "limit": NotRequired[dict[str, Any]],
        "epistemic": NotRequired[dict[str, Any]],
        "filter": NotRequired[dict[str, Any]],
        "scope": NotRequired[dict[str, Any]],
    })

    def reply(result: dict) -> CallToolResult:
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))],
            structured_content=result, is_error=not result["ok"],
        )

    class CodemapServer(MCPServer):
        async def call_tool(self, name, arguments, context=None):
            try:
                return await super().call_tool(name, arguments, context)
            except Exception as exc:
                cause = exc.__cause__
                if isinstance(cause, ValidationError) and cause.title == f"{name}Arguments":
                    from codemap.serve.session import request_error
                    return reply(request_error(str(cause)))
                raise

    server = CodemapServer(name, instructions=_INSTRUCTIONS)

    def tool(fn):
        fn.__annotations__["return"] = envelope
        for param in ("limit", "cap", "budget", "depth", "flow_depth"):
            if param in fn.__annotations__:
                minimum = 1 if param == "depth" and fn.__name__ in ("impact", "tests", "covers") else 0
                fn.__annotations__[param] = Annotated[int, Field(ge=minimum, strict=True)]
        return server.tool(annotations=ToolAnnotations(
            read_only_hint=fn.__name__ not in ("reload", "semantic_search"),
            destructive_hint=False if fn.__name__ != "semantic_search" else None,
            idempotent_hint=True if fn.__name__ == "reload" else None,
            open_world_hint=fn.__name__ == "semantic_search",
        ), structured_output=True)(fn)

    def op(name: str, args: dict | None = None) -> CallToolResult:
        return reply(session.handle({"op": name, "args": args or {}}))

    @tool
    def stats() -> dict:
        """Graph overview: target, schema version, node/edge counts by kind/type, and
        `freshness` for the graph ACTUALLY served — `stale: true` (+reason) if the
        on-disk artifact was rebuilt after this server loaded it. Call `reload` then.
        `currency` (also in EVERY answer's envelope) is the content check: `behind` means
        the source tree changed since this graph was built, so answers describe the older
        tree — rebuild, then `reload`."""
        return op("stats")

    @tool
    def reload() -> dict:
        """Reload the on-disk graph into this server without restarting — pick up an
        external rebuild (e.g. `codemap build --incremental`). Returns before/after
        counts and refreshed freshness. No-op with a reason if started from --build."""
        return op("reload")

    @tool
    def search(term: str, kind: str | None = None, limit: int = 50) -> dict:
        """Find symbols whose id contains `term` (case-insensitive). The discovery
        entry point for a cold agent. Optional `kind`: module|class|function|column.
        The `limit` block reports the true match total — a default page is often a
        small fraction of it, so check `truncated` before concluding a name is rare."""
        return op("search", {"term": term, "kind": kind, "limit": limit})

    @tool
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

    @tool
    def resolve(name: str) -> dict:
        """Resolve a short name / re-export id to the canonical node id, with an
        `ambiguous` flag and `alternatives` when the name maps to several defs."""
        return op("resolve", {"name": name})

    @tool
    def callers(symbol: str, min_confidence: str | None = None) -> dict:
        """Functions that statically call `symbol` (resolved calls only).
        `min_confidence` keeps only edges whose route grades at least that strong:
        `exact` (a binding in the source found the target), `inferred` (receiver type
        from Jedi or an annotated constructor field), `heuristic`
        (a name match, e.g. a factory fanned out across a registry family). Omit for
        every resolved edge. `stats` reports the whole graph's grade mix."""
        return op("callers", {"symbol": symbol, "min_confidence": min_confidence})

    @tool
    def callees(symbol: str, min_confidence: str | None = None) -> dict:
        """Internal symbols that `symbol` statically calls. `min_confidence` as in
        `callers`: exact | inferred | heuristic."""
        return op("callees", {"symbol": symbol, "min_confidence": min_confidence})

    @tool
    def tests(symbol: str, depth: int = 3, cap: int = 25, all_bands: bool = False) -> dict:
        """Which tests exercise `symbol` — the NEAREST band of test functions that reach
        it statically, as runnable pytest node ids. A nested helper's container costs no
        hop; a module-level helper costs one. `next_band` counts tests within `depth`
        (null if none); `all_bands=true` lists every band, each row with its distance.
        `confidence` is high/medium by distance and `unknown` when nothing is found within
        `depth`: unknown means unknown, never "untested". Needs a repo-scoped graph
        (`--consumer tests --mode full`). Raise `depth` above 3 only for low-confidence
        candidates."""
        return op("tests", {"symbol": symbol, "depth": depth, "cap": cap,
                            "all_bands": all_bands})

    @tool
    def covers(test: str, depth: int = 3, cap: int = 25) -> dict:
        """The inverse of `tests`: which core symbols this test reaches, by distance.
        Use it to check whether a test exercises what its name claims."""
        return op("covers", {"test": test, "depth": depth, "cap": cap})

    @tool
    def impact(symbol: str, depth: int = 2, limit: int = 40, full: bool = False,
               flow_depth: int = 5) -> dict:
        """Blast radius of changing `symbol`: inbound references up to `depth`, counted
        by provenance root (core/tests/docs/…), plus `flows` — which entry points reach
        it and at which step (`first_step`), within `flow_depth`. Compact by default
        (F22): omits the duplicate markdown and caps each list at `limit` (by_root counts
        stay complete; entries carry refs_shown/refs_total and flows_shown/flows_total).
        Flows follow resolved `calls` edges only: `non_call_refs` says how many
        references cannot appear there, `beyond_depth` how many entries reach further,
        and `in_call_graph: false` means the call layer never modelled the symbol — not
        that no flow reaches it. Pass full=true for the entire payload with markdown."""
        return op("impact", {"symbol": symbol, "depth": depth, "flow_depth": flow_depth,
                             "limit": limit, "full": full})

    @tool
    def call_contract(symbol: str, limit: int = 30, full: bool = False) -> dict:
        """Per-caller argument contract of calls into `symbol` (call-sites, posargs,
        kwargs, splat) — for reasoning about a signature change. Capped at `limit`
        entries by default (F22), with the `limit` block giving the true total; pass
        full=true for all of them."""
        return op("call_contract", {"symbol": symbol, "limit": limit, "full": full})

    @tool
    def implementers(protocol: str) -> dict:
        """Concrete classes that implement `protocol` (registry family)."""
        return op("implementers", {"protocol": protocol})

    @tool
    def family(cls: str) -> dict:
        """The Protocol(s) `cls` satisfies and its sibling implementations."""
        return op("family", {"class": cls})

    @tool
    def families() -> dict:
        """All registry/Protocol families with their registration recipe (decorator +
        key per member) — how to add a new implementation."""
        return op("families")

    @tool
    def column(name: str) -> dict:
        """Producers/consumers of a string-keyed column `name` (dataflow)."""
        return op("column", {"name": name})

    @tool
    def columns_of(symbol: str) -> dict:
        """Which string-key columns a function reads / writes (reverse dataflow)."""
        return op("columns_of", {"symbol": symbol})

    @tool
    def accessors(attribute: str) -> dict:
        """Who reads / writes a class `attribute` (field blast-radius; R1-C20).

        The attribute analog of `column`: `{reads: [funcs], writes: [funcs]}`.
        Lower bound — attribute access is modelled best-effort (self./ClassName./
        construction, and obj.field on the deep tier)."""
        return op("accessors", {"attribute": attribute})

    @tool
    def locate(file: str, line: int | None = None,
               start: int | None = None, end: int | None = None) -> dict:
        """Map a diff location to symbol(s): pass `file` + `line`, or `file` + `start`/
        `end` for a hunk range. Returns the innermost enclosing symbol(s)."""
        args = {"file": file}
        if line is not None:
            args["line"] = line
        if start is not None or end is not None:
            args["lines"] = [start, end]
        return op("locate", args)

    @tool
    def review(hunks: list[dict] | None = None, symbols: list[str] | None = None) -> dict:
        """Change-set review: pass `hunks` ([{file, ranges:[[start,end]]}]) and/or
        `symbols`. Returns a risk-sorted dossier per changed symbol + a blast summary."""
        return op("review", {"hunks": hunks, "symbols": symbols})

    @tool
    def architecture() -> dict:
        """Whole-system shape: layers + direction/violations, coupling (Ca/Ce/
        instability), god-objects & call-hubs, import cycles."""
        return op("architecture")

    @tool
    def diff(base: str) -> dict:
        """API diff a baseline graph.json (`base`) → this server's graph. Returns
        {ok, added, removed, changes:[{symbol, kind, severity, detail}], summary} —
        public-API breaking-change detection between two snapshots."""
        return op("diff", {"base": base})

    @tool
    def check(root: str | None = None, require_contract: bool = False,
              require_current: bool = False) -> dict:
        """Architecture-contract gate: does the graph still satisfy the [architecture]
        rules in codemap.toml? Returns {ok, violations:[{rule, summary, edges}]} — the
        'what did I break' check. `root` overrides where codemap.toml is read from.
        Set `require_contract` and `require_current` for a strict gate."""
        return op("check", {"root": root, "require_contract": require_contract,
                            "require_current": require_current})

    @tool
    def communities() -> list:
        """Data-driven module subsystems: clusters of modules that import each other
        more than the rest (deterministic greedy modularity), labelled by layer."""
        return op("communities")

    @tool
    def flows(symbol: str | None = None, depth: int = 5) -> dict:
        """Forward call-flow: what calling `symbol` sets in motion (edges by distance,
        the mirror of impact). Omit `symbol` to list entry points with their reach."""
        return op("flows", {"symbol": symbol, "depth": depth})

    @tool
    def source(symbol: str) -> dict:
        """Source span of a symbol. Code is returned when the file under source-root
        matches the served snapshot; otherwise read the status and recorded coordinates."""
        return op("source", {"symbol": symbol})

    @tool
    def report(kind: str) -> dict:
        """Render a markdown report. kind: api-surface | dependencies | dead-code |
        behavior | architecture."""
        return op("report", {"kind": kind})

    @tool
    def semantic_search(query: str, limit: int = 10) -> dict:
        """Concept search → codemap symbols. Routes the natural-language `query` to an
        opt-in semantic-search adapter (cocoindex), then resolves each fuzzy hit to the
        exact codemap symbol at its location — fuzzy retrieval, exact structure. Returns
        {resolver, hits:[{symbol, score, file, lines}]}; empty if no adapter is enabled.
        The adapter applies the limit itself, so a full page comes back with
        `limit.total: null` — unknown, not zero."""
        return op("semantic", {"query": query, "limit": limit})

    @tool
    def pack(budget: int = 2000, seeds: list[str] | None = None,
             direction: str | None = None) -> dict:
        """Token-budgeted context pack: the highest-ranked modules, classes and functions
        under `budget` estimated tokens (~4 characters each, not a model tokenizer — leave
        headroom), by PageRank importance — or by relevance to `seeds` (symbol
        / file ids you're working on). Returns {budget, used_tokens, included, truncated,
        items:[{id, kind, rank, tokens, text}], seeds, unreachable_from_seeds, coverage},
        top hubs first. With seeds the walk runs both ways by default — what the seeds use
        and what uses them (their callers, tests); `direction="uses"` keeps only what they
        use. `coverage.walk` names the walk taken; `direction` without seeds is an error.
        Read `seeds.unresolved` and each seed's `ambiguous`;
        if no seed resolves the answer is {error, seeds, coverage} — a refusal, not a
        global pack. `coverage.never_in_pack` counts node kinds (docs, attributes,
        columns) that can never appear."""
        args = {"budget": budget, "seeds": seeds or []}
        if direction is not None:
            args["direction"] = direction
        return op("pack", args)

    @tool
    def advise(need: str | None = None, languages: list[str] | None = None,
               tool: str | None = None, news_days: int | None = None) -> dict:
        """What to use for a need codemap does not cover (other languages, duplicates,
        security patterns, complexity, DB query counts, …), from the codemap lab's
        catalog. `need`: an id or free words ("ts call graph"); omit for the overview of
        every need with codemap's own coverage. `languages` filters; `tool` gives one tool's
        claims and news; `news_days` adds the feed. Every claim has a status: `measured`
        (scored against the lab's truth; evidence URL), `probed` (run, not scored), `read`
        (known from docs only — say so when you rely on it), `rejected`. `stale` and `drift`
        mean the claim may be out of date. With `languages` (or a language named in `need`),
        the answer starts with the lab's `recipe` for that language where one exists: per
        audit axis, what to use, what a lab tool adds, what to avoid, with evidence.
        Read `catalog.as_of`; `codemap advise --refresh`
        fetches the current catalog. Nothing here installs or runs a tool: check a claim
        with its `probe` on your own tree first."""
        return op("advise", {"need": need, "languages": languages, "tool": tool,
                             "news_days": news_days})

    return server


# tool names registered above (kept in sync for tests / introspection)
MCP_TOOLS = (
    "stats", "reload", "search", "query", "resolve", "callers", "callees", "impact",
    "call_contract", "tests", "covers", "implementers", "family", "families",
    "column", "columns_of",
    "accessors",
    "locate", "review", "architecture", "check", "diff", "communities", "flows", "source", "report",
    "semantic_search", "pack", "advise",
)
