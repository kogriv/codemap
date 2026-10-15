# CodeGraph after its release — re-measuring the published figures

**Status:** pre-registered (2026-10-15), before any run of 1.6.x on the tree. §7 is the reconciliation.
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
