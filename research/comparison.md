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
| graphlens | [card](tools/graphlens.md) | ? | ? | ? | ? | ? | ?¹ | ✅ | Py/TS/Go/Rust/PHP | MIT |
| CodeGraph (colbymchenry) | ? | ? | ? | ? | ? | ? | ? | ✅ | multi | MIT |
| GitNexus | ? | ? | ? | ? | ? | ? | ? | ✅ | multi | PolyForm NC |
| OntoIndex | ? | ? | ? | ? | ? | ? | ? | ✅ | multi | ? |
| Sentrux | ? | — | — | ? | ? | ✅ | ✅ | ✅ | 52 | ? |
| cocoindex-code | ? | ✅ | ✖ | ✖ | ✖ | ✖ | ✖ | ? | multi | Apache-2.0 |
| rag_for_git | ? | ✅ | ✅ | ◐ | ? | ? | ✖ | ✖ | ? | OSS |
| Understand-Anything | ? | ? | ? | ? | ? | ? | ? | ? | multi | OSS |

_Rows are seeded from R1/R1.5 (desk-level, hence `?`); each becomes measured as its card moves to
`hands-on`. `codemap` is the ground-truth reference for T1–T5._

¹ graphlens (v0.4.0): T1–T5 pending a **correctly-scoped** re-run. First hands-on attempt indexed the whole
repo including a 1.5 GB / 16k-file virtualenv (`venv_bquant`) — it **ignores `.gitignore`** and excludes
venvs only by hardcoded exact names (`.venv`/`venv`), so a non-standard venv name slips through
(> 3h45m, ~9 GB RAM, DNF). Workaround: point it at a clean source tree / the package dir. See the
[card](tools/graphlens.md).

## Quality summary

Filled per axis (accuracy · determinism · cost · speed · setup · languages · license · interface ·
honesty) as cards complete. See each card's Quality section for detail.

| Tool | Standout strength | Standout weakness | Verdict | Feeds |
|---|---|---|---|---|
| _(populated as cards land)_ | | | | |

## Where codemap is not closed

Running list of gaps surfaced by the разбор — capabilities peers have that codemap lacks, each linked to a
backlog candidate. Populated as cards complete.

- **Cross-boundary resolution into dependencies** — graphlens resolves calls *into* third-party libs
  (e.g. "what pandas API does bquant call"); codemap is source-only-of-target and does not. By design, but
  logged as a possible capability door. ([graphlens card](tools/graphlens.md))

## Notes for codemap's own positioning (differentiators, measured)

- **Layout robustness** — codemap takes the package dir explicitly and never wanders into a venv/deps;
  graphlens indexed a 1.5 GB non-standard venv because it ignores `.gitignore` and matches venv names by a
  hardcoded list. codemap's "point at the package" model sidesteps this class of failure. (→ R1-C14)
- **Determinism & artifact size** — codemap: ~4.8 MB canonical, diffable JSON, ~1 min. graphlens: a SQLite
  DB (non-diffable), and on a clean scope TBD but heavier by construction (LSP-grade `ty`). (→ R1-C14)
