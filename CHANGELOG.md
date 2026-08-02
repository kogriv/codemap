# Changelog

All notable changes to codemap. Format loosely follows [Keep a Changelog](https://keepachangelog.com);
the graph JSON has its own `SCHEMA_VERSION` (`codemap/model.py`), noted per entry.

## [Unreleased]

Extracted into a standalone repository from its incubation home (the `bquant` monorepo), preserving the
full M0–M16 development history; since extraction it has grown the MCP adapter (M17), graph freshness
(M18), SCIP export (R1-C1) and the research track (R1). Graph schema **0.9**; **152 tests** (+1 SCIP-CLI
check when the `scip` binary is present); warm serve surface with 21 ops, an MCP adapter, and SCIP export.

### Milestones

- **R1-C1 — SCIP export** (no schema change): `codemap export scip -o index.scip` emits a
  [SCIP](https://scip-code.org/) index so Sourcegraph, Glean and any SCIP consumer light up
  go-to-definition, symbol search and type hierarchy over codemap's graph. Highest-value interop move
  from the R1 landscape. **Honest scope:** codemap's graph is symbol-level (no call-site coordinates),
  so the export is *definitions + SymbolInformation* — one Definition occurrence per located node, kind,
  docstring, and `inherits`/`implements` as SCIP `relationships` (`is_implementation`); reference
  occurrences (find-references) are deliberately omitted rather than faked. Symbol strings are built from
  codemap's canonical ids via the SCIP descriptor grammar (namespace `/`, type `#`, method `().`, term `.`).
  `protobuf` is an **optional** extra (`pip install codemap[scip]`); vendored bindings generated from the
  official `scip.proto`, lazy-imported. Deterministic bytes; validated by protobuf round-trip and the real
  `scip print` CLI. Partially satisfies R1-C7 (structured descriptor ids). +8 tests.
- **R1 — research track opened** (docs only): survey of adjacent code-analysis / code-graph tools in
  `research/` — a landscape map (comparison matrix + integrate/wrap/learn verdicts) plus four theme reports
  (AI-context/repo-map, code-graph/index infra, query/dataflow engines, Python graph/arch peers). Grounded,
  web-verified. Net finding: the field is converging on codemap's thesis (source-only, deterministic,
  precise graph, no stale index); differentiators are the canonical diffable `graph.json` with provenance
  and native agent/MCP verbs. Concrete capability candidates (SCIP/ctags export, architecture-contracts
  `--check`, complexity metrics, relevance ranking + token-budgeted pack, …) logged as use-driven backlog
  items (R1-C1…C14, fully specified with scope/acceptance/effort, tiered by value÷cost). No code/schema change.
- **F23 — impact accepts a full/canonical id** (no schema change): `impact` (op, markdown, CLI) resolved
  its input by short name only, so passing a full id like `pkg.mod.Class` — exactly what `query`/`search`
  return — matched nothing and gave a falsely-empty blast radius (found on a live task). Added
  `Query.impact_targets` (node-id → itself, short name → all matches, else canonical/where_defined) and
  routed both `_op_impact` and `render_impact` through it. The extraction was fine — class instantiation
  was always captured; the bug was serve-layer input resolution.
- **M18 — graph freshness** (no schema change): the MCP server serves a static graph, so `stats` now
  reports `freshness` (`built_at` / `age_seconds` from the file mtime) — an agent can tell the map may be
  stale. The canonical graph.json stays timestamp-free (determinism preserved); build recipe + time live
  in a sidecar `<graph>.meta.json`, and `codemap refresh <graph.json>` rebuilds from it. First step of the
  deferred freshness work (M3.2), prompted by the now-live MCP consumer.
- **F22 — compact MCP payloads** (no schema change): shaped from the first live agent-over-MCP run.
  The `impact` and `call_contract` MCP tools are compact by default — `impact` omits the duplicate
  markdown and caps the flat ref list at `limit` (by_root counts stay complete); `call_contract` caps
  its list. `full=true` returns everything. On a hub (`MACDZoneAnalyzer`) this cut the `impact` payload
  ~65% and `call_contract` ~49%. Underlying ops / CLI unchanged (markdown still rendered there).
- **M17 — MCP adapter** (no schema change): `codemap serve --mcp` exposes the warm serve surface as
  Model Context Protocol tools (18 tools, one per agent-facing op) so an AI-agent host can drive
  codemap natively. Thin wrapper over `Session.handle` — the ambiguity signal (`resolved.ambiguous`)
  and error envelopes pass through unchanged. `mcp` is an **optional** dependency
  (`pip install codemap[mcp]`); the import is lazy so codemap works without it.
- **M16 — architecture overview** (schema 0.9): `report architecture` — layers + direction/violations
  (order-free), coupling (Ca/Ce/instability), god-objects & call-hubs (pervasive-tagged); `Query.layers/
  coupling/hotspots`, serve op `architecture`.
- **M15 — diff / change-review** (no schema change): `codemap review <diff>` → risk-sorted change-set
  dossier; `Query.symbol_at`/`symbols_in_range` (location→symbol), serve ops `locate`/`review`.
- **M14 — soundness** (schema 0.9): `canonical_info` surfaces ambiguity (`resolved.ambiguous`) instead of
  silently picking one of many defs; dataflow access-form (`subscripted` / `access`) so `columns()`
  returns real column-like keys, not dict-literal payload noise.
- **M13 — serve ergonomics** (no schema change): discovery/orientation ops — `search`, `families`,
  `columns_of`, `source`, `resolve`; re-export canonicalization; `file:line` in query results.
- **M3.1 — warm serve**: resident process, graph in memory, line-delimited JSON over stdio,
  transport-neutral (MCP-mappable).
- **M8–M12** (schema 0.5→0.8): provenance-aware dead-code, registry-family `implements` links,
  class-chunk call aggregation, call-site argument contracts, string-key column dataflow.
- **M6–M7**: repo-scope / impact (multi-root provenance); registry-aware call bridging.
- **M0–M5**: canonical graph (structure, imports, exports, inherits), query API, behavioral call graph,
  deep call resolution (jedi), and the RAG/vault/mermaid render views.

See [BACKLOG.md](BACKLOG.md) for the detailed milestone log and [gaps/](gaps/) for the dogfood runs that
drove each one.
