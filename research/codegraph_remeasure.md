# CodeGraph after its release — re-measuring the published figures

**Status:** ✅ measured (2026-10-15). §0–§6 pre-registered in `6f38c07` before any run of 1.6.x on the tree; §7 is the reconciliation.
**Backlog:** R2-codegraph. **Card:** [`tools/codegraph.md`](tools/codegraph.md).
**Harness:** [`bench/codegraph_remeasure.py`](bench/codegraph_remeasure.py).

## 0. Why now

Every CodeGraph figure this project publishes describes **1.6.0**: 136 reported cycles where 41 are real
(precision 10 %, recall 32 %), silent truncation of `callers` at `--limit 20`, and a two-file Python repro
in which a one-way import becomes a cycle. Those figures are quoted in the codemap README,
`docs/whole-graph-questions.md`, blog post 06 (both languages), `comparison.md`, `positioning.md`,
`00_landscape.md` and the R1-C29 gap. The author fixed both defects we reported on 2026-09-08
(PR #1772 — truncation; PR #1790 — built-in receivers; plus #1748 and #1749 for the Python shapes).

**1.6.1 (2026-09-29) and 1.6.2 (2026-10-03) are released.** Checked before writing this: the merge
commits of #1772, #1790, #1748 and #1749 are all ancestors of both tags (GitHub compare: `ahead`). We
noticed the release twelve days late, at a backlog review — the obligation was written down, but nothing
watched for the condition. Publishing a fixed defect's numbers is the offence we described in their
truncation, so the measurement comes before any further quoting.

## 1. What is measured

Same input as the card: the R2 scope, `scope_id sha256:300e0a01…5e47d2`, bquant@cb89a24, 280 files,
materialized into a staging tree (`materialize.py`, verify `== canonical ✓` — already run when this was
written: the tree had to exist to install nothing into it; no tool has touched it).

| # | what | how |
|---|---|---|
| M0 | index shape | `codegraph init -y`, then `status --json`: files, nodes, edges |
| M1 | cycle finder | library `CodeGraph.open(tree).findCircularDependencies()` |
| M2 | truncation | `callers <sym> --json` at the default limit and at `--limit 500`, five symbols from the card |
| M3 | the two-file repro | the exact files from our [#1566 comment](https://github.com/colbymchenry/codegraph/issues/1566#issuecomment-5451387031) |
| M4 | the six false edges | `calls` edges from `bquant/core/config.py` into `get` defined in `bquant/core/cache.py`, read from their DB |

**Scoring M1, fixed now.** Truth = every elementary cycle of the module import graph of `bquant/` with
**every** intra-package import counted — function-local and `TYPE_CHECKING` included — enumerated with
`networkx.simple_cycles` over `imports` edges from a codemap fast build of the same tree. A reported
cycle is **true** if its set of `bquant/*.py` modules equals the node set of a truth cycle; a cycle
through any file outside `bquant/` is false. Reported: `precision = true reported / reported`,
`recall = distinct truth sets hit / |truth|`. This is the rule the card's 13-of-41 was scored by
(set equality, R1-C29 gap §3–§4); C2 checks that the re-implementation reproduces it.

**Both versions run through the same harness** on separate copies of the same staging, 1.6.0 first as
the control. 1.6.1 is not measured: the figures to correct are 1.6.0's, the reader installs 1.6.2.
Telemetry off (`DO_NOT_TRACK=1`); `codegraph install` is never run.

## 2. Controls — must hold, or the comparison is void

- **C1 — the input.** Staging `scope_id` equals canonical (done, ✓) and both work copies are byte-copies
  of it.
- **C2 — the old numbers reproduce.** 1.6.0 through this harness gives the card's figures: 5 113 nodes /
  15 247 edges; **136** cycles, **13** of the 41 truth sets; `callers MACDZoneAnalyzer` 20 at the default
  and 79 at `--limit 500`, with no total or truncation field in the JSON. If C2 fails, the harness is not
  the card's measurement and no 1.6.2 number is published as a correction.
- **C3 — the truth reproduces.** The truth set has **41** cycles. (Measured with codemap 0.0.22, not the
  build that first counted 41; a different count is reported and the scoring uses what is measured.)
- **C4 — the repro reproduces.** 1.6.0 reports `[["cache.py","settings.py"]]` on M3.
- **C5 — telemetry off.** `codegraph telemetry` reports disabled under `DO_NOT_TRACK=1` for both versions.

## 3. Predictions for 1.6.2

Written from the merged PRs' descriptions, not from a run. Each can fail.

- **P1** — fewer cycles than 136.
- **P2** — precision above 10 %.
- **P3** — the `core/config.py ⇄ core/cache.py` cycle is not reported.
- **P4** — none of the six M4 edges into `MemoryCache.get` remains. (Weakest: `#1790` names `Map`; the
  Python shapes are `#1748` call-result receivers and a subscript receiver `MAPPING[k].get(…)`, which no
  PR title names. Recorded as a prediction to see which half holds.)
- **P5** — M3: no cycle on the two-file repro.
- **P6** — M2: the JSON of a cut answer says so (a total or a truncation field) for all five symbols, and
  the human header no longer prints the cut length as the count.

**No prediction on recall.** Fewer false call edges can also remove the ones that found true cycles —
the mechanism that gave them 32 % was the one being fixed. Measured and reported either way.

**At least one expectation fails if nothing changed:** if 1.6.2 behaves as 1.6.0, P1, P3, P5 and P6 fail.

## 4. Decision rules

- **R1 — C2 fails:** stop; report the harness gap; nothing published changes.
- **R2 — C2 holds:** every place that quotes the 1.6.0 figures gets a dated line naming the version
  they describe and the 1.6.2 figure beside it. Old numbers are **not rewritten** — they were true of
  the release measured, and blog posts are not edited beyond an update note. The card gets a 1.6.2
  section; `comparison.md` its version column.
- **R3 — P5 or P1 holds:** one comment to the author on #1566 with the before/after, as the backlog item
  promised — and the correction we owe him: our comment there said the tree has **1** genuine cycle;
  the next day's audit found **41** (R1-C29). Nothing else is asked.
- **R4 — a prediction fails:** reported as measured, no re-run with a different scoring rule.

## 5. What this does not check

T1/T3/T4 of the card, speed, the watcher, determinism, MCP, any language other than Python, any other
tree. Those figures stay labelled 1.6.0.

## 6. Surprises

Anything not listed above is reported in §7 as a surprise, not folded into a prediction.

## 7. Reconciliation (2026-10-15)

Raw results: [`bench/codegraph_remeasure_results.json`](bench/codegraph_remeasure_results.json) (truth
set, both versions, every reported cycle). Pre-registration commit: `6f38c07`.

| | 1.6.0 (control) | 1.6.2 |
|---|---:|---:|
| files / nodes / edges | 207 / 5 113 / 15 247 | 207 / 5 113 / **14 801** |
| cycles reported | 136 | **25** |
| of them true (set equal to a truth cycle) | 13 | **16** |
| truth sets hit, of 45 | 13 | **16** |
| precision | 9.6 % | **64 %** |
| recall | 28.9 % | **35.6 %** |
| `config.py ⇄ cache.py` reported | yes | **no** |
| M4: `calls` config.py → `MemoryCache::get` | 6 | **0** |
| M3: two-file repro | `[["cache.py","settings.py"]]` | **`[]`** |
| `callers MACDZoneAnalyzer`, default | 20, no total | **20, `total: 79`, `truncated: true`** |
| human header | `Callers of "MACDZoneAnalyzer" (20):` | **`(20 of 79):`** |

### Controls

- **C1 — held.** Staging `== canonical ✓`; both work trees are copies of it.
- **C2 — held, to the row.** 1.6.0 through this harness: 5 113 / 15 247; 136 cycles, 13 true; the five
  truncation rows of the card exactly (20 → 79, 20 → 62, 20 → 51, 20 → 72, 20 → 104), JSON `{symbol,
  callers}` with no total.
- **C3 — failed, and the failure is ours, in published figures.** The truth set on the scope tree has
  **45** cycles, not 41. Traced: codmap **0.0.4** from PyPI (the first release with R1-C29) on the same
  staging gives the same 266 import edges and 1 eager + 44 lazy = **45**, set-equal to the enumeration;
  the edge set of 0.0.22 differs from 0.0.4's by one edge's scope (`zones.cache → zones.pipeline` is now
  `type_checking`), not by an edge. **41 was counted on bquant@f4992d7** — the live tree on 2026-08-28,
  54 commits after the scope commit cb89a24 (88 modules, 276 import edges, 41 cycles: reproduced). The
  R1-C29 gap measured the live tree; the CodeGraph card then scored a cycle list from **cb89a24** against
  it. So the published 1.6.0 recall was **28.9 %, not 32 %**; precision 9.6 % rounds to the 10 % that
  was published; codemap's own "before" row is 1 of 45 (2.2 %), not 1 of 41 (2.4 %); and the "after
  R1-C29" row on this tree is 45 of 45.
- **C4 — held.** 1.6.0 reports `[["cache.py","settings.py"]]` on the repro.
- **C5 — held.** Both versions: `Telemetry: disabled (DO_NOT_TRACK environment variable)`.

### Predictions

- **P1 — held.** 136 → 25.
- **P2 — held.** 9.6 % → 64 %.
- **P3 — held.** The `core/config ⇄ core/cache` cycle is gone.
- **P4 — held, both halves.** All six edges are gone, the subscript receiver (`MAPPING[k].get(…)`,
  config.py:315) as well as the call-result ones. The weak half was wrong to be weak.
- **P5 — held.** The two-file repro reports no cycle.
- **P6 — held.** All five cut answers carry `total` and `truncated: true`, plus `limit`, `ambiguous`,
  `aggregation`; the human header prints `20 of 79`.
- **Recall (no prediction):** 13 → 16 of 45. **No truth set lost**; three gained
  (`analysis ⇄ analysis.statistical`; `zones.strategies.registry → core.config → core.logging_config`;
  `indicators.base ⇄ indicators.custom.macd`).

Decision rules: C2 held → **R2** applies (every quote site gets the version and the 1.6.2 figure).
P1 and P5 held → **R3** applies (one comment on #1566, with the correction owed). No prediction failed.

### Surprises

- **S1 — C3 above.** The largest finding of the run is about us: a truth set from a different commit,
  published in the README, `docs/whole-graph-questions.md`, the card, the R1-C29 gap, post 06 (both
  languages), `positioning.md` and `00_landscape.md`. Nothing in any of them named the commit the 41
  came from, which is why it survived seven weeks: the tables looked like one measurement.
- **S2 — the nine false cycles of 1.6.2, classified one by one** (the 1.6.0 card sampled six edges):
  - **5** route through `research/notebooks/02_ind_types.py`: `from scipy import stats` in five package
    modules is bound to a module-level variable `stats = …` in that notebook — an **external import
    resolved to a same-named project symbol**. 4 such edges in 1.6.0, 5 in 1.6.2. This is the Python
    sibling of their closed **#2101** (TypeScript: `import { app } from "electron"` → local `App`) and of
    the open #2491 (`node:` built-ins); no Python report of it was found in their tracker. **Not filed** —
    reporting it is the owner's call.
  - **2** route through `zone.to_dict()` in `sequence_analysis.py`, where `zone` is a `ZoneFeatures`
    (guarded by `isinstance`), bound to `Zone::to_dict` in `zones/__init__.py` — a name match between
    two **project** classes, which the built-in guard of #1790 is not meant to catch.
  - **2 are real runtime dependencies the truth cannot see.** `zones.models → visualization.zones` goes
    through `import_module(...)` + `getattr(…, 'ZoneVisualizer')` — no import statement exists, and
    `visualization.zones` imports `models` back. `indicators.macd → zones.pipeline` is a lazy
    `from bquant.analysis.zones import analyze_zones`: the truth has the cycle through the package
    `analysis.zones`, CodeGraph attributes it to the defining module `pipeline`, so the node sets differ.
    Scored false by the pre-registered rule and left so (R4); read as "runtime dependency cycles",
    precision would be 18 / 25.
- **S3 — the answer gained a kind of caller.** `analyze_zones` and `get_logger` now list `variable`
  callers (24 and 56), so their totals grew (72 → 95, 104 → 160); the three class symbols are unchanged
  (79, 62, 51). `analyze_zones` reports `ambiguous: true` with "2 distinct definitions (narrow with
  --file)". The card's T1 line "ambiguity is never flagged" was about `query`, which was not re-run, so
  it stays labelled 1.6.0 — but on `callers` it is now flagged.
- **S4 — our own harness double-counted rows on the first run.** 1.6.2 repeats the top-level `callers`
  inside `definitions[].callers`; counting both gave 40 for 20. Fixed before this reconciliation (the
  top-level list wins); the scalars (`total`, `truncated`) and the M1 scoring were never affected.
- **S5 — release watch.** The re-measure obligation sat in the backlog for 12 days past the release
  because nothing checks npm. Recorded, not fixed: a watcher for one peer is not worth a mechanism.

### What this does not establish

Everything in §5, plus: 1.6.1 alone; whether the 2 project-class `to_dict` edges are a pattern beyond
this tree; precision of `findDeadCode()`; T2's symbol-level caller set for `MACDZoneAnalyzer` beyond its
count (79, same as 1.6.0 — not compared row by row).
