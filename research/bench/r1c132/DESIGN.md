# R1-C132 — an independent benchmark of call-graph accuracy

**Status:** pre-registered 2026-11-23, before any run on the projects below. **Done (run 3, 2026-11-23)** —
reconciled in [`RESULTS.md`](RESULTS.md). Results go in
[`RESULTS.md`](RESULTS.md) and a section of [`docs/accuracy.md`](../../../docs/accuracy.md), reconciled against
this page; anything not listed here is reported as a surprise.

## Why

codemap's accuracy numbers so far come from a hand-labelled micro-suite it owns
([`research/bench/callgraph_truth/`](../callgraph_truth/)) and from the intrinsic resolution rate on bquant. Both
are self-measurements. The external audit (2026-11-23, §6.1 and §10.2 item 7) asked for a measurement on code
codemap was never tuned on, against a truth codemap did not produce. The follow-up audit named this the most
useful next step.

## The projects

Five public, pure-Python projects with their own test suites, chosen for different shapes of code. codemap was
never built on, tuned on, or fixed for any of them. attrs was considered and left out, because R1-C57 fixed a
build crash on its layout.

| project | tag | commit | package dir | shape |
|---|---|---|---|---|
| more-itertools | v11.2.1 | `4aeb4338ae14` | `more_itertools` | plain functions, generators |
| click | 8.5.1 | `cf19179e8e2f` | `src/click` | decorators, classes, context objects |
| rich | v15.0.0 | `6ac483cbea39` | `rich` | large OOP, render protocol, dataclasses |
| markdown-it-py | v4.3.0 | `d504583a458e` | `markdown_it` | rule chains held in lists (registry dispatch) |
| jinja | 3.1.6 | `15206881c006` | `src/jinja2` | compiler, visitor dispatch by `getattr` |

Static graphs come from **codmap 0.0.47 from PyPI**: `codemap build <package dir> -o fast.json` and
`codemap build <package dir> --deep --repeat 3 -o deep.json`. The package only, no consumer roots. Python 3.12.

## The truth: runtime calls under the project's own tests

[`r1c132_tracer.py`](r1c132_tracer.py) is a pytest plugin built on `sys.monitoring`. It records `F → G`
whenever a named package function G starts and F is the nearest package frame above it. It attributes calls
the way codemap does. The control package [`control/`](control/) shows the shapes, and
`tests/test_r1c132_harness.py` checks every one of them:

- **nested functions and lambdas.** A call from a nested function or lambda is attributed to the enclosing
  function, recorded as `nested`.
- **wrappers.** A call through another function's nested function, such as a decorator's wrapper, is
  recorded as `wrapper`.
- **foreign code.** A call through up to three frames of code outside the package is recorded as `external`.
  A call from a test, or from deeper outside, is not a package edge.
- **construction.** `X(...)` of a package class is recorded as `F → X`, seen at the call instruction. This
  catches dataclasses and classes without a Python `__init__`.
- **`super().__init__()`.** It is recorded as a call, not a construction.

Lines that ran in package files are recorded too; the precision side needs them.

## The measures ([`compare.py`](compare.py))

**Recall.** A runtime pair falls into one of the following categories:

