# comparison — codemap vs the field

The rolled-up view of the R2 deep-dive: coverage matrix (tools × capabilities) and quality summary, built
from the per-tool cards in [tools/](tools/). Method & convention: [README.md](README.md). Desk-level rows
come from R1; hands-on rows are filled as each card is measured on the common target (bquant).

**Legend:** ✅ yes · ◐ partial · ✖ no · ? not yet measured · — N/A.
**Card status:** `desk` = from R1 survey · `hands-on` = installed & measured on bquant.

## Coverage matrix

| Tool | Card | T1 defs | T2 callers | T3 impact | T4 sig-change | T5 arch | Determ. | MCP | Langs | License |
|---|---|---|---|---|---|---|---|---|---|---|
| **codemap** | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Py | MIT |
| graphlens | ? | ? | ? | ? | ? | ? | ? | ✅ | Py/TS/Go/Rust/PHP | MIT |
| CodeGraph (colbymchenry) | ? | ? | ? | ? | ? | ? | ? | ✅ | multi | MIT |
| GitNexus | ? | ? | ? | ? | ? | ? | ? | ✅ | multi | PolyForm NC |
| OntoIndex | ? | ? | ? | ? | ? | ? | ? | ✅ | multi | ? |
| Sentrux | ? | — | — | ? | ? | ✅ | ✅ | ✅ | 52 | ? |
| cocoindex-code | ? | ✅ | ✖ | ✖ | ✖ | ✖ | ✖ | ? | multi | Apache-2.0 |
| rag_for_git | ? | ✅ | ✅ | ◐ | ? | ? | ✖ | ✖ | ? | OSS |
| Understand-Anything | ? | ? | ? | ? | ? | ? | ? | ? | multi | OSS |

_Rows are seeded from R1/R1.5 (desk-level, hence `?`); each becomes measured as its card moves to
`hands-on`. `codemap` is the ground-truth reference for T1–T5._

## Quality summary

Filled per axis (accuracy · determinism · cost · speed · setup · languages · license · interface ·
honesty) as cards complete. See each card's Quality section for detail.

| Tool | Standout strength | Standout weakness | Verdict | Feeds |
|---|---|---|---|---|
| _(populated as cards land)_ | | | | |

## Where codemap is not closed

Running list of gaps surfaced by the разбор — capabilities peers have that codemap lacks, each linked to a
backlog candidate. Populated as cards complete.

- _(none confirmed hands-on yet)_
