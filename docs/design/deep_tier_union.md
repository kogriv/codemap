# Design — The deep tier is a union with the fast tier, not a replacement

**Status:** ✅ **shipped** (2026-08-25, no schema change). D6 shipped 2026-09-02.
**D7–D9:** ✅ **shipped** (2026-09-04, no schema change) — `--repeat N`, revisiting D6's rejection on the
consumer's measurement. Acceptance measured on the frozen tree: `--repeat 3` over the full repo scope is
exactly the union of eight sequential builds (4850 / 13675, one `seen` edge, non-jedi classes and nodes
byte-identical to a single build) in 109 s of wall-clock against ~100 s for one build; `--repeat 8` on the
core gives the probe edge `seen: 5` of 8, the share the eight sequential processes gave (issue [#16](https://github.com/kogriv/codemap/issues/16), gap
[deep_tier_union_by_repeat_2026-09-04](../../gaps/deep_tier_union_by_repeat_2026-09-04.md), backlog R1-C45).
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

---

## D7 — `--repeat N`: union N samples, merged per edge class (2026-09-04)

**Status:** ✅ shipped. **Gap:**
[deep_tier_union_by_repeat_2026-09-04](../../gaps/deep_tier_union_by_repeat_2026-09-04.md). **Backlog:** R1-C45.
**Reverses one line of D6** — "unioning N runs into one graph (still a sample, at N× cost)". The first half
stays true. The second half is a price, not an argument, and the consumer put the price beside what it buys:
a real edge present in 75 % of 168 full builds is missed by one build 1 time in 4, by two 1 in 16, by three
1 in 64. Our own eight builds of the same tree agree (5 of 8; union of any three equals the union of all
eight in 55 cases of 56). "Build again and see" was advice that did not say how many times.

**Recommended: yes — as an explicit, paid-for flag, merged by a per-class key, with what varied marked on
the artifact.**

### What is unioned

Only the two jedi passes vary. Measured: 13 674 of 13 675 edges byte-identical across eight builds, the one
exception an `accesses` edge; structural, dispatch, family, dataflow, consumer/doc and `references
name|annotation` edges identical in all eight — those are resolved without jedi. Their edges are expected
identical across samples and any that are not are counted as unstable like the rest — a deterministic pass
that turns out not to be is a finding, not something to hide behind an assert.

**Each sample is a fresh interpreter, run concurrently.** The first draft ran `build_structural` once and
`add_behavioral_layer` N times on copies in one process — cheap, and wrong to promise a share on: eight
in-process passes on the same tree gave two artifacts in streaks (1 | 2–6 | 7–8; gap §3a). Eight passes
cannot establish that consecutive in-process runs are independent, and the 75 % was measured across
processes — the consumer's 175 and our eight. So `collect_samples` spawns (`spawn`, not `fork`, which
would inherit the state that makes passes correlate) one interpreter per sample and runs them in parallel;
the consumer measured 8 parallel builds against sequential ones at the same share (10/12 vs 11/12). Cost:
N × the memory of one build, and about one build's wall-clock time on a machine with N cores.

### The merge key is per class — not `(type, source, target)`

The consumer proposed merging by the logical triple and letting the deeper variant win. Measured against
the data, that key collapses distinct facts: 96 triples inside a *single* build carry two records — a read
and a write of the same attribute by the same function; a name used as annotation and as value; a
`construct` write and a `deep` write of the same field from two different sites. All 96 are present in
every build. What counts as identity depends on how the pass resolves:

| class | how the pass resolves | identity key | what can vary between runs | rule |
|---|---|---|---|---|
| `calls` with `resolution ∈ {module, self, imported, deep}` | jedi first, fast fallback (D2) | `(source, target, via)` — unique within one build, verified on 2807 edges | the same site as `deep` in one run and `imported`/`self`/`module` in another; a `deep` run may also carry more `callsites` and extra method edges | keep the `deep` variant whole when any run has it, else the first run's variant |
| `accesses` | form first (`construct` / `self` / `class`), jedi **only** for a local or expression receiver | full key — the label is a property of the site's syntax | presence only; no label swap in 4649 keys × 8 runs | union by full key |
| everything else | no jedi | full key | nothing (measured 0 of 8) | union by full key; count as unstable if it does |

An edge seen in fewer than N runs carries `extras.seen: k`. Nothing is written when `k == N`, so a graph
built with `--repeat 1` (the default) is byte-identical in its edges to today's — the only new bytes in a
default build are `provenance.samples`.

### Node counters

`extras.calls` and `extras.attr_access` are per-**site** counters, and sites dedupe into edges: the measured
node had three counter variants (`resolved` 11/12/13 of 13) behind one flapping edge. Per node, take the
variant with the fewest `unresolved` (tie: most `resolved`, tie: first run). `control` and `complexity` are
AST-only and taken from the first run.

