# codemap — gap: a flat module directory builds a graph that is confidently empty

**Date:** 2026-08-24
**Source:** GitHub issues [#4](https://github.com/kogriv/codemap/issues/4) (crash) and
[#5](https://github.com/kogriv/codemap/issues/5) (silent 0 import edges), found while evaluating codemap
as a working tool on a **second real target** — a private research lab repo (sibling of the `bquant`
dogfood target) whose engine lives in a flat `shared/` module directory. Both were hit **within the first
twenty minutes, on the very first build**.
**Type:** robustness (§1a) + soundness / honesty (§1b) — the second is a *confident nothing*, the same
failure class as F14 (`canonical` picks 1 of N silently) and issue #3 (a stale graph reporting itself fresh).
**Related:** `attribute_impact_gap_2026-08-22.md` (same shape: an affirmative answer where `unknown` was
due), `dogfood_axes.md` **B2 robustness**, R1-C13 (lower-bound labels).
**Design:** [docs/design/flat_layout.md](../docs/design/flat_layout.md). **Backlog:** R1-C21.

## 1. The gap

A **flat module directory** — sibling `.py` files that import each other by bare name (`from alpha import X`),
working at runtime because the directory itself is on `sys.path` — defeats codemap in two different ways
depending on whether an `__init__.py` happens to be present.

### 1a. Without `__init__.py` — it crashes, and the message hides the cause

griffe classifies such a directory as a **namespace package**, whose `filepath` is a `list[Path]` rather
than a `Path`. `_rel()` (`extract/griffe_extractor.py:280`, called from `:193`) hands it straight to
`Path()`:

```
TypeError: argument should be a str or an os.PathLike object where __fspath__ returns a str, not 'list'
```

`_rel()` already guards the `None` shape; the namespace list is simply the second shape the field can take.
The message names neither the directory nor the reason, so from the CLI it reads as a bad **argument**
rather than an unsupported **layout**.

### 1b. With `__init__.py` — it succeeds, and the graph is wrong with nothing flagged

The build completes, and produces **zero `imports` edges**. Everything resting on the import graph —
layers, coupling, cycles, architecture, dependencies, orphan detection, and most of `impact` — degrades to
nothing, silently.

**Mechanism** (confirmed against griffe, not inferred): the package is loaded from its **parent**
(`griffe_extractor.py:47-48`), so modules are named `flatpkg.alpha` / `flatpkg.beta`, while griffe records
the import target exactly as the source writes it:

```python
flatpkg.alpha: imports={}
flatpkg.beta:  imports={'X': 'alpha.X'}      # source-literal, not package-qualified
```

`_resolve_edges` keeps only targets prefixed with the package name (`:164-166`), so `alpha.X` is discarded
as *external* — indistinguishable, at that point, from `pandas.DataFrame`.

## 2. Evidence

### 2.1 Reproduced here (2 files, no deps)

```bash
mkdir -p flatpkg
printf 'X = 1\n'                                           > flatpkg/alpha.py
printf 'from alpha import X\n\ndef use():\n    return X\n' > flatpkg/beta.py

codemap build flatpkg -o g.json
# error: argument should be a str or an os.PathLike object ... not 'list'        (§1a)

: > flatpkg/__init__.py && codemap build flatpkg -o g.json
python -c "import json,collections;print(collections.Counter(e['type'] for e in json.load(open('g.json'))['edges']))"
# Counter({'contains': 4})        <- imports: 0                                  (§1b)
```

`beta` demonstrably imports `alpha`; they are siblings; the edge is absent.

### 2.2 The damage downstream, measured on that same toy graph

```
report architecture → "3 core modules, 0 import edges"; 3 layers of 1 module each;
                      no inter-layer dependencies; "no layer violations"; "0 cycles — acyclic"
report dead-code    → Orphan modules — core (no incoming imports): 2
                      - flatpkg.alpha
                      - flatpkg.beta
```

Every one of those statements is *formally true of the graph* and *false about the code*. Note especially
"no layer violations" and "import graph is acyclic": absence of data is rendered as a **clean bill of health**.

### 2.3 On the real target (as reported in issue #5 — a private repo, numbers not independently reproducible here)

A 35-module, ~11k-line engine in this layout: 2827 edges built (`writes` 962, `contains` 795, `reads` 438,
`calls` 316, `accesses` 275, …) and **`imports` 0**; `report architecture` → "36 core modules, 0 import
edges"; `report dead-code` → **all 35 modules reported orphan** — the entire shipped engine;
`impact --symbol build_promoted_runtime` → *"No inbound references — isolated"*, where grep finds the symbol
in 10+ files including the promotion path and four test modules. Control on a proper package (`bquant`,
same build) answers correctly — so the tool is sound; the **layout** defeats it.

### 2.4 Shadowing risk of the obvious fix — measured, not assumed

The natural repair is to treat an unresolved import whose head names a **sibling module** as internal. How
often would that rule fire *wrongly* on a proper package (where `import types` means stdlib, not a local
`types.py`)? Audited both real packages at hand:

| package | modules | internal imports | external imports | **would be rewritten (false positives)** |
|---|---|---|---|---|
| codemap | 45 | 154 | 114 | **0** |
| bquant | 88 | 479 | 580 | **0** |

So the collision is rare in practice — but it is *possible* in principle, which is why §4 keeps the
assumption **labelled** rather than silent.

## 3. Why it matters

- **It is the failure mode codemap exists to not have.** The project's bet is a graph an agent can *trust*;
  every partial answer elsewhere carries a lower-bound disclaimer (R1-C13). Here the lower bound is **zero
  for everything**, which is indistinguishable from a correct answer about genuinely dead code. The reports'
  honest hedges ("Candidates, not proof", "pair with grep") do not help when the answer is a confident,
  well-formatted **nothing**.
- **The layout is not exotic.** Research code, `scripts/` directories, notebook-adjacent projects and plugin
  folders routinely use it. This is the **second real target** codemap was pointed at outside its dogfood
  package, and it failed on contact — a robustness signal (axis B2) that one dogfood target could not give.
- **Adoption is blocked on it.** Per issue #5, reshaping that repo into a proper package would mean
  rewriting imports across 88 files, **52 of them frozen experiment scripts** that must stay byte-stable for
  provenance. Fixing it here unblocks a whole class of target instead of asking each target to reshape
  itself around the tool.
- **A crash is the *better* half.** §1a fails loudly and wastes minutes; §1b succeeds and can waste a
  decision. The ordering of value in §4 follows from that.

## 4. Scope of a full (non-truncated) solution

Four parts, in descending value-per-line — the first two remove the *lie* and are independent of the third:

1. **Never render absence as a clean bill of health.** When a build produces **0 `imports` edges over ≥2
   modules**, say so at build time and carry it into the graph so downstream reports can refuse to sound
   confident. This alone converts the worst case (a silent wrong answer) into a visible one, and it is
   correct even if resolution is never fixed.
2. **Don't crash on a namespace package** (§1a). `_rel()` returns `None` for the list shape — a namespace
   package has no single file, and the field already accepts `None` — and the build states plainly which
   directory has no `__init__.py` and what that costs.
3. **Resolve sibling imports for the flat layout** (§1b), with the choice of mechanism, the shadowing
   trade-off (§2.4), and how the assumption is **labelled on the edge** worked out in the design-doc — this
   is an inference about `sys.path`, and codemap's rule is that approximations are labelled, not hidden.
4. **Regression-guard the layout**, so a flat fixture is built in CI beside the packaged one.

Design decisions, tiers and boundaries: [docs/design/flat_layout.md](../docs/design/flat_layout.md).
Backlog: **R1-C21** (see `BACKLOG.md`).
