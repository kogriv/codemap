# Design — every call site is counted somewhere, and the counts add up to the source

**Status:** ✅ **shipped** (2026-11-03, `ANSWER_FORMAT` 3 → 4 at the next release), with acceptance reconciled below. Pre-registered in 124605c before any code. **Motivates:** the R1-C71 reconciliation,
where the counters fell short of an independent count for a reason nobody had written down.
**Backlog:** R1-C74.

## The defect, measured

`extras.calls` counts the call sites in a definition node's *own* body. `report behavior` sums these
counters and prints "Call-site resolution (N sites in M functions)", which reads as the whole package.
It is not. An independent count of every `ast.Call`, by the scope that runs it
(`research/bench/r1c74/call_scopes.py`), agrees with today's counters *exactly*, node by node, on the
function scope: bquant 7288 = 7288, `_pytest` 7464 = 7464. Everything outside that scope is missing:

| bquant `8efa112` | sites | edges today | counted today |
|---|---:|---|---|
| own body of a function node | 7288 | yes | yes |
| a function nested in one (closures, inner defs) | 198 | yes, onto the owner, `via: "nested"` | **no** |
| module-level statements | 136 | yes, from the module (R1-C22) | **no** |
| a class body outside its methods | 42 | **no** | **no** |
| a definition replaced by a later one (R1-C46) | 1 | no, on purpose (it cannot run) | no |
| **all `ast.Call` in the source** | **7665** | | |

So 376 sites (4.9 %) are silently outside the resolution figure. The class-body sites are also outside
the call graph entirely: `class K: x = helper()` gives no edge (fixture, measured). That is the same
silent kind as R1-C22's module-level blindness, one scope further in.

## D1 — a counter for every scope that runs code

- **Module level:** the module node gets `extras.calls`, the same shape as a function's.
- **Class body:** the class node gets `extras.calls`. Its calls are resolved as module-level code is
  (the class body runs at import time), and resolved internal calls become `calls` edges **from the
  class node**. These are new edges. A class whose body calls `make_registry()` depends on it, as a
  module does.
- **Nested functions:** the owner gets `extras.calls_nested`, the same shape. That is the node their edges
  already point from. It is a separate key so that `extras.calls` keeps meaning "this body", unchanged
  for every existing consumer.
- **Shadowed definitions:** still not walked. The report states their count, so they are named, not
  absorbed.

## D2 — the report states the whole and its parts

`report behavior` says "N call sites — F in function bodies, X in nested functions, M at module level,
C in class bodies", and the percentages are over N. The JSON `call_sites` gains `by_scope`, plus
`shadowed_not_walked`. The answer changes shape, so `ANSWER_FORMAT` 3 → 4 at the next release.

## D3 — conservation, as a derived check

Σ counted sites + shadowed = every `ast.Call` in the readable source. This is the same law as R1-C23
D6 ("modules vs input files"), one level down. The acceptance asserts it on three packages; nothing is
stored for it.

## Pre-registered acceptance (committed before the code)

The predictions come from `call_scopes.py`, which does not import codemap. It is run on exactly the
trees that will be built: bquant `8efa112`; codemap at this commit, whose package source equals `a904eb9`;
pytest 9.1.1.

| | function | nested | module | class body | shadowed | all calls |
|---|---:|---:|---:|---:|---:|---:|
| bquant | 7288 | 198 | 136 | 42 | 1 | 7665 |
| codemap | 4113 | 212 | 53 | 27 | 0 | 4405 |
| `_pytest` | 7464 | 325 | 100 | 58 | 18 | 7965 |

- **C1, fixture.** One call in each scope (an own body, a nested def, module level, a class body). Each
  is counted on the expected node (`calls` on the function, `calls_nested` on the outer function, `calls`
  on the module, `calls` on the class), and the class-body call gives an edge `K → helper`.
- **C2, fast tier on the three trees.**
  - Σ `calls.out` over function and attribute nodes is the "function" column, *unchanged* from before.
  - Σ `calls_nested.out` is the "nested" column.
  - Σ `calls.out` over module nodes is the "module" column.
  - Σ `calls.out` over class nodes is the "class body" column.
  - Their sum + shadowed = "all calls".
- **C3, edges.** The only new edges are `calls` from class nodes. Each one's target is reached by a call
  written in that class body: checked by AST after the run, edge by edge. No other edge changes. Nodes
  change only by the new counter keys.
