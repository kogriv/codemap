# rag_for_git (rag-reviewer)

**Verdict:** learn (interim — Stage A only) · **Feeds:** R1-C13 (confirmed from outside), R1-C14, **R1-C59**
and **R1-C60** (new), M3.3 (stays deferred) · **Card status:** **hands-on (Stage A of three)** — §0
pre-registered before the run, reconciled in §0.4 (2026-09-12)

**Scope:** `sha256:300e0a010e351d0a91a7e006c3cc18047d7d400c94a525ddbe727f796a5e47d2` (R2 benchmark
`bquant.scope.json` — 280 files, 207 .py / 73 .md, bquant@cb89a24) · run mode: their indexer takes a git
clone + ref, so a **clone of the dogfood checkout with `cb89a24` checked out** (read-only on it), plus a
materialized staging to verify the id — both lines of the harness output checked

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

### 0.4 Reconciliation — Stage A (2026-09-12, `rag-reviewer` 0.7.0, library level)

Exact commands are in §Hands-on. One variable between the two builds: whether `scip-python@0.6.6` is on
`PATH`.

**Controls**

| # | outcome | how |
|---|---|---|
| **C1** | ✅ holds | `materialize.py` → `canonical scope_id: sha256:300e0a01…`, `280 files, 4331679 bytes, 112457 loc`, `git cb89a2434092 dirty=False`, `verify: staging scope_id == canonical ✓` |
| **C2** | ✅ holds | at cb89a24 `MACDZoneAnalyzer` **is** defined — `bquant/indicators/macd.py:48` — and `analyze_zones` at `bquant/analysis/zones/pipeline.py:718`. The class was removed from bquant *later*; the pinned commit is why the probe of the five earlier cards is still reproducible |
| **C3** | ✅ holds | ground truth re-run on this tree, not transcribed: fast build 9.9 s, deep build 3 m 40 s, then `query` / `report impact` / `call_contract` / `report architecture` — numbers in §Hands-on |
| **C4** | ✅ holds | same `stage_a.py`, same manifest file list (207 `.py`, all read), same ref; the only difference is `PATH` |

**Predictions**

