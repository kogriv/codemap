# Test mapping — which tests exercise a symbol

```bash
codemap tests build_provenance --graph graph.json
```

```
# tests for codemap.provenance.build_provenance — confidence: high, 1 hop(s) away
  tests/test_r1c25_provenance.py::test_building_a_path_free_block_is_enforced_not_hoped

pytest tests/test_r1c25_provenance.py::test_building_a_path_free_block_is_enforced_not_hoped
```

The last line is the point: the answer is a command, not a reading exercise.

**Requires a repo-scoped graph with per-function consumers:**

```bash
codemap build mypkg --consumer tests --mode full --deep -o graph.json
```

Without `--mode full` the consumer side is per-*file*, so there are no test functions to
find; without `--consumer` there are no tests in the graph at all. Both cases say so in
the answer's caveats rather than returning an empty list.

## What the answer is

Not "every test that touches this symbol" — that is the whole suite for anything
central. The walk goes **backwards** from the symbol over `calls` / `references` /
`accesses` / `inherits` and returns the **nearest band of tests that reach it**.

| field | meaning |
|---|---|
| `distance` | how many hops back the nearest tests were found |
| `confidence` | `high` (1–2 hops), `medium` (3), `low` (deeper, only if you ask), `unknown` (nothing found) |
| `tests[].node_id` | a pytest node id, **relative to the graph's path origin** (see below) |
| `total_at_distance` / `truncated` | how many were found, and how many the cap hid — never silently |
| `caveats` | what this answer is not (see below) |

## The pasted line, and where it runs from

`codemap tests` ends with a `pytest …` line you can paste. The ids inside the answer are
graph-relative — the graph does not know where on disk it was built, on purpose (see
[provenance.md](provenance.md)) — so the **CLI** resolves them against the build sidecar
and prints paths relative to your current directory:

```bash
$ codemap tests f --graph g.json            # built with roots under research/
  tests/test_mod.py::test_f                 # what the graph stores

pytest research/tests/test_mod.py::test_f   # what runs from here
```

Two rules, both from [#12](https://github.com/kogriv/codemap/issues/12), where the printed
line named a path that did not exist while looking exactly like one that did:

- a rewrite is printed **only when the file is really there**. An unverifiable one is not
  a convenience, it is the same defect with a different path in it;
- when it cannot be resolved (no sidecar — the graph was moved, or built by an older
  codemap), the path is left as the graph stores it and a caveat names the directory it is
  relative to, rather than leaving the reader to find out from pytest.

The served/MCP payload always keeps the graph-relative id: an answer may be read on a
machine where this tree does not exist, and a path that is wrong there is worse than one
that is honestly relative.

## Why the cutoff is 3

Measured against `coverage.py` ground truth on codemap's own suite (484 tests, per-test
contexts), precision by nearest hop:

| nearest hop | symbols | median precision | median tests returned |
|---|---|---|---|
| 1 | 63 | 1.00 | 2 |
| 2 | 91 | 1.00 | 4 |
| 3 | 44 | 1.00 | 8 |
| **4** | 61 | **0.67** | **78** |
| 5 | 29 | 0.33 | 78 |
| 6 | 5 | 0.23 | 78 |

By the fourth hop the walk has reached shared test infrastructure and is answering
"most of the suite". So 3 is the default, taken from the table rather than from taste.
`--depth 6` still gives you the deeper candidates, labelled `low`.

At that cutoff, on codemap's own repo: **57%** of exercised symbols get an answer (deep
tier; **43%** on fast), median precision **1.00**, and **93%** of answers contain at
least one test that coverage.py confirms executes the symbol.

Recall against the executed-set is **0.43** median over answered symbols — and it is
deliberately not the target. For a central symbol the executed-set *is* most of the
suite (`Graph.add_edge`: 151 tests), and returning 151 tests is not an answer. Re-run the
whole measurement yourself with
[`research/bench/test_mapping_accuracy.py`](../research/bench/test_mapping_accuracy.py).

## What the answer is not — three labels it always carries

- **over-set** — a test that *reaches* a symbol does not necessarily assert on it.
- **lower bound** — dynamic dispatch, fixtures resolved by name and monkeypatched calls
  are invisible to a static graph.
- **the tier** — 21% of methods have a resolved inbound call on the fast tier against
  56% on deep, and test suites call methods on objects. A fast-tier answer for a method
  is not slightly worse; it is usually empty. The caveat says so and points at `--deep`.

## `unknown` is not "untested"

**16%** of symbols that coverage.py proves are exercised produce no answer within 3 hops.
They come back as `confidence: "unknown"` with an explicit caveat, never as an empty list
that reads like "nothing tests this". That failure — a confident nothing over a blind
spot — is the one this project has now shipped fixes for five times ([#1](https://github.com/kogriv/codemap/issues/1),
[#3](https://github.com/kogriv/codemap/issues/3), [#5](https://github.com/kogriv/codemap/issues/5),
[#7](https://github.com/kogriv/codemap/issues/7), and R1-C23).

The dominant cause of that 16% is known and stated rather than hidden: **a method called
on an object the test constructed**. Consumer-root call resolution is name-based, so
`Engine().run()` in a test produces no edge to `Engine.run`.

## The inverse

```bash
codemap tests test_two_builds_of_a_frozen_tree_are_byte_identical --covers --graph graph.json
```

Same index read forward: which core symbols this test reaches, by distance. Useful in
review — is the test exercising what its name claims?

## Not built, and why

**The pytest fixture seam is not modelled.** 48% of bquant's tests and 63% of codemap's
receive their subject as a fixture parameter, and there are zero edges from a test to the
fixture that produces it — pytest binds those by name through the conftest chain, which
is a dispatch seam like any other.

It was measured before being built, on a suite that *has* a conftest (bquant, 68
fixtures): symbols reachable **only** through a fixture and not through any test body:
**1 out of 1043**. On codemap: **0**. The fixtures call the same entry points the tests
do. So the seam costs attribution, not coverage, and building a conftest-chain resolver
for 0.1% was deferred rather than done. If that number is different in your repo, this is
the thing to build first.

**Design:** [design/test_mapping.md](design/test_mapping.md).
**Gap:** [../gaps/test_mapping_2026-08-25.md](../gaps/test_mapping_2026-08-25.md).
