# Design — every route the extractor emits is graded, and a graph from a newer codemap says so

**Status:** ✅ **done** (2026-11-09, fix b784d0c; `ANSWER_FORMAT` stays 10), acceptance reconciled below. Pre-registered in 66feb01. **Backlog:** R1-C91. **Gap:**
[`gaps/route_vocabulary_drift_2026-11-09.md`](../../gaps/route_vocabulary_drift_2026-11-09.md).

## D1 — the missing rows

`("calls", "local")` and `("references", "local")` join `RESOLUTIONS`, graded `exact`, meaning `route`. The
route is a consumer-root name bound by a `def` at the level of the same module (R1-C80). This is the
`("calls", "module")` binding in a consumer root, so it gets the same grade. The emitted value stays `local`, so
graphs already built by 0.0.28–0.0.34 are graded correctly without a rebuild.

## D2 — the builders check the vocabulary, not a fixture list

`extract`, `extract_repo` and `update_graph` end with a strict check of every edge's `(type, resolution)` against
the table. An unknown pair raises and names the pair and the table. Every build in the suite then guards the
table, including fixtures written for later items. The `resolution_of` docstring already claims that "the
extractor" reads strictly; after D2 it is true. The R1-C39 fixture set also gains a consumer-helper probe, so
the reverse direction ("every row is observed") covers `local`.

## D3 — a graph built by a newer codemap is a diagnostic

A new graph diagnostic, `graph_from_newer_tool` (warning), joins `diagnostics()`. It fires when either is true:
- the graph's `provenance.tool.version` parses as newer than the running codemap;
- the graph carries `(type, resolution)` pairs this build's table does not know.

The diagnostic carries `built_by`, `running` and `unrecognised` (`{"type:resolution": edges}`). The message names
both versions and the unknown pairs, and says that those edges are graded `unknown` and dropped by
`min_confidence`. Its remedy: run a codemap at least as new as the graph (restart a long-running server). It
reaches every surface that already shows `diagnostics`: `stats`, report headers, `build`, the API and audit
reports. When the running version is unknown (an uninstalled source tree), only the route evidence counts.

## D4 — a cold CLI read says it once

A cold `--graph` read prints the D3 diagnostic as one `[warning]` line on stderr. Stdout and exit codes do not
change.

**`ANSWER_FORMAT` stays 10.** No answer changes layout or field meaning. D1 corrects values: `by_grade` moves
`local` edges from `unknown` to `exact`, and `min_confidence` keeps them. D3 adds a code to an open list that is
empty on a graph built by the same version.

## Honest limit

D3 cannot reach a server that already runs old code. bquant's server on 0.0.27 stays silent. The signal starts
with a server on this release reading graphs from later ones. The fix for the server that is running now is a
restart.

## Pre-registered expectations

E1, E2, E4 and E5 fail on 0.0.34.

| # | Expectation |
|---|---|
| E1 | Fixture repo, a test calling a helper defined in the test module: 0.0.34 grades the `local` edges `unknown`; the fix grades them `exact`; `callers(helper, min_confidence="exact")` includes the test function (0.0.34: excluded) |
| E2 | bquant graph at `cf039ef` built by 0.0.34, `stats` on the fix: no `unknown` grade, `exact` = 0.0.34's `exact` + 1107; no `graph_from_newer_tool` (the graph is older than the running code) |
| E3 | The same graph with `provenance.tool.version` set to `0.0.99`: the diagnostic fires with `built_by` 0.0.99 and empty `unrecognised`; with one edge's resolution renamed to `future`, `unrecognised` = `{"calls:future": 1}`. A cold `query … --graph` prints one `[warning]` line, and its stdout is byte-identical to the stdout for the unmodified graph |
| E4 | The bquant graph read with the table cut back to 0.0.27's rows: `unrecognised` sums to **2380**, the number bquant's 0.0.27 server reported |
| E5 | D2 works as a guard: with D1 reverted, the suite goes red at build time in the R1-C80 tests and in the new R1-C39 probe, naming `local` |
| E6 | `check` on bquant and the bquearch gate: identical to 0.0.34 apart from the version in the trailer |
| E7 | Full suite passes; mutations go red: D1 row removed, D2 check removed (with D1 removed), D3 version comparison off, D3 route evidence off, D4 off. A cosmetic control stays green |

Surprises go into the reconciliation.

## Reconciliation (2026-11-09, b784d0c)

| # | Result |
|---|---|
| E1 | ✅ fixture: `calls:local` and `references:local` graded `exact`, no `unknown` in `by_grade`; `callers(helper, min_confidence="exact")` includes the test. On 0.0.34 the same edges are `unknown` (shown on the real graph, E2) |
| E2 | ✅ bquant graph at `cf039ef` built by 0.0.34: 0.0.34 reads `exact` 9053, `unknown` 1107; the fix reads `exact` **10160** = 9053 + 1107, no `unknown`; no `graph_from_newer_tool` |
| E3 | ✅ stamped `0.0.99`: diagnostic with `built_by` 0.0.99, `unrecognised` empty; one edge renamed to `future` → `{"calls:future": 1}`; cold `query --graph`: one `[warning]` line, stdout identical (test) |
| E4 | ✅ table cut to 0.0.27's rows: `calls:typed` 972 + `calls:local` 671 + `references:local` 436 + `accesses:name` 301 = **2380**, bquant's number |
| E5 | ✅ with D1 reverted, the R1-C80 tests and the new R1-C39 probe fail at build time: `this build emitted route(s) its table does not know: {'calls:local': 4}` |
| E6 | ✅ bquant `check` and the bquearch gate identical to 0.0.34 apart from the version; no newer-tool warning on same-version graphs |
| E7 | ✅ suite 1270 passed / 3 skipped (1273 collected); mutations red: D1 row removed, D1+D2 removed, D3 version off, D3 routes off, D4 off; control green |

**Surprise (environment, and a limit worth stating):** the first local run of E2 reported the running codemap as
**0.0.23**, and the diagnostic fired on the 0.0.34 graph. The development venv held stale installed metadata
from an old editable install, and `codemap.__version__` reads the installed metadata. A reinstall fixed it.
The limit: the version D3 compares against is the installed distribution's. A stale editable install makes D3
fire falsely, and the same stale version is stamped into every graph that install builds. That second part is
older than this item.
