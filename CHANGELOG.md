# Changelog

All notable changes to codemap. Format loosely follows [Keep a Changelog](https://keepachangelog.com);
the graph JSON has its own `SCHEMA_VERSION` (`codemap/model.py`), noted per entry.

## [Unreleased]

Extracted into a standalone repository from its incubation home (the `bquant` monorepo), preserving the
full M0–M16 development history. Graph schema **0.9**; 123 tests; warm serve surface with 21 ops.

### Milestones

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
