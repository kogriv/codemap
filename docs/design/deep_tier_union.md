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

---

## D6 — The tier's noise floor is a property to declare, not to hide (R1-C42, 2026-09-02)

**Status:** ✅ shipped (no schema change). **Gap:**
[deep_tier_nondeterminism_2026-09-02](../../gaps/deep_tier_nondeterminism_2026-09-02.md).

D5.6 above says acceptance is "deterministic within the deep tier's known jedi variance". That phrase
was doing more work than it looked: the variance was *known* to this design and to the CI workflow, and
absent from the places a consumer reads. A second target compared two deep graphs across a release and
briefly concluded a regression that was the tool.

**Measured, both trees.** Ten deep builds of an unchanged tree here: two distinct artifacts (7/3), the
delta two per-symbol `calls` counters out of 2133 nodes and no edges. On their larger tree: one build in
seven, one real call edge of 9524 — a `getattr` receiver jedi typed six times and not the seventh.

**Mechanism, as far as we took it.** jedi bounds inference with per-script execution counters
(`total_function_execution_limit` and its per-function siblings); an inference that runs out returns no
values, and at our boundary no values is `unresolved`. At the first divergent call site the counter
entering it differs by exactly one between the two outcomes, with every earlier classification in that
file identical. Why that one execution differs between processes we did not establish; five external
explanations were refuted at ten runs each — hash-seed randomization, jedi's and parso's disk caches,
jedi's compiled subprocess, the garbage collector, and ASLR. "Cache warmth" was among them, and it is
the cause `docs/incremental.md` had been asserting all along; that bullet is now corrected in place, with
the refutation stated rather than the sentence quietly rewritten.

**Decision: declare it, three places.**

1. **On the artifact.** A `note` (never a warning — nothing in the graph is invalid; it is a correct
   sample of a slightly fuzzy function) on every `tier: deep` graph, carrying the measured numbers.
2. **On a comparison.** `comparability()` grows `caveats`, separate from `differences`: two deep graphs
   stay *comparable* — refusing would be wrong — and the noise floor is printed above the verdict.
   Mixed tiers keep their existing incomparability and take no caveat, so the softer signal can never
   dilute the harder one.
3. **In the docs**, with the numbers rather than "may vary slightly", and with the false cross-reference
   in `docs/ci.md` named as false instead of quietly repaired.

**Rejected.** Raising jedi's limits (changes both cost and results, and the cause of the spread is not
established — a guess presented as a fix); unioning N runs into one graph (still a sample, at N× cost);
moving the CI byte-identity gate to the deep tier (the fast tier is a *subset* of deep by D2 above, so
the gate loses nothing where it stands, and the noise lives exactly in the part fast does not touch).
