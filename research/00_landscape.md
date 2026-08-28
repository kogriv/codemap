# R1.0 — Landscape

The map of adjacent code-analysis / code-graph tools, where **codemap** sits among them, and a consolidated
integrate / wrap / learn verdict per tool. Detail lives in the four theme reports:
[R1.1 AI-context/repo-map](01_ai_context_repomap.md) · [R1.2 code-graph/index infra](02_codegraph_index_infra.md) ·
[R1.3 query/dataflow engines](03_query_dataflow_engines.md) · [R1.4 Python graph/arch peers](04_python_graph_arch_peers.md).
A bottom-up field intake (curated Telegram posts) adds the **live competitor roster** and hard benchmark
evidence in [R1.5 curated sources](05_curated_sources.md) — it confirms this map rather than changing it:
the whole field has converged on codemap's "code graph over MCP beats grep" thesis.

---

## The five families

1. **AI-context / repo-map** — build a map of a repo to feed a coding LLM (aider repo-map, Cursor, Continue,
   Cody, Repomix). Codemap's own category.
2. **Code-graph / index infrastructure** — standardized schemas & interchange formats for code intelligence
   (SCIP, LSIF, Kythe, Glean, Stack Graphs, ctags, Sourcegraph, LSP).
3. **Query / dataflow / structural-search** — ask questions of code via a DSL, pattern language, or library
   (CodeQL, Semgrep, ast-grep, tree-sitter, Comby, jedi/rope, PyCG).
4. **Python graph / dependency / architecture peers** — the direct reference peers (pydeps, pyan3, grimp,
   import-linter, snakefood, code2flow, vulture, radon, Doxygen, Sourcetrail).
5. **Doc / API-surface extraction** — griffe (codemap's own extractor), pydoctor, Sphinx autodoc.

## Where codemap sits — three structural signals

- **The AI-context frontier is drifting toward codemap's thesis.** Sourcegraph Cody is phasing out
  embeddings for *search + code graph*; Anthropic reports agentic grep beat RAG "by a lot." Source-only,
  deterministic, precise-graph, no-stale-index is where the category is heading, not away from it.
- **The whole graph-infra field converges on codemap's primitives.** Kythe VName, SCIP descriptor strings,
  LSIF monikers are three encodings of one idea codemap already implements: *a canonical, resolvable id that
  survives files, versions, and re-exports*. codemap is squarely in this tradition.
- **The two source-only *graph* precedents mark codemap's lane.** Stack-graphs (source-only name-resolution
  graph) was **archived in 2025** under the maintenance weight of hand-authored per-language binding DSLs;
  universal-ctags **thrives** by staying simple. The lesson: stay source-only + deterministic, but never
  build a bespoke name-resolution engine — delegate to jedi/griffe, stay Python-focused.

## codemap's differentiators (what nothing else combines)

1. **Canonical, timestamp-free, diffable `graph.json` with provenance** — no peer persists a deterministic,
   byte-stable graph you can commit and diff. (aider's map is ephemeral; embeddings tools aren't
   deterministic; Kythe/Glean need a build.)
2. **Native agent/MCP query verbs** — `impact`, `call_contract`, `architecture` answer structural questions
   grep and embeddings can't cheaply answer, delivered as JSON over MCP.
3. **Source-only + Python-depth middle band** — more precise than heuristic search (ctags, Sourcegraph
   search-tier, code2flow), lighter than compiler-integrated indexers (Kythe, Glean, most SCIP indexers).
4. **Provenance-aware analysis** — cross-root (package/tests/docs) resolution makes dead-code and impact
   context-aware, directly curing vulture's dominant false-positive source.

## Strategic positioning

codemap should aim to be **the precise structural leg feeding index-free agents via MCP** — integrate with
Claude Code-style agents, complement (not replace) embeddings RAG and Repomix-style packing. The category is
already conceding that structural precision + freshness beats a vector index for code; codemap's job is to be
the best deterministic, source-only, Python-deep, agent-facing graph — and to interoperate outward via SCIP.

---

## Comparison matrix

