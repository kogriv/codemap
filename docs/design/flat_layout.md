# Design — Flat module layout (sibling imports, namespace directories)

**Status:** ✅ **shipped** (2026-08-24, **no schema change**). **Motivates:** gap
[flat_layout_gap_2026-08-24](../../gaps/flat_layout_gap_2026-08-24.md), issues
[#4](https://github.com/kogriv/codemap/issues/4) (crash) and
[#5](https://github.com/kogriv/codemap/issues/5) (silent 0 import edges). **Backlog:** R1-C21.
**User docs:** [docs/flat-layout.md](../flat-layout.md).

**Decisions resolved (§9):** D1 = **A** (sibling-aware retry in `_resolve_edges`); D2 = **A**
(per-import, guarded); D3 = **yes** (`extras.resolution="flat"`, no schema bump); D4 =
normalize `filepath` at one boundary + **proceed and name it**; D5 = **derive** (build stderr,
`stats.diagnostics`, and three reports).

**One correction during build (§10):** the blindness was not confined to `imports` edges — the
**call layer** was blind to the same layout, because `_resolve` tests targets against the package
prefix and a flat target has none. Qualifying the *import map* once (`gsource.module_imports`)
fixes calls and attribute access together, instead of teaching each pass the layout separately.

A **flat module directory** — sibling `.py` files importing each other by bare name (`from alpha import X`),
valid at runtime because the directory itself is on `sys.path` — currently either **crashes** codemap (no
`__init__.py`) or yields a graph with **zero `imports` edges** that nothing flags (`__init__.py` present).
The second is the serious one: absence of data is rendered as a clean bill of health ("no layer violations",
"acyclic", "orphan modules: all of them"). This design makes the layout either **understood** or **loudly
unsupported** — never silently empty.

**Guiding invariants (unchanged):** source-only (no execution, no `sys.path` simulation beyond static
inference), deterministic output, **resolved-or-honestly-flagged**, closed edge vocabulary (R1-C7),
extras open-ended (DESIGN §2).

## 1. What the code does today

```python
# extract/griffe_extractor.py:47-48
search_path = pkg_dir.parent
root = griffe.load(module_name, search_paths=[str(search_path)])
```

The package is loaded **from its parent**, so every module id is package-qualified (`flatpkg.beta`), while
griffe records each import target exactly as the source writes it:

```
flatpkg.beta: imports={'X': 'alpha.X'}      # source-literal
```

`_resolve_edges` (`:164-166`) keeps only targets prefixed with the package name and drops the rest as
external — at that point `alpha.X` is indistinguishable from `pandas.DataFrame`. Hence 0 edges, silently.

**Measured, not assumed** (gap §2.4): a rule that rewrites an unresolved import whose head names a *sibling
module* produces **0 false positives** on both real packages at hand — codemap (45 modules / 114 external
imports) and bquant (88 / 580). The collision case (`import types` next to a local `types.py`) is real in
principle and rare in practice, which is why §4 keeps the inference **labelled**.

## 2. Decision D1 — how sibling imports get resolved

Three options; recommendation **A**.

- **A. Sibling-aware resolution at edge-resolve time (recommended).** In `_resolve_edges`, an import target
  that resolves to nothing is retried as `{parent_package}.{target}`; if that names a known module node, the
  edge is emitted and **marked as a flat-layout inference**. Pro: ~15 lines in one function; every node id,
  the `target` name, provenance roots, scope manifest and every other pass stay exactly as they are; a pure
  function of the module list, so determinism is untouched. Con: it is an *inference* about `sys.path`
  (mitigated by D3's label).
- **B. Load with the directory itself as the search path.** Makes `alpha` genuinely top-level, so griffe
  resolves the import natively. Con: **there is no single root object** for a directory of siblings — the
  loader would have to load N roots and merge them, and every id loses its package prefix (`alpha` instead
  of `flatpkg.alpha`), which changes `Graph.target`, the scope manifest, provenance-root matching, and every
  stored graph's ids. A large architectural change to serve one layout.
- **C. Push it to the user — a `--search-path` / `--flat` flag only.** Pro: no inference at all. Con: the
  tool still returns a confidently empty graph to anyone who doesn't know the flag exists, which is the
  actual defect being fixed. Acceptable *in addition to* A, never instead of it.

## 3. Decision D2 — when the rewrite applies

- **A (recommended).** Apply per-import, always, but **only where it changes nothing else**: the target must
  be otherwise unresolved *and* `{parent}.{head}` must name a known module node. On a proper package this
  fires zero times (measured, §1), so correct packages cannot be affected — an acceptance criterion below
  pins exactly that.
- **B.** Gate behind an explicit `--flat` flag. Rejected as the default: it preserves the silent-empty
  failure for the unaware user, and the whole point is that the tool should not need to be held right.
- **C.** Detect the layout first (0 internal imports over ≥2 modules + ≥1 rewritable candidate), then apply
  wholesale. Rejected as *more* magic than A for no gain: A's per-import guard is already the narrow case,
  and a whole-package mode switch would make one odd import reinterpret the entire graph.

## 4. Decision D3 — label the inference on the edge

**Recommended: yes.** A flat-layout `imports` edge carries `extras.resolution = "flat"` (package-qualified
edges stay bare, as today). It is an inference about runtime `sys.path`, and codemap's stated rule is that
approximations are *labelled, not hidden* (R1-C13) — the same way `calls` carries `extras.resolution` and
`accesses` carries `self` / `class` / `construct` / `deep`.

**Schema impact: none.** The closed vocabulary (R1-C7) is the set of edge *types*; `imports` is unchanged
and no type is added. `extras` is explicitly open-ended (DESIGN §2), and the R1-C9 serializer already sorts
edges by `(type, source, target, extras)`, so an added key stays deterministic. No `SCHEMA_VERSION` bump —
unlike R1-C20, which added a type and did bump.

## 5. Decision D4 — the namespace-package crash: scope and policy

**Scope — larger than issue #4 suggests.** The `filepath`-is-a-`list` shape is consumed in **five** places,
not one; fixing `_rel()` alone moves the crash rather than removing it (verified: after patching `_rel`, the
same build dies in `behavior.py:61`).

| site | code |
|---|---|
| `extract/griffe_extractor.py:193` | `file=_rel(obj.filepath, root)` |
| `extract/behavior.py:57-61` | `fp = getattr(mod, "filepath", None)` → `Path(fp).read_text(...)` |
| `extract/attrflow.py:78-82` | same shape |
| `extract/dataflow.py:46` | same shape |
| `extract/dispatch.py:46` | same shape |

Note the behavioral sites guard with `if not fp:` — which a **non-empty list passes**, so the guard does not
catch it.

**Recommended:** normalize once at the boundary — a single helper (`_module_file(obj) -> Path | None`,
alongside `_rel`) that returns `None` for the namespace list shape, used by all five sites. A namespace
package genuinely has no single file, and `None` is the value every one of those fields already accepts.

**Policy — proceed or refuse?** Recommended: **proceed**, and say what happened. A namespace directory *is*
the flat layout, so once D1 lands the graph is useful rather than degenerate. The build emits a named
diagnostic — which directory has no `__init__.py`, and that its modules are being treated as a flat layout —
so the user learns the fact without losing the run. Refusing would trade a useful graph for a lecture; being
silent is what §6 exists to prevent.

## 6. Decision D5 — never render absence as health

Independent of resolution, and the part that is correct even if D1 is never built: when a build produces
**0 `imports` edges over ≥2 modules**, that is almost certainly a layout the extractor did not understand.

**Recommended:** *derive, don't store.*

- **At build time** — one stderr line naming the condition and pointing at the likely cause (flat layout).
- **In `stats`** — a computed flag beside `freshness` (same spirit as issue #3: the surface tells you when
  it may be lying).
- **In the two reports that currently invert the meaning** — `architecture` ("no layer violations",
  "acyclic") and `dead-code` ("orphan modules") must, under this condition, state that the import graph is
  empty **before** listing conclusions drawn from it.

Deriving keeps `graph.json` unchanged (no schema surface, no new field to keep in sync), and any consumer can
recompute it from the graph it already holds.

## 7. Boundaries (explicitly not in v1)

- **Nested flat directories** — resolution assumes the sibling set of the importing module's own package.
- **Runtime `sys.path` manipulation** (`sys.path.insert`, `.pth` files, editable-install shims) — out of
  scope by the source-only invariant; the flat inference is the one `sys.path` assumption made, and it is
  labelled.
- **Conditional / function-local imports**, `importlib` — unchanged, still out.
- **Genuine ambiguity** (a local `types.py` *and* a real stdlib `types` import in the same package): the
  sibling wins and the edge is labelled `flat`. That is the correct answer for a flat layout and a wrong one
  for a package that merely shares a name — accepted, measured as not occurring on either real package, and
  visible in the edge rather than hidden.

## 8. Acceptance

- **Toy fixture, both shapes.** `flatpkg` with and without `__init__.py`: build succeeds in both; the
  `beta → alpha` edge exists and carries `extras.resolution="flat"`; the namespace build emits the named
  diagnostic.
- **No regression on real packages — byte-identical.** Graphs of `bquant` and `codemap` built before and
  after must serialize **byte-for-byte identically** (the measurement in §1 predicts zero rewrites; this
  turns the prediction into a test).
- **The honesty half stands alone.** With D1 reverted, a 0-import build still announces itself at build
  time, in `stats`, and in both reports.
- **Regression guard in CI** — the flat fixture is built alongside the packaged one, so this layout cannot
  silently regress again (gap §4.4).

## 9. Decisions — resolved

| # | Question | Decision (as shipped) |
|---|---|---|
| **D1** | How to resolve sibling imports | **A** — two-pass `_resolve_edges`: exact first, then a `_flat_sibling` retry |
| **D2** | When the rewrite applies | **A** — per-import, guarded (target unresolved **and** its head names a module beside the importer) |
| **D3** | Label the inference on the edge | **yes** — `extras.resolution="flat"`; **no** `SCHEMA_VERSION` bump (no new edge type) |
| **D4** | Namespace crash: scope & policy | `extract/gsource.py` normalizes `filepath` for all 5 sites; the build **proceeds** and names the directory |
| **D5** | 0-imports signal | **derived** in `codemap/diagnostics.py` — build stderr, `stats.diagnostics`, 3 reports; nothing stored |

## 10. What shipped (and the one thing this design missed)

- **`codemap/extract/gsource.py`** — the normalization boundary: `module_file()` (`None` for the
  namespace list shape, used by all five consumers), `is_namespace_dir()`, and
  **`module_imports()`**, which package-qualifies flat sibling targets once, for every pass.
- **`codemap/extract/griffe_extractor.py`** — two-pass import resolution + `_flat_sibling()`.
- **`codemap/diagnostics.py`** — `import_graph_diagnostic` (0 imports over ≥2 modules) and
  `namespace_target_diagnostic` (derived from the target node's `file is None`), wired into
  `cli build`, `stats`, and `report architecture` / `dependencies` / `dead-code`.

**The miss.** §2–§4 reasoned only about `imports` edges. The first test run showed
`beta.doubled()` → `alpha.base_width()` still unresolved: `behavior._resolve` classifies a call
target by package prefix, and a flat target has none — so the **call layer was blind to the same
layout**, and nothing in the design had noticed. Repairing it *at the import map* rather than
inside `_resolve` keeps the inference in one place and fixed attribute access (`attrflow`) for
free. Also added during implementation: **`report dependencies`**, which renders "acyclic" from
the same empty graph and therefore had the identical defect to the two reports D5 named.

### Acceptance — met

| criterion | result |
|---|---|
| flat fixture, both shapes | builds; `beta → alpha` present, labelled `flat`; namespace diagnostic emitted |
| package-qualified import stays exact | `gamma → alpha` carries no label |
| **no regression on a real package** | `bquant` graph **byte-identical** before/after (fast tier); `attrpkg` **byte-identical** on `--deep` |
| inference fires zero times on sound packages | asserted on `bquant` in CI |
| honesty half stands alone | a 0-import build warns at build time, in `stats`, and in all three reports |
| regression guard | `tests/test_r1c21_flat_layout.py` — 20 tests, fixture `flatpkg`; suite 369 → **389** |
