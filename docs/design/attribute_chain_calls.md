# Design — the fast tier follows a call through an attribute chain from an import

**Status:** 🧪 pre-registered (2026-11-03), not yet shipped. **Motivates:** the failed expectation E6
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