| # | outcome | measurement |
|---|---|---|
| **P1** | ◐ **holds for the answer, and is sharper than I wrote it** | The backend is returned by `build_code_graph` as a third tuple element and printed by `reviewer index`; it is **not** stored — `GraphStore.upsert_nodes(repo, node_ids, branch)` has nowhere to put it, and no answer builder mentions it. The single occurrence of `graph_backend` in the answer layer is in the **bug-report** environment payload, and it reports the *setting* (`auto`), not the backend used. Two sub-cases, and only one is silent: `scip-python` **absent** → `scip_available()` is False and nothing at all is logged (measured: my run 1 emitted no warning); `scip-python` present but failing → `log.warning("SCIP-индексация не удалась, откат на tree-sitter")`. With an explicit `backend="scip"` they re-raise instead of degrading — *"явный выбор бэкенда: пробрасываем ошибку, не деградируем молча"* — which is the right call and is theirs, not mine |
| **P2** | ✅ **holds, by far more than the 10% I pre-registered** | Same 207 files: **CALLS 9779 (tree-sitter) vs 4914 (SCIP)**, and they are *not* nested sets — shared 2671, tree-sitter-only 7108, SCIP-only 2243. So **27.3%** of the default graph's call edges are confirmed by the exact one, and the default **misses 45.6%** of the exact edges. IMPLEMENTS runs the other way and is a clean subset: 52 ⊂ 138 |
| **P3** | ❌ **refuted — and the residue points at us** | `path#fqn` → dotted module id is a pure mechanical transform, and **2304 of 2354 (97.9%)** of their nodes land on an existing codemap node id. The 50 that do not are **nested definitions** — `cached.decorator.wrapper`, `_apply_modular_config.ModuleLevelFilter`, six `register_*.decorator` — which **codemap does not emit as nodes at all**. That is not an id-scheme disagreement; it is a gap of ours, found by mapping ids to theirs. (In the other direction 1921 of our 4225 nodes have no counterpart: modules, module-level constants, `__all__`, doc nodes — expected, their graph is functions/classes/methods only) |
| **P4** | ✅ holds | No whole-graph question exists in their surface. `graph/summaries.py` clusters **by path prefix**, not by graph structure; `graph/metrics.py` is edge counts by relation plus regression detection; `graph/family.py` answers "who else is like this node" per symbol. No cycles, no layers, no hubs, no coupling. **Six hands-on cards, six tools, both whole-graph columns still empty** (post 06's claim survives a sixth measurement) |
| **P5** | ✅ holds for the product, ❌ at store level | `get_impact(repo, pr)` takes no symbol: it computes *changed signatures in the diff → callers outside the diff*, so "blast radius of X" is not expressible in the product. But `GraphStore` has symbol-scoped `callers`, `callers_detailed`, `bases_of`, `in_degree` and `expand(node_ids, hops=2)` — a symbol-scoped blast radius **exists in the library** and is not exposed as a tool |

**Score:** four controls hold; of five predictions two hold as written, one holds in a sharper form, one is
refuted with a finding against us, one splits by layer. Nothing in the list was vacuous, and the refuted one
(P3) produced the most useful item of the stage.

### Surprises — nothing below was on the list

**S1 — the two backends disagree by mechanism, not by margin, and the damage is concentrated.** 98.3% of the
7108 tree-sitter-only call edges point at a **simple name that is ambiguous inside the scope**: `.get()` fans
out to seven different `get` methods (`DiskCache.get` 153, `MemoryCache.get` 153, `CacheManager.get` 152, …),
`.info()` to both `ContextualLogger.info` and a module-level `info` (152 each). Name resolution multiplies
one call site into one edge per same-named symbol. The consequence is uneven, and saying only "72% of the
edges differ" would overstate it: on a **distinctively named** symbol the default is nearly as good as the
exact backend (see S2), and on common method names it is unusable. Both statements are needed.

**S2 — three independent implementations, and the two exact ones agree exactly.** Callers of
`MACDZoneAnalyzer` and its members, code roots only, distance 1:

| | callers | vs codemap |
|---|---|---|
| codemap (deep tier) | **58** | — |
| their **SCIP** backend | **60** | a strict **superset**: all 58, plus 2 intra-class calls (`MACDZoneAnalyzer.analyze_complete`, `.analyze_complete_modular`) that codemap does not count as inbound |
| their **tree-sitter** default | **58** | same *count*, **not the same set**: 57 shared, one each way — it drops `tests.unit.test_macd_analyzer.…test_convenience_functions`, which both exact resolvers find |

Two exact resolvers with no code in common produce the same 58 callers, and the difference at the seams is a
*definitional* one (does a class calling its own method count) rather than an error. The equal count from the
default backend is a coincidence of one dropped and one invented — the kind of agreement that would have
survived a count-only comparison and not a set comparison.

**S3 — their empties are already two kinds, and their fallback is not labelled.** `find_callers` returns
`"(граф недоступен)"` when the store is down and `"(вызовов не найдено)"` when the answer is genuinely empty
— R1-C44 (`unknown` ≠ `none`), independently implemented, and traceable to their own brief
`PRI-276 neo4j-down-silent-gap`. `get_definition`, by contrast, falls back to **semantic retrieval** when the
graph finds nothing and returns the retrieved pack with no marker saying the answer changed provenance; the
two branches are distinguishable only by output format. Same tool, two different habits — which is exactly
the pattern the `.pyi` finding on our own side was about (one concept, several places).

**S4 — they measure graph completeness across rebuilds and we do not.** `reviewer index` reads the previous
edge counts *before* rebuilding and prints `⚠ Просадка полноты графа против предыдущего индекса ветки` when a
relation's count drops (`graph/metrics.py`, their brief `PRI-252`). codemap has provenance and a schema
version, and nothing that says "this build resolved 30% fewer calls than the last one on the same tree" —
the exact failure our own post 04 is about. **This is the item to take.**

**S5 — construction is deterministic on both backends.** Two runs each, same 207 files: tree-sitter
2354 nodes / 9831 edges twice, SCIP 2354 / 5052 twice, node and edge sets identical both times (4.6 s / 4.5 s
and 52.6 s / 51.3 s). Their *artifact* is a Neo4j database plus a ParadeDB index and is not diffable, so the
determinism verdict splits the way GitNexus's did — the **answer** is stable, the **artifact** is not
comparable byte-wise. The artifact half is not measured until Stage B.

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
- Repo / site: [mimfort/rag_for_git](https://github.com/mimfort/rag_for_git) (default branch `dev`)
- License: **MIT** (read/learn freely; no code copied)
- Last commit / release: HEAD `bfcefdf` (2026-09-06) · release v0.7.0 (2026-08-26) · PyPI `rag-reviewer`
  **0.7.0** (2026-08-26), 20 runtime deps
- Stack / language: Python 3.11–3.13 · tree-sitter · `scip-python` (optional, external, npm) · ParadeDB
  (pgvector + BM25, RRF) · Neo4j 5 · MCP (`FastMCP`) · Voyage embeddings + reranker (`voyageai` is a hard
  dependency)
- Install (exact command, Stage A):
  ```bash
  uv venv --python 3.12 venv_rr && VIRTUAL_ENV=venv_rr uv pip install rag-reviewer==0.7.0
  npm install --prefix ./npm @sourcegraph/scip-python@0.6.6      # only for the SCIP half
  ```
  **reproduced: yes** for the library layer (one retry — a PyPI download of `aiohttp`, pulled in by
  `voyageai`, timed out the first time). Stages B and C not installed; see §0.2 and "what we did NOT check".

## What it is
An **AI pull-request reviewer**, not a graph service: hybrid retrieval (ParadeDB — BM25 + pgvector fused by
RRF) plus a code graph (Neo4j), driving Claude Code / Codex to post inline PR comments. The code graph is a
component of that product, and every graph-bearing MCP op is keyed by `(repo, pr)` — the unit of work is a
pull request.

- **Graph model:** one node label `Symbol {repo, branch, id}` with `id = path#fqn`
  (`bquant/analysis/zones/models.py#ZoneAnalysisResult._load_pickle`), three relation types — `CALLS`,
  `IMPLEMENTS`, `TESTED_BY`. Functions, classes and methods only; no module, constant or doc nodes.
- **Two graph backends, one surface:** `scip` (exact `CALLS` + method-level `IMPLEMENTS`, via a real
  `index.scip` from `scip-python` run in a temporary git worktree, with class inheritance added back by
  tree-sitter because scip-python 0.6.6 misses it) and `treesitter` (name-resolved `CALLS` only). `auto` —
  the default — picks SCIP if the binary is on `PATH`. Measured consequences: §0.4 P1/P2, S1.
- **Needs a build:** not source-only. A clone plus a git ref, a running ParadeDB and Neo4j, an embedding API
  key for the retrieval half.
- **Deterministic:** graph construction yes, byte-for-byte on two runs per backend (§0.4 S5). The artifact is
  a database, so it is not comparable the way a JSON file is.

## Coverage vs codemap

| Capability | codemap | this tool |
|---|---|---|
| symbol lookup (T1) | ✅ | ◐ `get_definition` resolves via graph `find_symbol` (substring `CONTAINS` on the id) and **falls back to semantic retrieval unlabelled**; needs a PR session — not run (Stage C) |
| callers/callees (T2) | ✅ | ✅ in the graph — `callers_detailed`; measured at graph level, 58/60 callers (§0.4 S2) |
| impact / blast-radius (T3) | ✅ symbol-scoped, role-tagged | ✖ as a product — `get_impact(repo, pr)` is diff-scoped; ◐ in the library (`expand(hops)`) |
| signature-change surface (T4) | ✅ `call_contract`, per-caller posargs/kwargs/splat | ✖ `get_impact` names callers of a changed signature but never how each call site passes arguments |
| architecture / layers (T5) | ✅ | ✖ nothing whole-graph: clustering is by path prefix, metrics are edge counts (§0.4 P4) |
| determinism | ✅ artifact byte-identical (fast tier) | ◐ construction byte-identical; artifact is a DB |
| provenance / roots | ✅ core/tests/docs/examples roles | ✖ one repo+branch scope; `TESTED_BY` is the only role-ish edge |
| epistemic labels | ✅ envelope + per field | ◐ two kinds of empty in `find_callers`, a completeness field in `family`, and an unlabelled fallback in `get_definition` |
| graph-completeness regression | ✖ **(gap — ours)** | ✅ `detect_edge_regression` on every index |
| nested definitions as nodes | ✖ **(gap — ours, 50 on this scope)** | ✅ |
| MCP | ✅ 28 tools | ✅ ~20 tools, graph ops PR-keyed |
| languages | Python | Python (`tree-sitter-python` only) |
| license | MIT | MIT |

## Hands-on measurements (target: bquant)

**Scope:** `sha256:300e0a01…`, 280 files (207 `.py` / 73 `.md`), bquant@cb89a24, extracted with
`git clone` + `checkout cb89a24` (read-only on the dogfood checkout) and materialized; all 207 `.py` read by
both backends.

**Their graph, both backends, same files** (`build_code_graph(repo, ref, files, src_by_path, backend)`):

| | tree-sitter (what `pip install` alone gives you) | SCIP (`scip-python` on `PATH`) |
|---|---|---|
| nodes | 2354 | 2354 — **identical set** |
| `CALLS` | **9779** | **4914** |
| `IMPLEMENTS` | 52 | 138 (52 ⊂ 138) |
| build time | 4.6 s / 4.5 s | 52.6 s / 51.3 s |
| two runs identical | ✅ | ✅ |
| `CALLS` overlap | shared 2671 · ts-only 7108 · scip-only 2243 | |

**codemap ground truth, re-run on this tree** (deep tier, `--mode full`, 4 consumer roots + docs;
build 3 m 40 s; 4225 nodes, 89 core modules, 659 import edges):

| Task | Their answer | codemap | Notes |
|---|---|---|---|
| T1 `analyze_zones` | not run (needs Stage C) | 2 definitions, **ambiguity declared** (`ambiguous: true` + alternatives), exact signatures | their resolver is a substring `CONTAINS` match capped at 3 ids, with an unlabelled semantic fallback — mechanism read, answer not measured |
| T2 callers of `MACDZoneAnalyzer` | **60** (SCIP) / **58** (tree-sitter) | **58** (code roots, d1) · 66 with docs, split core 3 / docs 7 / examples 1 / scripts 2 / tests 53 | SCIP ⊃ codemap exactly (+2 intra-class); tree-sitter agrees on 57 of 58 and drops one. §0.4 S2 |
| T3 impact of `MACDZoneAnalyzer` | ✖ not expressible (PR-scoped) | **69 references**, risk HIGH, depth 2 (d1×66, d2×3), per-root calls/references split | their `expand(hops=2)` could answer it; no tool exposes it |
| T4 sig-change of `analyze_zones` | ✖ different question | **47 callers, 88 call sites** with per-caller `posargs`/`kwargs`/`splat`, by root: examples 27, research 26, tests 30, core 5; envelope carries `resolved.ambiguous` + `epistemic: partial` | **six hands-on cards, six tools, T4 answered by nobody but codemap** |
| T5 architecture | ✖ absent | 8 layers + inter-layer edges; **0 hard cycles**; 3 lazy tangles (29 modules, 27 independent loops); 1 never-executed tangle (19 modules, 20 loops); import scopes read: 633 module-level, 25 function-local, 1 `TYPE_CHECKING`, 0 `.pyi` | their clustering is directory rollup; §0.4 P4 |

**Cost/latency note.** Their per-question cost is not comparable yet: the graph ops run inside an
LLM-driven review session, so tool-call counts only mean something in Stage C. What is comparable is
construction: 4.6 s (tree-sitter) or 52.6 s (SCIP) for the graph alone, against codemap's 9.9 s fast /
3 m 40 s deep for a graph that also carries modules, docs, roles and import scopes.

## Quality (on the covered part)
- **accuracy** — SCIP backend: exact on T2 and a superset of codemap by a declared definitional difference.
  Default backend: 27.3% of its call edges confirmed by its own exact backend, and the error is concentrated
  on ambiguous simple names (98.3% of the extra edges).
- **determinism** — construction byte-identical per backend, two runs each. Artifact is a database.
- **cost** — not measured (Stage C).
- **speed** — 4.6 s / 52.6 s construction on 207 files.
- **setup friction** — high: docker compose (two services), a GitHub token, and a **paid embedding key** for
  the retrieval half. The library layer alone installs clean.
- **language coverage** — Python only.
- **license** — MIT, same as ours.
- **interface** — CLI + MCP; graph ops keyed by `(repo, pr)`.
- **honesty of claims** — good, and uneven in an instructive way: two kinds of empty in `find_callers`, a
  completeness field on `family`, `get_impact`'s docstring telling the agent it does not judge — against an
  unlabelled provenance change in `get_definition` and a backend choice that never reaches the answer.

## Разбор
- **What we'd take:** **graph-completeness regression detection** (§0.4 S4). They read the previous edge
  counts per relation *before* a rebuild and warn when a count drops on the same branch. codemap has
  provenance, a schema version and two tiers, and nothing that notices "this build resolved 30% fewer calls
  than the last one on the same tree" — which is the shape of the defect [post 04](../blog/04-the-determinism-test-that-was-right.md)
  is about, caught from the other side. Filed as a backlog candidate below.
- **What we'd do differently and why:** the **backend must reach the answer**. Two graphs that differ on 72%
  of their call edges cannot be selected by `PATH` and reported identically — R1-C13 exists because we made a
  neighbouring mistake and it cost a published claim (post 01). Their explicit-backend path already re-raises
  instead of degrading; it is the default that hides. Second: a `CONTAINS` substring resolver with a cap of 3
  will answer the wrong symbol silently on a codebase with `get`/`info`-shaped names; codemap resolves, then
  *declares ambiguity* with alternatives.
- **What the author knows that we didn't:** (1) that a rebuild is the natural place to measure completeness,
  and that the comparison is cheap if you store counts per relation; (2) that nested definitions —
  decorators-inside-methods, classes-inside-functions — are worth being nodes, which we found only by mapping
  their ids onto ours (50 on this scope); (3) that `TESTED_BY` deserves to be a first-class relation in the
  same graph rather than a separate op.
- **What we did NOT check** (§0.5 plus what the run added):
  - **Stages B and C were not run**: no Neo4j, no ParadeDB, no embedding key. So every *product* answer above
    is read from source, not measured — T1 in particular.
  - **The retrieval half is entirely unmeasured** (BM25 + pgvector + RRF + reranker), and it is half the tool.
  - **`TESTED_BY` was never populated** in our run — no edge of that type appeared, and we did not establish
    what produces it.
  - **One target, one commit, 207 files.** Nothing here speaks to scale, and both SCIP and Neo4j are built
    for trees far larger.
  - **Their test suite was not run.** Their PR-review output was never invoked, and no write of any kind
    touched their repository or anyone's PR.
  - **The 2243 SCIP-only edges were not individually verified** — sampled and spot-checked against codemap's
    own answers, not audited.

## Verdict & backlog effect

**Interim verdict (Stages A only): learn — an adjacent product with one capability we should copy.** It is
not a competitor in the T1–T5 sense: three of our five task rows are structurally absent, and the product
that *is* there (PR review) is not something codemap does. What it carries back is real, though:

- **New backlog candidate — graph-completeness regression.** Store per-relation resolution counts with the
  graph and warn when a rebuild of the same tree resolves materially fewer; we have the provenance to do it
  and the two-tier split to make it meaningful.
- **New backlog candidate — nested definitions as nodes.** 50 symbols on this scope exist in their graph and
  not in ours, and our absence is undeclared, which is the class R1-C53 is about.
- **R1-C13 confirmed from outside.** An independent implementation shipped the same silent-resolver-degrades
  hazard, with the same root cause (a binary on `PATH`), and its answers carry no trace of which graph
  produced them. The rule is not our idiosyncrasy.
- **R1-C14 (differentiators) holds and gains a sixth data point.** Whole-graph questions and the
  signature-change surface remain unanswered by any measured peer; role-tagged provenance likewise.
- **M3.3 (deferred DB backend) stays deferred, now with a second measurement behind it.** Neo4j here buys
  symbol-scoped traversal that a JSON graph already gives us, at the price of two services and a
  non-diffable artifact.
