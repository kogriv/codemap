# Design — the fast tier follows a call through an attribute chain from an import

**Status:** ✅ **shipped** (2026-11-03, no schema change), with acceptance reconciled below. Pre-registered in 3462ed0 before any code. **Motivates:** the failed expectation E6
in [dotted_imports.md](dotted_imports.md). **Backlog:** R1-C71.

## The defect

The fast tier's `_resolve` reads a callee of the form `Name(...)` or `Name.attr(...)` and nothing
deeper. Measured on fixtures in R1-C68:
- `import pkg.analysis.b` + `pkg.analysis.b.f()` gives no call edge.
- `from pkg.analysis import b` + `b.f()` gives the edge.

The same call is resolved or lost depending on the spelling of its import. The deep tier (jedi)
resolves both.

Two more shapes have the same root:
- **An external chain is counted as unresolved.** `import numpy as np` + `np.random.rand()` lands in
  `calls.unresolved`, while `np.zeros()` lands in `calls.external`. The root is the same import.
  "Unresolved" claims ignorance where the tool knows the call leaves the package.
- **The package root itself is read as external.** The internal test is
  `target.startswith(pkg + ".")`, so `import pkg` + `pkg.f()` is filed as external. The bound target
  `pkg` is the package, but `"pkg".startswith("pkg.")` is false. The same test lets a dotted import's
  bound name `pkg` fall outside the package.

## D1 — follow an internal chain hop by hop, emit only onto a node

For `root.a1.….ak.attr(...)`, where `root` is bound by an import to an internal target `T` (the package
or anything in it):
- start with `cur = T`;
- for each part, set `cur = _follow_reexport(cur + "." + part)`. This is the function the depth-1 case
  already uses: one hop through a re-export when the name is not a node;
- the result is offered as `resolution="imported"`.

The soundness guard in `_process_function` is unchanged: an internal target that is not a graph node
is counted as unresolved and emits nothing. So a chain through a module-level *object*
(`b.registry.get()`) stays unresolved. That needs a type, which is the deep tier's job.

The depth-1 case becomes the one-hop instance of the same loop and gives the same answer as today.

## D2 — an external chain is external, at any depth

A chain whose root is bound to a target outside the package is `external`, whatever its depth. No
edge, as for every external call: only the counter moves, from `unresolved` to `external`.

## D3 — the package root is internal

`internal(t) := t == pkg_root or t.startswith(pkg_root + ".")`. It is used for the call and name-value
resolvers alike, so `import pkg; pkg.f()` resolves as `from pkg import f; f()` does.

**Out of scope:**
- `self.a.b()` chains: an instance attribute, so a type question.
- Shadowing and import order: not modelled by the fast tier anywhere, and unchanged.
- The deep tier: unchanged. It falls back to the fast tier only where jedi finds nothing, so it may
  gain an edge there, and that is measured.

## Pre-registered acceptance (committed before the code)

The predictions come from an independent AST script, `research/bench/r1c71/predict_chain_calls.py`,
written from Python semantics. It does not import codemap. Its outputs, computed before any code, are
committed beside it:
- `pred71__pytest.json`: pytest 9.1.1;
- `pred71_bquant.json`: bquant `8efa112`;
- `pred71_codemap.json`: codemap at this commit's source.

- **C1, fixtures** (fast tier). Each row is one call in `pkg/core/a.py`, with `pkg/analysis/b.py`
  defining `f`, `class K` with method `m`, and `registry = {}`:

  | import + call | expected |
  |---|---|
  | `import pkg.analysis.b` + `pkg.analysis.b.f()` | edge `→ pkg.analysis.b.f` (was none) |
  | `import pkg.analysis as pa` + `pa.b.f()` | edge `→ pkg.analysis.b.f` (was none) |
  | `from pkg import analysis` + `analysis.b.f()` | edge `→ pkg.analysis.b.f` (was none) |
  | `import pkg.analysis.b` + `pkg.analysis.b.K.m()` | edge `→ pkg.analysis.b.K.m` |
  | `import pkg.analysis.b` + `pkg.analysis.b.registry.get()` | no edge; counted unresolved |
  | re-export `from .b import f` in `pkg/analysis/__init__.py` + `import pkg.analysis` + `pkg.analysis.f()` | edge `→ pkg.analysis.b.f` |
  | `import pkg` + `pkg.analysis.b.f()` | edge `→ pkg.analysis.b.f` |
  | `import pkg` + `pkg.top()` (with `top` defined in `pkg/__init__.py`) | edge `→ pkg.top` (D3; was external) |
  | `import os.path` + `os.path.join("a")` | counted external (was unresolved) |
  | `from pkg.analysis import b` + `b.f()` | edge, unchanged (control) |

- **C2, `_pytest` (fast).**
  - The new `calls` edges are the predicted 16 pairs, less any pair already present before (a pair
    can also be reached by a depth-1 call elsewhere). Pair-by-pair reconciliation; every mismatch is
    named as the script's error or the code's.
  - Σ `calls.external` over all nodes rises by exactly **126**.
  - Σ `calls.unresolved` falls by exactly **126 + 20**: the external sites plus the internal sites
    that now resolve.
  - The one predicted internal-unresolved site stays unresolved.
  - Nothing else changes: nodes outside `extras.calls`, and every non-`calls` edge.
- **C3, bquant (fast).** 0 new edges. Σ `external` +39, Σ `unresolved` −39. Every edge byte-identical.
- **C4, codemap's own tree (fast).** 0 new edges. Σ `external` +17, Σ `unresolved` −17. Edges
  byte-identical.
