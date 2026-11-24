# R1-C136 — virtual method override candidates

**Status:** preregistered before implementation and measurement, 2026-11-24.
Measured according to this plan. [Results and decision](RESULTS.md).
**Gap:** [override dispatch](../../../gaps/override_dispatch_2026-11-24.md).

## Candidate

Keep each existing resolved call edge and its grade. An eligible instance
method call can also point to known overrides under the applicable receiver
class. Add a distinct `override` route, graded `heuristic`. Restrict fan-out
to same-name method definitions in internal descendants. Deduplicate targets
and keep deterministic order. The additional edge describes a possible
runtime target. Preserve existing call counts and argument contracts.

Use call-site receiver evidence rather than assuming every edge to a base
method is virtual. Support recognized instance receivers such as eligible
`self`, an annotated field, or an instance receiver resolved by deep.
Exclude explicit base-method calls, `super()`, calls on a directly constructed
known class, class/static methods, name-mangled private methods and unresolved
receiver forms. Use known receiver-class bounds when they are available.
Keep independent heuristic routes such as protocol and registry distinct.

Full and incremental extraction must derive the same candidates for a fixed
input on fast. A change that adds or removes an override can affect an
unchanged caller. Deep repeated samples must preserve the receiver evidence
needed for fan-out. A graph lacking the new evidence remains readable. Measure
additional candidates against the baseline within the same graph sample.

On the current Codemap graph after 0.0.50, `impact` links `extract` to six
direct calls in core and 260 in tests, including CLI build and graph loading.
It links `update_graph` to two direct CLI calls and ten in tests, and shows
reachability from watch. The study checks both entry paths.

## Workloads and comparison

- The three pinned projects and union of trace pairs from R1-C132 are click,
  rich and jinja. Reuse the archived traces and verified source revisions.
- Build both a 0.0.50 baseline and a candidate. Run fast for exact output
  comparison and deep with two samples per variant, at most two CPUs on m99
  in the slot agreed with tgsh. Record exact source and tool identities.
- For the primary result, also remove only `override` edges from each deep
  candidate graph and score that ablated graph against the same trace union.
  This isolates the change from Jedi sampling variance. Report independent
  baseline drift separately. Use the R1-C132 `compare.py` scoring rules for
  explicit recall and decided precision. Record confirmed, contradicted and
  undecided new pairs, the candidate count and caller completeness.
- Use invented fixtures for positive calls, transitive overrides, unrelated
  siblings and exclusions. Check deterministic extraction, buildup and
  removal after an incremental edit, and the behavior of repeated samples.

## Acceptance

| ID | Evidence and decision |
| --- | --- |
| V1 | Synthetic cases give only eligible override candidates. Existing fast call identities and grades match 0.0.50 on all three pinned trees. |
| V2 | Default `callers` and `callees` may include candidate targets, with `min_confidence="exact"` excluding the heuristic edge. `impact` reflects the possible path and marks the heuristic basis. Full, incremental and repeated paths pass controls. |
| V3 | Relative to the ablated graph, explicit deep recall rises at least **5 percentage points in at least two of three trees**, and decided precision falls at most **3 percentage points in each tree**. Show per-tree values and the new-edge outcome counts. |
| V4 | Before promoting the candidate, requirements V1–V3 hold and the Codemap suite passes in the agreed m99 slot. Keep the raw comparison and measured source patch as research evidence if V3 fails. |

The thresholds govern this candidate's default use. A failed threshold is a
measured result for the study. Any later candidate or opt-in policy gets its
own scope and comparison.