| category | what it is | in the headline? |
|---|---|---|
| `call` | an ordinary call between package functions | yes |
| `construct` | `F → class` | yes |
| `init` | `F → C.__init__` when F also constructs; the construction stands for it | no |
| `implicit` | a dunder reached by an operator or protocol | no, reported apart |
| `property` | the target is not a function or class node | no, reported apart |
| `decorator` | applied at import (codemap's `decorated_by`) | no, reported apart |

- **Headline recall** = explicit pairs (`call` + `construct`) that are `calls` edges, over all explicit pairs.
- Recall is also reported by how the pair was reached: `direct`, `nested`, `external`, `wrapper`.
- A second figure counts a pair as found if it is a `references` edge too. A function passed as a value is a
  reference in codemap.

**Precision.** Each `calls` edge `F → G` gets one outcome:

| outcome | what it means | judged? |
|---|---|---|
| `confirmed` | the pair was observed | yes |
| `contradicted` | **every** call site in F naming G's last segment ran, and G was never entered from F | yes |
| `unexercised` | the sites did not run | no |
| `partly_run` | some sites ran and some did not | no |
| `caller_not_run` | F never ran | no |
| `no_site` | no site in F names G | no |

- Precision is decided = confirmed / (confirmed + contradicted), by tier, by grade (`exact` / `inferred` /
  `heuristic`) and by route.
- The undecided shares are reported next to it, since a precision over a small decided set says little.

**`callers()` completeness.** This is the share of called functions whose every runtime caller is a static
caller. It answers "can I trust the list `callers` gives me".

## Controls (each can fail)

- **C1, C2.** The harness tests are green: the tracer attributes every control shape as codemap does, and a
  planted false edge is `contradicted` while an unrun site is not judged. Five mutations of the harness each
  turn a control red: no `CALL` constructions, no `super()` check, any-site instead of all-sites, wrapper read
  as nested, never contradicted.
- **C3 (determinism).** The traced suite runs twice. Explicit pairs differ by at most 1%; above that, the
  difference is reported and the union is used.
- **C4 (exercise).** At least 50% of package functions start under the suite. A project below that is reported,
  not dropped.
- **C5 (adjudication).** Every `contradicted` edge is read by hand and labelled `false edge` or `method artifact`
  — the line ran but the call on it could not, as with short-circuit, a conditional expression or an exception.
  Above 30 per project and tier, a random 30 (seed 132) are read. Precision is reported raw and adjudicated.
- **C6 (no interference).** Pass, fail and skip counts with the tracer equal those without it.

## Predictions (written before the runs)

- **H1.** `exact`-grade decided precision is ≥ 97% on every project and both tiers.
- **H2.** `inferred` (deep) decided precision is ≥ 93% on every project.
- **H3.** Where a project has ≥ 10 decided `heuristic` edges, their precision is below `exact`, and below 85%.
- **H4.** Explicit recall:
  - deep median across projects in [50%, 75%];
  - fast median in [35%, 60%];
  - deep > fast on every project.
- **H5.** `external` recall is the lowest of the four reaching ways on every project where it has ≥ 10 pairs.
  These are higher-order calls through foreign code.
- **H6.** Deep `callers()` completeness has a median ≥ 50%.
- **H7.** The lowest deep recall is jinja or rich; the highest is more-itertools or click.
- **H8.** Deep explicit recall is < 90% on every project. The micro-suite's 100% on decidable edges is not a
  claim about real code.
- **H9.** Contradicted edges, after adjudication, are < 3% of all `calls` edges on every project and tier.

## What it does not measure

- Calls the tests never make. Recall is over exercised pairs, so it is an upper bound on recall over all real
  pairs.
- Edges into third-party code.
- Calls from tests into the package. The `tests` and `covers` answers deserve a separate benchmark.

## Deviations (recorded as they happened)

1. **Generator calls were attributed to the consumer, not the caller (tracer v1).** C5 found it on the first
   run of more-itertools (33 "contradicted" deep edges, such as `strip → rstrip`). A generator's frame first
   runs at `next()`, in whoever iterates it. The tracer now takes generators, coroutines and async generators
   at the call instruction (`CALL`) and no longer at `PY_START`. The control package gained the case, and the
   mutation of it turns C1 red.
2. **Edges to attribute nodes are not judged.** In `self._key(x)`, `_key` holds a function the caller passed,
   and codemap points the edge at the attribute node. The truth cannot see that call, so the outcome is
   `attribute_target`, not judged.
3. **The first launch raced on the shared codmap environment**, and click failed before it started. The
   comparisons of the four finished projects came from tracer v1 and are discarded. All five projects are
   rerun with the fixed harness. Nothing from the first run is used.
4. **Run 2 (tracer v2): C5 found three more defects of the truth, not of codemap.** Reading the contradicted
   edges of run 2 turned up three causes, each with its own control case and mutation:
   - **A closure, lambda or generator expression lost its owner when the owner was no longer on the stack.**
     Examples: a decorator factory's inner function, a rule a factory returned (`make_fence_rule`), a
     generator expression the caller consumed (`run_length.encode → ilen`). The tracer walked up the stack,
     while codemap attributes lexically. Nested code is now attributed lexically, to the function it is
     defined in. The exception is a wrapper: a nested frame that holds the callee itself as a value (a
     decorator's `fn`), which keeps the stack walk.
   - **A call site was switched off after its first foreign class or generator.** contextlib has one site
     that starts every `@contextmanager`, and a site whose name a test monkeypatched first met the test's
     class (click's `raise Abort()`). These sites now stay on. Only builtin types, C callables and plain
     functions switch a site off.
   - These changed the truth only. codemap's graphs, the projects and the measures are unchanged. Run 2's
     tables are kept in [`RESULTS.md`](RESULTS.md#appendix-run-2-tracer-v2), not discarded.
5. **A third C5 label, "dispatched elsewhere" (post hoc).** Some contradicted edges' sites ran and their calls
   ran, but they entered another function of the same name: a subclass override (`Parameter.__init__ →
   Parameter._parse_decls` entered `Option._parse_decls`), a protocol's implementation, or a definition for
   another platform. They are neither a false edge nor a measurement artifact, so they get their own label.
   compare.py counts them mechanically (`contradicted_same_name`, guarded in C2). Precision is given both
   ways: strict (they count as false) and dispatch-aware (they count as confirmed).
6. **In the deep graph, nearly every `calls` edge has resolution `deep` (grade `inferred`).** That includes
   edges the fast graph resolves exactly, so the deep tier's `exact` grade is nearly empty. H1's deep half is
   therefore read on what is there. A post-hoc split of deep precision (edges in both graphs vs deep only) is
   reported, labelled as such.
7. **click's three suites (plain, traced ×2) ran side by side** (`R1C132_CONCURRENT=1`), because its plain
   suite takes 53 minutes here. C6 would show any interference.
8. **The first launch of run 3 was stopped.** C6 caught interference on rich: one test fails only under the
   tracer (`test_broken_getattr`). The new wrapper check looked attributes up on arbitrary objects, and an
   object whose `__getattr__` raises broke it. The check now goes by exact type, without lookups, and the
   control package gained the case. All five projects were rerun. Nothing from that launch is used.
