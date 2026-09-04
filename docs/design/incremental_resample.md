# Design — The incremental chain samples N times everywhere it samples at all

**Status:** ✅ **shipped** (2026-09-04, no schema change). Acceptance measured on the replay's fourth arm — a `--repeat 3` base and `--incremental --repeat 3` on every tick: **3** edge-ticks missed against the plain `--repeat 3` chain's 6, the periodic-full chain's 10 and the single-sample chain's 16; the fallback tick was a full `--repeat 3` build; ordinary ticks 11–28 s, the two 27–29-module ticks 46–51 s.
**Motivates:** gap [incremental_chain_replay_2026-09-04](../../gaps/incremental_chain_replay_2026-09-04.md) —
R1-C43 door (2), "a periodic full rebuild every N ticks", measured on twenty real commits and refuted.
**Backlog:** R1-C47 (this document); R1-C43 door (2) closes here.
**Revises:** [deep_tier_union.md](deep_tier_union.md) D8 — `--repeat` and `--incremental` were made
mutually exclusive there; the reason was right and the conclusion was too broad (see D1 below).
**User docs:** [../incremental.md](../incremental.md).

**Guiding invariants (unchanged):** source-only, two tiers, resolved-or-honestly-flagged, fast tier
byte-identical to a full build (R1-C9), a graph says what it is (R1-C43).

The replay put three chains through the same twenty commits and compared each tick with a fresh
`--repeat 3` build of that commit. A chain with a `--repeat 3` base and nothing else missed **6**
edge-ticks; the same chain with a full `--repeat 3` rebuild every fifth tick missed **10**; a chain with a
single-sample base missed **16**, and the edge its base lost at tick 0 was still missing at tick 20.
Every miss traced to a **single jedi sample** taken somewhere in the chain — the base, the fallback full
build that a 63-module commit forced on tick 3, or the recompute of the modules a tick touched. None
traced to age. So the fix is not to rebuild more often; it is to stop sampling once.

---

## D1 — `--repeat N` is a property of the chain, and is allowed with `--incremental`

**Recommended: yes — N travels with the graph, and a different N is a different builder.**

D8 refused the combination because `extras.seen` on a recomputed edge would be "k of *this* build's N"
while on a spliced edge it would be "k of *some earlier* build's N". That is only a contradiction when N
changes between builds. Make N a chain property: the graph records it (`provenance.samples.runs`, written
by every build since 0.0.11), and `update_graph` treats a request with a different N the way it treats a
different tool or tier — a full rebuild, `reason: samples-changed`. Then every `seen` in the graph is "of
N", and the splice carries them unchanged.

- **Alternative rejected: keep the exclusion and add a periodic full.** Measured: no benefit over twenty
  ticks, and the periodic full is itself only as good as its own sampling.
- **Alternative rejected: strip `seen` from spliced edges.** Loses the one per-edge fact the tier can
  state, on exactly the edges that were not looked at this build.

## D2 — Three places sample; all three sample N times

**Recommended: base, fallback and recompute all use N fresh interpreters.**

| where | today | with `--repeat N` |
|---|---|---|
| base full build (`build --deep`, first `watch` build) | 1 sample | N — already the case since 0.0.11 |
| fallback full build inside `update_graph` (> 50 % of modules affected, builder changed, N changed) | 1 sample | N — `collect_samples` + `merge_samples`, same as a full build |
| recompute of the affected modules on an incremental tick | 1 sample | N workers, each `build_structural` + the behavioural layer **restricted to the affected modules**, merged; the unaffected modules are spliced from the old graph as today |

The worker gains an `only` parameter — the same hook `add_behavioral_layer` already has for the
incremental path (R1-C9). The structural base is rebuilt in every worker (~4 s on the dogfood target) —
cheaper than shipping it across processes, and deterministic, so the merge sees identical nodes.

`provenance.samples` on such a graph is `{"runs": N, "unstable": K}` with K **recounted over the final
graph** — edges carrying `seen` whether recomputed this tick or spliced — because the number must describe
the artifact a reader holds, not the part of it this build touched. `incremental: true` stays as it is;
the two fields say different things.

## D3 — Cost

Per tick: N processes in parallel, each ~4 s of structural work plus jedi over the affected modules
(1–29 of 88 on the replay; one tick in twenty hit the fallback). Wall-clock is close to today's tick on a
machine with N free cores; memory is N × one build. The fallback tick costs a full `--repeat N` build
(~110 s on the dogfood target for N = 3, three cores). `watch` keeps its "save → answer" property on the
ordinary tick; the debounce is untouched.

## D4 — No periodic full rebuild

**Recommended: do not build it; record why.**

The replay is the measurement door (2) asked for, and the number it produced is zero ticks of benefit.
The mechanism explains it: a lost edge does not decay with time and does not return with time — it waits
for its module to be recomputed, and the recompute is the same coin. Rebuilding on a schedule tosses the
coin on a schedule. Sampling N times fixes the coin.

## D5 — `watch --repeat N`

`watch` passes the flag to every build it makes and records it in the sidecar recipe, so `refresh`
replays it. The stale-at-start rebuild and the fallback use it too — there is no path through `watch` that
takes one sample when N was asked for.

## Acceptance (R1-C47)

- On a toy package on the deep tier: a `--repeat 2` base followed by an edit and `update_graph(repeat=2)`
  is `mode: incremental` with `samples.runs == 2` and `incremental: true`; a request with `repeat=3` over
  that graph is `mode: full`, `reason: samples-changed`, `samples.runs == 3`; an edit touching every module
  falls back to a full build that still records `runs == 2`.
- A `seen` value on an edge of an unaffected module survives the splice, and `samples.unstable` counts it.
- `build --deep --incremental --repeat 2` exits 0 and the second run is incremental; `--repeat 2` without
  `--deep` still exits 2; `_watch_build_argv` carries `--repeat`.
- The fast tier's byte-identity to a full build (R1-C9) is unchanged — the `repeat == 1` path is the code
  that ran before.
- **On the replay, the new arm:** the same twenty commits with a `--repeat 3` base and `--incremental
  --repeat 3` on every tick, against the saved `--repeat 3` truth of each commit — measured edge-ticks
  missed, expected at or below the 6 of the plain `--repeat 3` chain, with the fallback tick no longer a
  single sample.
