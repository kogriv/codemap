# Test mapping — which tests exercise a symbol

```bash
codemap tests trades_at_exit --graph graph.json
```

```
# tests for bquant.analysis.trading.exit_at.trades_at_exit — confidence: high, 1 hop(s) away
  tests/unit/test_the_outcome_at_a_given_exit_bar.py::test_empty_frames_carry_the_same_types_on_both_paths
  … 6 more test(s) at distance 2 — `--all-bands` lists them

pytest tests/unit/test_the_outcome_at_a_given_exit_bar.py::test_empty_frames_carry_the_same_types_on_both_paths
```

(bquant at `cf039ef`, codemap 0.0.28, run from the repository root.)

The last line is the point: the answer is a command, not a reading exercise.

**Requires a repo-scoped graph with per-function consumers:**

```bash
codemap build mypkg --consumer tests --mode full --deep -o graph.json
```

Without `--mode full` the consumer side is per-*file*, so there are no test functions to
find; without `--consumer` there are no tests in the graph at all. Both cases say so in
the answer's caveats rather than returning an empty list.

Pass `--consumer` once per root: `--consumer tests --consumer examples`. A root that does not
exist or is not a directory is refused (exit 2) before anything is built, and two roots
written as one string, `--consumer tests,examples`, get that split command as a hint. An
existing empty directory is accepted; the graph then has nothing from it.

## What the answer is

Not "every test that touches this symbol" — that is the whole suite for anything
central. The walk goes **backwards** from the symbol over `calls` / `references` /
`accesses` / `inherits` and returns the **nearest band of tests that reach it**.

| field | meaning |
|---|---|
| `distance` | how many hops back the nearest tests were found |
| `confidence` | `high` (1–2 hops), `medium` (3), `low` (deeper, only if you ask, or reached only through a dispatch over-approximation), `unknown` (nothing found) |
| `tests[].node_id` | a pytest node id, **relative to the graph's path origin** (see below) |
| `total_at_distance` / `truncated` | how many were found, and how many the cap hid — never silently |
| `next_band` | `{distance, count}` of the next band within `--depth`, or `null` when there is none (0.0.28) |
| `caveats` | what this answer is not (see below) |

### More than the nearest band: `next_band` and `--all-bands` (R1-C80, 0.0.28)

The nearest band is the answer because, measured, it is the precise part. But the answer used to stop
there and say "searched 1 hop(s) back", which read as a short walk rather than a closed one. Now it names
the next band, as in the example above: six more tests call `trades_at_exit` through `_vector`, a helper
function in the same test module, so they sit one hop further. `--all-bands` (MCP: `all_bands: true`)
lists every band up to `--depth`, each test with its distance and confidence:

```bash
codemap tests trades_at_exit --graph graph.json --all-bands
```

Before 0.0.28 those six tests were not one hop further. They were **unreachable**: a test calling a
helper in its own module produced no edge, so the walk stopped at the helper. Since 0.0.28, in `--mode full`,
a consumer module's uses of its own top-level functions and classes are edges (`resolution: "local"`).

**Why a helper still costs a hop.** Making a module-level test helper free was tried and measured against
coverage.py on bquant and on codemap. It moved tests into the nearest band through shared helpers, and
72–80% of the tests it added were not executed by those tests at all, because a helper used by sixty tests reaches far
more than each of them runs. A function **nested inside** a test is different. It is the test's own body,
and from it the walk steps to the test at no cost.

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

**A graph built somewhere else** (another machine, another checkout, a post-commit build
copied in) records a directory that is not here. The CLI then tries the bases in order:
the sidecar's directory if it exists here, then the current directory. Each path is
rewritten against the first base where that file actually is. Run from the repository root,
the line is right, and a note says the build directory is not on this machine. Anywhere
else, name the root:

```bash
codemap tests f --graph g.json --source-root ~/work/repo
```

With `--source-root`, only that directory is tried. A wrong one is named in the caveat
rather than quietly corrected by the current directory. `report dead-code --source-root DIR`
reads its `[dead_code]` whitelist from `DIR/codemap.toml`, as `serve --source-root` does.

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

Until 0.0.31 the dominant cause of that 16% was **a method called on an object the test
constructed**: consumer-root call resolution was name-based, so `Engine().run()` in a test
produced no edge to `Engine.run`. Now a receiver is typed when a constructor or a return
annotation names its class: `Engine().run()`, `fc = make().fit(df); fc.band(…)` with
`make() -> Model` and `fit(...) -> "Model"`, and a local helper whose every `return` agrees.
Such edges carry `resolution: "typed"`. Nothing is guessed: an unannotated return or a name
assigned twice gives no edge (R1-C81).

## Protocols and dispatch guesses

A Protocol's implementers are linked by structure: a class that has every Protocol method
with the same parameter names and kinds `implements` it, whether or not it inherits it or
a registry names it. A call on a Protocol method, from core or from a test, then fans out
to every implementer's method (`resolution: "protocol"`). That is an over-approximation, the
same kind as a registry `registry-candidate`: the receiver is one of them, and which one is
not known.

So a test reached **only** through such a fan-out is `low`, whatever its distance, and the
answer says how many rows are like that ("reached only through a dispatch
over-approximation"). A test with at least one exact path keeps its distance's confidence.
If every test in the nearest band is a guess, the answer's own confidence is `low` as well.

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
