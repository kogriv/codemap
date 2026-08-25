# Design — Test mapping: which tests cover this symbol (axis A10)

**Status:** ⬜ **open** — decisions below are recommendations, not yet built.
**Motivates:** gap [test_mapping_2026-08-25](../../gaps/test_mapping_2026-08-25.md).
**Backlog:** R1-C24.
**Related design:** [scope.md](scope.md) (consumer roots and roles — where "this is a test" comes from),
[source_visible_references.md](source_visible_references.md) (the honesty precedent for labelling an
approximation instead of hiding it).

The measurement says three things and they set the whole shape of the design: the direct answer covers 18% of
symbols, the reachable answer covers 80% but returns a median of 21 tests, and on the fast tier only 21% of
**methods** have any inbound call at all. So the feature is not "add an op that walks the graph". It is
*ranking* plus *an honest statement of what the answer is*.

**Guiding invariants (unchanged):** source-only, deterministic, two tiers, resolved-or-honestly-flagged,
closed edge vocabulary (R1-C7), `extras` open-ended.

---

## D1 — What counts as a test: derive, do not store

**Recommended: derive at query time. No new node kind, no new `extras`, no schema change.**

A node is a test when all three hold: it lives under a consumer root whose role is `tests` (already recorded
by `scope.py`'s `_KNOWN_ROLES` and by the consumer-root machinery), its kind is `function`, and its name
matches pytest's collection rule (`test_*`, or a method on a `Test*` class).

- **Why derived:** the rule is pure syntax over data already in the graph, and R1-C21's diagnostics
  established the pattern — a fact you can recompute is not a fact you store. It also means an existing
  `graph.json` gains the feature on upgrade with no rebuild.
- **Rejected:** marking `extras.role="test"` at build time. It bakes one test framework's naming convention
  into the artifact, and the artifact outlives the convention.

**Consequence to state in the docs:** with `--mode thin` (the default) consumers are per-*file* nodes, so
there are no test-function nodes to find and the answer degrades to a list of test **files**. That is still
useful (`pytest tests/test_x.py` runs), and it must be labelled as the coarser answer rather than silently
returned as if it were per-test.

## D2 — The relation: bounded, distance-ranked reachability

**Recommended: reachability with distance banding, a hard cap, and both honesty labels.**

Distance 1 answers 18% of symbols — not a candidate. Unbounded reachability answers 80% but returns a median
of 21 tests and a maximum of 126 out of 416. Measured banding:

| answer | median | p90 | max |
|---|---|---|---|
| everything within 6 hops | 21 | — | 126 |
| nearest band only | 6.5 | 66 | 76 |

**The rule:** walk backwards from the symbol over `calls` / `references` / `accesses`, collect test functions
by hop distance, return the **nearest non-empty band**; if that band exceeds the cap, return it truncated and
say so. Deeper bands are available on request (an explicit `--depth`), never by default.

- **Cap:** 25, and **`log` what was dropped** — the "no silent caps" rule. A truncated answer that does not
  say it is truncated is the #5 failure in a new costume.
- **Two labels, both required** (R1-C13 lower-bound discipline):
  - *over-set* — "a test that reaches this symbol does not necessarily assert on it";
  - *lower bound* — "dynamic dispatch, fixtures resolved by name and monkeypatched calls are invisible".
- **Rejected: a scoring heuristic** (name similarity, module proximity, file adjacency). It ranks better in
  demos and cannot be justified from the source, which puts it outside "source-only, deterministic". Distance
  is a fact about the graph; similarity is a guess about intent.

## D3 — The tier is part of the answer

**Recommended: carry `tier` in every response and warn when it is `fast`.**

Methods with any resolved inbound call: **21% fast, 56% deep**. Tests overwhelmingly call methods on objects.
An A10 answer computed on a fast graph is not a slightly worse answer; for a method it is usually *empty*, and
an empty answer reads as "nothing tests this".

- The response envelope gains `tier`, and on `fast` a note: *"built on the fast tier — method calls are
  largely unresolved; rebuild with `--deep` for a usable test set"*.
- **Rejected: refusing to answer on a fast graph.** It is right about the risk and wrong about the user —
  the free-function answer (91% resolved) is genuinely good, and a hard refusal would hide it.
- **Rejected: silently upgrading the graph.** A query op must not trigger a one-minute rebuild.

## D4 — The pytest fixture seam: bridge by name

**Recommended: yes — same treatment M7 gave the plugin registry, one honesty label.**

63% of test functions take their subject as a parameter and **0** edges connect them to the fixture that
produces it. pytest binds fixture→parameter by name, at collection time, along the conftest chain.

Resolution rule, in pytest's own precedence order: a fixture visible to a test function is one defined **in
its module**, then in a `conftest.py` in its directory, then in each parent directory's `conftest.py` up to
the rootdir. Match the parameter name against that chain; on a hit, emit `references` from the test to the
fixture with `extras.resolution = "fixture"`.

- **Why `references` and not `calls`:** the test does not call the fixture, pytest does. `references` is
  already defined as "dispatch site → the symbol it names", which is precisely this.
- **Honest limits, to be documented, not hidden:** `@pytest.fixture(params=…)`, `usefixtures`, plugin-provided
  fixtures (`tmp_path`, `monkeypatch`) and dynamically-registered fixtures will not resolve. An unresolved
  parameter name simply produces no edge — never a guessed one.
- **Measured value on codemap: 0 additional symbols covered** (fixtures reach a subset of what test bodies
  reach) — so this is bought for *attribution*, not coverage, and codemap's own suite is a weak witness
  because it has **no `conftest.py`**. Before building D4, measure it on a suite that does; if the number is
  still zero there, D4 is a candidate to defer rather than a requirement.

## D5 — The surface: an answer you can paste into a shell

**Recommended: `Query.tests_for(symbol)` → serve op `tests` → `codemap tests <symbol>`, emitting pytest node
ids.**

Graph ids are `tests.test_r1c22_source_visible_refs.test_shadowed_functions_stay_high`. pytest wants
`tests/test_r1c22_source_visible_refs.py::test_shadowed_functions_stay_high`. The translation is mechanical
from the node's `file` field plus its own name, and without it the feature is a reading exercise.

Response shape: `{symbol, tier, distance, truncated, tests:[{node_id, file, line, distance}], caveats:[…]}` —
and the CLI prints a runnable `pytest` invocation as its last line.

- **Also expose the inverse** (`what does this test cover`) — it is the same index read the other way and
  costs one function. It answers "is this test actually exercising the thing it claims to" during review.
- **Do not** add it to `review`'s dossier in this milestone. It is the obvious next step and it deserves its
  own measurement of whether the added bulk helps the reviewer.

## D6 — Acceptance: precision/recall against `coverage.py`, not a vibe

**Recommended: measure before claiming.**

The claim "these are the tests for X" is exactly the kind that F14/F15 caught being confidently wrong. The
ground truth is obtainable: run the suite per-test under `coverage.py`, collect the real symbol set each test
executes, and invert it.

Acceptance:

1. On a **sample of 20 symbols** spanning free functions, methods and classes, report precision and recall of
   `tests_for` against the coverage-derived truth, on **both** tiers. Publish the numbers in the backlog entry
   — including the bad ones.
2. **Recall on the nearest band is the number that matters**; precision is expected to be below 1 by
   construction (the over-set label says so) and must not be quietly optimised by tightening the walk until
   recall collapses.
3. The `high`-confidence analogue: any symbol reported as covered by **zero** tests must be spot-checked
   against coverage. A false "no tests cover this" is the same affirmative-over-a-blind-spot this project has
   now shipped four fixes for.
4. Deterministic: two runs on a frozen tree return identical, identically-ordered answers.
