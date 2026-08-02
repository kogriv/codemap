# R1.2 — Code-graph / semantic-index infrastructure & interchange formats

The infrastructure layer: standardized code-graph schemas and interchange formats. These matter to
codemap less as competitors and more as **export targets** (interop) and **schema teachers**.

**Baseline (codemap):** source-only Python graph (griffe + jedi), deterministic canonical `graph.json`
with provenance and canonical ids + re-export resolution, networkx queries, CLI-AI-first, warm serve + MCP.

---

## SCIP — Sourcegraph Code Intelligence Protocol

- **What / data model.** A language-agnostic *interchange format* (Protobuf `scip.proto`), not a graph DB.
  An `Index` holds `Document`s (per file); each has `Occurrence`s (symbol string + source range +
  `SymbolRole` bitmask: Definition/Import/Read/Write…) and `SymbolInformation` (docs, relationships, kind).
  Its defining innovation: a **human-readable structured symbol string** (scheme + package manager +
  package + version + descriptor path, e.g. `scip-python python mypkg 1.0 mymod/MyClass#method().`) that is
  globally stable and comparable *without* resolving opaque ids.
- **How produced.** Per-language indexers (`scip-python`, `scip-typescript`, `scip-go`, `scip-java`…),
  mostly compiler/type-checker-integrated (scip-python builds on Pyright) → semantically precise.
- **Determinism.** Flat serialized snapshot; symbol strings deterministic by construction. Incrementality
  handled at the consumer, not the format.
- **Interface.** Protobuf on disk; `scip` CLI (converts SCIP↔LSIF, prints/snapshots for debugging).
- **License / status.** Apache-2.0, very active; **moved to open governance March 2026** (steering
  committee incl. Uber/Meta/Sourcegraph) — becoming the de-facto open standard, displacing LSIF.
- **Verdict: EXPORT-TARGET (highest-value interop).** codemap already produces canonical structured symbol
  identities with provenance — exactly what SCIP formalizes. A `codemap → scip.proto` writer would light up
  Go-to-def / Find-references in Sourcegraph and any SCIP consumer at ~zero semantic cost for defs/refs.
  Caveat: codemap's jedi/griffe reference precision is below compiler-backed indexers — export what it's
  confident about, mark the rest. **Schema lesson:** adopt SCIP's *structured descriptor id* (already close
  to codemap's canonical ids) and its Occurrence-with-role model.

## LSIF — Language Server Index Format

- **What / data model.** SCIP's predecessor (Microsoft). A **JSON graph** of vertex/edge records (ranges,
  resultSets, definition/reference/hoverResult, **monikers** for cross-index identity) — persists the
  output of an LSP session so no live server is needed.
- **How produced.** Language-server-backed indexers (`lsif-go`, `lsif-tsc`…). LSP-derived.
- **Determinism.** Relies on **opaque integer ids** to wire edges — fragile, hard to produce/debug/compare.
  This is exactly why SCIP replaced it.
- **License / status.** Open but **effectively deprecated** — Sourcegraph removed LSIF *reading* in v4.6
  (auto-migrating to SCIP); most `lsif-*` indexers superseded by `scip-*`.
- **Verdict: LEARN-ONLY (do NOT target).** A *negative* lesson that validates codemap's design: opaque
  numeric ids are the anti-pattern; stable string ids (SCIP / codemap canonical ids) are the fix. Don't
  export LSIF. Its one durable idea — **monikers** (cross-index symbol identity) — is what codemap's
  re-export resolution already serves.

## Kythe (Google)

- **What / data model.** Language-agnostic **graph** as `(node, fact)` and `(edge)` entries: nodes carry
  string key/value **facts**, connected by directed **labelled edges** (`defines/binding`, `ref`, `childof`,
  `typed`). Node identity = **VName** (corpus/path/root/signature/language tuple). Low-level store; the
  *schema* assigns meaning.
- **How produced.** Two-stage, **compiler-integrated**: extractors wrap the build to capture hermetic
  compilation units, then per-language indexers emit the graph. Heavy.
- **License / status.** Apache-2.0, open, but **perpetually pre-1.0** and low-velocity — a reference
  architecture more than a turnkey product.
