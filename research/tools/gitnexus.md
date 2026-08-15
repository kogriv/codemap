# GitNexus

**Verdict:** learn (strong peer, different niche)  ·  **Feeds:** R1-C13, R1-C14, R1-C15 (+ new gap: semantic search / flow-tracing)  ·  **Card status:** hands-on

**Scope:** `sha256:300e0a010e351d0a91a7e006c3cc18047d7d400c94a525ddbe727f796a5e47d2`
(R2 benchmark `bquant.scope.json` — 280 files, 207 .py / 73 .md, bquant@cb89a24) ·
run mode: **materialized** (byte-identical staging via `_scope/materialize.py`, `scope_id` verified == canonical).
GitNexus walks a working tree and wants a `.git` (or `--skip-git`); it can't take a file list, so it gets the
staging, exactly the venv-trap escape hatch the harness exists for. One file (`>512 KB`, the embedded sample
`bquant/data/samples/embedded/tv_xauusd_1h.py`) is skipped by GitNexus's default large-file cap — noted, not a
scope deviation (the file is in the manifest; GitNexus just declines to parse it).

## Identity
- **Repo / site:** `abhigyanpatwari/GitNexus` · gitnexus.vercel.app · akonlabs.com (enterprise)
- **License:** **PolyForm Noncommercial 1.0.0** — commercial use requires an enterprise license. (codemap: MIT.)
- **Last commit / release:** v**1.6.9** (measured 2026-08-06 via `npm install gitnexus`).
- **Stack / language:** TypeScript / Node.js 24 (CLI + React web UI). Tree-sitter ASTs; **LadybugDB** embedded
  graph store (formerly KuzuDB) with a vector index; **transformers.js / ONNX** local embeddings.
- **Install (exact command):** `npm install gitnexus` (or `npx gitnexus`) · reproduced? **yes** — but the
  install is **1.7 GB of `node_modules`** (tree-sitter grammars + `onnxruntime-node` + native `lbugjs.node`).

