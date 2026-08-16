# research

Survey of adjacent code-analysis / code-graph tools and how **codemap** should relate to each —
**integrate** (call it), **wrap** (thin adapter / export target), or **learn-only** (borrow the idea,
don't take the dependency). Grounded in a working baseline: codemap's core (deterministic graph +
warm serve + MCP) is done, so the comparison measures against a real tool, not a plan.

**Status:** 🟢 active. **R1** — landscape survey (done). **R2** — per-tool deep-dive разбор + hands-on
validation on a common target (in progress). Tracked in [../BACKLOG.md](../BACKLOG.md).

## codemap's positioning axes

Every tool below is placed against the stance codemap commits to:

- **source-only** — parses source (griffe + jedi), never builds or runs the target
- **deterministic** — canonical `graph.json`: sorted, timestamp-free, byte-stable across runs
- **CLI-AI-first** — JSON by default; warm serve + MCP so an AI agent drives it natively
- **graph-model** — nodes/edges with provenance (which root: package / tests / docs), canonical ids
- **Python-focused** — one language done well (multi-language is a deferred door)
- **local / offline** — no service, no cloud, no account

## R1 — Landscape survey (done)

| # | Report | Category |
|---|--------|----------|
| R1.0 | [00_landscape.md](00_landscape.md) | The map: categories, positioning, comparison matrix, integrate/wrap/learn verdicts |
| R1.1 | [01_ai_context_repomap.md](01_ai_context_repomap.md) | AI-context / repo-map tools (aider repo-map, Cursor, Continue, Cody) |
| R1.2 | [02_codegraph_index_infra.md](02_codegraph_index_infra.md) | Code-graph / semantic-index infra & interchange (SCIP, LSIF, Kythe, Glean, ctags) |
| R1.3 | [03_query_dataflow_engines.md](03_query_dataflow_engines.md) | Query / dataflow / structural-search (CodeQL, Semgrep, ast-grep, tree-sitter, PyCG) |
| R1.4 | [04_python_graph_arch_peers.md](04_python_graph_arch_peers.md) | Python graph / dependency / architecture peers (pydeps, grimp, import-linter, vulture, radon) |
| R1.5 | [05_curated_sources.md](05_curated_sources.md) | Field intake — curated Telegram posts (live competitor roster + grep-vs-graph benchmark) |

R1 method: per tool — what it does, data model, source-only vs needs-build, determinism, interface,
license/maintenance, one-line verdict. Desk-level; grounded but not hands-on.

## R2 — Deep-dive разбор (per-tool, hands-on)

R1 mapped the field top-down. R2 goes tool-by-tool with a **hands-on measurement on a common target**,
producing one **card** per tool in [`tools/`](tools/) and a rolled-up [comparison.md](comparison.md)
(coverage matrix + quality summary). This is where "does it actually work, and how does it stack up
against codemap" gets answered with numbers, not adjectives.

- **[comparison.md](comparison.md)** — the hub: coverage matrix (tools × capabilities) + quality summary + verdicts.
- **[tools/](tools/)** — one card per tool; template + rules in [tools/README.md](tools/README.md).
  Measured hands-on so far: [graphlens](tools/graphlens.md), [GitNexus](tools/gitnexus.md),
  [cocoindex-code](tools/cocoindex-code.md) — all on the shared R2 scope ([tools/_scope/](tools/_scope/)).
- **[positioning.md](positioning.md)** — the *publication layer*: article-ready build-story + positioning,
  distilled from the cards (realizes R1-C14). Story Zero (codemap + roadmap) + one build-story per notable
  разбор. Facts live in the cards; this narrates them.

### The разбор convention (codemap-native)

Adapted from the tgsh project's "разбор чужих реализаций" convention, retuned for a code-graph tool
(measurement- and coverage-first). Principles kept from tgsh: разбор happens *before* building the matching
capability; we come with **measurements, not a verdict** (tool authors are potential collaborators, not
review targets); license care (read/learn freely, never copy code without a license).

**When.** Do a tool's card *before* building the codemap capability it overlaps (R1-C…). Not after —
otherwise the разбор becomes a justification of what we already shipped.

**Common target & task-set (so cards are comparable).** Every hands-on run uses the same target — the
**bquant** package (codemap's dogfood target) — and the same five questions, with codemap's own answer as
the ground-truth reference:

| # | Task | Probe symbol (bquant) |
|---|------|-----------------------|
| T1 | Where is X defined? | `analyze_zones` |
| T2 | Callers / callees of X | `MACDZoneAnalyzer` |
| T3 | Impact / blast-radius of X | `MACDZoneAnalyzer` |
| T4 | What breaks if the signature of X changes? | `analyze_zones` |
| T5 | Architecture: layers / cycles | whole package |

Per task record: **correct?** (vs codemap ground truth / manual check), **cost** (tokens or tool-calls),
**latency**, **deterministic?** (same output on a re-run). Tasks a tool structurally can't do → mark N/A
in the coverage matrix (that *is* the finding).

**Quality axes** (scored on the covered part): accuracy · determinism · cost (tokens/tool-calls) · speed ·
setup friction · language coverage · license · interface (CLI / MCP / lib) · honesty of the tool's own claims.

**What each card records** (see [tools/README.md](tools/README.md) for the fill-in template):
identity (link / license / last commit / stack / install) · what it is (mechanism, data model) ·
coverage vs codemap (matrix row + notes) · hands-on measurements (the task-set, with numbers) ·
quality per axis · **what we'd take · what we'd do differently and why · what the author knows that we
didn't · what we did NOT check** (the honest boundary) · verdict (integrate / wrap / learn) + the backlog
effect (which R1-C it feeds).

**Don'ts.** Don't assess a tool without running it when it's runnable ("looks grey" is not a measurement).
Don't copy code from an unlicensed repo. Don't publish a criticism of someone's code without being ready
to show the author first. Record exact versions / commit hashes / commands so every number reproduces.

**Output back to the roadmap.** Findings don't become features directly — each returns to
[../BACKLOG.md](../BACKLOG.md) as a concrete, use-driven capability (a gap codemap should close, or an
external tool to integrate/wrap); the raw comparison lives in the cards + comparison hub, and the
article-ready **build story** is distilled into [positioning.md](positioning.md).
