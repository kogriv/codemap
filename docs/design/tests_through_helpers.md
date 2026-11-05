# Design — `tests` through a helper in the test module, and an answer that names the next band

**Status:** 🟡 pre-registered (2026-11-05), no code, no measurement. **Backlog:** R1-C80. **Gap:**
[`gaps/tests_nearest_band_helpers_2026-11-05.md`](../../gaps/tests_nearest_band_helpers_2026-11-05.md).
**Builds on:** [`test_mapping.md`](test_mapping.md) (R1-C24: nearest band, cutoff 3 measured against coverage.py).
**Tracking:** [kogriv/codemap#25](https://github.com/kogriv/codemap/issues/25).

## The defect

bquant `cf039ef`: `tests trades_at_exit` → 1 test; six more call it through `_vector`, a plain function in the same
test module, and are dropped because they sit one hop further. `--depth` cannot add them, and the caveat ("searched
1 hop(s) back") does not say that a nearer band closed the search. Details in the gap.

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
one hop away.

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
