# codemap — gap: robustness on hard Python (axis B2) — a symlink turns 17 files into 615 modules

**Date:** 2026-08-25
**Source:** deliberate probe of axis **B2** — the last axis still marked `⬜ open` in
[dogfood_axes.md](dogfood_axes.md), and the axis that produced issues
[#4](https://github.com/kogriv/codemap/issues/4)/[#5](https://github.com/kogriv/codemap/issues/5) for free the
first time a stranger pointed the tool at a second real target. Not a bug report from outside: a measurement
run before someone else runs it.
**Type:** robustness / honesty — every finding below is a **silent** one. The build exits 0 and prints
nothing; the damage is visible only if you already know the answer.
**Related:** `flat_layout_gap_2026-08-24.md` (same class — a confident graph over a tree the extractor did not
read), `dead_code_high_band_2026-08-24.md` (R1-C13 lower-bound labels).
**Design:** [docs/design/hard_python_robustness.md](../docs/design/hard_python_robustness.md).
**Backlog:** R1-C23.
**Status:** ⬜ open — measured, designed, not yet built.

## 1. The probe

A 17-file package (2814 bytes, 157 loc) exercising the constructs the axis names, one per module so a failure
localises: metaclass + `__init_subclass__` registry, `type()`-built class, module `__getattr__` (PEP 562),
monkeypatching, conditional imports (`try/except ImportError`, `TYPE_CHECKING`), PEP 695 generics
(`def f[T]`, `class C[T]`, `type X = …`), `match`/walrus, `async`/`await`/`async with`, `Protocol`,
`@overload`, `functools.wraps`, `singledispatch`, star-import, mutual imports, a `.pyi` stub, a BOM file, an
empty file, a syntax-error file, a latin-1 file, and a directory symlink pointing at its own parent.

`codemap build` on it: **exit 0, no warning, no note.**

## 2. What held — stated first, because honesty cuts both ways

The majority of "hard Python" is handled, and handled *honestly*:

| construct | result |
|---|---|
| metaclass, `__init_subclass__` registry | class extracted, `inherits` correct; the registry seam is unmodelled but nothing false is claimed |
| `type("Generated", …)` | recorded as an **attribute**, not invented as a class — the honest answer |
| module `__getattr__` (PEP 562) | module and its helpers extracted, internal call resolved |
| monkeypatching (`mod.fn = other`) | `references` edge to the replacement |
| PEP 695 `def f[T]`, `class C[T]` | extracted normally |
| `match`/walrus, `async with`/`await`, `Protocol`, `@overload` | extracted normally |
| `functools.wraps`, `singledispatch` + `.register` | decorated function keeps its own body's call edges |
| mutual imports (`circ_a` ↔ `circ_b`) | no crash, no infinite walk |
| BOM file, empty file, `.py` next to `.pyi` | handled (`.py` correctly wins over the stub) |
| **`dead-code high`** | **empty** — not one false confident claim on this fixture |

That matters for sizing: B2 is not a rewrite. It is five specific holes.

## 3. Findings

### B2-1 — a directory symlink cycle inflates the graph 36× (silent)

`hardpkg/loop → .` (a directory symlink to its own parent — an ordinary thing in a repo: a `latest` link, a
vendored checkout, a bind-mounted subtree).

| | files on disk | modules in graph | nodes | edges |
|---|---|---|---|---|
| the truth | 17 | 15 | 58 | 91 |
| what codemap built | 17 | **615** | **2378** | **3771** |

**600 of 615 modules (98%) are phantom**, nested to depth 40 (`hardpkg.loop.loop.loop.…`). No warning.
Every aggregate is then computed over that fiction: `stats`, `architecture` (layers, cycles, coupling),
`hotspots`, `communities`, dead-code. The walk terminates, so nothing even hangs to tip the reader off.

**And the tool already holds the refutation.** `codemap scope` on the same tree, with the symlink in place,
answers **`files: 17`** — the scope manifest (M19.A) enumerates the real input correctly. Two halves of the
same tool disagree by 36× and nothing compares them.

### B2-2 — a file the extractor cannot read simply disappears (silent)

`broken.py` (a syntax error) and `latin1.py` (`# -*- coding: latin-1 -*-`, one non-UTF-8 byte) are **absent
from the graph**, with no message on stdout, in `stats`, or in any report. Both are ordinary in a real
repository: a work-in-progress file, a vendored legacy module, a generated file.

This is the exact shape of #5 — the graph reports on a tree it did not fully read, and renders the omission
as a clean bill of health. A function defined only in the skipped module is not "dead", it is *unseen*; a
dependency declared only there does not exist as far as `architecture` and `check` are concerned.

### B2-3 — `from X import *` produces no `imports` edge

```python
from .meta import *        # ← no edge at all
from .wrapped import trace # ← edge recorded
```

Measured on the fixture: `star.py` yields exactly one `imports` edge, to `wrapped`. The dependency on `meta`
is invisible, so it cannot appear as a layer violation, cannot close an import cycle, and cannot be seen by
`check`. A star-import is the *least* explicit dependency in the language and the one most worth surfacing.

### B2-4 — string and `TYPE_CHECKING` annotations are invisible

```python
def fetch(r: Reader): ...        # → references edge, resolution="annotation"
def dump(o) -> "Base": ...       # → nothing
```

R1-C22 taught the graph that an annotation is a reference. It only learned the *unquoted* form. The quoted
form is the standard idiom for a type that would otherwise be a circular import — i.e. exactly the
dependencies that matter most to layering are the ones dropped.

### B2-5 — a stub-only module is presented as real code

With `api.pyi` present and no `api.py`, the graph gains a module `hardpkg.api` containing a function
`stub_only` — a symbol that does not exist at runtime. Low blast radius (it takes a stub-only module to hit
it), but it is an invented node, and inventing is worse than omitting.

### Two honest omissions noticed in passing (not defects, recorded so they are not rediscovered)

- PEP 695 `type Alias = int | str` produces no node — type aliases are not in the node vocabulary.
- A function-local `from .circ_a import a_fn` followed by `return a_fn` produces no reference; the import map
  is built from module-level imports only (R1-C22-f1 deliberately does not treat local imports as shadowing,
  but it does not resolve them either).

## 4. Why it matters

Every one of B2-1…B2-4 is an **affirmative over a blind spot**, the failure this project has now hit four
times (#1 `risk:"none"`, #3 stale-labelled-fresh, #5 0 imports rendered as health, #7 `high` over a visible
reference). The pattern is stable enough to name: *the tool answers from what it read, and never says what it
failed to read.*

B2-1 is the severe one. A 97%-fiction graph is worse than no graph, because it is confident, plausible and
shaped correctly — the phantom modules have real names and real edges.

## 5. Scope of a full solution

Four repairs plus one generic safety net; sizes are small because the parsing already works.

1. **B2-1** — resolve directories to a canonical real path and refuse to descend into one already visited.
2. **B2-2** — the extractor must *return* what it skipped, and the build must say so.
3. **B2-3** — emit the module-level `imports` edge for `from X import *` (the target module is known
   exactly; expanding the names it binds is a separate, optional decision).
4. **B2-4** — parse string annotations and resolve them like unquoted ones (`resolution="annotation"`).
5. **The net** — a derived diagnostic comparing graph module count against the scope manifest's file count.
   It catches B2-1 without knowing about symlinks, and it would have caught #5 too.

Acceptance is **not** byte-identity: B2-3/B2-4 deliberately add true edges, and B2-1 removes fictional ones.
The criterion is *the fixture's numbers match the truth column of §3, the codemap and bquant graphs change by
additions only (plus whatever B2-3/B2-4 legitimately add), and every skipped input is named on stdout.*

Design decisions and sizing: [docs/design/hard_python_robustness.md](../docs/design/hard_python_robustness.md).
