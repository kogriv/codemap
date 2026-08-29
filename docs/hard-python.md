# Hard Python — what codemap handles, and what it says when it can't

Real packages are not tidy. This page states, from a measured probe rather than from
intent, which awkward Python constructs come through the extractor intact, which are
approximated (and labelled as such), and which conditions make codemap **warn instead of
answering confidently**.

The probe is `tests/fixtures/hardpkg` — one module per construct — plus the hazards a
repository cannot sensibly hold (a file with a syntax error, a latin-1 file, a directory
symlink into its own ancestry), which the tests build in a temp copy.

## Handled

| construct | what you get |
|---|---|
| metaclasses, `__init_subclass__` registries | class + `inherits` normally. The *registry* seam is a separate mechanism ([dispatch bridging](../gaps/dispatch_bridging_2026-07-28.md)) |
| `Generated = type("Generated", (…), {…})` | an **attribute** node — honest: it is a value. codemap does not invent a class node the source never declares |
| module `__getattr__` (PEP 562) | module and helpers extracted; internal calls resolve |
| monkeypatching (`mod.fn = other`) | a `references` edge to the replacement. The *static* call edge to the original stays — that is what the source says |
| PEP 695 generics (`def f[T]`, `class C[T]`) | extracted normally. A `type X = …` alias produces **no node** (type aliases are not in the node vocabulary) |
| `match`/walrus, `async`/`await`/`async with`, `Protocol`, `@overload` | extracted normally |
| `functools.wraps`, `singledispatch` + `.register` | the decorated function keeps its own body's call edges |
| mutual imports | no crash, no unbounded walk |
| BOM files, empty files, `.py` beside `.pyi` | handled (`.py` wins over the stub) |
| flat module directories, namespace packages | see [flat-layout.md](flat-layout.md) |

## Approximated, and labelled

**Stub-only modules.** A `.pyi` with no sibling `.py` is kept — a stubs distribution has
a real declared surface — but every node from it carries `extras.stub = true`, and
consumers that reason about execution exclude it. A stub is never a dead-code candidate:
"nothing calls it" says nothing about a symbol with no body.

**Star imports.** `from X import *` now emits the `imports` edge to `X`, so the
dependency appears in layers, cycles and `check`. Which *names* it binds is not expanded
— the edge is the part that was missing, and expanding names is unmeasured work; a use of
a star-imported name therefore may not resolve to its definition.

**Quoted annotations.** `def f() -> "Base"` resolves like the unquoted form and carries
the same `resolution="annotation"` label. Whether the author quoted the type is syntax,
not meaning. An annotation string that is not a type expression yields nothing.

## Conditions codemap refuses to answer over quietly

### A directory symlink into its own ancestry

A `loop -> .` link makes every file reachable under unboundedly many module names. The
measured damage before the fix: **615 modules for 15 real ones**, 2378 nodes from 58,
nested 40 deep — with no warning, and every aggregate (layers, cycles, hotspots,
dead-code) computed over the fiction.

Directory symlinks *are* followed — a symlinked source tree is a legitimate layout — but
a directory whose real path was already walked is not re-entered. The module that would
have been the duplicate is recorded:

```json
"aliased_modules": [{"id": "pkg.loop", "same_as": "pkg"}]
```

### A file the extractor cannot read

A syntax error or a non-UTF-8 byte used to remove a module from the graph in silence,
after which the report was about a tree codemap had not fully seen — the same shape as
[issue #5](https://github.com/kogriv/codemap/issues/5), where absence of data rendered as
a clean bill of health. Now:

```
[warning] 2 input file(s) produced no module (1 encoding, 1 syntax): pkg/broken.py, pkg/latin1.py
```

…and the list travels in the graph itself, under
[`provenance.inputs.skipped`](provenance.md), so a consumer holding only `graph.json` is
told too.

### Syntax newer than the interpreter you run on

**codemap parses a target with the `ast` of the Python it is running on.** It never imports
your code, but it does have to *parse* it — so a module written in syntax your interpreter
does not know is, to codemap, a file it cannot read. It lands in the same place as a
genuine syntax error: named, with `reason: "syntax"`, in `provenance.inputs.skipped`, and
counted in the `[warning]` line above.

Concretely: codemap running on 3.11 cannot read a target that uses PEP 695 generics
(`class Box[T]:`, `def identity[T](x: T) -> T:`), because that syntax arrived in 3.12.
Nothing is silently lost — but the graph is a graph of the modules that parsed.

**Run codemap on a Python at least as new as the code you point it at.** Since the tool
itself needs 3.11+, this only bites on targets using very recent syntax; when it does, the
skipped list says exactly which files and why.

*(The project's own suite asserts this property on every interpreter it supports — a
3.12-syntax fixture is either extracted or named, never dropped. See [ci.md](ci.md).)*

### The counts not adding up

A conservation check compares modules against input files in both directions:

- more modules than files → the tree was walked more than once;
- fewer, beyond the files already accounted for as unreadable → files went missing
  unexplained.

Neither is a heuristic and neither has a threshold: both are provably impossible states.
The point of the check is the cause codemap has *not* met yet — it flags the symlink
explosion without knowing what a symlink is.

## Known gaps

- A function-local `from .x import a_fn` **is** in the import map since R1-C29 (issue #11),
  carried on the edge as `extras.scope = "function"`, so it counts for coupling, layers,
  dependents and orphan detection. Since R1-C30 it also resolves *calls and references* on
  both tiers — the name map is built per function, so an import in one function resolves
  nothing in its neighbours. It is deliberately not treated as *shadowing* — see
  [dead-code.md](dead-code.md). It is also excluded from **import cycles** on purpose: a
  lazy import does not run at import time, so a cycle closed only by one cannot break on
  import. Those appear separately, as "dependency cycles closed only by a function-local
  import". A class-body import is treated as eager, because it runs at class-definition
  time; griffe records neither, so both are collected by codemap's own AST pass.
- `type X = int | str` (PEP 695 alias) produces no node.
- The names a star import binds are not expanded.
- Dynamic dispatch remains dynamic: `getattr`, `importlib`, and registry lookups by a
  computed key are lower bounds, as everywhere else in codemap.

**Gap:** [../gaps/hard_python_robustness_2026-08-25.md](../gaps/hard_python_robustness_2026-08-25.md).
**Design:** [design/hard_python_robustness.md](design/hard_python_robustness.md).
