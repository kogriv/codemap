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
**Status:** ⬜ open — measured, designed, not yet built.

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