- **C5, deep tier on bquant.** Two builds before, two after. The `imports` edges are identical, and the
  `calls`/`accesses` differences after the change are within the before-vs-before noise. That noise
  is jedi in `_validate`, measured in R1-C68.
- **C6, cost.** bquant fast build within ±10 % (median of 3).
- **C7, mutation.** Each guard is red on a reverted piece:
  - hop following off: rows 1–3 lose their edge;
  - root equality off: row 8 is external again;
  - external chains off: row 9 is unresolved again.
- **C8, suite.** All green; the README count is moved in the same commit.

At least one expectation fails if nothing is done: C1 rows 1–3, 6–9 and C2–C4 all differ from today.

## Acceptance reconciled (2026-11-03)

Fixtures ran locally. The trees, the deep builds, the timing and the suite ran on the stand inside the
shared core-slot accounting: before = `3462ed0`, after = the same tree plus the change. The three
predictions were re-run on the stand's copies and reproduce byte for byte.

| | expected | measured | |
|---|---|---|---|
| C1 (10 rows + 1) | as tabled | all 10 rows exact. One row was added during the work: `pkg.analysis.b.registry.get("k")` is `dynamic` before and after (see "changed in the code" below) | holds |
| C2 edges | the 16 predicted pairs, less those present before (0) | **16 new pairs, exactly the predicted ones**; none missing, none extra, none removed | holds |
| C2 Σ external | +126 | **+117** | **differs, reconciled below** |
| C2 Σ unresolved | −146 | **−114** | **differs, reconciled below** |
| C2 else | nothing | nodes identical outside `extras.calls`; no non-`calls` edge changed | holds |
| C3 bquant | 0 edges; external +39, unresolved −39 | 0 edges; **external +38, unresolved −36, dynamic −2** | edges hold; counters reconciled below |
| C4 codemap | 0 edges; external +17, unresolved −17 | 0 edges; **external +16, unresolved −16** | edges hold; counters reconciled below |
| C5 deep bquant | `imports` identical; `calls`/`accesses` within noise | `imports`: 299 edges, one hash in all four builds. Before→after: `calls` +1, `accesses` +1. Before→before: `calls` +1, `accesses` ±1. After→after: `calls` −2, `accesses` +1 | holds |
| C6 | ±10 % | median 8.21 s → 8.22 s | holds |
| C7 | three mutations red | all three red. With `behavior.py` reverted, 11 of 14 tests fail; the 3 that pass are the rows that do not change | holds |
| C8 | suite green | 1105 passed, 3 skipped (1091 + 14) | holds |

**The counters, reconciled exactly.** The scripts are in `research/bench/r1c71/`: `compare_graphs.py`, `own_body_external.py` and `own_body_literal_dispatch.py`. Every edge prediction held. Every counter difference has one of
three causes, each counted.
1. **The prediction counted sites that codemap keeps no counter for.** `extras.calls` counts a node's
   *own* call sites. Calls at module level and in a function nested in another produce edges, but no
   counts: `_process_module_level` and `_collect_nested_calls` emit edges only. This is not changed
   here. The script assumed otherwise.
   - bquant: 1 site (`stats.norm.cdf` in `ks_distance`, nested in `lilliefors_normal`).
   - codemap: 1 site (`os.path.getmtime` in `probe`, nested in `mtime_probe`).
   - `_pytest`: 1 internal site, plus the external sites below.
2. **String-keyed dispatch was counted as `dynamic` before.** `X.get("lit")`, `.create(…)` and
   `.register(…)` on a chain fell through to the `dynamic` rule. An external chain now answers
   `external` first. Counted independently in node bodies: **22** in `_pytest`, **2** in bquant, **0** in
   codemap, which are exactly the `dynamic` deltas. That is why unresolved fell by less than external
   rose: 117 + 19 = 114 + 22.
3. **A stdlib module shadowed by a same-named internal one** (`_pytest` only). `import pathlib` in
   `_pytest/config/__init__.py` is the standard library, but the flat-layout rule (`qualify_target`,
   R1-C21) rewrites it to `_pytest.pathlib`, a module of the package. The chain `pathlib.Path.cwd()` is
   then followed internally, lands on no node, and stays unresolved: 2 sites (`Config.__init__`,
   `get_config`). This is a defect, but not R1-C71's: it is **R1-C72**, below.

Per node in `_pytest`, the own-body external sites predicted sum to 118. Measured: 118 − 2 (cause 3)
+ 1 = 117. The +1 is `_pytest.pathlib._is_same`, defined twice under a module-level `if/else`: codemap
counts it as a node, and the script took it for a nested function. That is the script's error.

**Changed in the code during the work:** a chain of depth ≥ 2 that lands on no definition falls through
to the old rules. Without that, `b.registry.get("k")` would have changed from `dynamic` to `unresolved`,
losing information the old answer had. The row was added to the tests.

**Surprise, recorded as R1-C72.** In the `_pytest` graph, **65 edges carry `resolution: "flat"`** (24
`imports`, 41 `export`) in a packaged layout, where there should be none. Every one of them is a stdlib
import (`warnings` 34, `pathlib` 23, `doctest`, `logging`, `unittest`, `pprint` 2 each) rewritten to the
same-named module of the package. That includes `_pytest.doctest → _pytest.doctest`, an import of
itself. bquant and codemap have 0 such edges. Not fixed here.
