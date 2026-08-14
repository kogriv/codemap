# comparison — codemap vs the field

The rolled-up view of the R2 deep-dive: coverage matrix (tools × capabilities) and quality summary, built
from the per-tool cards in [tools/](tools/). Method & convention: [README.md](README.md). Desk-level rows
come from R1; hands-on rows are filled as each card is measured on the common target (bquant).

**Legend:** ✅ yes · ◐ partial · ✖ no · ? not yet measured · — N/A.
**Card status:** `desk` = from R1 survey · `hands-on` = installed & measured on bquant.

**Benchmark scope (parity anchor).** Every `hands-on` row is measured on the shared R2 scope
[`tools/_scope/bquant.scope.json`](tools/_scope/bquant.scope.json) — **`scope_id
sha256:300e0a01…5e47d2`**, 280 files (207 .py / 73 .md), `bquant@cb89a24`, venv-free by git enumeration.
A card is only comparable here if its **Scope** field carries this `scope_id` (or notes the deviation, as
graphlens does — measured on a near-identical pre-harness staging). codemap runs in place; venv-trap tools
get a byte-identical staging via [`materialize.py`](tools/_scope/materialize.py).

## Coverage matrix

| Tool | Card | T1 defs | T2 callers | T3 impact | T4 sig-change | T5 arch | Determ. | MCP | Langs | License |
|---|---|---|---|---|---|---|---|---|---|---|
| **codemap** | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Py | MIT |
| graphlens | [card](tools/graphlens.md) | ✅ | ✅¹ | ✅¹ | ✖ | ✖ | ✖ | ✅ | Py/TS/Go/Rust/PHP | MIT |
| CodeGraph (colbymchenry) | ? | ? | ? | ? | ? | ? | ? | ✅ | multi | MIT |
| **GitNexus** | [card](tools/gitnexus.md) | ✅ | ◐² | ✅² | ✖ | ◐² | ◐² | ✅ | 14 (tree-sitter) | PolyForm NC |
| OntoIndex | ? | ? | ? | ? | ? | ? | ? | ✅ | multi | ? |
| Sentrux | ? | — | — | ? | ? | ✅ | ✅ | ✅ | 52 | ? |
| cocoindex-code | ? | ✅ | ✖ | ✖ | ✖ | ✖ | ✖ | ? | multi | Apache-2.0 |
| rag_for_git | ? | ✅ | ✅ | ◐ | ? | ? | ✖ | ✖ | ? | OSS |
| Understand-Anything | ? | ? | ? | ? | ? | ? | ? | ? | multi | OSS |

_Rows are seeded from R1/R1.5 (desk-level, hence `?`); each becomes measured as its card moves to
`hands-on`. `codemap` is the ground-truth reference for T1–T5._

² GitNexus (v1.6.9), hands-on on the R2 scope (materialized staging, `scope_id` verified). **T1** ✅
`context` surfaces the same 2-def ambiguity codemap does. **T2** ◐ `context` returns import fan-in (22) +
methods, **not** call-sites — a file-import model, not codemap's 65 symbol-refs by role. **T3** ✅ `impact`
is a transitive upstream **import closure** (48 impacted; byDepth 5/15/28; `risk: MEDIUM`; per-answer
`epistemic`/`confidence`) — richer in depth+risk, but file-level and **provenance-blind**. **T4** ✖ no
per-call argument contract (`detect-changes` ≈ codemap `review`, and needs git). **T5** ◐ `check --cycles`
(3 cycles) + 276 Leiden clusters + 294 flows, but no coupling/god-object metrics. **Determinism** ◐: answer
is byte-identical across clean-room A/B, but the artifact is a **123 MB binary LadybugDB** (non-diffable), and
in-place re-`analyze` without `clean` is non-idempotent. Setup is heavy (**1.7 GB `node_modules`**), license is
**non-commercial**. Net: a strong, adjacent **semantic+structural hybrid** — complementary, not competing. See
the [card](tools/gitnexus.md).

¹ graphlens (v0.4.0), re-measured on the fair scope (same 6 dirs codemap indexes) **with the `ty` LSP
working**: **T1–T3 all work.** `search` finds the flagship symbol (~260 ms); `relations` returns a real
resolved call graph (`resolver_status: ok`) — on `MACDZoneAnalyzer`: 9 callers + 1 callee + 2 refs (tests
auto-excluded by design), ≈ codemap's 12 non-test refs. **Correction:** the first pass reported T2/T3
*empty*, but that was **our** environment — graphlens bundles `ty` yet resolves it via `shutil.which("ty")`,
and `uv tool install` leaves the bundled `bin/` off `PATH`, so it silently fell back to tree-sitter-only.
Fixed by putting the bundled bin on `PATH`; then indexing goes type-resolved (**2 m 20 s / 424 MB / 31 MB DB
/ 32 399 nodes / 55 691 edges**, vs the degraded **12 s / 246 MB / 17.5 MB / 16 796 nodes**). T4/T5 remain
genuinely absent (surface is only search/relations/info). (The separate > 3h45m / 9 GB / 1.1 GB catastrophe
was the venv trap — repo-root scope pulling `venv_bquant` because graphlens ignores `.gitignore`; point it at
a clean source tree.) See the [card](tools/graphlens.md).

