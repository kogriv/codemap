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

---

## Update 2026-09-12 — what hands-on measurement did to this map

Everything above is **desk research from 2026-08-02**, written before a single peer had been installed.
Six tools have since been measured hands-on on a shared benchmark scope (`research/tools/`), three of them
on byte-identical input verified by content hash. This section reconciles the map with what measuring
actually found — and says where the map is still desk-level.

### The ten capability candidates were a plan; nine of them shipped

| # | Candidate | Outcome |
|---|---|---|
| 1 | SCIP export | ✅ R1-C1 (2026-08-02) |
| 2 | ctags export | ✅ R1-C2 (2026-08-16) |
| 3 | Architecture contracts + `check` | ✅ R1-C3 (2026-08-14), and since extended to three kinds of import cycle |
| 4 | Complexity metrics in hotspots | ✅ R1-C4 (2026-08-16) |
| 5 | API breaking-change report | ✅ R1-C5 (2026-08-14) |
| 6 | Relevance ranking + token-budgeted pack | ✅ R1-C6 (2026-08-22) |
| 7 | Closed edge vocabulary + structured ids | ✅ R1-C7 (2026-08-22), and the **resolution** vocabulary closed the same way in R1-C39 (2026-09-07) |
| 8 | Dead-code confidence + whitelist | ✅ R1-C8 (2026-08-22) |
| 9 | Incremental / Merkle-style updates | ✅ R1-C9 (2026-08-23) |
| 10 | rope-backed safe edits | ⬜ still a door (R1-C12) — read-only remains the default stance |

So the list reads as a to-do and is a **record**. The one item left open is the one that would break the
read-only invariant, which is why it stayed shut.

### Five tools the matrix does not contain

They arrived after it — from R1.5's live roster and the R2 hands-on track — and they are the *actual*
competitors, not the canonical infrastructure the matrix catalogues:

| Tool | Mechanism | Artifact | Verdict (measured) | Card |
|---|---|---|---|---|
| CodeGraph | tree-sitter + Rust kernel, SQLite+FTS5, 20 languages | 15.5 MB SQLite, **different md5 across builds** | learn-only (strong) — fastest peer measured; its cycle finder reported 136 where 41 were real | [codegraph](tools/codegraph.md) |
| GitNexus | graph DB + embeddings + RRF, LLM-free indexing | 123 MB binary DB, not diffable | learn (strong peer, different niche) — transitive import-closure impact richer than ours, file-level and provenance-blind | [gitnexus](tools/gitnexus.md) |
| OntoIndex | tree-sitter, 14 languages, vendored Cypher store | not reproducible build-to-build | learn — **the closest epistemic model in the field**: per-edge resolution reason with a graded confidence | [ontoindex](tools/ontoindex.md) |
| graphlens | LSP-backed (`ty`), watch mode | 31 MB SQLite, not diffable | learn (competent peer; overlaps our thesis) — cross-boundary resolution *into* dependencies, which we lack | [graphlens](tools/graphlens.md) |
| cocoindex | incremental dataflow engine + embeddings | binary LMDB/SQLite | **wrap** — the first MIT/Apache semantic-search adapter candidate (R1-C16) | [cocoindex](tools/cocoindex-code.md) |

### Differentiator #1 was the one claim that got tested, and it held

"No peer persists a deterministic, byte-stable graph you can commit and diff" was an argument in August.
It is now a measurement across every peer installed: **SQLite 15.5 MB with a moving md5**, **123 MB binary
DB**, **31 MB SQLite**, **binary LMDB**, **a graph that is not reproducible run to run**. Five independent
implementations, five non-diffable artifacts. Meanwhile our own determinism had to be narrowed in the same
period — it is byte-stable on the **fast** tier only, and the deep tier is a sample (R1-C42) — so the claim
survived measurement only because it was made smaller while being tested.

### What measurement took away

- **"Epistemic honesty" can no longer be claimed as ours alone.** OntoIndex ships a per-edge resolution
  *reason* with a graded confidence; our per-answer label is coarser. That finding became R1-C39 — we
  implemented the idea we found in a competitor, and the entry we had written for it turned out to describe
  our own tool wrongly.
- **Our recall was worse than a peer's, and we phrased the gap as a property.** CodeGraph's library cycle
  finder scored precision 10% / recall 32%; codemap scored 100% / **2.4%** — and reported the result as
  *"import graph is acyclic"*. Fixed the same day (R1-C29), but the lesson outlives it: a whole-graph answer
  inherits every flaw of the graph it is computed from, **including the edges that graph never read**.

### The track's real yield was not a shopping list

Three defects in *codemap* were found by measuring someone else's tool and then asking the same question of
ourselves: the silent `--limit` truncation (R1-C28, found in CodeGraph, present in our own `search`), the
ungraded edge route (R1-C39, found in OntoIndex), and "where does a change land in a scenario" (R1-C40,
found in OntoIndex, and its own defect found by a consumer two days later). That pattern — *measure a peer,
then turn the question inward* — produced more than the ten candidates did.

It also runs outward. One issue and one comment were filed upstream on CodeGraph; **both were fixed by the
author** ([#1639](https://github.com/colbymchenry/codegraph/issues/1639) → PR #1772,
[#1566](https://github.com/colbymchenry/codegraph/issues/1566) → PR #1790, both 2026-09-08, neither
released). A measured report with a minimal repro gets acted on; a verdict about someone's tool does not
have to be a takedown to be useful.

### Where this map is still desk-level

- **25 of the 30 rows above were never installed.** SCIP and ctags were exercised as export targets, jedi
  and griffe are dependencies, tree-sitter was reasoned about, not used. The rest is reading.
- **The five families predate the live roster.** Four of the five tools in the table above do not fit the
  families cleanly — they are all "AI-context + code-graph + MCP" at once, which is the category the field
  actually converged on, and the taxonomy has not been redrawn to match.
- **Every number in the peer cards describes the version measured.** CodeGraph's four fixes are merged and
  **unreleased** (npm `latest` is still 1.6.0), so its figures stop being true at their next release; the
  re-measurement is logged as its own backlog item rather than left to rot here.
