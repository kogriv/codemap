# Design — `import a.b.c` depends on `a.b.c`, not on `a`

**Status:** 🧪 pre-registered (2026-11-03), not yet shipped. **Motivates:** gap
[contract_silent_passes_2026-11-03](../../gaps/contract_silent_passes_2026-11-03.md). The probe's
own control failed: `forbidden core → analysis` answered "✅ satisfied" on a tree that breaks it.
**Backlog:** R1-C68.

**Guiding invariants (unchanged):** source-only, resolved-or-honestly-flagged, the import map says
what each scope contributed (R1-C29), and a gate names what it did not judge (R1-C30-f2).

## The defect

A module-level `import pkg.analysis.b` (no `as`) produces the `imports` edge `pkg.core.a → pkg`. The
same happens for `import pkg.analysis`, in the fast tier and the deep tier alike. Every other spelling
gets the right target: `import … as`, `from pkg.analysis import b`, `from pkg.analysis.b import X`,
and both relative forms.

Mechanism: the module-level import map comes from griffe, which records "bound name → path". For
`import a.b.c` the bound name is `a`, so the path is recorded as `a`. Python, meanwhile, loads `a`,
`a.b` and `a.b.c`. The module names `a.b.c` in its source and uses it through the attribute chain.

codemap's own AST pass (R1-C23/R1-C29/R1-C48) already reads `ast.Import` with the full `a.name` for
imports written inside a function, inside a class body or under `if TYPE_CHECKING:`. So those spellings
are right. Two places are not:
1. **Module level.** That pass does not record module-level `ast.Import` at all. It treats griffe as the
   source of truth there.
2. **The file gate.** `NESTED_IMPORT_HINT` decides whether a file is parsed at all. It matches only
   indented imports and star imports. A file whose only imports are at the top is never parsed.

A suspected second symptom of the same root, to be measured rather than assumed:
`if TYPE_CHECKING: import pkg.analysis.b`. griffe files the head `pkg` as module-level. Our pass
records `pkg.analysis.b` as `type_checking`. The demotion rule compares targets, `pkg` against
`pkg.analysis.b`, so they never meet, and an **eager** edge `→ pkg` is left behind.

Neither bquant nor codemap uses the spelling (`git grep '^\s*import <pkg>\.'` → 0), so the R2 truth set
of 266 edges could not have caught it. `_pytest` (pytest 9.1.1) has 9 such lines and `docutils` 4.

## D1 — the edge goes to the module named, and only to it

**Recommended:** `import a.b.c` yields `→ a.b.c` (its containing module, resolved as for every other
spelling) and **not** `→ a`. That is what `import a.b.c as x` and `from a.b import c` already produce.
It is also the convention the R2 truth uses for `from bquant.visualization import charts`.

- **Rejected: keep `→ a` and add `→ a.b.c`.** It is true that Python executes `a/__init__`. But no other
  spelling records that implicit parent edge. Recording it for one spelling only would make two
  equivalent imports give different graphs, which is the defect itself, turned around.
- **Rejected: also add `→ a.b`.** Same reason.

## D2 — drop griffe's head entry only when the head is bound by nothing else

griffe's map cannot tell `import a` from `import a.b.c`: both give `{"a": "a"}`. The AST can. The
pass records:
- `dotted_heads`: heads of module-level dotted `import` statements without `as`, including under
  `TYPE_CHECKING`, which griffe also files at module level;
- `plain_heads`: names imported plainly, as in `import a`.

The entry `a → a` from griffe is skipped when `a ∈ dotted_heads − plain_heads`. `from a import x`
never produces the griffe entry `a → a` (its key is `x`), so it needs no rule.

## D3 — the file gate learns the spelling

A file is parsed when it has an indented import, a star import, **or** a top-level `import` statement
whose names contain a dot. The gate stays a cheap regex; a false positive costs one parse. The shared
`NESTED_IMPORT_HINT` is left alone: call resolution (`behavior`) does not need the change. In Python,
`import a.b.c` binds the name `a`, and resolving `a.b.c.f()` through `a` is semantically right. That
claim is measured in acceptance (E6), not assumed.

Known limit, stated rather than fixed: a dotted name after a backslash continuation line is not seen
by the gate.

## Pre-registered acceptance (committed before the code)

Fixture builds run locally (seconds). The three tree builds, before and after, run on the stand inside
the shared core-slot accounting.

- **E1, the forms.** One fixture per spelling, in `pkg/core/a.py`, with `pkg/analysis/b.py` present:

  | spelling | `imports` edges after the change |
  |---|---|
  | `import pkg.analysis.b` | exactly `pkg.core.a → pkg.analysis.b`, scope module |
  | `import pkg.analysis` | exactly `→ pkg.analysis` |
  | `import pkg.analysis.b, pkg.x` (with `pkg/x.py`) | `→ pkg.analysis.b` and `→ pkg.x` |
  | `import pkg` + `import pkg.analysis.b` | `→ pkg` and `→ pkg.analysis.b` |
  | `def f(): import pkg.analysis.b` | `→ pkg.analysis.b`, scope function (unchanged, already right) |
  | `if TYPE_CHECKING: import pkg.analysis.b` | exactly `→ pkg.analysis.b`, scope type_checking; **no** eager `→ pkg` |
  | `try: import pkg.analysis.b` / `except ImportError: pass` | `→ pkg.analysis.b`, scope module |

  Before the change, measured on the same fixtures: the TYPE_CHECKING row also has an eager `→ pkg`.
  If it does not, the suspected second symptom is wrong and is reported as such.
- **E2, the gate.** `forbidden = [{from="core", to="analysis"}]` with `import pkg.analysis.b`: exit 2, and
  the edge is named. This is exactly the control that failed in the probe.
- **E3, no-op trees.** bquant (`8efa112`) and codemap's own tree (the commit before the change): the graph
  JSON is **byte-identical** before and after, `provenance` aside. Neither uses the spelling.
- **E4, `_pytest` (pytest 9.1.1), predicted from Python semantics by an independent AST script, not by
  codemap's code:**
  - new: `assertion.util → _code`, `config → deprecated`, `config → hookspec`,
    `config.argparsing → _io`, `main → _code`, `terminal → _version`;
  - removed: `assertion.util`, `config.argparsing`, `main`, `nodes`, `terminal`, `unittest` → `_pytest`;
  - nothing else changes: every node and every non-`imports` edge is identical.

  A removed edge is predicted only where the before-graph has it. A mismatch is reconciled pair by
  pair: either the script or the code is wrong, and which one is named.
- **E5, cost.** bquant build time after the change is within ±10 % of before (3 runs each, median).
- **E6, calls untouched.** On a fixture `import pkg.analysis.b` + `def g(): return pkg.analysis.b.f()`:
  the `calls` edge `g → pkg.analysis.b.f` is present before **and** after.
- **E7, mutation.** Three guards, each shown red on a reverted piece:
  - without the module-level append, the E1 row 1 test fails;
  - without the head suppression, a "no edge to `pkg`" assertion fails;
  - without the gate extension, a fixture with **only** top-level imports fails.

At least one expectation fails if nothing is done: E1 and E2 fail on the current code, as the probe
showed.