- **C4, report.** `report behavior` on bquant names 7664 sites and the four parts, and says 1 call sits in
  a shadowed body, not walked.
- **C5, deep tier, bquant.** The same four sums: conservation holds on the deep tier too (resolution
  differs, the counts do not).
- **C6, cost.** bquant fast build within ±10 %, alternating runs on an idle stand.
- **C7, mutation.**
  - Class bodies not walked: the conservation test and C1's class-body row go red.
  - Module counters off: the module row goes red.
- **C8, suite** green, README count moved, and the pinned rendered hash re-pinned with the format bump.

At least one expectation fails if nothing is done: C1 and the conservation sum fail today.

## Acceptance reconciled (2026-11-03)

Fast and deep builds and the suite ran on the stand, inside the shared core-slot accounting: before =
`124605c`, after = the same tree plus the change. The scripts are `research/bench/r1c74/call_scopes.py` (the
prediction, revised as said below) and `sum_by_scope.py` (sums, edge diff, class-edge check).

| | expected | measured, final run | |
|---|---|---|---|
| C1 fixture | each scope on its node; a class-body edge | so (7 tests) | holds |
| C2 bquant | 7288 / 198 / 136 / 42, shadowed 1, total 7665 | **7289** / 198 / 136 / 42, shadowed **0**, total **7665** | conservation holds exactly; the split differs, reconciled below |
| C2 codemap | 4113 / 212 / 53 / 27, total 4405 | exactly so | holds |
| C2 `_pytest` | 7464 / 325 / 100 / 58, shadowed 18, total 7965 | **7482** / 325 / 100 / 58, shadowed **0**, total **7965** | conservation holds exactly; the split differs, reconciled below |
| C3 edges | only new `calls` from class nodes; nothing else | bquant: +16 from class nodes, **16 of 16 verified** against the class-body source, 0 removed. codemap: 0. `_pytest`: 0 added, **1 removed**: the false self-loop `FixtureManager.getfixturedefs → itself` | **fails as written, by one edge that was wrong**, below |
| C3 nodes | only new counter keys | plus the `calls` of nodes that own two bodies: 1 in bquant, 8 in `_pytest` (their increases sum to 18) | **fails as written**, below |
| C4 report | bquant names 7664 sites and the parts | 7665 sites: 7289 / 198 / 136 / 42; no shadowed line, there are none | holds in form; the number is the corrected one |
| C5 deep | the same sums | 7289 / 198 / 136 / 42 = 7665 | holds |
| C6 cost | ±10 % | first run +11 %. After computing the shadow map once per module: **+8 %** (median 8.85 → 9.56 s, alternating 5 + 5) | holds on the second run, at the edge |
| C7 mutation | red | class bodies unwalked: red. `behavior.py` reverted: 5 of 5 then-existing tests fail | holds |
| C8 suite | green | 1125 passed, 3 skipped | holds |

**The first run found two defects the conservation law was built to find, and one error in my
prediction.**
1. **My shadowing rule was not codemap's.** The script took "the last definition wins, through `if`/`try`
   branches". R1-C46 documents the opposite: only a direct statement of a body shadows. A definition under
   `if`/`try`, or a legitimate rebinding (a property's setter), keeps *both* bodies walked. That made the
   predicted "shadowed" 1 and 18 where codemap has none. The script was corrected to the documented rule
   after the run. That is a post-run revision, and it is named as one.
2. **That exposed a real loss.** Both bodies of such a node were walked, but `_process_function` *overwrote*
   the node's counter with the last body's. So the first body's sites were counted nowhere: neither on
   the node nor as shadowed. Fixed: counts of bodies that share a node add up. This is the 1 (bquant,
   `ZigZagSwingStrategy.deviation`, a property) and the 18 (`_pytest`) moving into the function scope.
3. **A nested namesake became the method.** In `_pytest`, `def getfixturedefs` nested in
   `FixtureManager.getfixtureclosure` was taken for the *method* `FixtureManager.getfixturedefs`, because a
   node id is built from the class chain only. Its calls and edges went to a namesake, including a false
   self-loop. Fixed: a def nested in a function is never a definition node. The conservation check had
   counted its 2 sites as nested, where codemap counted them in a method.

**Surprises:** items 2 and 3 are defects older than this work, found only because the counts now have to
add up to the source. Item 1 is my prediction being wrong about a rule that is written down in the code.
