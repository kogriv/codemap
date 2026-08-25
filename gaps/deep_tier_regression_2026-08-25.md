# codemap — gap: `--deep` is a **downgrade** on a flat layout — 158 cross-module call edges → 0

**Date:** 2026-08-25
**Source:** GitHub issue [#10](https://github.com/kogriv/codemap/issues/10), filed after the reporter verified
R1-C21's flat-layout fixes on their own target: the import graph went 0 → 407 edges and `report impact`
started working, but *"0 of 338 in-core call edges cross a module boundary"*.
**Type:** soundness / honesty — and a **regression between tiers**: the expensive tier silently returns less
than the free one. A user who pays a minute for `--deep` gets a worse answer than the default.
**Related:** `flat_layout_gap_2026-08-24.md` (R1-C21 taught the structural and fast layers the flat-layout
inference — this is the layer it did **not** reach), R1-C13 (tier honesty).
**Design:** [docs/design/deep_tier_union.md](../docs/design/deep_tier_union.md).
**Backlog:** R1-C26.
**Status:** ✅ **closed same day** (2026-08-25, no schema change) — the jedi boundary learned the
flat-layout inference and the tiers became a union. **`calls(deep) ⊇ calls(fast)` now holds**: fast-only edges
went **158 → 0** on the reporter's target (cross-module `calls` **0 → 234**), **5 → 0** on codemap and
**5 → 1** on bquant — where the one remaining difference is deep being *more precise*, not losing anything
(see §5). Accuracy bench precision **unchanged at 100%** on both tiers. Tests 503 → **512**.

## 1. The gap

`add_behavior` chose its resolver by tier, **exclusively**:

```python
if script is not None:               # deep
    def resolve(call): return _resolve_jedi(call, script, target_pkg)
else:                                # fast
    def resolve(call): return _resolve(call, modpath, class_prefix, imports, modmembers, members)
```

Not a union — a *replacement*. Everything the name-based resolver knows is discarded the moment `--deep` is
passed, including the flat-layout import map R1-C21 built specifically so a sibling import resolves.

## 2. Evidence

### 2.1 The reporter's target, reproduced

A flat root of 37 modules, siblings imported absolutely, no `__init__.py`:

| tier | `imports` edges | `calls` edges | **cross-module** `calls` |
|---|---|---|---|
| **fast** | 77 | 487 | **158** |
| **deep** | 77 | 336 | **0** |

The import graph is identical on both tiers — R1-C21's work holds. The call graph is not: `--deep` loses
**158 true cross-module edges** and 151 calls net. Their reported "0 of 338" reproduces exactly.

### 2.2 Minimal reproducer — 2 files

```python
# flat/leaf.py
def helper(x): return x + 1

# flat/mid.py
from leaf import helper
def use_both(x): return helper(x)
```

| tier | `imports` | `calls` |
|---|---|---|
| fast | `flat.mid → flat.leaf` (`resolution="flat"`) | `use_both → leaf.helper` ✅ |
| deep | `flat.mid → flat.leaf` (`resolution="flat"`) | **none** |

### 2.3 The mechanism is not "jedi failed"

jedi resolves the call **correctly** — to `leaf.helper`. That name does not start with `flat.`, so
`_resolve_jedi`'s internal test rejects it and classifies the call **external**, and an external call emits
no edge.

This is precisely the R1-C21 defect one layer down. griffe reported the import target as the source writes
it (`leaf.helper`), and R1-C21 taught **one boundary** — `gsource.module_imports` — to qualify it. The jedi
boundary was never taught, because at the time the flat-layout work was scoped to the structural and fast
layers and nobody built a flat target with `--deep`.

Note what this means for the reporter's workaround options: it is not the missing `__init__.py`. Adding one
does not help, because the *import statement* is still absolute.

### 2.4 It is not confined to flat layouts

The tiers being exclusive costs edges on ordinary packaged targets too — measured as
`calls(fast) − calls(deep)` on frozen copies:

| target | fast | deep | **edges present on fast and missing on deep** |
|---|---|---|---|
| codemap | 422 | 628 | **1** |
| bquant | 931 | 1514 | **5** |

Small, but they are real edges, e.g. `ZoneVisualizer.plot_zones_comparison →
ZoneVisualizer._create_matplotlib_zones_comparison` — a `self.` call the fast tier resolves from the class
member table and jedi does not. **The deep tier is not a superset of the fast tier**, which is what every
consumer assumes when choosing it.

## 3. Why it matters

- **The failure is silent and inverted.** Paying for the better tier and receiving less is the one direction
  a user cannot anticipate. Nothing in the graph or the reports says the deep tier declined a call the fast
  tier would have resolved.
- **It defeats a fix that was already shipped.** R1-C21 exists so a flat target has a working graph; on
  `--deep` the call half silently reverts to the pre-R1-C21 state, and `--deep` is exactly what a user reaches
  for when the fast answer looks thin.
- **`impact`, `callers`, `flows`, `dead-code` and the architecture views all read that call graph.** On the
  reporter's target every one of them was answering with zero cross-module structure.

## 4. Scope of a full solution

1. **Teach the jedi boundary the flat-layout inference** — the mirror of `module_imports`, at the one place
   jedi's answer is classified. Not a fallback: jedi's answer is *correct*, it is the internal/external test
   that is wrong.
2. **Make the tiers a union, not a replacement** — when jedi finds nothing, consult the name resolver rather
   than discarding the call. This is what closes §2.4.
3. **Do not fall back when jedi answers `external`** — there it resolved the name to a real definition
   outside the package, and that judgement beats a name-based guess that might match an internal symbol by
   coincidence.

Acceptance is **not** byte-identity: this deliberately adds true edges. The criterion is *deep ⊇ fast on
every target measured, the reporter's cross-module count restored, and the call-graph accuracy bench's
precision unchanged*.

Design decisions and sizing: [docs/design/deep_tier_union.md](../docs/design/deep_tier_union.md).

---

## 5. Results, and the one difference that is not a loss

| target | fast | deep before | deep after | fast-only before | fast-only after | cross-module (fast / before / after) |
|---|---|---|---|---|---|---|
| the reporter's target | 487 | 336 | **573** | 158 | **0** | 158 / **0** / **234** |
| codemap | 424 | 628 | 631 | 5 | **0** | 103 / 298 / 298 |
| bquant (frozen) | 931 | 1514 | 1518 | 5 | **1** | 340 / 836 / 836 |

The reporter's target is the headline: the deep tier went from answering **zero** cross-module structure to
**234** edges — more than the fast tier's 158, which is what "deep" is supposed to mean.

**The single remaining bquant difference was checked, and it is a refinement.** `create_financial_chart →
create_candlestick_chart`: the fast tier names the module-level function, the deep tier resolves the same
call to `FinancialCharts.create_candlestick_chart` — the method on the class the receiver is an instance of.
Deep is right. So the acceptance was restated honestly: *no true edge is lost*, rather than *the fast-only
set is empty*, because those are not the same claim.

## 6. Two things the work turned up

**The fallback had to be wider than "jedi found nothing".** The first cut fell back only on `unresolved`,
and it did not close §2.4 — because `_process_function` performs a soundness downgrade *after* the resolver
returns: a jedi answer naming a symbol that is not a graph node (a `self.x` bound to the subclass while the
method lives on the base) was discarded at a point where the cheap resolver was already out of reach. The
fallback now also fires on an internal answer that is not a node, which is what took codemap 5 → 0.

**The first before/after comparison was contaminated by the fix's own source.** codemap's "fast-only" set
appeared to *grow* from 1 to 2, and both entries were calls to `_resolve_jedi` — a function this very change
had stopped calling directly. The fast baseline had been built before the edit. Same lesson as R1-C25 one
more time: a comparison is only as frozen as its least frozen half.
