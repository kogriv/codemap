# Design — a call on a Protocol reaches its implementers; a test's chain is typed by return annotations

**Status:** 🟡 pre-registered (expectations below, committed before code). **Backlog:** R1-C81. **Gap:**
[`gaps/protocol_factory_methods_2026-11-06.md`](../../gaps/protocol_factory_methods_2026-11-06.md).

## The defect

On bquearch `703696d`, `tests` answers `unknown` for the methods of every model behind the `PathForecaster`
Protocol. Two breaks: nothing links a Protocol method to its implementations (registry families understand only
`@Registry.register` on a class), and a consumer root does not resolve `_spec().build().fit(df)` /
`fc.band(…)`, though return annotations name every link.

## D1 — structural implementers

A core class **implements** a Protocol (a class inheriting `typing.Protocol`) when it has, itself or through
its bases in the graph, every method the Protocol declares, and each one has the same parameter names and kinds
(positional, `*args`, keyword-only, `**kwargs`; `self`/`cls` dropped; annotations and defaults ignored).
Dunder methods do not count, except `__call__`. A Protocol with no methods links nothing. The edge is
`implements`, `extras.via = "structural"`; a pair already linked through a registry keeps `via: "registry"`.

Measured before the design on bquant: the parameter check turns the name-only match (5 false implementers) into
the registry's own sets, plus one class that structurally does implement (`AdaptiveSwingStrategy`).

## D2 — a call on a Protocol method fans out to implementers

For every resolved `calls` edge to a Protocol method `P.m`, from any root, add `calls` edges from the same caller
to `C.m` for every implementer `C`, with `resolution: "protocol"`. In the resolution table it is
`route`/`heuristic`: "a call on a Protocol-typed receiver, fanned out to every structural implementer". This is
the honest over-approximation `registry-candidate` already is. It runs after the core passes and again after the
consumer scans, so consumer edges fan out too.

## D3 — a test reached only through a guess says so

In `tests_for`, a test whose every shortest path to the symbol crosses a `heuristic` call edge
(`registry-candidate` or `protocol`) gets row confidence **`low`**, whatever its distance. The answer's caveats
name the reason: "N test(s) reached only through a dispatch over-approximation (registry/Protocol)". Without
this, a fan-out at distance 1 would read `high`. Measured on bquant against coverage.py: rows before and after.

## D4 — consumer roots: chains typed by return annotations (`--mode full`)

Inside a consumer function, the type of an expression is known when:

- it is a call to an imported core **class**: an instance of it;
- it is a call to an imported core **function** or a **method** of a known type, whose return annotation
  resolves to a core class in the defining module (its own member, or a name it imports). `Optional[X]` and a
  quoted `"X"` count as `X`; other generics do not resolve;
- it is a call to a **local helper** whose every `return` has the same known type (one level deep);
- it is a name assigned once in that function from an expression of known type.

A call `expr.m(…)` on an expression of type `T` gives `calls → T.m`, with the method found on `T` or its bases
in the graph and `resolution: "typed"` (route/exact: the annotation names it). Nothing is guessed: an
unannotated return, a reassigned name or an unresolvable annotation gives no edge. This is the fast tier, with
no jedi. D2 then fans `typed` edges onto Protocol methods out to implementers.

**Graph change:** new `implements` (structural) and `calls` (`protocol`, `typed`) edges, and two resolution
values added to the table. The schema stays **0.13**, since no new edge type is added. **`ANSWER_FORMAT` 6 → 7**:
row confidence in `tests` becomes route-aware (D3), so the field means something else.

## Pre-registered expectations

Run on the R1-C81 branch against 0.0.30. Trees: bquearch `703696d` (graph as in their MCP script, deep and fast),
bquant `cf039ef` (deep, four consumers + `docs`) with the coverage.py contexts measured for R1-C80, and codemap
`3e311a0` with its coverage. E1, E2, E4 and E5 fail on 0.0.30, so the list cannot pass if nothing was done.

| # | Expectation |
|---|---|
| E1 | bquearch: `implementers(PathForecaster)` = the 6 menu forecasters and `implementers(RuntimeForecaster)` = 5, by name; bquant: every registry link kept, and structural adds exactly `AdaptiveSwingStrategy → SwingCalculationStrategy` |
| E2 | bquearch deep: `tests KnnRecursiveForecaster.band` is not `unknown`, and its rows include `test_knn_recursive.test_a_rows_scenarios_do_not_depend_on_who_else_was_asked` and `test_gate_and_runtime_give_one_band` |
| E3 | Those rows come through D4 (`typed`) and D2 (`protocol`), so their confidence is `low`; the caveat names the dispatch over-approximation |
| E4 | Fixture: `X().build().fit(df).band(…)` with Protocol return annotations gives `typed` edges to `X.build`, `P.fit`, `P.band` and `protocol` edges to each implementer's `band`; an unannotated return, a reassigned name and a name-only "implementer" with different parameters give none |
| E5 | Over 11 bquearch methods that answered `unknown` (prototype count), at least 9 answer with tests |
| E6 | bquant and codemap, scored with coverage.py truth (`research/bench/r1c80/tests_bands.py`): median precision does not fall below 0.0.30's (1.00); no row whose path crosses a heuristic edge reads `high`; the number of changed answers and their precision are reported |
| E7 | Graph: node ids identical to 0.0.30; no edge removed; added edges are only `implements/structural`, `calls/protocol`, `calls/typed` (bquearch, bquant, codemap) |
| E8 | `check` on bquant and the bquearch gate: exit 0, output identical apart from the trailer (`answer format 7`) |
| E9 | Full suite passes; guards for D1 (incl. the parameter check), D2, D3 and D4 each go red when reverted; a cosmetic control mutation stays green |

Surprises are reported in the reconciliation.
