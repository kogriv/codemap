# Design — The deep tier is a union with the fast tier, not a replacement

**Status:** ✅ **shipped** (2026-08-25, no schema change).
**User docs:** [../flat-layout.md](../flat-layout.md#the-deep-tier).
**Decisions resolved:** D1 = **yes** (`_flat_qualify`, the mirror of `module_imports` at the jedi boundary),
D2 = **yes, and wider than first drafted** — the fallback also fires when jedi names something that is not a
graph node, which is what the packaged-target losses turned out to be; D3 = **no fallback on `external`**,
held; D4 = done; D5 met, with criterion 2 restated (see gap §5 — one difference on bquant is deep being more
precise, not a loss).
**Motivates:** gap [deep_tier_regression_2026-08-25](../../gaps/deep_tier_regression_2026-08-25.md),
issue [#10](https://github.com/kogriv/codemap/issues/10).
**Backlog:** R1-C26.
**Related design:** [flat_layout.md](flat_layout.md) — this is the layer its "normalise at one boundary"
lesson did not reach.

Two independent defects wearing one costume. Fixing only the visible one would leave the other in place.

**Guiding invariants (unchanged):** source-only, deterministic, two tiers, resolved-or-honestly-flagged,
closed edge vocabulary (R1-C7), `extras` open-ended.

---

## D1 — Qualify a jedi answer that names a flat sibling

**Recommended: yes — and note that this is not a fallback.**

jedi resolves `from leaf import helper` **correctly**, to `leaf.helper`. What is wrong is the test that
follows it: `full_name.startswith(target_pkg + ".")` reads a flat sibling as external. In a flat layout the
directory itself is on `sys.path`, so a sibling's canonical name has no package prefix — exactly the
condition R1-C21 handled for griffe's import map.

The rule is the mirror of `gsource.module_imports`, with the same guard: only a name that is not already
package-internal, and only when its head names a module sitting **beside** the caller.

```python
parent = modpath.rsplit(".", 1)[0]
if f"{parent}.{full_name.split('.', 1)[0]}" in known_modules:
    return f"{parent}.{full_name}", "deep"
```

- **Alternative rejected: strip the check and accept any jedi answer as internal.** It would resolve the
  reported case and invent edges into `pandas` on the next one.
- **Alternative rejected: fall back to the name resolver on `external`.** That treats a *correct* jedi answer
  as a failure, and it would fire on genuinely external calls too — see D3.

**Label:** the edge keeps `resolution="deep"`. The flat inference is already visible on the corresponding
`imports` edge (`resolution="flat"`), and a call edge's `resolution` names *which tier resolved it*, not
which layout the target has. Splitting it would put layout information in a field that means something else.

## D2 — Fall back to the name resolver when jedi finds nothing

**Recommended: yes.**

The tiers were exclusive: with `deep=True` the name-based resolver was never consulted. Measured on frozen
copies, that costs real edges even where nothing is flat — 1 on codemap, 5 on bquant (`self.` calls the class
member table resolves and jedi does not).

So: run jedi first; when it answers `unresolved`, ask the fast resolver. The result is `fast ∪ deep`, which
is what every consumer already assumes when they choose the expensive tier.

- **Precision is not at risk in principle** — these are exactly the edges a fast build emits and the accuracy
  bench already scores at 100% precision — but it must be **measured**, not argued: run
  `research/bench/callgraph_accuracy.py` before and after and require precision to hold.
- **Applies to all three call paths** — named functions, module-level statements (R1-C22 D2) and calls inside
  nested defs (R1-C22 D3). The third is easy to miss and would leave closures resolved by a weaker rule than
  their neighbours.

## D3 — Do not fall back on `external`

**Recommended: no fallback there.**

`external` means jedi resolved the name to a definition outside the package. That is a *judgement*, not a
failure, and it is better than a name-based guess which could match an internal symbol of the same name by
coincidence. Falling back there would trade a correct "not ours" for a plausible-looking wrong edge — the
exact bargain this project keeps refusing.

The consequence is that D1 must do its job properly: after it, a flat sibling is no longer misfiled as
`external`, so nothing depends on the fallback to rescue it.

## D4 — Distinguishing `unresolved` from `external`

**Recommended: fix the classification while we are here.**

`_resolve_jedi` returned `"external"` whenever it found no *internal* name — including when jedi found
nothing at all. D2's rule needs the two apart: `unresolved` (jedi has no answer) is the only case that may
fall back. The per-function `counts` already report both, so this also makes the existing coverage numbers
honest.

## D5 — Acceptance

Byte-identity is **not** the criterion — this adds true edges.

1. The minimal reproducer resolves on `--deep`: `use_both → leaf.helper`, `resolution="deep"`.
2. **`calls(deep) ⊇ calls(fast)`** on the reporter's target, codemap and bquant — measured, with the
   fast-only set empty. This is the invariant the whole milestone is about.
3. The reporter's cross-module count is restored on `--deep` (fast measured 158; deep must not be below it).
4. `research/bench/callgraph_accuracy.py` precision is **unchanged**; recall may rise.
5. Additions only: no call edge present before the change disappears.
6. Deterministic within the deep tier's known jedi variance (documented in `docs/incremental.md`).
