# Design — `tests` through a helper in the test module, and an answer that names the next band

**Status:** ✅ **done** (2026-11-05; code b458352 + 21e0c80; `ANSWER_FORMAT` 4 → 5, schema unchanged). **D1 was measured, failed E6, and shipped narrowed** — see §Measured. **Backlog:** R1-C80. **Gap:**
[`gaps/tests_nearest_band_helpers_2026-11-05.md`](../../gaps/tests_nearest_band_helpers_2026-11-05.md).
**Builds on:** [`test_mapping.md`](test_mapping.md) (R1-C24: nearest band, cutoff 3 measured against coverage.py).
**Tracking:** [kogriv/codemap#25](https://github.com/kogriv/codemap/issues/25).

## The defect

bquant `cf039ef`: `tests trades_at_exit` → 1 test; six more call it through `_vector`, a plain function in the same
test module, and are dropped because they sit one hop further. `--depth` cannot add them, and the caveat ("searched
1 hop(s) back") does not say that a nearer band closed the search. Details in the gap.

## Correction before any code (2026-11-05, same day)

The first version of this design, committed in e666077, diagnosed a band problem only. A two-file toy showed the
larger cause: a consumer root in `full` mode gets edges **into core** only (`codemap/extract/roots.py`,
`_scan_consumer_module`), so the call `test_through_helper → _helper` inside the test module is never extracted.
The walk reaches `_vector` and stops: no edge leads to it. That is why `--depth 6` found nothing. The fact bquant
reported ("the edge `_vector → trades_at_exit` is in the graph") was true, and I did not check the other edge.
D0 is added below; D1–D4 stand, and the expectations are re-stated after it. Nothing was measured or coded
between the two versions; the ground-truth run on the stand computes only coverage and 0.0.27 baselines.

## D0 — a consumer module's uses of its own top-level definitions become edges (`full` mode)

In `full` mode, a use inside a consumer module of a function or class **defined at the top level of that same
module** becomes an edge from the enclosing definition, `calls` if called and `references` otherwise, with
`resolution: "local"`. This covers `test_x → _vector`, `test_x → _run` and a nested `def one(): _vector(...)`,
whose edge starts at the nested def. Scope stays tight. There are no cross-module consumer edges, no `self.method` calls, and no
names rebound before use (the same R1-C46 dead-body rule as the core edges). `thin` mode is unchanged: it has no
consumer-internal nodes to connect.

Consequences named up front. Repo-scoped graphs gain edges inside consumer roots and nowhere else; core edges,
node set and schema (0.13) do not move. `check` is unaffected, since consumer roots are outside layering. `impact` and
`used_by` counts can grow for consumer roots, because a symbol reached through a consumer helper now reaches the helper's callers.

## D1 — a helper inside a collected test module costs no hop

When the backward walk reaches a function or method that is **not** a test but is defined in a module pytest
collects (`test_*.py` / `*_test.py` under a `tests` root — the same file rule `_is_test` uses), the walk continues
from it **at the same distance**. Such a helper exists only to be called by the tests beside it; a test that calls
`_vector`, which calls `trades_at_exit`, exercises `trades_at_exit` exactly as a test that calls it directly.

Not transparent: anything outside a collected test module, which means conftest.py, `tests/fixtures/`, `tests/helpers.py`
and shared packages. Those are the "shared test infrastructure" the R1-C24 measurement found at hop 4, where
precision fell from 1.00 to 0.67. The rule is the file name, nothing cleverer. A helper is transparent only on
the path *into* the tests of its own module: it is never itself a test (`_is_test` is unchanged).

`covers` (the forward walk from a test) applies the same rule, so a test's helpers do not push the symbols they call
one hop away. A nested def inside a test or helper is treated the same way: from it the walk also steps to the
function that contains it (`contains`, the enclosing def only), at no cost. Otherwise `def one(): _vector(...)`
inside a test would end at `one`.

## D2 — the answer names the next band

The envelope of `tests` gains `next_band`, always present (R1-C28):
`{"distance": d, "count": n}` for the next non-empty band within `depth`, or `null` when there is none within
`depth`. The walk already visits it; counting costs one more level at most. The CLI prints one line under the
list: "N more test(s) at distance d — `--all-bands` lists them". The caveat "searched N hop(s) back" becomes
"nearest band at distance d; looked up to depth D for more", which is what happened.

## D3 — `--all-bands` lists every band within the depth

`codemap tests X --all-bands` (MCP: `"all_bands": true`) returns every band up to `depth`, each row carrying its
`distance` and the answer `confidence` of its band. The default stays the nearest band: R1-C24's measurement
that "all reachable" is "most of the suite" still holds, and it was measured. `total_at_distance` keeps its
meaning (the nearest band); `total` is added for the union under `--all-bands`.

## D4 — answer format 4 → 5

`tests` gains a field and a line, which is a structure change a consumer sees (R1-C63). `ANSWER_FORMAT` becomes 5
with this change, and `RENDERED_SHA` moves in the same commit. The release note says what changed shape: the
`tests` answer (`next_band`, the caveat wording, `--all-bands`), and the distances in `tests`/`covers` where a
test-module helper sits on the path.

## Pre-registered expectations (committed before code and before the ground-truth run)

Ground truth is coverage.py with per-test contexts, mapped through the graph's `symbol_at` by
[`research/bench/test_mapping_accuracy.py`](../../research/bench/test_mapping_accuracy.py), on two suites: **codemap's
own** (as R1-C24 D6) and **bquant at `cf039ef`**. Both tiers on codemap; fast and deep on bquant. Baseline = 0.0.27
on the same trees and the same coverage data.

**D0 on the graph (bquant `cf039ef`, fast):**
- **E0a** new `calls`/`references` edges appear only between nodes of consumer roots, each with `resolution:
  "local"`; core edges, all node ids and `SCHEMA_VERSION` are identical to 0.0.27's graph of the same tree.
- **E0b** the edges `test_one_set_reproduces_… → _vector` and `test_trades_from_zones_reproduce_the_reference →
  _run` (names abbreviated) exist.
- **E0c** two builds are byte-identical; `check` output on bquant and bquearch is unchanged.

**On the bquant cases (fast tier):**
- **E1** `trades_at_exit`: distance 1, **7 tests** (one direct, six through `_vector`), against 1 now. The 0.0.27
  test is among them.
- **E2** `zone_trades`: **≥ 15**, against 13 now. Includes the parametrized test of
  `test_trades_from_zones_reproduce_the_reference.py` that goes through `_run`, and the tests that go through
  `_rowwise`.
- **E3** every 0.0.27 answer is a subset of the new one for the same symbol (D1 only moves tests nearer, never
  farther), except where a nearer band now opens and replaces a farther one. Those cases are counted and listed.

**Against coverage (both suites, at the shipped cutoff):**
- **E4** median precision stays **≥ 0.95** (0.0.27: 1.00 on codemap in August); hit rate does not fall; answered
  does not fall; median recall rises on bquant.
- **E5** median tests shown stays **≤ 2×** the baseline's. If it more than doubles, D1 is pulling in infrastructure
  and the rule is wrong.
- **E6** the symbols whose answer changes are listed with precision for them alone; their median precision is
  **≥ 0.95**.

**Shape and guards:**
- **E7** `next_band` is present on every answer, `null` exactly where no further band exists within `depth`.
- **E8** `--all-bands` is the union of the bands, each row with its distance; two runs byte-identical.
- **E9** `covers` from a test that calls only a helper reports the helper's core callees at distance 1.
- **E10** mutation: making the helper step cost a hop again turns E1/E2's tests red; a cosmetic change leaves them green.
- **E11** `ANSWER_FORMAT` 5, `RENDERED_SHA` updated in the same commit, `check` output unchanged (bquant, bquearch).

At least E1, E2 and E7 fail if nothing is done.

## What this does not establish

- Fixtures resolved by name stay invisible (R1-C24 D4, measured and not built); a test that reaches a symbol only
  through a fixture is still not found.
- Methods on objects from a factory (R1-C81) are a resolution question, not a band question.

## Measured (2026-11-05) — and D1 narrowed by it

Ground truth: coverage.py with per-test contexts. bquant `cf039ef` ran 4350 passed and 35 skipped in 22 min under coverage.
codemap `3e311a0` ran 1177 passed. Every coverage context was matched to a graph test: 1198 matched and 8 unmatched on
bquant, 881 matched and 0 unmatched on codemap. Bench [`research/bench/r1c80/tests_bands.py`](../../research/bench/r1c80/tests_bands.py);
baselines with the published 0.0.27 on its own graphs, the new code on graphs of the **same** trees.

**First run: D0 + D1 as designed (module-level helpers free).**

| | bquant fast | bquant deep | codemap fast | codemap deep |
|---|---|---|---|---|
| answers changed | 25 | 37 | 90 | 129 |
| median precision, changed answers (**E6 ≥ 0.95**) | **0.89** | **0.86** | **0.87** | **0.73** |
| median shown, base → new (E5 ≤ 2×) | 2 → 2 | 2 → 3 | 4 → 5 | 5 → 8 |
| tests added / of them executed by the test | 439 / 122 (28 %) | — | — | 5941 / 1175 (20 %) |

E1 and E2 held: `trades_at_exit` went from 1 test to 7, and `zone_trades` from 13 to 18. **E6 failed on all four.** The added
tests came mostly through *shared* helpers. One helper called by sixty tests reaches everything it can call, and each test
runs a fraction of it: `get_sample_data` went from 60 to 273 tests, `collect_samples` from 167 to 501.

**Ablation: D0 alone (helpers cost a hop).** The nearest band did not change on bquant at all (0 answers changed), and on codemap
3 answers changed. The noise was D1's, not D0's.

**Decision.** D1 is narrowed to a def **nested** in a test or helper: it is the container's own body, and coverage attributes
its execution to the test. A module-level helper costs a hop again. D0 stays: tests behind a helper go from unreachable to one
hop further. They are named by `next_band` and listed by `--all-bands`. This is the third of the outcomes bquant asked for
("at least say N more tests at distance 2"), now chosen by measurement rather than by default.

**Shipped rule (21e0c80):**

| | bquant fast | bquant deep | codemap fast | codemap deep |
|---|---|---|---|---|
| answers changed | 6 | 6 | 8 | 10 |
| old answer not a subset of new | 0 | 0 | 1 | 1 |
| median precision, all answers (E4) | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 |
| hit rate | 0.921 → 0.926 | 0.899 → 0.903 | 0.897 → 0.901 | 0.902 → 0.905 |
| median recall | 0.50 → 0.50 | 0.28 → 0.29 | 0.35 → 0.36 | 0.31 → 0.31 |
| median shown | 2 → 2 | 2 → 2 | 4 → 4 | 5 → 5 |
| median precision, changed answers (E6) | **0.26** | **0.26** | 0.78 | 0.83 |

E6 as written still fails on bquant, and the table says why. Each changed answer gained exactly one test. The low medians are
inherited from answers that were already imprecise before this change: `StrategyRegistry.register` had 0 true tests out of 192. Counted
over the **added** tests only, 3 of 6 are executed on bquant and 19 of 19 on codemap, where 2 false tests also dropped out
(`build_mcp_server`, distance 3 → 2, 0 → 8 true). On bquant, 75 of the 215 answers now name a next band.

### Reconciliation

| | expected | measured | |
|---|---|---|---|
| E0a new edges only inside consumer roots; nodes, core, schema unchanged | as stated | nodes identical; 1108 edges added, 0 removed; **1 added edge touches a core node** (not yet identified); schema read not checked by the script (key name) | **open: one edge** |
| E0b `test → _vector`, `test → _run` | exist | `… → _run` edges present in several modules | holds |
| E0c byte-identical builds; `check` unchanged | as stated | not run in this pass | **to do before release** |
| E1 `trades_at_exit` 7 at distance 1 | 7 | D1 as designed: 7. Shipped: 1, plus `next_band` 6 at distance 2, which are the six `_vector` tests | fails as written, by decision |
| E2 `zone_trades` ≥ 15 | ≥ 15 | as designed: 18. Shipped: 13, plus 5 at distance 2 | fails as written, by decision |
| E3 old ⊆ new except nearer-band replacements | as stated | 0 / 0 / 1 / 1 exceptions, each a nearer band (`build_mcp_server`) | holds |
| E4 precision ≥ 0.95, hit rate and answered not down, recall up on bquant | as stated | precision 1.00, hit rate up, answered equal; recall up on bquant deep, **equal** on bquant fast | holds but for bquant-fast recall |
| E5 shown ≤ 2× | as stated | equal on all four | holds |
| E6 changed answers ≥ 0.95 | as stated | as designed 0.73–0.89, shipped 0.26 / 0.26 / 0.78 / 0.83 (see above) | **fails**; drove the decision |
| E7 `next_band` always present | as stated | tests + pin | holds |
| E8 `--all-bands` union, stable | as stated | tests | holds |
| E9 `covers` through a helper | distance 1 | distance 2 under the shipped rule; a nested def at no cost | changed with D1 |
| E10 mutation | as stated | D0 removed → 8 tests red; nested step removed → 4 red; `next_band` removed → 3 red; cosmetic → green | holds |
| E11 format 5, pin, `check` unchanged | as stated | `ANSWER_FORMAT` 5; the six-surface `RENDERED_SHA` does **not** cover `tests`, so it did not move. A new pin `TESTS_SHA` now covers the `tests` answer. `check` comparison to be run before release | holds, with a gap closed |

### Slips

- **The diagnosis was wrong at first** (see the correction above): I wrote "distance 2" without checking the second edge.
- **My first coverage run of bquant failed at collection.** `hypothesis` is a dev extra that is missing from the environment I borrowed, so the
  baseline printed "exercised 0". I re-ran it with `hypothesis` on the side path.
- **The first bench resolved named symbols by suffix.** It picked a different node for `zone_trades` than the CLI does; it now
  resolves through the session.
- **The ablation's named-symbol lines were not ablated**: they came from a fresh `Query` built inside the session. The
  per-symbol numbers were ablated and are the ones quoted.
