# Design — a method outside a Protocol, called on a Protocol-typed receiver, fans out to the implementers that have it

**Status:** ✅ **done** (2026-11-06, fix 709f89c), acceptance reconciled below. Pre-registered in 3d7c0f3. **Backlog:** R1-C88. **Gap:**
[`gaps/protocol_outside_method_2026-11-06.md`](../../gaps/protocol_outside_method_2026-11-06.md).

## D1

In a consumer root (R1-C81 D4), a call `expr.m(…)` whose receiver is typed as a Protocol `P` that does **not**
declare `m` gets `calls` edges to `C.m` for every implementer `C` of `P` that has `m` (itself or through its
bases), with `resolution: "protocol"`. This is the same heuristic grade and the same route-aware `low` in
`tests` (R1-C81 D3) as the D2 fan-out. If no implementer has `m`, there is no edge. If the receiver is not a
Protocol, nothing changes: an attribute missing from a concrete class is not guessed. The result of such a call
is not typed further, because the implementers may disagree.

**Not covered:** the same pattern in core code. There jedi resolves the receiver or does not, and a fan-out
there would need the core's own typer. That boundary goes in the docs.

No new edge type or resolution value; schema 0.13. `ANSWER_FORMAT` stays at 8 (released together with R1-C87):
the answer shape does not change, only which edges exist.

## Pre-registered expectations

Run on the branch against 0.0.31. E1 and E2 fail on 0.0.31.

| # | Expectation |
|---|---|
| E1 | bquearch `703696d` (their MCP graph, deep): `tests KnnPathForecaster.member_values` includes `test_zone_scale.test_scale_neighbours_are_the_band_neighbours`, confidence `low` |
| E2 | Fixture: `member_values` on two of three implementers → `protocol` edges to exactly those two; a name no implementer has → no edge; an unknown attribute on a concrete class → no edge |
| E3 | Graph against the R1-C87 commit: node ids equal, nothing removed, every added edge is `calls/protocol` from a consumer root (bquearch, bquant, codemap) |
| E4 | Full suite passes; the guard goes red when D1 is reverted; a cosmetic control stays green |

## Reconciliation (2026-11-06, 709f89c)

| # | Result |
|---|---|
| E1 | ✅ bquearch `703696d`, deep: 0.0.31 `unknown`, 0 tests; now `test_zone_scale.test_scale_neighbours_are_the_band_neighbours` at distance 1, `low` |
| E2 | ✅ fixture: the one implementer defining `member_values` (and its subclass through it) get the edge; a name no implementer has, and a missing method on a concrete class, get none; the row is `low` |
| E3 | ✅ against 0.0.31: node ids equal, nothing removed; added only `calls/protocol` from consumer roots: bquearch +107 (fast and deep), bquant 0 |
| E4 | ✅ suite 1233 passed / 3 skipped; mutations (off; concrete class guessed; graded `typed` instead of `protocol`) red; control green |