## What it is
A **hybrid code-intelligence engine**: tree-sitter parse → symbol/edge graph in LadybugDB → Leiden community
**clustering** → **process/flow tracing** (call chains from entry points) → **BM25 + semantic (vector) search
with RRF**. Indexing is **LLM-free and deterministic**; an optional LLM only names clusters / writes the wiki.
Interfaces: **CLI**, **MCP** (`gitnexus mcp`, stdio + HTTP), **HTTP server** + **web UI**, Docker. Source-only
(no build/import of the target), but **git-oriented**: no `.git` → commit-tracking and incremental updates are
disabled, and change-detection (`detect-changes`) is a git-diff feature. 14 languages (Py/TS/JS/Java/Kotlin/
C#/Go/Rust/PHP/Ruby/Swift/C/C++/Dart); Py/TS/Java add type-annotation extraction.

Every answer carries an **`epistemic`** label (`"exact"` here) and per-edge `confidence` — a built-in
honesty signal codemap should note (see Разбор).

## Coverage vs codemap

| Capability | codemap | GitNexus |
|---|---|---|
| symbol lookup (T1) | ✅ | ✅ (`context`, surfaces ambiguity like codemap) |
| callers/callees (T2) | ✅ | ◐ (`context` = import fan-in + methods, not call-sites) |
| impact / blast-radius (T3) | ✅ | ✅ (`impact` = transitive import closure + risk + depth) |
| signature-change surface (T4) | ✅ | ✖ (no per-call arg contract; `detect-changes` ≈ codemap `review`) |
| architecture / layers (T5) | ✅ | ◐ (cycles + Leiden clusters + flows; no coupling/god-object metrics) |
| determinism | ✅ (diffable JSON) | ◐ (answer deterministic; artifact = 123 MB binary DB, non-diffable) |
| MCP | ✅ | ✅ (+ HTTP + web UI + Docker + 1-cmd editor setup) |
| semantic / vector search | ✖ | ✅ (BM25 + local embeddings + RRF) |
| community clustering + flow tracing | ✖ | ✅ (276 clusters · 294 process-flows) |
| languages | Python | 14 (tree-sitter) |
| license | MIT | PolyForm Noncommercial |

## Hands-on measurements (target: bquant, R2 scope)
Index: **6 344 nodes · 14 661 edges · 276 clusters · 294 flows**; artifact **123 MB `.gitnexus/`**
(105 MB LadybugDB `lbug` + parse caches). Index time **12–74 s** across runs (variance = embedding/model
warmup + machine load), vs codemap's ~1 min deterministic build (4.83 MB canonical JSON). codemap's answer is
the ground-truth reference.

| Task | Correct? | Cost | Latency | Deterministic? | Notes |
|---|---|---|---|---|---|
| T1 where defined (`analyze_zones`) | ✅ | 1 call | <1 s | yes | `context` → **ambiguous**, 2 candidates: `pipeline.py:717` func + `analyzer.py:121` method. Matches codemap's 2 defs (`pipeline.py:718`, `analyzer.py:122` — GitNexus off-by-one/decorator line). Both honestly surface the ambiguity. |
| T2 callers (`MACDZoneAnalyzer`) | ◐ | 1 call | <1 s | yes | `context` → `incoming: {imports: 22}`, `outgoing: {has_method: 3}`, `epistemic: exact`. Reports **import fan-in + methods**, not call-sites. codemap (deep/full build): 65 refs by role — core 2 · docs 7 · examples 1 · scripts 2 · **tests 53**. Different model — file-import vs symbol-reference. |
| T3 impact (`MACDZoneAnalyzer`) | ✅ | 1 call | <1 s | **yes (A/B identical)** | `impact` → upstream transitive import closure: **48 impacted** (direct 5; byDepth 5/15/28), **risk MEDIUM**, `epistemic exact`, per-edge confidence. Richer depth+risk than codemap; but **file-level & provenance-blind** (codemap splits by role, symbol-level, 1 hop). Both correct in their own model. |
| T4 sig-change (`analyze_zones`) | ✖ | — | — | — | No per-call argument contract / signature-change surface. `detect-changes` (git diff → symbols + flows) is the analog of codemap **`review`**, not T4 — and it **requires git** (errored on the git-less staging). |
| T5 architecture | ◐ | 1 call | <1 s | yes | `check --cycles` → **3 import cycles** (correct, file-level). Plus 276 **Leiden clusters** + 294 **process-flows** — groupings codemap lacks. But **no** layers / coupling (Ca/Ce/instability) / god-objects metrics that codemap's `architecture` report gives. |

**A note on codemap's own count (cross-card consistency).** The **non-test** reference count for
`MACDZoneAnalyzer` is a stable invariant — **12** (core 2 · docs 7 · examples 1 · scripts 2) — and matches the
[graphlens card](graphlens.md) exactly. The **test** count differs by *codemap build depth*: this card's
`--deep --mode full` build resolves 53 test references (jedi deep call resolution), where the graphlens card's
shallower build surfaced 19. Tests are call-dominated (depth-sensitive); non-test is import-dominated (stable).
When comparing across cards, the depth-invariant **12 non-test** is the figure to trust.

**Determinism, measured honestly.** Two independent clean-room stagings (same `scope_id`) → **identical
counts** (6 344/14 661/276/294) and a **byte-identical `impact` answer** (sorted JSON). GitNexus's
"deterministic indexing" claim holds at the answer level. Caveats: (1) the artifact is a **123 MB binary
LadybugDB** (WAL) — the *answer* is reproducible, the *artifact* is not `git diff`-able like codemap's JSON;
(2) re-`analyze` **without** `clean` is **non-idempotent** — it merged into the old index and drifted
6 344 → 6 356 nodes (a fresh index is stable; an in-place re-index is not); (3) cluster *count* is stable,
membership not verified.

## Quality (on the covered part)
- **accuracy** — T1/T3 correct; T2 correct-but-different-model (imports, not calls); honest ambiguity on T1.
- **determinism** — answer deterministic ✓; artifact non-diffable (binary DB) ◐; in-place re-index non-idempotent.
- **cost** — heavy: 1.7 GB `node_modules`, 123 MB index for 4.3 MB of source (~28× the input; codemap ~1.1×).
- **speed** — 12–74 s index (variance from embedding warmup); queries sub-second.
- **setup friction** — high (Node + native modules + ONNX runtime + 1.7 GB); but `gitnexus setup` auto-wires
  MCP into Claude Code/Cursor/Codex in one command — the *agent onboarding* is smoother than codemap's.
- **language coverage** — 14 langs (tree-sitter) vs codemap's Python-deep-only.
- **license** — **PolyForm Noncommercial** — a hard blocker for commercial use; codemap's MIT is the differentiator.
- **interface** — richest of the field: CLI + MCP + HTTP + web UI + Docker; `context`/`impact`/`trace`/
  `cypher`/`query`/`detect-changes`/`check`/`wiki`.
- **honesty-of-claims** — high: `epistemic` + per-edge `confidence` on every answer; large-file skips announced;
  git-degradation warned. This is a model to learn from.

## Разбор
- **What we'd take** (with where from):
  - **Per-answer epistemic labels + edge confidence** (`epistemic: "exact"`, `confidence: 1`). codemap labels
    *approximations* structurally; GitNexus attaches a confidence to *every* answer/edge. → R1-C13 (honesty),
    a small, high-value ergonomic.
  - **Transitive, depth-bucketed impact + a risk rating** (`byDepth {1:5,2:15,3:28}`, `risk: MEDIUM`).
    codemap's `impact` is one-hop by design; an opt-in transitive closure with a depth histogram + a coarse
    risk band is a natural extension. → reranks R1-C? (impact depth).
  - **Process / flow tracing** (call chains from entry points, 294 flows) and **community clustering** (Leiden)
    — a "how execution moves through the system" lens codemap doesn't have. → new gap (below), candidate for a
    codemap `flows` / `communities` view atop the existing call graph.
  - **One-command agent onboarding** (`gitnexus setup` wires MCP into every detected editor). codemap's MCP is
    a manual config; a `codemap setup` would lower adoption friction. → R1-C14 (positioning: adoption).
- **What we'd do differently and why** (mandatory):
  - **Keep the artifact a canonical, diffable JSON, not a 123 MB binary DB.** GitNexus's LadybugDB answer is
    reproducible but the store isn't reviewable in a PR; codemap's whole determinism thesis is a graph you can
    `git diff`. The *why*: an index an agent can't diff can't be trusted to be fresh-and-reviewed — 28× input
    size in an opaque WAL is the opposite of "commit the index."
  - **Keep impact provenance-split and symbol-level, not file-import-level.** GitNexus's `impact` is a file
    IMPORTS closure; it can't tell you "5 of these 48 are tests, 7 are docs." codemap's per-role, per-symbol
    answer is more actionable for "what actually breaks in *core*." The *why*: blast-radius without provenance
    over-counts (tests dominate) and under-locates (file, not symbol).
  - **Don't require git for the graph.** GitNexus disables incremental + change-detection without `.git` and
    errors `detect-changes` on a bare tree. codemap graphs any directory. The *why*: analysis shouldn't be
    gated on VCS state — you often want the map of a checkout/tarball/vendored dir.
- **What the author knows that we didn't** (the most valuable part):
  - **Semantic retrieval belongs *next to* the structural graph, not instead of it.** GitNexus fuses BM25 +
    local embeddings (RRF) with the graph so an agent can go from a fuzzy concept → the right symbols → their
    exact structure. codemap deliberately has no fuzzy layer; GitNexus shows the two compose well. This is the
    single biggest thing to learn — it reframes codemap as "the precise structural leg" that a retrieval layer
    *feeds into* (which is exactly the positioning thesis, now with a concrete peer proving the split works).
  - **Clustering + flows turn a call graph into a *narrative*.** 276 communities + 294 entry-point flows is a
    higher-altitude "how does this system work" answer than any single symbol query — closer to R1-C15
    (living docs) than to T1–T5.
- **What we did NOT check** (honest boundary):
  - Semantic `query` **quality** (did it retrieve the *right* flows for a concept?) — only that it runs.
  - `wiki` generation (needs an LLM key), `trace <from> <to>`, `group` cross-index impact, the web UI, and
    multi-language behavior (measured Python only, on the shared scope).
  - Cluster **membership** determinism (only the count, 276, was shown stable across A/B).
  - MCP transport (measured the CLI, which is the same graph; MCP wiring not exercised end-to-end).

## Verdict & backlog effect
**learn (strong peer, adjacent niche).** GitNexus is a *semantic + structural hybrid retrieval engine* for
"understand a repo / feed an agent" — multi-language, git-integrated, embeddings-backed, with a heavy binary
index. codemap is the *deterministic, diffable, provenance-precise, Python-deep structural leg*. They are
**complementary, not competing** — GitNexus is living proof of the positioning thesis (precise graph ← fed by
→ retrieval layer). 
- **Confirms R1-C14** differentiators with a concrete foil: MIT vs PolyForm-NC, 4.83 MB diffable JSON vs
  123 MB binary DB, provenance/symbol-level impact vs file-import closure, no-git-required, real T4 (call
  contracts) it lacks.
- **Feeds R1-C13** (honesty): adopt per-answer `epistemic` + edge `confidence`.
- **Adds a gap** (→ comparison.md): **semantic search + flow-tracing + community clustering** — a retrieval/
  narrative axis codemap doesn't have and, per the thesis, should *interoperate with* rather than build.
- **Nudges R1-C15** (living docs): clusters + flows are the raw material for a generated, honestly-labeled wiki.
- **Integration stance (R1-C16 licensing policy, decided 2026-08-06):** GitNexus can be a **routable opt-in
  plugin** (codemap calls a user-installed GitNexus, never bundles it → codemap stays clean MIT), gated behind
  a one-time noncommercial-use disclaimer. The router (`codemap route`, mode 4) is **implemented**; its binary
  detection falls back to `npx --no-install gitnexus`, so a **local** `npm install gitnexus` is enough — no
  global install, no surprise download (R1-C16-f1, 2026-08-15). But because of the **PolyForm-NC license**, its unique capabilities
  (semantic search, multi-language) — if we build parity ourselves — are better wrapped around an **MIT/Apache**
  peer (cocoindex / graphlens), not GitNexus. So: **learn** for building, **routable opt-in** for using-as-is.
  See [DESIGN §13](../../DESIGN.md) licensing policy.
