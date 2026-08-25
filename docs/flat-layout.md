# Flat module layouts

Not every Python target is a well-formed package. Research code, `scripts/` directories,
notebook-adjacent projects and plugin folders are often a **flat directory of sibling
modules** that import each other by bare name:

```
shared/
  alpha.py        # X = 1
  beta.py         # from alpha import X     ← works because `shared/` is on sys.path
```

codemap builds these. It did not always — the two defects this page describes were found
within twenty minutes of pointing it at such a repo ([#4](https://github.com/kogriv/codemap/issues/4),
[#5](https://github.com/kogriv/codemap/issues/5)), and the worse of the two was silent.

## What you get

```bash
codemap build ./shared -o graph.json
```

Sibling imports resolve, whether or not the directory has an `__init__.py`, and each such
edge is **labelled as inferred**:

```json
{"type": "imports", "source": "shared.beta", "target": "shared.alpha",
 "extras": {"resolution": "flat"}}
```

The label matters. A bare `imports` edge is a fact the source states
(`from shared.alpha import X`); a `flat` one is an **inference about `sys.path`** — codemap
reads source only and never executes the target, so it cannot *know* the directory is
importable, only that the layout says so. Package-qualified imports in the same file stay
unlabelled, so an exact edge and an inferred one remain distinguishable.

The same inference feeds call resolution, so `beta.doubled()` → `alpha.base_width()` is a
real `calls` edge rather than an unresolved name.

### Directories without `__init__.py`

griffe treats those as **namespace packages**, which have no single source file. codemap
builds them anyway: the target module node carries `file: null` (honest — there is no file),
the modules inside keep their real paths, and the build says what it saw:

```
[warning] `shared` has no __init__.py — it is a namespace package, so its modules are only
a package by directory. Imports between them are resolved by codemap's flat-layout
inference (edges labelled resolution="flat"), not by packaging.
```

## Consumer roots

`--consumer tests` exists so `impact` can answer *"who uses this across the whole repo — core, tests,
scripts"*. On a flat layout those roots import the core the same bare way, and that resolves too:

```bash
codemap build ./shared --consumer ./tests --consumer ./scripts -o graph.json
```

```json
{"type": "imports", "source": "tests.test_alpha", "target": "shared.alpha",
 "extras": {"resolution": "flat"}}
```

This is **gated on the core actually being flat** — a namespace directory, or one whose own modules already
needed the inference. On a properly packaged core the gate is inert by construction, not by luck: that
directory is never on `sys.path`, so a bare `import config` in a script cannot be reaching `pkg/config.py`,
and inferring an edge there would invent one. The gate reads evidence rather than the presence of an
`__init__.py`: a core that ships one but still imports its own modules by bare name is flat in practice and
is treated as such.

## The deep tier

`--deep` used to be a **downgrade** on a flat layout: jedi resolves `from leaf import helper`
correctly, to `leaf.helper`, and the internal/external test read a name without the package
prefix as external — so every cross-module call was dropped. On one real flat target that was
**158 cross-module call edges on the fast tier and 0 on deep**.

The jedi boundary now applies the same sibling inference as the import map, and the two tiers
are a **union**: when jedi has no usable answer, the name-based resolver is consulted instead
of the call being discarded. `calls(deep)` is a superset of `calls(fast)`, which is what
choosing the expensive tier is supposed to buy.

Call edges keep `resolution="deep"` — that field names *which tier resolved the call*, not
which layout its target has. The flat inference stays visible where it belongs: on the
`imports` edge (`resolution="flat"`).

One thing deliberately not done: when jedi resolves a name to a definition **outside** the
package, that answer stands. It is a judgement, not a failure, and a name-based guess could
match an internal symbol of the same name by coincidence.

## When the graph is empty, codemap says so

The expensive part of the original defect was not a wrong number — it was a **confident
nothing**. With zero import edges, `architecture` reported "no layer violations" and
"acyclic", and `dead-code` listed every module of a live engine as an orphan. All true of
the graph; all false about the code.

So a build that produces **0 import edges across ≥2 modules** now announces itself, in
every place the graph is presented:

```
[warning] 0 import edges across 36 modules — the import graph is empty, so layers, cycles,
coupling and orphan detection are vacuous rather than clean. This usually means a layout
the extractor did not understand …
```

- at **build time**, on stderr;
- in **`stats`** (a `diagnostics` list, beside `freshness`);
- at the top of **`report architecture`**, **`report dependencies`** and
  **`report dead-code`**, before any conclusion drawn from the empty graph.

A second check covers the dimension the first one misses: **consumer roots were supplied, but not one
reference from them reaches the core**. That case has plenty of import edges — just none crossing a root
boundary — so the empty-graph check stays quiet while cross-root `impact` reads "isolated" for everything.

This check is independent of the resolution above: it stays correct for any layout codemap
fails to parse in future, and it is **derived, never stored** — `graph.json` gains no field,
and any consumer recomputes it from the graph it already holds.

## Boundaries

- **Ambiguity resolves toward the sibling.** A local `types.py` next to `import types`
  resolves to the local module — correct for a flat layout, wrong for a package that merely
  shares a name with a stdlib module. The edge is labelled `flat` so the assumption is
  visible. Measured on two real packages (codemap, bquant) the inference fires **zero**
  times, so a correctly-laid-out package is untouched — a test pins exactly that.
- **Only siblings.** The head of the import must name a module beside the importer;
  deeper `sys.path` games are out of scope.
- **No runtime `sys.path` reasoning** — `sys.path.insert`, `.pth` files and editable-install
  shims are outside the source-only contract. The flat layout is the one `sys.path`
  assumption codemap makes, and it is labelled.

Design and the measurements behind it: [docs/design/flat_layout.md](design/flat_layout.md),
gap [gaps/flat_layout_gap_2026-08-24.md](../gaps/flat_layout_gap_2026-08-24.md).
