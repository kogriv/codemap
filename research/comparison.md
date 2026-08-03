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
| graphlens | [card](tools/graphlens.md) | ✅ | ✅¹ | ✅¹ | ✖ | ✖ | ✖ | ✅ | Py/TS/Go/Rust/PHP | MIT |
| CodeGraph (colbymchenry) | ? | ? | ? | ? | ? | ? | ? | ✅ | multi | MIT |
| GitNexus | ? | ? | ? | ? | ? | ? | ? | ✅ | multi | PolyForm NC |
| OntoIndex | ? | ? | ? | ? | ? | ? | ? | ✅ | multi | ? |
| Sentrux | ? | — | — | ? | ? | ✅ | ✅ | ✅ | 52 | ? |
| cocoindex-code | ? | ✅ | ✖ | ✖ | ✖ | ✖ | ✖ | ? | multi | Apache-2.0 |
| rag_for_git | ? | ✅ | ✅ | ◐ | ? | ? | ✖ | ✖ | ? | OSS |
| Understand-Anything | ? | ? | ? | ? | ? | ? | ? | ? | multi | OSS |

_Rows are seeded from R1/R1.5 (desk-level, hence `?`); each becomes measured as its card moves to
`hands-on`. `codemap` is the ground-truth reference for T1–T5._

¹ graphlens (v0.4.0), re-measured on the fair scope (same 6 dirs codemap indexes) **with the `ty` LSP
working**: **T1–T3 all work.** `search` finds the flagship symbol (~260 ms); `relations` returns a real
resolved call graph (`resolver_status: ok`) — on `MACDZoneAnalyzer`: 9 callers + 1 callee + 2 refs (tests
auto-excluded by design), ≈ codemap's 12 non-test refs. **Correction:** the first pass reported T2/T3
*empty*, but that was **our** environment — graphlens bundles `ty` yet resolves it via `shutil.which("ty")`,
and `uv tool install` leaves the bundled `bin/` off `PATH`, so it silently fell back to tree-sitter-only.
Fixed by putting the bundled bin on `PATH`; then indexing goes type-resolved (**2 m 20 s / 424 MB / 31 MB DB
/ 32 399 nodes / 55 691 edges**, vs the degraded **12 s / 246 MB / 17.5 MB / 16 796 nodes**). T4/T5 remain
genuinely absent (surface is only search/relations/info). (The separate > 3h45m / 9 GB / 1.1 GB catastrophe
was the venv trap — repo-root scope pulling `venv_bquant` because graphlens ignores `.gitignore`; point it at
a clean source tree.) See the [card](tools/graphlens.md).

## Quality summary

Filled per axis (accuracy · determinism · cost · speed · setup · languages · license · interface ·
honesty) as cards complete. See each card's Quality section for detail.

| Tool | Standout strength | Standout weakness | Verdict | Feeds |
|---|---|---|---|---|
| graphlens | working type-resolved impact (≈codemap non-test); resolves into deps; 5 languages; minimalist 3-verb MCP; smart test-de-emphasis | no arch/sig-change tools (no T4/T5); non-deterministic DB; **`ty`-on-PATH gotcha** silently degrades impact; venv-scoping trap; 12× index cost | learn (competent peer) | R1-C13, R1-C14 |

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
