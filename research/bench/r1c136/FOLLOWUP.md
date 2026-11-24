# R1-C136 — call-site receiver evidence

**Preregistered 2026-11-24 before the second implementation and scoring.**
[First candidate and measurements](RESULTS.md).

Jinja's `as_const` candidates include 249 contradicted pairs and 84 confirmed
pairs. Dropping that entire group would leave 48 extra confirmed explicit
pairs, 3.25 percentage points of recall. The second candidate seeks a smaller
set of possible implementations at each call site.

## Rule

Use the first candidate's eligibility, graph paths and `override` route. For
eligible virtual calls, distinguish concrete receiver evidence from an upper
bound. Where a local value has source-visible allocations, or Jedi reports a
finite set of internal instance types narrower than the original receiver
bound, use those classes and select the implementation they inherit through
the class hierarchy. Use the normal method-resolution order for inheritance
that can be established. Abstain on incomplete resolution of this evidence.

An upper bound alone, including a declaration of `self` or an annotation,
can add candidates only when there are at most three distinct additional
implementations under that bound. An ambiguous wider set contributes no edge.
Apply the limit per site before aggregating edges. Keep deterministic behavior.
Use the existing first lookup on all sites and avoid additional Jedi inference
for names with no possible override family. Preserve the original `calls` edge,
its grade, argument contracts and exact-only query behavior. The additions
stay `heuristic`. Full, repeated and incremental entry points retain usable
receiver evidence, so a hierarchy edit can re-evaluate unchanged sites.

Fixtures cover an inferred receiver with more than one feasible concrete
type, an inherited method, a broad upper bound that abstains, a narrow
upper bound, sibling exclusion, exact-only filters, repeated evidence and
adding or removing an override in an incremental build. Examples use invented
classes. The classifier uses Python evidence and has no project-specific names.

## Workloads and gates

- Repeat the [first plan](DESIGN.md) on Click, Rich and Jinja and compare against
  both the published 0.0.50 wheel and within-sample removal of `override` edges.
  Publish the original four measures and the difference from the first candidate.
- Holdout: Werkzeug `3.1.3`, commit `6389612fd1ee1bd93579eed5026e8fd471d04abd`,
  package `src/werkzeug`. Chosen before implementation and scoring for its
  internal class hierarchies in routing, HTTP wrappers and exceptions. Run
  the upstream `tests` directory once plain and twice with the R1-C132 tracer
  in a Python 3.12 environment. Compare the exit codes and pass/skip counts,
  report trace agreement and package function coverage, and score the trace
  union against frozen baseline and candidate builds. Report test failures
  that prevent equivalent tracing. Keep the holdout out of candidate tuning.
- The original V1–V4 thresholds stand. On the three original projects, at
  least two must gain 5 percentage points of explicit recall and every project
  may lose at most 3 percentage points of decided precision. Fast original
  routes must match and the synthetic and query controls must pass. On the
  holdout, and independently of the original three, fast parity must hold,
  explicit recall must not fall, and the same 3-point precision cap applies.
  Check the holdout against both the independent wheel and the ablation.
  Show the number of decided novel pairs so a thin holdout signal stays visible.
- Product integration and the full suite follow a passing comparison. Archive
  the patch and comparison if it falls short; then move to R1-C106.

The `pde` agent works on k99. Use the tgsh-coordinated m99 slots for trace
generation, comparison and any full suite. HP hosts the research records.
