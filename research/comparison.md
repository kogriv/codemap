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
| graphlens | [card](tools/graphlens.md) | ✅ | ✖¹ | ✖¹ | ✖ | ✖ | ✖ | ✅ | Py/TS/Go/Rust/PHP | MIT |
| CodeGraph (colbymchenry) | ? | ? | ? | ? | ? | ? | ? | ✅ | multi | MIT |
| GitNexus | ? | ? | ? | ? | ? | ? | ? | ✅ | multi | PolyForm NC |
| OntoIndex | ? | ? | ? | ? | ? | ? | ? | ✅ | multi | ? |
| Sentrux | ? | — | — | ? | ? | ✅ | ✅ | ✅ | 52 | ? |
| cocoindex-code | ? | ✅ | ✖ | ✖ | ✖ | ✖ | ✖ | ? | multi | Apache-2.0 |
| rag_for_git | ? | ✅ | ✅ | ◐ | ? | ? | ✖ | ✖ | ? | OSS |
| Understand-Anything | ? | ? | ? | ? | ? | ? | ? | ? | multi | OSS |

_Rows are seeded from R1/R1.5 (desk-level, hence `?`); each becomes measured as its card moves to
`hands-on`. `codemap` is the ground-truth reference for T1–T5._

¹ graphlens (v0.4.0), measured on the fair scope (same 6 dirs codemap indexes): **T1 `search` works**
(~260 ms, finds the flagship symbol), but **T2/T3 `relations` returned empty** (0 callers/refs vs codemap's
68) — its `ty` LSP resolver failed to initialize in this env (`resolver_status: degraded`); T4/T5 have **no
tool at all** (surface is only search/relations/info). Indexing the fair scope: **12 s / 246 MB / 17.5 MB DB /
16 796 nodes**. (The earlier > 3h45m / 9 GB / 1.1 GB run was the *misconfigured* repo-root scope: graphlens
**ignores `.gitignore`** and excludes venvs only by hardcoded names, so the non-standard `venv_bquant`
1.5 GB / 16k-file venv got pulled in. Workaround: point it at a clean source tree.) See the
[card](tools/graphlens.md).

## Quality summary

Filled per axis (accuracy · determinism · cost · speed · setup · languages · license · interface ·
honesty) as cards complete. See each card's Quality section for detail.

| Tool | Standout strength | Standout weakness | Verdict | Feeds |
|---|---|---|---|---|
| graphlens | 5 languages; resolves into deps (when ty works); minimalist 3-verb MCP | impact empty out-of-box (ty LSP fragile); no arch/sig-change tools; non-deterministic 1 GB-capable DB; venv-scoping trap | learn-only | R1-C13, R1-C14 |

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
