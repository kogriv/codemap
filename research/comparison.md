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
| **CodeGraph** (colbymchenry) | [card](tools/codegraph.md) | ✅ | ✅⁴ | ✅⁴ | ✖ | ✖ | ◐⁴ | ✅ (1 tool) | 20 (Rust kernel) | MIT |
| **GitNexus** | [card](tools/gitnexus.md) | ✅ | ◐² | ✅² | ✖ | ◐² | ◐² | ✅ | 14 (tree-sitter) | PolyForm NC |
| OntoIndex | ? | ? | ? | ? | ? | ? | ? | ✅ | multi | ? |
| Sentrux | ? | — | — | ? | ? | ✅ | ✅ | ✅ | 52 | ? |
| cocoindex-code | [card](tools/cocoindex-code.md) | ◐³ | — | — | — | — | ◐³ | ✅ | multi (tree-sitter) | Apache-2.0 |
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

³ cocoindex-code `ccc` (0.2.41 on cocoindex 1.0.20), hands-on on the R2 scope (materialized staging,
`scope_id` verified; `ccc` also picked up the harness `manifest.json` via its broad default include).
**Semantic-only** — a vector index, **no symbol graph**, so T2–T5 are structurally **N/A** (`search "who calls
X"` returns similar *docs/tests*, not callers). **T1** ◐: `search` returns a relevant spread (scores 0.69–0.71,
def ranks #5 not #1), but bundled **`ccc grep`** (tree-sitter, no index) pinpoints defs exactly. **Where it
wins:** a concept query ("detect swing high/low pivot points within a zone") nails
`strategies/swing/pivot_points.py` (0.72) with zero knowledge of names — the fuzzy leg codemap lacks.
**Determinism** ◐: answer byte-identical across runs, artifact is a binary LMDB/SQLite blob. Runs **fully
local, no DB, no API key** (280 files → 6403 chunks; **incremental re-index ≈ 1 s**). GPU blocked on **Pascal only**
(its torch 2.13/cu130 ships no sm_61 cubin); on an RTX 3070 the cold build runs **~4.5× faster** (48 s vs
216 s, same box, same scope). **Apache-2.0** makes it the first license-clean semantic-search tool codemap
can *wrap* (vs GitNexus's NC). See the [card](tools/cocoindex-code.md).

⁴ CodeGraph (1.6.0, npm), hands-on on the R2 scope (materialized staging, `scope_id` verified). The
**most-adopted tool measured so far** — 68 420 ★ — and on the questions it answers it is fast and right.
**Index:** 207 of the 280 scope files (`.md` are not in its model) → 5 113 nodes / 15 247 edges in **1.4 s**,
15.5 MB SQLite — **~9× faster than codemap's fast tier, ~68× than deep**. **T1** ✅ both real definitions
at codemap's exact lines, plus fuzzy neighbours and an inline `signature`; ambiguity is a ranked list but is
**never flagged as ambiguity**. **T2** ✅ **symbol-level**: 58 callers, and codemap's 57 are a *complete
subset* — the one extra is `assert isinstance(analyzer, MACDZoneAnalyzer)`, a **reference counted as a
call** (its own `--help` says "call"). **T3** ✅ 89 affected at depth 2, but a **flat, untagged** list —
codemap's 69 refs each carry `type` (calls 60 / references 9), `root` (core 3 · docs 7 · examples 1 ·
scripts 2 · tests 56), `distance` and an aggregate `risk`. **T4/T5** ✖ — no argument-level contract, no
layers/cycles. **Determinism** ◐: structure reproduces exactly across clean-room A/B (same counts, same DB
byte-size), the artifact does not (different md5), and `query` carries a wall-clock `updatedAt` per node, so
**one answer changes when nothing about the code did**. **Trap:** `--limit` defaults to **20**, the
file-kind rows sort first, and there is **no `truncated` flag** — the default answer reads as a file-import
model when the real one is symbol-level. Also ships the **debounced file watcher** codemap deferred
(**121 ms** incremental sync). See the [card](tools/codegraph.md).

## Quality summary

Filled per axis (accuracy · determinism · cost · speed · setup · languages · license · interface ·
honesty) as cards complete. See each card's Quality section for detail.

| Tool | Standout strength | Standout weakness | Verdict | Feeds |
|---|---|---|---|---|
| graphlens | working type-resolved impact (≈codemap non-test); resolves into deps; 5 languages; minimalist 3-verb MCP; smart test-de-emphasis | no arch/sig-change tools (no T4/T5); non-deterministic DB; **`ty`-on-PATH gotcha** silently degrades impact; venv-scoping trap; 12× index cost | learn (competent peer) | R1-C13, R1-C14 |
| GitNexus | hybrid semantic+structural: BM25+embeddings+RRF search, Leiden clusters + 294 process-flows, transitive risk-rated impact, per-answer `epistemic`/`confidence`, 14 langs, MCP+HTTP+web, 1-cmd editor setup | **non-commercial license**; 1.7 GB install + 123 MB binary non-diffable index (28× input); T2 is import-fan-in not call-sites; no T4 (call contracts) & partial T5 (no coupling/god-objects); **git-required** for incremental/change-detection | learn (strong, adjacent niche) | R1-C13, R1-C14, R1-C15 |
| PyCG | academic reference for Python call-graph accuracy; hand-labeled micro/macro benchmark corpus (the ~99%P/~70%R ceiling citation) | **does not run on Python 3.12** (import-hook surgery collides with stdlib; fails on a 3-line file); batch CLI, not a service; unmaintained (0.0.8, 2021) | learn (methodology only — spike-negative as a live oracle) | R1-C13 |
| cocoindex-code | local Apache-2.0 semantic search, **no DB / no API key**; concept queries nail the right files with zero name knowledge; **incremental re-index ≈ 1 s** (content-hash); bundled tree-sitter `grep`; MCP + agent skill | **no structural analysis** (T2–T5 N/A — vector index only); exact symbol lookup is fuzzy via `search`; binary non-diffable index; `[full]` torch drops pre-Turing GPUs (CPU-only on Pascal) | **wrap** (opt-in semantic adapter) + learn (incremental engine) | R1-C16, R1-C9, R1-C6 |
| CodeGraph | **speed** (1.4 s cold index, 0.3 s queries, **121 ms** incremental sync + a debounced watcher); symbol-level callers that *contain* codemap's set; MIT; 20 languages; one npm command, no service; **exemplary claim honesty** — publishes the axis where it loses and retracted its own earlier benchmark after finding the control arm contaminated 26/28 | no T4/T5 (no argument contract, no layers/cycles); impact is **flat and untagged** (no calls-vs-references, no root roles); `.md` outside the model; **silent `--limit 20` truncation** with no marker (filed upstream as [#1639](https://github.com/colbymchenry/codegraph/issues/1639); the same defect turned up in codemap's own `search` and is fixed as R1-C28); a wall-clock `updatedAt` in the answer; binary 15.5 MB artifact | **learn-only (strong)** | M3.2, R1-C13, R1-C6, R1-C14 |

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
- ~~**A debounced file watcher**~~ — **closed 2026-08-28 (M3.2)**, and this разбор is why: CodeGraph shipped
  the loop codemap had deferred (native OS file events → 2 s debounce → incremental re-index, **121 ms** for
  one modified file), which turned "we are waiting for a live scenario" into "we are waiting because we never
  priced it". codemap now ships `codemap watch` + `serve --watch`. The honest comparison is **not** favourable
  and is worth stating: their 121 ms is a Rust-kernel re-index; our end-to-end save→answer is **8.1–8.7 s** on
  a real 90-file package at the defaults, of which **4.3 s** is the fast-tier rebuild. Polling, not native
  events (a dependency we declined), measured at 50 ms per poll. The loop exists; the rebuild floor is the next
  thing to move, if anyone needs it moved. ([CodeGraph card](tools/codegraph.md))
