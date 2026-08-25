# codemap — gap: "which tests cover this symbol?" has no answer (axis A10)

**Date:** 2026-08-25
**Source:** deliberate probe of axis **A10**, on the watchlist since 2026-07-30 —
*"a real task, 'which tests do I run when I change X', ran into the absence of a symbol→tests slice."*
Measured on codemap's own repo (`build codemap --consumer tests --mode full`, both tiers).
**Type:** missing capability — not a wrong answer, an absent one. But the *naive* answer the surface does
offer today is wrong 82% of the time, which puts it in the honesty family after all.
**Related:** `agent_workflow_dogfood_2026-07-29.md` (F9–F13 — the same shape: the data is in the graph, the
step the human needs is not), `dispatch_bridging_2026-07-28.md` (F5 — pytest fixtures are a dispatch seam of
exactly the kind M7 bridged for bquant's plugin registry).
**Design:** [docs/design/test_mapping.md](../docs/design/test_mapping.md).
**Backlog:** R1-C24.
**Status:** ✅ **closed same day** (2026-08-25, no schema change) — `Query.tests_for` / `covers`, serve ops
`tests`/`covers`, `codemap tests <symbol>` emitting runnable pytest node ids. Validated against **coverage.py**
ground truth rather than asserted: at the measured cutoff, **57%** of exercised symbols get an answer (deep;
43% fast), **median precision 1.00**, and **93%** of answers contain at least one test coverage.py confirms
executes the symbol. The other 16% come back `unknown`, never "untested". **D4 (the fixture seam) was measured
and deliberately not built** — see §6. Tests 484 → **503**.

## 1. The gap

There is no op for it. Of the 29 serve ops, the closest are `callers` and `impact`, which return *whatever*
references a symbol — tests indistinguishable from production callers, and only at distance 1.

The question is asked constantly and answered by hand: change a function, run the whole suite, or grep for
its name and hope.

## 2. Evidence — measured on codemap itself

Repo-scope graph: 1492 nodes, 3585 edges (fast) / 4117 (deep). **416 test functions**, **380 core
functions and classes**.

### 2.1 The direct answer is empty for 82% of symbols

| relation | core symbols covered |
|---|---|
| **direct** inbound edge from a `tests.*` node (what `callers`/`references_to` return today) | **68 / 380 — 18%** |
| reachable from some test function, fast tier | 225 / 380 — 59% |
| reachable from some test function, **deep** tier | **304 / 380 — 80%** |

A test calls `extract()`; `extract()` calls two hundred things. Almost nothing a test exercises is something
the test *names*. Distance 1 is the wrong question.

### 2.2 The fast tier is structurally crippled here — because tests call methods

| | inbound `calls` resolved, fast | deep |
|---|---|---|
| free functions (229) | 208 — **91%** | 211 — 92% |
| **methods** (129) | 27 — **21%** | 72 — **56%** |

Test suites are written as `q = Query(g)` then `q.hotspots()`. `Query.hotspots`, `Query.references_to` and
`Query.consumers` are all covered by real tests and all have **zero** inbound `calls` on the fast tier. This
is the known method-on-object limit (the jedi tier exists for it), but A10 is the first consumer for which it
is *decisive* rather than a recall number.

### 2.3 The reachable answer is too big to act on

| ranking | tests returned per symbol |
|---|---|
| everything reachable within 6 hops | median **21**, max **126** |
| only the nearest band (shortest distance) | median **6.5**, p90 **66**, max 76 |

Distribution of the shortest test→symbol distance: 1 hop 63 symbols, 2 hops 95, 3 hops 49, 4 hops 64,
5 hops 28, 6 hops 5.

"Run 126 of your 416 tests" is not an answer; it is the suite. Distance banding cuts the median 3× and still
leaves a p90 of 66. **Ranking is not a polish item here — it is the feature.**

### 2.4 The pytest fixture seam is unmodelled

**262 of 416 test functions (63%)** receive their subject as a parameter — a fixture or a parametrize value.
19 fixtures are defined across the suite. Edges from a test function to the fixture it consumes: **0**.
(The 17 edges that exist between tests and fixtures are `contains`, module→fixture.)

This is structurally the F5 dispatch seam: pytest resolves a fixture by *name*, through the conftest chain,
at collection time — the same "factory + registry + call on the object" shape that broke the bquant plugin
chain until M7 bridged it.

**Measured consequence on this repo: zero.** Symbols reachable *only* through a fixture and not through any
test body: **0** — the fixtures here call `extract()`, and so do the tests. So the seam costs no *coverage*;
it costs *attribution* — when the work happens in the fixture, the tests that trigger it are not linked to it,
and it is the tests that are runnable. Note the limit of this measurement honestly: **codemap's suite has no
`conftest.py`**, so the worst form of the seam (a fixture defined in a parent conftest, consumed by a hundred
tests in child directories) is not represented here at all.

### 2.5 41% of core symbols are reachable from no test — and that number cannot be trusted yet

155 of 380 on the fast tier, 76 on the deep tier. Spot-checking the fast-tier set against the source shows
most of the difference is §2.2, not missing tests. Any surface that publishes this number must present it as
a **lower bound on coverage**, never as "untested".

## 3. Why it matters

- **It is the change-safety question.** R1-C5 (`diff`) and M15 (`review`) both answer "what does this change
  touch"; neither answers "and what proves it still works". A change-review dossier that names the risk and
  not the tests is half a dossier.
- **The answer must be runnable.** Node ids are `tests.test_x.test_y`; pytest wants `tests/test_x.py::test_y`.
  The translation is mechanical, and without it the answer is a reading exercise instead of a command.
- **The naive answer is actively misleading.** `callers("Query.hotspots")` returns nothing today. An agent
  reads that as "nothing tests this".

## 4. Scope of a full solution

1. Identify test nodes (consumer role `tests` + pytest naming), and translate ids to **pytest node ids**.
2. Answer with **bounded, distance-ranked reachability**, not distance 1 — with an explicit cap and an
   explicit honesty label: an over-set (a test that reaches a symbol may not assert on it) and a lower bound
   (dynamic dispatch is invisible).
3. Carry the **tier** in the answer and warn on `fast` — 21% method resolution is not a basis for "these are
   your tests".
4. Bridge the fixture seam by name, within a module and along the conftest chain.
5. Ship the inverse (`what does this test cover`) if it is free from the same index.

**Acceptance must be measured against ground truth, not asserted.** `coverage.py` can produce the real
per-test symbol set for a sample; the milestone's honesty claim is precision/recall against that sample,
in the manner of `soundness_dogfood_2026-07-30.md` — not "the answer looks reasonable".

Design decisions and sizing: [docs/design/test_mapping.md](../docs/design/test_mapping.md).

---

## 6. What the measurement decided that the design could not

The design named the acceptance (precision/recall against `coverage.py`) but guessed at two things. Running
the suite under `coverage.py` with per-test contexts settled both, and overturned one of them.

### The distance cutoff is a cliff, not a taper

Precision of the nearest non-empty band, by how far back that band was:

| nearest hop | symbols | median precision | mean | median tests returned |
|---|---|---|---|---|
| 1 | 63 | 1.00 | 0.98 | 2 |
| 2 | 91 | 1.00 | 0.79 | 4 |
| 3 | 44 | 1.00 | 0.73 | 8 |
| **4** | 61 | **0.67** | 0.59 | **78** |
| 5 | 29 | 0.33 | 0.47 | 78 |
| 6 | 5 | 0.23 | 0.42 | 78 |

At the fourth hop the walk reaches shared test infrastructure and starts answering "most of the suite" —
the answer size jumps 8 → 78 in one step. So the default depth is **3**, chosen from this table. Deeper
walks remain available and are labelled `low`.

### "Recall on the nearest band" was the wrong acceptance metric — and the design said it was the one that mattered

Against coverage's truth set, median recall of the returned band is **0.43** over the symbols that get an
answer (p25 0.17, p75 1.00) — and **0.02** across all exercised symbols, counting an `unknown` as zero. The
low figure is not a defect, and the spread says why: recall collapses exactly where the truth set is widest.
For `Graph.add_edge` the truth set is **151 tests** — every test that executes one of its lines — and the
band returns 3, so recall is 0.02. Reporting 151 is reporting the suite.

So the honest claim had to change with it. The feature does not answer *"every test that covers X"*; it
answers *"the closest tests to X"*, and the number that turned out to matter is **93% of answers contain at
least one genuinely covering test** at a median precision of 1.00. Recall against the executed-set is
published here — in both denominators — because it is the number a reader would otherwise assume, not because
it is the target. The bench that produces it is
[`research/bench/test_mapping_accuracy.py`](../research/bench/test_mapping_accuracy.py), so the claim is
re-runnable rather than a sentence in a document.

### And the honesty rule needed a fifth application

**16% of symbols that coverage.py proves are exercised get no answer within the cutoff.** An empty list would
read as "nothing tests this" — the same confident-nothing as #1, #3, #5, #7 and R1-C23. They return
`confidence: "unknown"` with an explicit caveat instead. The dominant cause is identified rather than left
mysterious: **a method called on an object the test constructed** — consumer-root call resolution is
name-based, so `Engine().run()` produces no edge to `Engine.run`, on either tier.

## 7. D4 (the pytest fixture seam) — measured, then deliberately not built

The design required this to be measured on a suite that *has* a `conftest.py` before being built, since
codemap's own suite has none. Measured on bquant — 894 tests, **48% of them taking a fixture parameter**, 68
fixtures, and (as expected) **zero** edges from a test to the fixture that produces it:

> symbols reachable **only** through a fixture and not through any test body: **1 of 1043**.

On codemap the same number is **0**. The fixtures call the same entry points the test bodies do, so bridging
the seam buys attribution, not coverage. Building a conftest-chain resolver for 0.1% would be gold-plating
against this project's own stop criterion, so it is recorded here and left. If the number is materially
different in another repo, that is the trigger to build it.
