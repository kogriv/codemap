# rag_for_git (rag-reviewer)

**Verdict:** — (not yet measured) · **Feeds:** R1-C13, R1-C14, M3.3 (deferred) · **Card status:**
**§0 pre-registered, run not started** (2026-09-12)

**Scope:** `sha256:300e0a010e351d0a91a7e006c3cc18047d7d400c94a525ddbe727f796a5e47d2` (R2 benchmark
`bquant.scope.json` — 280 files, 207 .py / 73 .md, bquant@cb89a24) · run mode: to be decided in Stage A
(their indexer takes a git clone + ref, so a **git-archive extract of the pinned commit**, not the live
checkout — the procedure in [`README.md`](README.md))

---

## 0. Pre-registration (written and committed **before** the run)

This card's measurements will be published (comparison hub, positioning, and probably a post), so the run
carries pre-registered expectations the same way a dogfood run does: **controls** that must hold, **predictions**
I expect to fail, a **stop rule**, and a declared boundary. Reconciliation goes in §0.4 with anything unlisted
reported as a surprise. A green run with no list proves only that nothing crashed.

Everything in §0.1 comes from **reading their public repository**, not from running it. It is desk material and
is labelled as such; if a measurement later contradicts any of it, the measurement wins and the contradiction
is recorded.

### 0.1 Why this tool, and what reading it already showed