- **Signature on the symbol-lookup answer** — CodeGraph returns a `signature` inline on every `query` hit;
  codemap makes you ask `call_contract` separately. Free ergonomics. ([CodeGraph card](tools/codegraph.md))
- **A contamination-proof two-arm benchmark harness** — CodeGraph blocks its own CLI in *both* arms
  (sanitized `PATH` + a `PreToolUse` hook) because it measured the control arm reaching the tool through
  Bash in **26 of 28 runs**. codemap has no with/without-agent benchmark; if it ever builds one, this
  control is not optional. ([CodeGraph card](tools/codegraph.md))

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
  graphlens has no tool for either (3-verb surface). **Nor does CodeGraph**, the most-adopted tool measured.
  Across four hands-on cards, T4 and T5 remain **unmatched by any peer**. (→ R1-C14)
- **Which differentiators CodeGraph took off the table** (2026-08-28) — an honest subtraction, since the
  list above was written against smaller peers. **Speed is gone**: CodeGraph indexes the same 280 files
  ~9× faster than codemap's fast tier and ~68× faster than deep. **License is gone**: MIT vs MIT.
  **Multi-language is gone**: 20 vs 1. **"Honest about its own claims" is gone as a *unique* stance** — its
  README publishes the axis on which the product loses (≈80% more resident context) and retracts its own
  earlier benchmark numbers. What survives is narrower and sharper: **byte-diffable artifact**,
  **declared-root provenance** (calls vs references; core vs docs vs tests, where CodeGraph labels
  `examples/` as "tests"), **argument-level call contracts**, **architecture contracts**, **docs as
  first-class references**, and **no clock anywhere in an answer**. (→ R1-C14)
