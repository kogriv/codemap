# research

Survey of adjacent code-analysis / code-graph tools and how **codemap** should relate to each —
**integrate** (call it), **wrap** (thin adapter / export target), or **learn-only** (borrow the idea,
don't take the dependency). Grounded in a working baseline: codemap's core (deterministic graph +
warm serve + MCP) is done, so the comparison measures against a real tool, not a plan.

**Status:** 🟢 active (opened 2026-08-02). Tracked as **R1** in [../BACKLOG.md](../BACKLOG.md).

## codemap's positioning axes

Every tool below is placed against the stance codemap commits to:

- **source-only** — parses source (griffe + jedi), never builds or runs the target
- **deterministic** — canonical `graph.json`: sorted, timestamp-free, byte-stable across runs
- **CLI-AI-first** — JSON by default; warm serve + MCP so an AI agent drives it natively
- **graph-model** — nodes/edges with provenance (which root: package / tests / docs), canonical ids
- **Python-focused** — one language done well (multi-language is a deferred door)
- **local / offline** — no service, no cloud, no account

## Reports

| # | Report | Category |
|---|--------|----------|
| R1.0 | [00_landscape.md](00_landscape.md) | The map: categories, positioning, comparison matrix, integrate/wrap/learn verdicts |
| R1.1 | [01_ai_context_repomap.md](01_ai_context_repomap.md) | AI-context / repo-map tools (aider repo-map, Cursor, Continue, Cody) — direct AI-first peers |
| R1.2 | [02_codegraph_index_infra.md](02_codegraph_index_infra.md) | Code-graph / semantic-index infra & interchange (SCIP, LSIF, Kythe, Glean, Stack Graphs, ctags) |
| R1.3 | [03_query_dataflow_engines.md](03_query_dataflow_engines.md) | Query / dataflow / structural-search (CodeQL, Semgrep, ast-grep, tree-sitter, PyCG) |
| R1.4 | [04_python_graph_arch_peers.md](04_python_graph_arch_peers.md) | Python graph / dependency / architecture peers (pydeps, pyan, grimp, import-linter, vulture, radon) |

## Method

Each report states, per tool: what it does, its data model, source-only vs needs-build, determinism,
interface, license/maintenance, and a one-line **verdict for codemap**. Findings do not become features
directly — each promising idea returns to [../BACKLOG.md](../BACKLOG.md) and the
[axis register](../gaps/dogfood_axes.md) as a concrete, use-driven capability.