- **Verdict: LEARN-ONLY.** Too build-coupled to integrate for a source-only tool, but the **canonical
  teacher for codemap's graph model**: the node/edge/fact triad, *labelled edge kinds as a first-class
  vocabulary*, and the **VName** (structured, corpus-scoped node identity) — a direct analogue of codemap's
  canonical-id-with-provenance. Adopt Kythe's discipline of a **documented, closed set of edge labels.**

## Glean (Meta)

- **What / data model.** A **fact database** for code. Schema = typed **predicates** (like tables);
  instances = **facts** (rows). Covers defs, refs, types, calls, inheritance, imports — more relational than
  a flat node-edge graph.
- **How produced.** Language indexers (mostly compiler-derived) **plus it ingests SCIP/LSIF** to cover
  Go/Java/Rust/TS. So Glean both produces and *consumes the SCIP ecosystem*.
- **Interface.** Queried with **Angle** — a declarative, Datalog-style logic language. Server + query API.
- **License / status.** Open-sourced by Meta Dec 2024 (BSD-style), active; Haskell.
- **Verdict: LEARN-ONLY (with a free export path via SCIP).** Won't wrap (Haskell, heavyweight), but the
  strongest teacher for **query surface**: a typed relational fact model queried by logic. codemap's
  networkx ops are an imperative version of what Angle expresses declaratively. Strategic point: **because
  Glean consumes SCIP, a codemap→SCIP exporter also gets codemap into Glean for free.**

## Stack Graphs (GitHub)

- **What / data model.** A **name-resolution graph** (extends scope graphs): resolving a reference = finding
  a valid path using a symbol *stack*. Answers "what does this name bind to" incrementally, cross-file,
  without a full compile.
- **How produced.** **Source-only**, from **tree-sitter** parse trees + a per-language `.tsg` binding DSL.
  No build, no type-checker — the closest philosophical cousin to codemap's stance.
- **Determinism.** File-incremental, sub-100ms navigation; per-file subgraphs stitched.
- **License / status.** MIT/Apache, **but `github/stack-graphs` was ARCHIVED 2025-09-09** — the
  `.tsg`-per-language maintenance burden proved unsustainable.
- **Verdict: LEARN-ONLY (cautionary).** Validates that a purely static name-resolution graph is viable and
  useful — but its **archival is a strategic warning**: a bespoke per-language binding DSL doesn't scale in
  maintenance. codemap's Python-only focus + reuse of jedi/griffe (rather than authoring binding rules) is
  the pragmatic answer to exactly the problem that sank stack-graphs. **Lesson: keep leaning on existing
  resolvers; never build a general name-binding engine.**

## Sourcegraph (the product)

- **What.** Code search + navigation platform; the primary SCIP/LSIF *consumer*.
- **Model.** Two tiers: **search-based** (tree-sitter + heuristics, always-on, some false +/−) and
  **precise** (SCIP/LSIF, compiler-accurate, needs uploaded indexes), falling back search→precise.
- **License / status.** Commercial (open components); driving SCIP's 2026 open-governance push.
- **Verdict: EXPORT-TARGET / downstream consumer.** The destination that makes a codemap SCIP exporter
  worthwhile — upload the index, get cross-repo navigation UI free. Strategic lesson: its **two-tier model
  (heuristic fast path + precise slow path)** mirrors codemap's own tradeoff (source-only ≈ "more precise
  than search, less than compiler"). codemap occupies a useful middle rung and should position itself there.

## universal-ctags

- **What / data model.** The simplest model: a **tags file** — one line per definition
  (`name  file  address  kind` + extension fields: scope, roles, signature). Flat, not a graph. Modern
  universal-ctags adds a **roles** field (def, and some reference roles).
- **How produced.** **Source-only**, single-pass, regex/parser per language. Fast, no build, no cross-file
  resolution.
- **License / status.** GPL-2.0, **actively maintained** (v6.2.1, Oct 2025).
- **Verdict: EXPORT-TARGET (cheap, high-reach) + LEARN-ONLY.** codemap could trivially emit a `tags` file
  from its definition nodes — instant compatibility with every editor, near-zero effort. Lesson: a
  **dead-simple, ubiquitous interchange format** has value; a ctags export is the lowest-friction interop
  win, and marks the *floor* (definitions only, no edges) that codemap clearly clears.

## LSP — Language Server Protocol

