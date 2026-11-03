# Design — the flat-layout inference stays out of a package that imports itself by name

**Status:** 🧪 pre-registered (2026-11-03), not yet shipped. **Motivates:** the R1-C71 reconciliation
([attribute_chain_calls.md](attribute_chain_calls.md), "Surprise"). **Backlog:** R1-C72. **Revises:**
[flat_layout.md](flat_layout.md) D2.

## The defect

R1-C21 D2 rewrites an unresolved bare import `X` into `<importer's parent>.X` when a module of that
name sits beside the importer. Its safety argument was a measurement: on a proper package this "fires
zero times". It was measured on bquant and codemap, and neither has a module named like a top-level
module it imports.

pytest has several (`_pytest/warnings.py`, `pathlib.py`, `logging.py`, `doctest.py`, `unittest.py`,
`_io/pprint.py`). In a package, `import warnings` is absolute: it is always the standard library.
Measured on pytest 9.1.1:
- **65 edges labelled `resolution: "flat"`**: 24 `imports` and 41 `export`. Among them is
  `_pytest.doctest → _pytest.doctest`, a module importing itself.
- **50 bindings in 29 modules** are rewritten into the package. The 114 call sites through them, in
  counted bodies, read as internal and unresolved instead of external.
- bquant has 3 such bindings: `import pandas_ta`, `import pandas_ta as ta` and `import talib` in the
  same-named modules of `indicators/library/`. They produce no edge today, only by luck: a module never
  links to itself, and the 5 calls through them sit at module level or in nested functions.

The rewrite happens in three places, and they must agree:
- `_resolve_edges` (pass B for `imports`, and `export` for re-exports);
- `gsource.module_imports` / `qualify_target`, the import map for calls and attribute access;
- `roots.core_is_flat`, the cross-root gate (R1-C21 D6).

## D1 — a package that imports itself by qualified or relative name is not flat

**Recommended:** the flat inference applies only when the core shows no sign of being a package. The
sign is at least one import of one of its own modules by a package-qualified or relative name
(`from _pytest.pathlib import …`, `from .x import …`). That is exactly what pass A resolves, so the
test is "pass A would emit at least one internal edge". It is computed from the collected imports
*before* anything is emitted, so edge order in the artifact does not move.

Why this is the right evidence:
- A genuinely flat directory imports its siblings by bare name *only*: that is the layout R1-C21
  fixed, where 0 qualified internal edges came out over ≥ 2 modules.
- A package's qualified self-imports work only if its parent is on `sys.path`, and there a bare
  `import X` is absolute.
- One rule, one place: the same predicate as `roots.core_is_flat` (a namespace root, or flat edges
  present), so after this change the three sites agree by construction.

**Kept, deliberately:**
- In a genuinely flat layout, a sibling named `logging.py` *does* shadow the standard library at
  runtime (the script directory comes first on `sys.path`), so the inference stays and stays right.
- A package with no internal imports at all is ambiguous, and keeps today's behaviour. That limit is
  named in the docs.

- **Rejected: never rewrite a stdlib name** (`sys.stdlib_module_names`). It is wrong for the flat layout
  just described. It also misses third-party twins (`pandas_ta`, `talib` in bquant).
- **Rejected: key on `__init__.py`.** R1-C21 already found a flat directory that ships one
  (`flat_layout.md` D6).

## D2 — the import map follows the same verdict

`module_imports` / `qualify_target` get an empty "known modules" set when the core is packaged, so no
binding is rewritten. Calls through `warnings.warn` then count as external, as they should.
`roots.core_is_flat` keeps its definition, and it now agrees with D1 because no flat edge is emitted in
a packaged core.

## Pre-registered acceptance (committed before the code)

The predictions come from the package source plus the before-graph, by scripts that do not import
codemap. They are committed beside this design in `research/bench/r1c72/`:
- `twins.py`: bindings and call sites;
- `predict72.py`: flat edges;
- `twin_edges.py`: non-flat edges reached through a twin binding.

- **F1, `_pytest` (pytest 9.1.1, fast).**
  - Exactly the 65 flat edges disappear (listed in `pred72__pytest.json`); 0 of them are public
    exports, so none turns into an external export.
  - **No other edge changes.** `twin_edges.py` finds no non-flat edge reached only through a twin
    binding; the 3 `imports` it lists are also reached by a qualified import in the same module.
  - Nodes are identical outside `extras.calls`.
  - Σ `calls.external` rises by **114**, and Σ (`unresolved` + `dynamic`) falls by **114**.
- **F2, bquant (`8efa112`) and codemap (this commit's source), fast:** graphs **byte-identical**.
- **F3, fixtures.**
  - A packaged `pkg` with `pkg/logging.py`, `pkg/a.py` doing `import logging` + `logging.getLogger()`,
    and `pkg/b.py` doing `from pkg import a`: no edge `a → pkg.logging`; the call counts as external.
  - The same tree **without** `pkg/b.py`'s qualified import, i.e. flat: the flat edge `a → pkg.logging`
    is present. That is the shadowing, kept.
  - The existing R1-C21 tests (flat fixtures, issue #6 cross-root, issue #10 deep) stay green unchanged.
- **F4, deep tier on bquant:** `imports` identical; the rest within the jedi noise measured before.
- **F5, cost:** bquant fast build within ±10 %.
- **F6, mutation.**
  - With the packaged verdict forced to "flat", F3's packaged fixture gets the false edge back.
  - With the import map ungated, its call is internal-unresolved again.
- **F7, suite:** green, with the README count moved in the same commit.

At least one expectation fails if nothing is done: F1 and F3's packaged row both differ from today.

## Addendum, before acceptance (2026-11-03): D1 as written was wrong, and the suite said so

The first implementation of D1 ("any package-qualified self-import means packaged") turned 6 existing
tests red. Four are in R1-C21, two in R1-C26. Their fixture `tests/fixtures/flatpkg` is **mixed**:
`gamma.py` has both `import beta` (bare sibling) and `from flatpkg.alpha import WIDTH` (qualified). That
works when both the directory and its parent are on `sys.path`. There the bare import *does* reach the
sibling, so the inference is right, and D1 switched it off.

So the evidence is the wrong way round. Whether the package imports itself by name does not decide the
layout. What decides it is whether some bare import *can only be a sibling*.

**D1, revised.** The flat inference applies when the core root is a namespace directory, or when at least
one bare import names a sibling module (other than the importer itself), and that name is not a
standard-library module (`sys.stdlib_module_names`). Such an import works only with the directory on
`sys.path`, and then siblings do shadow the standard library, so the inference applies to every bare
import, twins included. Without such evidence a twin of a stdlib name is the standard library, and
nothing is rewritten.

- `_pytest`: all six twins are stdlib names, so there is no evidence and the inference is off.
- bquant: its twins are self-imports (`pandas_ta.py` importing `pandas_ta`), which are not evidence, so
  it is off.
- `flatpkg`: `alpha` and `beta` are evidence, so it is on.

**Named limits:**
- A package with a twin of a *third-party* name and no other evidence (say `mylib/requests.py` with
  `import requests`) still gets the false edge: telling an installed package from a sibling would make the
  graph depend on the machine.
- `sys.stdlib_module_names` differs slightly between Python versions (removed modules), so such a twin
  can read differently on 3.11 and 3.14.

**Acceptance F1–F7 is unchanged.** One row is added:
- **F3b.** The mixed fixture keeps its flat edges and its qualified edge exactly as R1-C21 pinned them.
  That is the existing tests, green.

F6's first mutation now forces the evidence to "found".