- **Repo:** [mimfort/rag_for_git](https://github.com/mimfort/rag_for_git) · ★21 · **MIT** · Python
  (`>=3.11,<3.14`) · created 2026-06-07 · default branch `dev`, HEAD `bfcefdf` (2026-09-06) ·
  latest release **v0.7.0** (2026-08-26) · PyPI `rag-reviewer` 0.7.0 (same date), 20 runtime deps.
- **What it actually is:** an **AI pull-request reviewer** — hybrid RAG (ParadeDB: BM25 + pgvector, RRF) plus
  a code graph (Neo4j), driving Claude Code / Codex to leave inline PR comments. The desk roster
  ([`../05_curated_sources.md`](../05_curated_sources.md)) called it a "hybrid index + Neo4j call graph",
  which is accurate about the component and wrong about the product. **The code graph is a means here, not
  the deliverable** — and that difference is the first thing this card has to measure rather than assume.
- **Why it is still the closest next разбор of the eight left in R2.2:**
  1. **`path#fqn` as the single symbol key** — codemap's canonical id / SCIP-descriptor idea, arrived at
     independently by someone solving a different problem.
  2. **Neo4j under the graph.** codemap's **M3.3 (a database backend) is deferred by decision** — "a graph in
     a file you can `git diff` beats a database". Neo4j now appears in a second peer (after GitNexus). A
     measurement is the only honest way to keep that decision or drop it.
  3. **SCIP.** `reviewer/graph/scip.py` + a vendored `scip.proto` parse a real `index.scip` produced by
     `scip-python`. codemap ships SCIP *interop* and no resolver dependency; this tool takes the other side of
     exactly that trade.
  4. **It will attack a published differentiator.** Post 06 published that two columns are empty in every peer
     measured so far — whole-graph questions, which have no seed symbol. This tool has a real call graph in a
     real graph database, so it is the most likely of the eight to fill one. A разбор that cannot cost us
     anything is not worth running.
- **Surface, read off `reviewer/entrypoints/`:**
  - CLI (`reviewer`): `start` / `stop` (docker compose), `index <clone> [--ref]`, `search`, `status`,
    `check`, `gc`.
  - MCP (`reviewer-mcp`): `prepare_review(repo, pr)` **first**, then `search_code`, `get_definition`,
    `find_callers`, `get_related_symbols`, `get_impact(repo, pr)`, `read_file`,
    `get_changed_file_diff`, plus a task-board half (`index_task`, `sync_board`, …) that is out of scope here.
  - **Every graph op is keyed by `(repo, pr)`.** The unit of work is a pull request, not a repository.
- **Infrastructure it needs:** docker compose (ParadeDB + Neo4j 5), `GITHUB_TOKEN`, and
  **`VOYAGE_API_KEY`** — `voyageai` is a hard runtime dependency and `EMBEDDING_MODEL=voyage-code-3` is the
  default, with no local-embedding option visible in `.env.example`. GitNexus and cocoindex-code both ran
  embeddings locally; this one does not appear to.
- **The thing in their source I most want to measure** (`reviewer/graph/backend.py`, their own docstring):
  > `auto` mode picks SCIP when `scip-python` is on `PATH`, **and otherwise silently falls back to
  > tree-sitter** — exact `CALLS` + `IMPLEMENTS` from SCIP versus name-resolved `CALLS` only.

  Two materially different graphs behind one answer surface, selected by whether a binary happens to be
  installed. That is the class this project spent two months closing (R1-C13), and it is the mechanism of
  [post 01](../blog/01-the-competitor-wasnt-broken.md): a peer's impact analysis looked broken and the cause
  was **our** `PATH`. An independent implementation reproducing the same hazard — and documenting it in its
  own docstring — is the most valuable thing this разбор can carry back.
- **Two more of their own records worth reading before measuring** (they keep briefs in-repo):
  `docs/superpowers/briefs/2026-08-14-PRI-252-scip-graph-edge-count-regression.md` and
  `2026-08-30-PRI-276-neo4j-down-silent-gap.md`. The second is, by its title, our own central defect class
  — a silent gap when the graph is down — found by another author in their own product. The `index` command
  already prints `⚠ Просадка полноты графа против предыдущего индекса ветки` from
  `graph/metrics.py:detect_edge_regression`, i.e. **they measure graph completeness across rebuilds**. We do
  not, except via schema/provenance.

### 0.2 The plan: three stages, cheapest first, with a stop rule

| stage | what it needs | what it can answer |
|---|---|---|
| **A** — library level | a venv + tree-sitter; `scip-python` from npm for the second half. No docker, no keys | `build_code_graph` on the pinned scope, **twice**: with and without `scip-python` on `PATH`. Node/edge counts, the edge vocabulary, `path#fqn` identity, and the cost of the silent fallback |
| **B** — graph store | + docker (Neo4j only) | their graph answers at store level — T1/T2, and whether T3 is expressible without a PR |
| **C** — the product | + ParadeDB, `GITHUB_TOKEN`, **a paid `VOYAGE_API_KEY`** | `reviewer index` end to end, MCP `prepare_review` against an **existing merged** PR, `search_code`, `get_impact` |

**Stop rule, fixed here:** if Stage C needs a paid key, **stop after B** and publish the card as
`hands-on (stages A–B)` with the boundary stated in §Разбор → "what we did NOT check". Do not buy a key, do
not ask the author for one, do not substitute a different embedding model and report it as theirs.

**What must not happen, whatever the stages produce:** no write of any kind to their repository (no issue,
no PR, no comment); no PR created anywhere to make a probe possible — if the PR-keyed ops need a PR, the only
admissible one is an **already-merged PR in a repo the owner already owns** (bquant #111 is the merge commit
of the pinned scope itself, which is why it is the candidate); no edit to the bquant checkout — the pinned
tree comes out via `git archive`, which reads.

### 0.3 Expectations

**Controls** — must hold; a failed control means the *measurement apparatus* is wrong, not the tool.

| # | control | refuted by |
|---|---|---|
| **C1** | The staging tree resolves to the canonical `scope_id` `sha256:300e0a01…`, and the harness prints both the id line and `verify: staging scope_id == canonical ✓` | any other id, or a missing verify line |
| **C2** | Both probe symbols exist at bquant@cb89a24 — `analyze_zones` **and `MACDZoneAnalyzer`**, which has since been *removed* from bquant. If it is absent at the pinned commit, the T2/T3 probe of the five earlier cards is not reproducible and this card must say so **before** reporting any number | `MACDZoneAnalyzer` absent at cb89a24 |
| **C3** | codemap's own ground-truth answers are **re-run on this tree**, not transcribed from the earlier cards (R1-C25: a moving target makes a measurement measure the target) | any ground-truth number quoted without a command in this card |
| **C4** | The two Stage-A builds differ **only** in whether `scip-python` is on `PATH` — same files, same ref, same process otherwise | any other difference between the two runs |

**Predictions** — I expect these to fail (that is the point of the run). If all five hold, the run still
produced a result, and a different one.

| # | prediction | refuted by |
|---|---|---|
| **P1** | **The silent fallback is silent in the answer.** The backend (`scip` vs `treesitter`) is named only on the `index` console line; no node, edge, store row or MCP answer payload carries it, so a consumer reading the answer cannot tell which graph produced it | any answer-level field naming the backend |
| **P2** | **The two backends disagree materially on our scope** — `CALLS` edge count differs by **>10%** between the SCIP and tree-sitter builds of the same 207 files | a delta ≤10% (then the silent fallback is cheap and my concern is overstated) |
| **P3** | **`path#fqn` is not quite our canonical id.** Being path-qualified, identity moves when a symbol moves file, and the two schemes disagree on at least one class of symbol on this scope (re-exports through `__init__.py`, conditional definitions) | a clean 1:1 mapping to codemap node ids across the scope |
| **P4** | **The two columns post 06 published stay empty.** Their graph is `CALLS` + `IMPLEMENTS`; I expect **T4** (signature-change surface) and **T5** (layers / cycles) to be structurally absent — no op answers a whole-graph question. *Genuinely uncertain:* `graph/metrics.py`, `graph/family.py` and `graph/summaries.py` may already do clustering or cycle work, in which case this is the finding that costs us a published differentiator | any op answering T4 or T5 without a seed symbol |
| **P5** | **Impact is PR-scoped, not symbol-scoped.** `get_impact(repo, pr)` takes no symbol, so codemap's T3 probe ("blast radius of `MACDZoneAnalyzer`") is not expressible in their product at all | a symbol-scoped impact path at CLI, MCP or store level |

### 0.4 Reconciliation

*Empty by design — filled after the run, with a separate "surprises" block for anything not listed above.*

### 0.5 What this run will not cover

- **The reviewer itself** — comment quality, false-positive rate, cost per review. That is their product and
  it needs an LLM in the loop; this card measures the **graph and retrieval layer** only.
- **The task-board half** of the MCP surface (`index_task`, `sync_board`, `create_task`, …) — adjacent
  product, not a code-graph capability.
- **Languages other than Python.** Their tree-sitter dep is `tree-sitter-python` only, and our scope is
  Python; nothing here says anything about other languages.
- **Their test suite.** Whether it passes is not measured unless Stage A needs it for a diagnosis.
- **Anything about scale.** 280 files on one scope is one point, and both the SCIP indexer and Neo4j are
  designed for trees much larger than that.

---

## Identity
- Repo / site: *see §0.1*
- License: **MIT** (read/learn freely; no code copied)
- Last commit / release: HEAD `bfcefdf` (2026-09-06) · release v0.7.0 (2026-08-26) · PyPI `rag-reviewer` 0.7.0
- Stack / language: Python 3.11–3.13 · tree-sitter · `scip-python` (optional, external) · ParadeDB (pgvector
  + BM25) · Neo4j 5 · MCP (`FastMCP`) · Voyage embeddings + reranker
- Install (exact command): *not yet run* — Stage A of §0.2
- reproduced? *not yet*

## What it is
*Not yet measured beyond the desk reading in §0.1.*

## Coverage vs codemap
*Filled after the run.*

| Capability | codemap | this tool |
|---|---|---|
| symbol lookup (T1) | ✅ | ? |
| callers/callees (T2) | ✅ | ? |
| impact / blast-radius (T3) | ✅ | ? |
| signature-change surface (T4) | ✅ | ? |
| architecture / layers (T5) | ✅ | ? |
| determinism | ✅ (fast tier, byte-identical) | ? |
| MCP | ✅ (28 tools) | ✅ (surface read, not measured) |
| languages | Python | Python (tree-sitter-python only) |
| license | MIT | MIT |

## Hands-on measurements (target: bquant)
*Not yet run — expectations are in §0.3 and must be reconciled in §0.4 before this section is trusted.*

| Task | Correct? | Cost (tokens/calls) | Latency | Deterministic? | Notes |
|---|---|---|---|---|---|
| T1 where defined (`analyze_zones`) | | | | | |
| T2 callers (`MACDZoneAnalyzer`) | | | | | |
| T3 impact (`MACDZoneAnalyzer`) | | | | | |
| T4 sig-change (`analyze_zones`) | | | | | |
| T5 architecture | | | | | |

## Quality (on the covered part)
*Filled after the run.*

## Разбор
- **What we'd take:** *after the run.*
- **What we'd do differently and why:** *after the run.*
- **What the author knows that we didn't:** *after the run — the candidate going in is graph-completeness
  regression detection across rebuilds (`detect_edge_regression`).*
- **What we did NOT check:** *§0.5 is the pre-run version of this list; it gets extended, never trimmed.*

## Verdict & backlog effect
*After the run.*
