# Design — a graph and its sidecar must describe one build, or the sidecar is not used

**Status:** ✅ **done** (2026-11-09, fix 6798a3c; `ANSWER_FORMAT` stays 10), acceptance reconciled below. Pre-registered in 8f525ea. **Backlog:** R1-C92. **Gap:**
[`gaps/sidecar_pair_mismatch_2026-11-09.md`](../../gaps/sidecar_pair_mismatch_2026-11-09.md).

## D1 — incremental builds check the pair

Before an incremental build uses `meta.scope` as its baseline, it compares `meta.scope.scope_id` with the
graph's `provenance.scope_id`. If they differ, the build is full, and its `info` says why: "the sidecar
describes another build than the graph". This covers both paths, single-package and repo-scoped core, and so
`watch` as well. The `[incremental]` line now prints the reason of any full build that had a reason, including
the existing ones (a different builder, tier or sample count). Until now those reasons were computed and never
shown.

## D2 — `currency` does not trust a foreign sidecar

When `meta.scope.scope_id` differs from the graph's `scope_id`, the recipe is treated as unusable. The check
falls back to the graph's provenance roots (R1-C90), with the reason "the sidecar describes another build". So
there are no counts from a foreign baseline, and no status from a foreign recipe.

## D3 — the docs say the pair moves together

`docs/incremental.md`: whoever replaces a graph file replaces its sidecar with it. With D1, a mismatch costs
one full build, never a stale graph.

**`ANSWER_FORMAT` stays 10.** A matched pair behaves exactly as before. Only a mismatched pair changes:
incremental becomes full, and `currency.via` names the roots.

## Pre-registered expectations

E1, E2, E4 and E5 fail on 0.0.35.

| # | Expectation |
|---|---|
| E1 | Fixture above (graph 0 + meta 1, then an edit): 0.0.35 prints `incremental` and misses `calls pkg.m1.f1 → pkg.m3.f3`. The fix prints `[incremental] full` with the sidecar reason, and the graph equals a full build |
| E2 | Meta older than the graph (graph 1 + meta 0): full with the same reason (0.0.35: `incremental`) |
| E3 | Matched pair: the incremental build is unchanged, with the same mode, module count and bytes as 0.0.35 |
| E4 | Repo-scoped (`--consumer tests`), mismatched pair: full with the reason (0.0.35: `incremental`) |
| E5 | `currency` on graph 0 + meta 1 after an edit, run from the tree: 0.0.35 `behind` `via: recipe` with counts; the fix `behind` via provenance roots, with no counts |
| E6 | `watch` over a mismatched pair: the first rebuild logs `full` with the reason |
| E7 | `check` on bquant and the bquearch gate identical to 0.0.35 apart from the version |
| E8 | Full suite passes; mutations go red: D1 check removed, D1 reason not printed, D2 check removed; a cosmetic control stays green |

Surprises go into the reconciliation.

## Reconciliation (2026-11-09, 6798a3c)

| # | Result |
|---|---|
| E1 | ✅ 0.0.35: `[incremental] incremental: 1 module(s) recomputed`, `f1 → f3` missing, not equal to a full build. Fix: `[incremental] full: 0 module(s) recomputed (the sidecar describes another build than the graph)`, equal to a full build |
| E2 | ✅ 0.0.35: `incremental: 2 module(s)`, and the graph happened to equal a full build (the safe direction). Fix: full with the reason |
| E3 | ✅ matched pair: `incremental: 1 module(s) recomputed`, equal to a full build (unit test). Checked against a full build, not byte-compared with 0.0.35's output |
| E4 | ✅ `--consumer tests --mode full`, mismatched pair: 0.0.35 `incremental`, `f1 → f3` missing; fix full with the reason, equal to a full build |
| E5 | ✅ graph 0 + sidecar 1: 0.0.35 `behind` `via: recipe` with **0 added, 0 changed, 0 removed**, a self-contradicting answer whose counts come from the foreign baseline. Fix: `behind` via provenance roots, no counts |
| E6 | ✅ `watch` over a mismatched pair: the first rebuild logs `[incremental] full … (the sidecar describes another build than the graph)` |
| E7 | ✅ bquant `check` and the bquearch gate identical to 0.0.35 apart from the version |
| E8 | ✅ suite 1275 passed / 3 skipped (1278 collected); mutations red: D1 check off, reason not printed, D2 off; control green |

**Surprises.** E5 on 0.0.35 shows the wrong counts in their most confusing form: behind, yet nothing changed.
On my side, the first mutation loop ran before the fix was committed. `git checkout -- codemap` restored HEAD,
which threw away D1 and D2 along with the mutant, so the next three mutants "did not apply". Detected by that
output, the code was restored, committed, and the loop rerun with `git checkout HEAD -- <file>`.
**Corroboration (bquant, same day):** the first `--incremental` after moving the pin from 0.0.34 to 0.0.35 took
153 s against the usual ~35, and nothing said why. That was the existing `builder-changed` full build; with D1
the reason is printed.
