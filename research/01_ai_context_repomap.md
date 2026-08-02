# R1.1 — AI-context / repo-map tools

The direct AI-first peers: tools that build a "map" of a repo to feed a coding LLM. This is the
category codemap lives in, so the verdicts here matter most for positioning.

**Baseline (codemap):** source-only Python code-graph analyzer (griffe + jedi, no build/runtime),
deterministic canonical `graph.json`, networkx queries, CLI-AI-first (JSON), warm serve + MCP adapter
(search, dossier, impact/blast-radius, callers/callees, call-contract, architecture, diff/change-review).

---

## The field splits three ways

| Camp | Mechanism | Members | Freshness | Determinism |
|---|---|---|---|---|
| **Deterministic structural graph** | AST/tree-sitter → symbol graph | **aider repo-map**, Cody/SCIP, **codemap** | rebuild/index | ✅ (given fixed graph) |
| **Probabilistic embeddings RAG** | chunk → vector index → nearest-neighbor | Cursor, Continue, LlamaIndex, Cody (legacy) | re-embed on change | ❌ |
| **Index-free agentic grep** | glob + ripgrep + read, model-driven | Claude Code, Amp | always fresh | grep exact, path model-driven |

The strategically important signal: **the frontier is drifting toward codemap's thesis.** Sourcegraph
Cody is phasing out embeddings in favor of search + code graph; Anthropic reports agentic grep beat RAG
"by a lot." Source-only, deterministic, precise-graph, no-stale-index is where the category is heading.

---

## aider — repo-map (the closest peer)

- **Mechanism.** Parses every file with **tree-sitter** + per-language tag queries (`.scm`) to extract
  `def`/`ref`. Builds a directed multigraph (files as nodes, ref→def as edges), then runs
  **personalized PageRank** (biased toward files in the chat + mentioned identifiers) to rank symbols.
- **Data model / output.** The graph is *transient*; the deliverable is a **token-budgeted text map** —
  top-ranked files with key definition signatures (bodies elided), fit via **binary search** into a
  `--map-tokens` budget (~1k default).
- **Source-only / determinism.** Source-only; tags cached in SQLite. Made deterministic via improved
  caching; PageRank is deterministic on a fixed graph.
- **Interface.** Internal to the aider CLI chat loop (regenerated each turn). No standalone MCP, but the
  algorithm has been reimplemented standalone (e.g. `RepoMapper`).