## Quality summary

Filled per axis (accuracy · determinism · cost · speed · setup · languages · license · interface ·
honesty) as cards complete. See each card's Quality section for detail.

| Tool | Standout strength | Standout weakness | Verdict | Feeds |
|---|---|---|---|---|
| graphlens | working type-resolved impact (≈codemap non-test); resolves into deps; 5 languages; minimalist 3-verb MCP; smart test-de-emphasis | no arch/sig-change tools (no T4/T5); non-deterministic DB; **`ty`-on-PATH gotcha** silently degrades impact; venv-scoping trap; 12× index cost | learn (competent peer) | R1-C13, R1-C14 |
| GitNexus | hybrid semantic+structural: BM25+embeddings+RRF search, Leiden clusters + 294 process-flows, transitive risk-rated impact, per-answer `epistemic`/`confidence`, 14 langs, MCP+HTTP+web, 1-cmd editor setup | **non-commercial license**; 1.7 GB install + 123 MB binary non-diffable index (28× input); T2 is import-fan-in not call-sites; no T4 (call contracts) & partial T5 (no coupling/god-objects); **git-required** for incremental/change-detection | learn (strong, adjacent niche) | R1-C13, R1-C14, R1-C15 |
| PyCG | academic reference for Python call-graph accuracy; hand-labeled micro/macro benchmark corpus (the ~99%P/~70%R ceiling citation) | **does not run on Python 3.12** (import-hook surgery collides with stdlib; fails on a 3-line file); batch CLI, not a service; unmaintained (0.0.8, 2021) | learn (methodology only — spike-negative as a live oracle) | R1-C13 |

## Where codemap is not closed

Running list of gaps surfaced by the разбор — capabilities peers have that codemap lacks, each linked to a
backlog candidate. Populated as cards complete.

- **Cross-boundary resolution into dependencies** — graphlens resolves calls *into* third-party libs
  (e.g. "what pandas API does bquant call"); codemap is source-only-of-target and does not. By design, but
  logged as a possible capability door. ([graphlens card](tools/graphlens.md))
- **Incremental / watch-mode freshness** — graphlens persists to SQLite and re-indexes on file-change
  (`serve --watch`); codemap rebuilds in-memory. codemap's M18/M3.2 (freshness sidecar + `refresh`) is the
  partial answer; a true incremental graph is still open. ([graphlens card](tools/graphlens.md))
- **Agent context-budget shaping** — graphlens's `relations` *deliberately* drops test call-sites by default
  so impact answers don't drown in tests (a traced ergonomics decision). codemap returns everything with
  provenance and leaves filtering to the caller — worth considering an opt-in `--exclude-role tests`.
- **Semantic retrieval + flow/community narrative** — GitNexus fuses BM25 + local embeddings (RRF) with the
  graph, and adds Leiden **community clustering** (276) + **process-flow tracing** (294 entry-point call
  chains). codemap has no fuzzy layer and no "how execution moves through the system" view. Per the positioning
  thesis this is a layer codemap should *interoperate with* (feed the precise graph into a retrieval/narrative
  tool), not necessarily build — but flows/communities atop the existing call graph are a candidate view.
  ([GitNexus card](tools/gitnexus.md))
- **Per-answer epistemic labels** — GitNexus tags every answer/edge with `epistemic` + `confidence`. codemap
  labels *approximations* structurally but doesn't attach a confidence to each answer — a small honesty
  ergonomic worth adopting. ([GitNexus card](tools/gitnexus.md))
- **Transitive, depth-bucketed, risk-rated impact** — GitNexus's `impact` returns a depth histogram
  (`byDepth`) + a coarse `risk` band over a transitive closure; codemap's `impact` is one-hop by design. An
  opt-in transitive mode with a depth histogram is a natural extension. ([GitNexus card](tools/gitnexus.md))

## Notes for codemap's own positioning (differentiators, measured)

- **Layout robustness** — codemap takes the package dir explicitly and never wanders into a venv/deps;
  graphlens indexed a 1.5 GB non-standard venv because it ignores `.gitignore` and matches venv names by a
  hardcoded list. codemap's "point at the package" model sidesteps this class of failure. (→ R1-C14)
- **Determinism & artifact size** — measured on the identical staging: codemap ~3.6 MB **canonical, diffable
  JSON** in ~1 min; graphlens a **31 MB SQLite DB** (non-diffable, WAL) in 2 m 20 s. Determinism + git-friendly
  artifact is a hard differentiator. (→ R1-C14)
- **Single-call, provenance-complete impact** — codemap `impact` returns one number split by role
  (core/docs/examples/scripts/tests) in a single call; graphlens needs two tools (`relations` for resolved
  code edges + `search exhaustive` for the file list) and hides tests by default. (→ R1-C14)
- **No-LSP-dependency robustness** — codemap resolves impact source-only via jedi/griffe with nothing to
  provision; graphlens's core impact silently degrades to tree-sitter if `ty` isn't on PATH (exactly the trap
  we hit). "Works out of the box, offline, deterministically" is a positioning line. (→ R1-C14)
- **T4/T5 coverage** — codemap has call-contract (signature-change surface) and architecture/layers ops;
  graphlens has no tool for either (3-verb surface). (→ R1-C14)