- **What / data model.** Not an index/graph — a **JSON-RPC protocol** for *live* editor↔server interaction
  (hover, definition, references, completion, diagnostics) computed on demand.
- **How produced.** **Runtime**, by a resident language server; results ephemeral. (LSIF was invented to
  *persist* LSP-style results.)
- **License / status.** MIT spec, ubiquitous, active.
- **Verdict: LEARN-ONLY (contrast, not integration).** codemap's philosophical opposite:
  online/stateful/ephemeral vs offline/deterministic/canonical-artifact. Don't build an LSP server; but the
  LSP request vocabulary (definition, references, callHierarchy, typeHierarchy) is a **good checklist of
  operations users expect** — codemap's dossier/callers/callees/impact already cover the graph-answerable
  subset. For editor integration the path is SCIP/ctags export, not a live server.

---

## Themes — what this category teaches codemap

**Graph schema.** The whole field converges on the same primitives codemap already uses:
**nodes + labelled edges + facts, with a stable structured node identity.** Kythe's VName, SCIP's descriptor
symbol string, and LSIF's monikers are three encodings of one idea — *a canonical, resolvable id that
survives files, versions, and re-exports*. codemap's canonical ids + provenance + re-export resolution are
squarely in this tradition; the concrete borrow is to (a) keep a **small, documented, closed vocabulary of
edge kinds** (Kythe-style) and (b) shape node ids as **structured descriptors** (SCIP-style).

**Interchange / export.** The clear strategic move is **SCIP as export target** — the ascendant open
standard (open governance since 2026), consumed by Glean and Sourcegraph, mapping almost 1:1 onto codemap's
model, so one exporter buys interop with the entire precise-code-intel ecosystem. **ctags export** is the
cheap complement (universal editor reach). **LSIF is a dead end** (deprecated; its opaque-numeric-id design
is the cautionary tale SCIP fixed, and codemap already avoids it). LSP is contrast, not a target.

**Source-only vs compiler-integrated.** codemap sits in a proven middle band. Compiler-integrated systems
(Kythe, Glean, most SCIP indexers) buy *semantic precision* at the cost of *build coupling, weight, and
per-language investment*. Pure source-only heuristic systems (ctags, Sourcegraph search) are trivial but
shallow. The two source-only *graph* precedents are the sharpest signals: **stack-graphs was archived in
2025** under the weight of hand-authored per-language binding DSLs, while **universal-ctags thrives** by
staying simple and maintained. Lesson: **stay source-only and deterministic** (the differentiator vs the
compiler-heavy crowd) but **never build a bespoke name-resolution engine** — delegate to jedi/griffe, stay
Python-focused, and compete on determinism, canonical output, provenance, and the CLI-AI-first/MCP surface.

---

### Sources

- SCIP: [github.com/sourcegraph/scip](https://github.com/sourcegraph/scip) ·
  [scip-code.org](https://scip-code.org/) · [Announcing SCIP](https://sourcegraph.com/blog/announcing-scip) ·
  [scip-python](https://github.com/sourcegraph/scip-python)
- LSIF: [lsif.dev](https://lsif.dev/) · [LSIF→SCIP migration](https://5.0.sourcegraph.com/admin/how-to/lsif_scip_migration)
- Kythe: [schema overview](https://kythe.io/docs/schema-overview.html) · [storage model](https://kythe.io/docs/kythe-storage.html)
- Glean: [Meta open-sourcing](https://engineering.fb.com/2024/12/19/developer-tools/glean-open-source-code-indexing/) ·
  [glean.software](https://glean.software/docs/introduction/) · [Angle guide](https://glean.software/docs/angle/guide/)
- Stack Graphs: [Introducing stack graphs](https://github.blog/open-source/introducing-stack-graphs/) ·
  [Creager paper](https://arxiv.org/pdf/2211.01224) (repo archived 2025-09-09)
- Sourcegraph: [Precise code navigation](https://sourcegraph.com/docs/code-search/code-navigation/precise_code_navigation)
- universal-ctags: [github.com/universal-ctags/ctags](https://github.com/universal-ctags/ctags) ·
  [tags format](https://docs.ctags.io/en/latest/man/tags.5.html)
- LSP: [spec](https://microsoft.github.io/language-server-protocol/)