- **License / maintenance.** Apache-2.0, very actively maintained.
- **Verdict: LEARN-ONLY (strong).** The reference implementation of "graph-rank symbols → token-budgeted
  map." codemap **differentiates** by persisting a *canonical deterministic diffable* `graph.json`
  (aider's map is ephemeral text), an explicit query/MCP surface (impact, call-contract, architecture),
  and provenance. codemap should **learn its two missing ideas**: (a) **relevance ranking**
  (personalized PageRank) to decide *what* an agent sees, and (b) **token-budgeted rendering** — turn the
  graph into a size-bounded payload, not just point-query answers.

## Cursor — codebase indexing

- **Mechanism.** Syntactic chunking → **embeddings** in a server-side vector DB; a **Merkle tree** of
  chunk-content hashes syncs only changed chunks; embeddings cached by content.
- **Data model.** Remote vector index + client Merkle tree (paths/chunks obfuscated). Not a symbol graph.
- **Source-only / determinism.** Source-only; retrieval **non-deterministic** (nearest-neighbor).
- **Interface.** Proprietary IDE feature; not drivable as CLI/lib/MCP.
- **License / maintenance.** Closed commercial; active.
- **Verdict: LEARN-ONLY.** Opposite axis (embeddings vs graph). Borrowable idea: the **Merkle-tree
  incremental update** — content-hash the source tree, recompute only changed subgraphs (feeds M3.2).

## Continue.dev — codebase indexing / `@codebase`

- **Mechanism.** Hybrid: **embeddings** (local `all-MiniLM-L6-v2`) + keyword FTS + **tree-sitter AST**,
  with optional LLM re-rank (retrieve 25 → re-rank → 5).
- **Data model.** Local vector index + SQLite FTS in `~/.continue/index`.
- **Source-only / determinism.** Source-only; non-deterministic; `@codebase` now deprecated for newer
  agentic retrieval.
- **Interface.** Open-source (Apache-2.0) IDE extension; actively maintained.
- **Verdict: LEARN-ONLY.** Open reference for the hybrid pattern. Lesson: **keyword + structural + semantic,
  then re-rank** — codemap's deterministic graph is best positioned as the *structural/precise leg* of
  such a hybrid, not a full RAG replacement.

## Sourcegraph Cody — context fetching

- **Mechanism.** Multi-source: keyword/regex/structural search + **SCIP-based precise code intelligence**
  (go-to-def / find-refs as hard links) + (legacy) embeddings.
- **Data model.** SCIP code-graph index + (legacy) embeddings, over Sourcegraph's search engine.
- **Source-only / determinism.** SCIP indexing is typically **build/compiler-assisted** (not pure
  source-only) → high precision but heavier; graph portion deterministic, embeddings not. Embeddings
  being phased out.
- **License / maintenance.** Cody Free/Pro **discontinued Jul 2025**, now Enterprise-only; Sourcegraph
  pivoted individuals to **Amp** (agentic); Dec 2025 Cody and Amp split into separate companies.
- **Verdict: LEARN-ONLY (spec-relevant).** Philosophically closest — a precise code graph feeding an LLM —
  and its move *away from embeddings toward search + graph* validates codemap's thesis. Contrast: SCIP
  leans on build/compiler indexers (multi-language, heavy); codemap is source-only + Python + deterministic
  canonical. **The SCIP data model is worth studying as a mature code-graph interchange format**
  (→ see [R1.2](02_codegraph_index_infra.md); possible export/consume target).

## Claude Code (and similar agents) — built-in codebase understanding

- **Mechanism.** **No index, no embeddings.** Agentic **glob + ripgrep + read**, iteratively refined;
  optionally LSP for symbol-precise confirmation.
- **Data model.** None persisted — context assembled live per task.
- **Source-only / determinism.** Source-only; always fresh (no stale index); grep results exact, path
  model-driven.
- **Interface.** Agent-native; extensible via **MCP**.
- **License / maintenance.** Proprietary (Anthropic), active. The pattern is industry-wide (agents
  converging on grep + LSP over RAG).
- **Verdict: INTEGRATE / WRAP (primary opportunity).** This is codemap's **consumer, not competitor.**
  The gap agents still have is **structural/graph reasoning** (blast-radius, callers across the tree,
  call-contract) that grep can't do cheaply — exactly codemap's ops. codemap's **MCP adapter drops
  straight into this ecosystem**, trading many grep round-trips for one deterministic, token-cheap graph
  answer. This is where codemap should aim its positioning.

## Repomix / gpt-repository-loader / LlamaIndex code loaders

- **Repomix** (formerly Repopack) — concatenates a repo into one AI-friendly pack (XML/MD/text) with
  token counting, security scan, `--compress` (tree-sitter signature stripping), gitignore/glob. Source-only,
  deterministic (it's a formatter), CLI + web + VS Code + **MCP server**. MIT, very active.
  **Verdict: WRAP / COMPLEMENTARY** — no intelligence overlap (dumb concat + shallow signature compress);
  codemap could adopt **token-budgeted packing as an output format** (render the graph's relevant slice as
  a bounded pack); its MCP server is a good UX reference.
- **gpt-repository-loader** — flattens a git repo into one prompt blob. Source-only, deterministic, MIT,
  dormant. **Verdict: LEARN-ONLY (baseline)** — the naive floor codemap improves on.
- **LlamaIndex code loaders** — ingest a repo into documents for embedding/vector RAG. Source-only,
  non-deterministic, MIT, active. **Verdict: LEARN-ONLY** — the embeddings-RAG library path; codemap could
  be a *retriever plugin* (deterministic-graph alternative) into such frameworks.

---

## Themes — what this category teaches codemap

The field splits into deterministic structural graph vs probabilistic embeddings RAG, with an ascendant
third camp of index-free agentic grep — and the frontier is drifting **toward codemap's thesis** (Cody
dropping embeddings for search + graph; Anthropic finding agentic grep beat RAG). codemap's genuine
differentiators against the whole field: the **canonical, timestamp-free, diffable `graph.json` with
provenance** (nobody else persists a deterministic graph) and **native agent/MCP query verbs** (impact,
call-contract, architecture) that grep and embeddings can't cheaply answer. Its clearest borrowable gaps:

1. **Relevance ranking** — aider's personalized PageRank is the proven way to decide *what* to surface;
   codemap has the graph but no ranking. → **backlog candidate.**
2. **Token-budgeted rendering** — aider and Repomix both turn structure into a size-bounded payload;
   codemap answers point queries. A "render the relevant slice under N tokens" mode would make it a
   first-class context provider. → **backlog candidate.**
3. **Incremental / Merkle-style updates** — Cursor's content-hash sync, for fast recompute on change.
   Aligns with the deferred M3.2 watcher.

**Strategic positioning:** codemap should be **the precise structural leg feeding index-free agents via
MCP** (integrate with Claude Code, complement Repomix packing) rather than competing head-on with
embeddings RAG — the category is already conceding that structural precision + freshness beats a vector
index for code.

---

### Sources

- aider: [Building a better repository map with tree-sitter](https://aider.chat/2023/10/22/repomap.html) ·
  [repo map docs](https://aider.chat/docs/repomap.html) ·
  [DeepWiki: Repository Mapping System](https://deepwiki.com/Aider-AI/aider/4.1-repository-mapping-system)
- Cursor: [Securely indexing large codebases](https://cursor.com/blog/secure-codebase-indexing) ·
  [How Cursor Actually Indexes Your Codebase (TDS)](https://towardsdatascience.com/how-cursor-actually-indexes-your-codebase/)
- Continue: [Codebase retrieval docs](https://docs.continue.dev/features/codebase-embeddings)
- Sourcegraph Cody: [How Cody understands your codebase](https://sourcegraph.com/blog/how-cody-understands-your-codebase) ·
  [Anatomy of an AI coding assistant](https://sourcegraph.com/blog/anatomy-of-a-coding-assistant) ·
  [Changes to Cody plans](https://sourcegraph.com/blog/changes-to-cody-free-pro-and-enterprise-starter-plans)
- Agentic grep: [Claude Code Doesn't Index Your Codebase](https://vadim.blog/claude-code-no-indexing/) ·
  [Why coding agents still use grep](https://yage.ai/share/why-coding-agents-still-use-grep-en-20260327.html)
- [Repomix](https://github.com/yamadashy/repomix) · [gpt-repository-loader](https://github.com/mpoon/gpt-repository-loader) ·
  [LlamaIndex GPT Repo reader](https://llamahub.ai/l/readers/llama-index-readers-gpt-repo)