| Tool | Family | Mechanism | Source-only | Deterministic | Interface | Verdict for codemap |
|---|---|---|---|---|---|---|
| **codemap** | AI-context / graph | griffe + jedi graph | ✅ | ✅ canonical | CLI / JSON / **MCP** | — (baseline) |
| aider repo-map | AI-context | tree-sitter + PageRank | ✅ | ✅ | aider CLI (internal) | **learn** (ranking, budgeting) |
| Cursor index | AI-context | embeddings + Merkle | ✅ | ❌ | IDE (closed) | learn (Merkle incrementality) |
| Continue `@codebase` | AI-context | embeddings + AST + rerank | ✅ | ❌ | IDE ext (OSS) | learn |
| Cody | AI-context | SCIP + (legacy) embeddings | ⚠️ build-assisted | ⚠️ | IDE (Enterprise-only) | learn (validates thesis) |
| Claude Code | AI-context | agentic grep + LSP | ✅ | grep exact | agent + **MCP** | **INTEGRATE (consumer)** |
| Repomix | AI-context | concat + ts-signatures | ✅ | ✅ | CLI / **MCP** | wrap / complementary |
| **SCIP** | index infra | Protobuf occurrences | ⚠️ indexer-dep | ✅ | file + `scip` CLI | **EXPORT-TARGET** |
| LSIF | index infra | JSON graph (opaque ids) | ⚠️ LSP-derived | ⚠️ | JSON upload | learn-only (dead end) |
| Kythe | index infra | node/fact/edge graph | ❌ compiler | ✅ | graph store API | learn (schema: VName, edge labels) |
| Glean | index infra | fact DB + Angle | ❌ mostly compiler | ✅ | Angle query API | learn (+ free via SCIP) |
| Stack Graphs | index infra | tree-sitter name-res graph | ✅ | ✅ | Rust lib | learn (cautionary — archived) |
| universal-ctags | index infra | tags file (defs) | ✅ | ✅ | `tags` file | **EXPORT-TARGET** (cheap) |
| LSP | index infra | live JSON-RPC | ✅ | ❌ ephemeral | protocol | learn (op checklist) |
| CodeQL | query/dataflow | Datalog DB + taint | ⚠️ build for compiled | ✅ | CLI / CI | learn (taint model) |
| Semgrep | query/dataflow | YAML patterns + taint | ✅ | ✅ | CLI / CI | learn (taint vocab) |
| ast-grep | query/dataflow | tree-sitter structural | ✅ | ✅ | CLI / **MCP** | **wrap** (multi-lang front-end) |
| tree-sitter | query/dataflow | incremental parser | ✅ | ✅ | C lib + bindings | **INTEGRATE** (multi-lang backend) |
| Comby | query/dataflow | delimiter templates | ✅ | ✅ | CLI | learn-only |
| jedi | query/dataflow | Python inference | ✅ | ⚠️ | library | **already used** |
| rope | query/dataflow | Python refactoring | ✅ | ✅ | library | integrate-if-edits |
| PyCG / Scalpel | query/dataflow | static call graph | ✅ | ✅ | library / CLI | learn (benchmark, ceiling) |
| pydeps | py peers | bytecode imports → dot | ⚠️ | ⚠️ | CLI | already-covered |
| grimp | py peers | import graph lib | ✅ | ✅ | library | already-covered |
| pyan3 | py peers | AST call/def-use | ✅ | ✅ | CLI | already-covered |
| code2flow | py peers | heuristic call graph | ✅ | ✅ | CLI / MCP | learn (differentiator) |
| import-linter | py peers | import contracts (grimp) | ✅ | ✅ | CLI / CI | **LEARN-AND-ADOPT** (biggest gap) |
| vulture | py peers | AST unused names | ✅ | ✅ | CLI | already-subsumed (+edge) |
| radon / wily | py peers | complexity metrics | ✅ | ✅ | CLI / CI | **LEARN-AND-ADOPT** (metrics gap) |
| griffe | doc/API | AST API model + diff | ✅ | ✅ | CLI / lib | **already used** (+ API-diff gap) |
| Doxygen | py peers | doc + call graphs | ✅ | ✅ | CLI | already-covered (weak Python) |
| Sourcetrail | py peers | interactive map (SQLite) | ✅ | ✅ | GUI (discontinued) | learn (cautionary) |

Legend: ✅ yes · ⚠️ partial/conditional · ❌ no.

---

## Consolidated verdicts

**INTEGRATE / consume** — Claude Code-style agents (codemap's MCP adapter drops in as the structural leg);
tree-sitter (the eventual multi-language extraction backend).

**WRAP / export-target** — **SCIP** (highest-value interop: one exporter → Sourcegraph + Glean + the whole
precise-code-intel ecosystem); **ctags** (cheap, universal editor reach); ast-grep (multi-language structural
front-end); Repomix (token-budgeted packing as an output form); rope (if codemap ever adds safe edits).

**LEARN-AND-ADOPT (concrete gaps)** — import-linter (architecture-constraints-as-CI-gate); radon/wily
(complexity metrics for hotspot ranking); griffe API-diff (signature-level breaking-change reporting);
aider (relevance ranking + token-budgeted rendering).

**LEARN-ONLY** — Cursor/Continue/Cody/LlamaIndex (embeddings, opposite axis); Kythe/Glean (schema teachers,
too build-coupled); LSIF (dead end); Stack Graphs & Sourcetrail (cautionary — maintenance-killed);
CodeQL/Semgrep (taint vocabulary); Comby; PyCG (benchmark + honest ceiling).

**ALREADY COVERED / SUBSUMED** — pydeps, grimp, snakefood, pyan3, code2flow, Doxygen-for-Python (import &
call graphs); vulture (dead-code, bettered by provenance); griffe & jedi (already the extractor/resolver).

---

## Capability candidates fed back to the backlog

Per the track's principle (findings become concrete, use-driven capabilities — not speculative features),
these are logged in [../BACKLOG.md](../BACKLOG.md) under **R1**, ordered by value ÷ cost:

1. **SCIP export** — `codemap export --scip` → interop with the whole precise-code-intel ecosystem.
2. **ctags export** — `codemap export --ctags` → instant editor reach, near-zero effort.
3. **Architecture contracts + `--check`** — declarative layer/independence/forbidden contracts, non-zero
   exit → architecture report becomes an enforceable CI gate (import-linter parity).
4. **Complexity metrics in hotspots** — cyclomatic / Halstead / MI over the existing griffe AST → richer
   hotspot ranking (radon parity, on-brand & deterministic).
5. **API breaking-change report** — signature-level diff between two graphs (griffe API-diff idea; overlaps
   the deferred two-graph diff for added/deleted symbols).
6. **Relevance ranking + token-budgeted context pack** — PageRank-style ranking + "render the relevant slice
   under N tokens" → makes codemap a first-class context provider, not only a point-query service.
7. **Documented closed edge-label vocabulary + structured descriptor ids** — Kythe/SCIP schema discipline
   (mostly already true; formalize and document).
8. **Dead-code confidence + whitelist UX** — graded certainty (vulture parity) on top of provenance-aware
   dead-code.
9. **Incremental / Merkle-style graph updates** — content-hash the tree, recompute changed subgraphs
   (fed the M3.2 watcher, shipped 2026-08-28).
10. **rope-backed safe edits** — optional mutation layer (rename across a computed blast radius); keep
    read-only as the default stance.
