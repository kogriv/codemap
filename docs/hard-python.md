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

### The counts not adding up

A conservation check compares modules against input files in both directions:

- more modules than files → the tree was walked more than once;
- fewer, beyond the files already accounted for as unreadable → files went missing
  unexplained.

Neither is a heuristic and neither has a threshold: both are provably impossible states.
The point of the check is the cause codemap has *not* met yet — it flags the symlink
explosion without knowing what a symlink is.

## Known gaps

- A function-local `from .x import a_fn` is not resolved (the import map is built from
  module-level imports only). It is deliberately not treated as *shadowing* either — see
  [dead-code.md](dead-code.md).
- `type X = int | str` (PEP 695 alias) produces no node.
- The names a star import binds are not expanded.
- Dynamic dispatch remains dynamic: `getattr`, `importlib`, and registry lookups by a
  computed key are lower bounds, as everywhere else in codemap.

**Gap:** [../gaps/hard_python_robustness_2026-08-25.md](../gaps/hard_python_robustness_2026-08-25.md).
**Design:** [design/hard_python_robustness.md](design/hard_python_robustness.md).
