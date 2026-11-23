# R1-C132 — results

Pre-registration and deviations: [`DESIGN.md`](DESIGN.md). Everything below is **run 3**: codmap 0.0.47 from PyPI,
Python 3.12.16, the tracer and controls in this directory. Raw comparisons: [`results/run3/`](results/run3/).
Run 2, the tracer before deviation 4, is kept in the [appendix](#appendix-run-2-tracer-v2).

## In short

- **Precision is high, and the misses are rarely false edges.** C5 read 105 contradicted edges. One is a false edge:
  the deep tier inferred `Span` for a list of spans. The rest are three other kinds:
  - a call on a line that ran, but in a branch that did not;
  - a call that ran but entered another function of the same name, such as a subclass override, a protocol's
    implementation, a test double, or a definition for another Python;
  - code that runs when a definition executes (a decorator, a default argument), which codemap attributes to
    the function it belongs to.
- **Recall, deep:**

  | project | deep recall |
  |---|---|
  | more-itertools | 89% |
  | rich | 82% |
  | click | 73% |
  | markdown-it-py | 72% |
  | jinja | 60% |

  Fast is lower everywhere. The deep tier adds 1 to 32 points, the most where code calls methods on
  attributes (markdown-it-py, rich).
- **Virtual dispatch costs on both sides.** codemap points `obj.m()` at the declaring class's `m`, and at
  runtime the call enters an override:
  - on the precision side, these are the "dispatched elsewhere" edges;
  - on the recall side, they are 19–36% of the deep misses on click, rich and jinja, counted post hoc. There,
    codemap has the call with the right name but to another definition.
- **The truth needed the same scrutiny as the graph.** C5 found five defects of the tracer over three runs,
  C6 one more. Each was fixed with its own control case and mutation (DESIGN.md, deviations 1, 4 and 8).

## Controls

| control | result |
|---|---|
| C1, C2 (harness) | green: 26 truth pairs on the control package, a planted false edge contradicted, an unrun site not judged, same-name count right; 9 mutations each turn it red, the idle mutation stays green |
| C3 (determinism) | 0 differing explicit pairs between the two traced runs, on all five projects |
| C4 (exercise) | 84.5% (click) to 96.6% (more-itertools) of package functions start under the suite — all above 50% |
| C5 (adjudication) | every contradicted edge read, except rich deep (a random 30 of 42, seed 132) — table below |
| C6 (no interference) | pass, fail and skip counts equal with and without the tracer, on all five (rich's 8 failures are the same 8 without it) |

## Tables

| project | functions | started (C4) | explicit pairs | fast recall | deep recall | deep recall, calls or references |
|---|---|---|---|---|---|---|
| more-itertools | 265 | 96.6% | 93 | 88.2% | 89.2% | 92.5% |
| click | 483 | 84.5% | 646 | 53.4% | 73.2% | 74.9% |
| rich | 767 | 88.7% | 1240 | 58.0% | 82.1% | 88.8% |
| markdown-it-py | 215 | 89.3% | 386 | 39.9% | 72.0% | 74.6% |
| jinja | 688 | 90.8% | 1476 | 46.1% | 60.0% | 61.2% |

**Deep recall by how the pair was reached** (found / pairs):

| project | direct | nested | external | wrapper |
|---|---|---|---|---|
| more-itertools | 77/84 (91.7%) | 6/9 (66.7%) | 0/0 (—) | 0/0 (—) |
| click | 426/530 (80.4%) | 32/43 (74.4%) | 15/64 (23.4%) | 0/9 (0.0%) |
| rich | 966/1165 (82.9%) | 50/64 (78.1%) | 0/4 (0.0%) | 2/7 (28.6%) |
| markdown-it-py | 272/365 (74.5%) | 6/7 (85.7%) | 0/14 (0.0%) | 0/0 (—) |
| jinja | 851/1203 (70.7%) | 30/38 (78.9%) | 2/190 (1.1%) | 3/45 (6.7%) |

**Runtime pairs outside the headline** (deep found / pairs): implicit dunders, properties, decorators.

| project | implicit | property | decorator | init (behind a construction) |
|---|---|---|---|---|
| more-itertools | 0/16 | 0/5 | 0/0 | 7 |
| click | 0/45 | 0/33 | 0/0 | 53 |
| rich | 3/197 | 0/207 | 0/5 | 229 |
| markdown-it-py | 6/34 | 1/32 | 0/0 | 17 |
| jinja | 4/124 | 0/28 | 0/1 | 144 |

**Precision, fast** — decided = confirmed / (confirmed + contradicted); the rest is not judged.

| project | calls edges | confirmed | contradicted | not judged | decided precision | exact | inferred | heuristic |
|---|---|---|---|---|---|---|---|---|
| more-itertools | 95 | 82 | 0 | 13 (13.7%) | 100.0% | 100.0% of 82 | — | — |
| click | 429 | 345 | 11 | 73 (17.0%) | 96.9% | 96.9% of 356 | — | — |
| rich | 996 | 721 | 24 | 251 (25.2%) | 96.8% | 96.8% of 745 | — | — |
| markdown-it-py | 166 | 160 | 2 | 4 (2.4%) | 98.8% | 98.8% of 162 | — | — |
| jinja | 789 | 682 | 3 | 104 (13.2%) | 99.6% | 99.6% of 685 | — | — |

**Precision, deep** — decided = confirmed / (confirmed + contradicted); the rest is not judged.

| project | calls edges | confirmed | contradicted | not judged | decided precision | exact | inferred | heuristic |
|---|---|---|---|---|---|---|---|---|
| more-itertools | 97 | 83 | 1 | 13 (13.4%) | 98.8% | 0 decided of 6 | 98.8% of 84 | — |
| click | 567 | 473 | 14 | 80 (14.1%) | 97.1% | 0 decided of 6 | 97.1% of 487 | — |
| rich | 1429 | 1023 | 42 | 364 (25.5%) | 96.1% | 0 decided of 15 | 96.1% of 1065 | — |
| markdown-it-py | 294 | 285 | 4 | 5 (1.7%) | 98.6% | — | 98.6% of 287 | 100.0% of 2 |
| jinja | 1037 | 890 | 16 | 131 (12.6%) | 98.2% | 0 decided of 14 | 98.2% of 906 | — |

**Contradicted edges whose caller entered another function of the same name** (an override, a protocol's implementation, a definition for another platform) — counted by compare.py:

| project | fast: same name / contradicted | deep: same name / contradicted |
|---|---|---|
| more-itertools | 0/0 | 0/1 |
| click | 9/11 | 12/14 |
| rich | 2/24 | 16/42 |
| markdown-it-py | 0/2 | 2/4 |
| jinja | 3/3 | 15/16 |

**Deep precision, split by whether the fast graph has the edge too** (post hoc, not pre-registered):

| project | in both: confirmed / contradicted | deep only: confirmed / contradicted | deep only: decided precision |
|---|---|---|---|
| more-itertools | 82 / 0 | 1 / 1 | 50.0% |
| click | 345 / 8 | 128 / 6 | 95.5% |
| rich | 721 / 24 | 302 / 18 | 94.4% |
| markdown-it-py | 160 / 2 | 125 / 2 | 98.4% |
| jinja | 677 / 3 | 213 / 13 | 94.2% |

**`callers()` completeness** — callees whose every runtime caller is a static caller:

| project | fast | deep |
|---|---|---|
| more-itertools | 68/74 (91.9%) | 69/74 (93.2%) |
| click | 168/357 (47.1%) | 240/357 (67.2%) |
| rich | 237/495 (47.9%) | 363/495 (73.3%) |
| markdown-it-py | 82/178 (46.1%) | 117/178 (65.7%) |
| jinja | 235/611 (38.5%) | 300/611 (49.1%) |

## C5 — every contradicted edge, read

Labels:
- **artifact.** The line ran, but the call on it could not: a conditional expression, `or`/`and` short-circuit.
- **dispatched elsewhere.** The call ran and entered another function: an override, a protocol's
  implementation, a test double, or the definition for another Python version or platform.
- **definition time.** A decorator or a default argument, executed by the enclosing scope when the definition
  runs. codemap attributes it to the function.
- **false edge.** No such call.

| project | tier | contradicted | read | artifact | dispatched elsewhere | definition time | false edge |
|---|---|---|---|---|---|---|---|
| more-itertools | fast | 0 | 0 | — | — | — | — |
| more-itertools | deep | 1 | 1 | 0 | 1 | 0 | 0 |
| click | fast | 11 | 11 | 0 | 11 | 0 | 0 |
| click | deep | 14 | 14 | 0 | 14 | 0 | 0 |
| rich | fast | 24 | 24 | 17 | 3 | 4 | 0 |
| rich | deep | 42 | 30 | 14 | 12 | 3 | 1 |
| markdown-it-py | fast | 2 | 2 | 2 | 0 | 0 | 0 |
| markdown-it-py | deep | 4 | 4 | 2 | 2 | 0 | 0 |
| jinja | fast | 3 | 3 | 0 | 3 | 0 | 0 |
| jinja | deep | 16 | 16 | 0 | 16 | 0 | 0 |

**Examples:**
- **dispatched elsewhere, overrides:** click's `Parameter.__init__ → Parameter._parse_decls` (entered
  `Option._parse_decls`), jinja's `Tuple.as_const → Expr.as_const`, markdown-it-py's
  `MarkdownIt.render → RendererProtocol.render`.
- **dispatched elsewhere, test doubles:** click's `BashComplete._check_version` and `termui.getchar`, rich's
  `SystemPager._pager`. The tests replace them.
- **dispatched elsewhere, another platform or Python:** click's `_winconsole._get_windows_console_stream`
  (Windows only; the stub in `_compat` ran); more-itertools' `_fsumprod` (`math.sumprod` on 3.12).
- **definition time:** rich's `@rich_repr()`, `@group()`, and `highlighter=ReprHighlighter()` in
  `Console.__init__`'s signature.
- **the false edge:** rich's `Text.append → Span.extend`, where `self._spans.extend(...)` is `list.extend`.

**Adjudicated precision.** Artifacts leave the denominator: the call never ran, so the edge was not judged.
There are two readings:
- *strict*: dispatched elsewhere and definition time count as false;
- *dispatch-aware*: they count as confirmed.

rich deep scales its sample of 30 to 42.

| project | fast raw | fast strict | fast dispatch-aware | deep raw | deep strict | deep dispatch-aware |
|---|---|---|---|---|---|---|
| more-itertools | 100.0% | 100.0% | 100.0% | 98.8% | 98.8% | 100.0% |
| click | 96.9% | 96.9% | 100.0% | 97.1% | 97.1% | 100.0% |
| rich | 96.8% | 99.0% | 100.0% | 96.1% | 97.9% | 99.9% |
| markdown-it-py | 98.8% | 100.0% | 100.0% | 98.6% | 99.3% | 100.0% |
| jinja | 99.6% | 99.6% | 100.0% | 98.2% | 98.2% | 100.0% |

## Misses, post hoc (not pre-registered)

[`misses_posthoc.py`](misses_posthoc.py) takes each deep miss (an explicit runtime pair codemap has no `calls`
edge for) and asks two questions:
- is the target's name at a call site in the caller's source?
- if so, does codemap point that call at another function of the same name?

| project | misses | named at a site in the caller | of them: the caller has a static edge to another function of that name | not named (variable, foreign code, protocol) |
|---|---|---|---|---|
| more-itertools | 10 | 0 (0%) | 0 | 10 (100%) |
| click | 173 | 85 (49%) | 63 | 88 (51%) |
| rich | 222 | 94 (42%) | 43 | 128 (58%) |
| markdown-it-py | 108 | 9 (8%) | 0 | 99 (92%) |
| jinja | 590 | 184 (31%) | 136 | 406 (69%) |

The fourth column is the recall side of "dispatched elsewhere": `self.get_default()` resolved to
`Parameter.get_default`, while the runtime entered `Option.get_default`. The last column is where a static graph
without the values cannot follow:
- markdown-it-py's rules held in lists;
- jinja's compiled templates calling back into the runtime (190 `external` pairs);
- callbacks.

## The predictions

| | prediction | outcome |
|---|---|---|
| H1 | `exact` decided precision ≥ 97%, every project, both tiers | **Fails raw** on click (96.9%) and rich (96.8%) fast. After C5, it fails strict on click only (96.9%: all 11 are overrides and test doubles) and holds dispatch-aware. The deep half cannot be tested: the deep tier grades nearly every edge `inferred`, leaving 0 decided `exact` edges (deviation 6). |
| H2 | `inferred` (deep) ≥ 93%, every project | **Holds** raw: 96.1–98.8%. |
| H3 | `heuristic` below `exact` and below 85% where ≥ 10 decided | **Not testable**: at most 2 decided `heuristic` edges on any project. |
| H4 | deep median in [50%, 75%]; fast median in [35%, 60%]; deep > fast on every project | **Holds**: deep median 73.2% (click), fast median 53.4% (click), deep > fast on all five (more-itertools by 1 point). |
| H5 | `external` the lowest reaching way where ≥ 10 pairs | **Fails on click**: external 15/64 (23%) against wrapper 0/9. It holds on markdown-it-py (0/14) and jinja (2/190). See surprise 3. |
| H6 | deep `callers()` completeness median ≥ 50% | **Holds**: median 67.2%; jinja 49.1% is the lowest. |
| H7 | lowest deep recall jinja or rich; highest more-itertools or click | **Holds**: jinja 60.0%, more-itertools 89.2%. |
| H8 | deep recall < 90% on every project | **Holds**, barely: more-itertools 89.2%. In run 2 it was 90.9%. |
| H9 | contradicted after adjudication < 3% of `calls` edges, every project and tier | **Holds** even strict: highest click fast, 11/429 = 2.6%. False edges alone: 1 seen in 105 read. |

## Surprises

1. **The truth was the weaker side.** Six defects were found in the runtime truth over three runs, against one
   false edge in the graph. Without C5 and C6, run 1's numbers would have been published with 33 false
   "contradictions" in more-itertools alone.
2. **Most contradictions are dispatches, a class the design did not foresee.** Precision under the design's two
   labels would have to call an override either false or an artifact, and it is neither. The third label is
   post hoc (deviation 5) and is counted mechanically by compare.py (`contradicted_same_name`). Every edge it
   counts was also labelled "dispatched elsewhere" by hand. The hand reading adds five more that a name match
   cannot see: three test doubles (click's two, rich's `SystemPager._pager`), jinja's Protocol implemented by
   a test's object, and more-itertools' C function.
3. **click's `external` pairs are mostly found (15/64), against the expectation.** After deviation 4,
   `@contextmanager` functions are seen at contextlib's call site. codemap has those calls directly, so they
   count as found `external` pairs.
4. **Deep-only edges are less precise than edges both tiers have** (post hoc). Decided precision, raw:

   | project | deep only | in both tiers |
   |---|---|---|
   | jinja | 94.2% | 99.6% |
   | rich | 94.4% | 96.8% |
   | click | 95.5% | 97.7% |
   | markdown-it-py | 98.4% | 98.8% |

   more-itertools has 2 deep-only decided edges, too few to read.
5. **Properties and implicit dunders are almost never found** (0–6 per project of up to 207). This is by design:
   codemap records attribute reads as `accesses`, not `calls`, and does not model operators. They stay out of
   the headline, as pre-registered.

## What it means for codemap

- **The call graph's edges can be trusted.** In 105 contradicted edges read across five projects codemap was
  never tuned on, one is a call that does not exist.
- **The cheapest recall left is the override.** When `obj.m()` resolves to `Base.m`, the overrides of `m` in
  `Base`'s subclasses are where the runtime goes. Edges to them, graded as an override route, would recover
  most of the fourth column above. They would also turn most "dispatched elsewhere" edges into confirmed
  ones, at a precision cost that this benchmark can measure. That is backlog item R1-C136, to be designed
  with its own pre-registration.
- **Definition-time code is a convention.** codemap attributes decorators and default arguments to the
  function they belong to. The truth attributes them to the scope that executes them. Both are defensible.
  The difference is now documented, not hidden.

## Appendix: run 2 (tracer v2)

Kept, not discarded (deviation 4). Same graphs and projects; the truth still had the three defects run 3 fixed — closures attributed by stack, call sites switched off by a foreign class or generator. Raw files: [`results/run2/`](results/run2/). Its precision has no C5 labels: its contradicted edges are where the defects were found.

| project | functions | started (C4) | explicit pairs | fast recall | deep recall | deep recall, calls or references |
|---|---|---|---|---|---|---|
| more-itertools | 265 | 96.6% | 88 | 89.8% | 90.9% | 92.0% |
| click | 483 | 84.5% | 609 | 53.5% | 71.9% | 73.4% |
| rich | 767 | 88.7% | 1231 | 58.1% | 82.0% | 88.6% |
| markdown-it-py | 215 | 89.3% | 389 | 39.6% | 70.2% | 72.8% |
| jinja | 688 | 90.8% | 1480 | 45.9% | 58.7% | 59.9% |

**Deep recall by how the pair was reached** (found / pairs):

| project | direct | nested | external | wrapper |
|---|---|---|---|---|
| more-itertools | 77/84 (91.7%) | 3/3 (100.0%) | 0/0 (—) | 0/1 (0.0%) |
| click | 425/528 (80.5%) | 13/16 (81.2%) | 0/40 (0.0%) | 0/25 (0.0%) |
| rich | 966/1165 (82.9%) | 37/49 (75.5%) | 0/4 (0.0%) | 6/13 (46.2%) |
| markdown-it-py | 272/365 (74.5%) | 1/2 (50.0%) | 0/14 (0.0%) | 0/8 (0.0%) |
| jinja | 851/1203 (70.7%) | 15/22 (68.2%) | 0/187 (0.0%) | 3/68 (4.4%) |

**Runtime pairs outside the headline** (deep found / pairs): implicit dunders, properties, decorators.

| project | implicit | property | decorator | init (behind a construction) |
|---|---|---|---|---|
| more-itertools | 0/16 | 0/5 | 0/0 | 5 |
| click | 0/44 | 0/32 | 0/0 | 54 |
| rich | 3/199 | 0/208 | 0/5 | 228 |
| markdown-it-py | 6/34 | 1/32 | 0/0 | 17 |
| jinja | 1/125 | 0/29 | 0/1 | 144 |

**Precision, fast** — decided = confirmed / (confirmed + contradicted); the rest is not judged.

| project | calls edges | confirmed | contradicted | not judged | decided precision | exact | inferred | heuristic |
|---|---|---|---|---|---|---|---|---|
| more-itertools | 95 | 79 | 3 | 13 (13.7%) | 96.3% | 96.3% of 82 | — | — |
| click | 429 | 326 | 29 | 74 (17.2%) | 91.8% | 91.8% of 355 | — | — |
| rich | 996 | 717 | 29 | 250 (25.1%) | 96.1% | 96.1% of 746 | — | — |
| markdown-it-py | 166 | 160 | 2 | 4 (2.4%) | 98.8% | 98.8% of 162 | — | — |
| jinja | 789 | 680 | 5 | 104 (13.2%) | 99.3% | 99.3% of 685 | — | — |

**Precision, deep** — decided = confirmed / (confirmed + contradicted); the rest is not judged.

| project | calls edges | confirmed | contradicted | not judged | decided precision | exact | inferred | heuristic |
|---|---|---|---|---|---|---|---|---|
| more-itertools | 97 | 80 | 4 | 13 (13.4%) | 95.2% | 0 decided of 6 | 95.2% of 84 | — |
| click | 567 | 438 | 48 | 81 (14.3%) | 90.1% | 0 decided of 6 | 90.1% of 486 | — |
| rich | 1429 | 1014 | 52 | 363 (25.4%) | 95.1% | 0 decided of 15 | 95.1% of 1066 | — |
| markdown-it-py | 294 | 280 | 9 | 5 (1.7%) | 96.9% | — | 96.9% of 287 | 100.0% of 2 |
| jinja | 1037 | 870 | 35 | 132 (12.7%) | 96.1% | 0 decided of 14 | 96.1% of 905 | — |

**`callers()` completeness** — callees whose every runtime caller is a static caller:

| project | fast | deep |
|---|---|---|
| more-itertools | 65/71 (91.5%) | 66/71 (93.0%) |
| click | 161/345 (46.7%) | 225/345 (65.2%) |
| rich | 236/492 (48.0%) | 359/492 (73.0%) |
| markdown-it-py | 82/178 (46.1%) | 112/178 (62.9%) |
| jinja | 234/609 (38.4%) | 295/609 (48.4%) |