### Provenance

`provenance.samples = {"runs": N}` on **every** build, fast tier included — one sample is a fact about every
graph ever built, and writing it removes the need to know the field's history. With `N ≥ 2` the block also
carries `"unstable": K` (edges with `seen < N`). `unstable` is **absent** for `N = 1`: it is not measurable
from one run, and absent means *unmeasured*, not zero (R1-C28).

### Refused loudly, not swallowed

`--repeat N > 1` on the fast tier exits 2 with the reason: the fast tier is byte-stable and CI pins it, so N
runs buy nothing and cost N minutes. A flag silently ignored is the defect D6 of
[absent_answers](absent_answers.md) is fixing elsewhere.

- **Alternative rejected: repeat the layer in one process on copies of the structural base.** Cheapest to
  write and the first draft; refuted by the in-process measurement above before it shipped.
- **Alternative rejected: union everything by full key and let `calls` carry two records.** That is the
  consumer's own retraction: one call described as `imported` and as `deep` at once, with contradicting
  metadata, and `diff` reading it as an added edge.
- **Alternative rejected: average or vote instead of union.** The tiers are lower bounds by construction
  and the accuracy bench scores precision at 100 %; a variant present in any run is a variant jedi found,
  not one it invented. Voting would throw away exactly the edges the flag exists to recover.

## D8 — Where `--repeat` applies, and where it is refused

**Recommended: full builds only — single-package and repo-scoped; mutually exclusive with `--incremental`;
`refresh` inherits it; `watch` does not get it.**

- `extract_repo(repeat=N)` passes it to `extract`; consumer and doc scans are deterministic and run once.
- **`--incremental` and `--repeat` together exit 2.** The spliced part of an incremental graph is the
  earlier build's sample by definition (R1-C43); resampling only the affected modules would leave a graph
  where `seen` on one edge is relative to this build's N and on its neighbour to some earlier build's, with
  no way to tell which. The two flags have opposite intent — one freezes the sample, the other widens it —
  and the honest combination is "periodic full build with `--repeat`", which is R1-C43 door (2) and is
  designed there, not here.
- `codemap refresh` replays the sidecar's `argv`, so a graph built with `--repeat 3` refreshes with
  `--repeat 3` without a code change. `watch` is the incremental loop and keeps its per-tick cost; the docs
  say so.
- `serve --build` keeps building single samples; a served graph is loaded from a file the user built.

## D9 — The note names the measured share and the N it implies

**Recommended: yes — two wordings, chosen by `provenance.samples.runs`, both carrying numbers.**

Today the note says "roughly one run in three" and stops. The consumer's point is that a reader deciding
whether to trust an *absence* needs the per-edge share and what N does to it, and that a graph built with
`--repeat` should say what it saw vary rather than quote a constant.

- **`runs = 1`:** the tier is not byte-stable; measured on an 88-module tree, a real `accesses` edge was
  present in 126 of 168 full builds (75 %) — one build misses such an edge about 1 time in 4, two builds
  1 in 16, three 1 in 64; `--repeat N` unions N samples. Consequence: do not read a missing call or
  attribute edge in one build as absence.
- **`runs = N ≥ 2`:** union of N samples; K edge(s) were seen in fewer than N runs and carry
  `extras.seen`; at the measured rate an edge missed by all N runs has probability 0.25^N. Consequence:
  edges with `seen` are the ones the tier is unsure about; everything else was in every run.
- **`comparability()`** adds the sample count of each side to its caveat. Two deep graphs stay comparable;
  a reader now sees "1 sample → 3 samples" and knows the noise floor is not symmetric.

The 75 % is stated as *measured on one tree for one edge*, never as a property of the tier: the consumer's
own batches ranged from 1 of 7 to 7 of 7, and eight builds cannot see an edge with a 95 % share at all
(gap §3). The note's job is to name the number the advice rests on, so that when the number is wrong for
some tree, the reader can see which number to distrust.

**Acceptance (R1-C45):** a synthetic pair of samples — one with `imported`, one with `deep` plus a method
edge — merges to the `deep` variant and the method edge with `seen: 1`, and a read/write pair of `accesses`
on one key survives as two edges; `--repeat 3` on bquant on a frozen tree yields a graph whose edge set
equals the union of the three underlying samples, `samples.unstable` equals the count of `seen` edges, and
every non-jedi edge class is identical across the three; `--repeat 1` changes no edge byte on either tier
(only `provenance.samples`); fast tier + `--repeat 2` and `--incremental` + `--repeat` both exit 2 with a
message; the note carries the numbers in both wordings and a mutation dropping the `runs ≥ 2` branch
reddens a test that feeds an actual union graph (R1-C37).
