# codemap

**A static analyzer that turns a Python package's source into a queryable code graph.**
It reads source only — no runtime import — so it works on any package and stays decoupled from
the code it analyzes. One canonical, deterministic graph store → many renders: API surface,
dependency/architecture audit, RAG chunks, an Obsidian vault, mermaid diagrams, change-set review,
and a **SCIP index** for interop with Sourcegraph / Glean and other precise-code-intelligence tools.

**Status:** 🟢 M0–M19.A implemented + research track (R1/R2) — schema 0.11, **369 tests green** (+ a SCIP-CLI
check that runs when the `scip` binary is present), warm serve surface with 29 ops (26 exposed as MCP tools),
and SCIP export. See **[DESIGN.md](DESIGN.md)** (product design &
v1 boundaries), **[BACKLOG.md](BACKLOG.md)** (roadmap), and **[research/](research/)** (tool landscape).

## Why it exists

Docs describe code and CLIs call code; without a parsed map of the code both are done blind. codemap
builds that map as **facts**: modules, classes, functions, the public API surface, import/inherit/
export edges, best-effort call edges, registry-family `implements` links, string-key column dataflow,
and per-call argument contracts — then answers questions over it.

Design principles: **source-only** (static `ast`/`griffe`, never imports the target), **deterministic**
(canonical sorted JSON, no timestamps — diffable), **CLI-AI-first** (JSON by default, stable exit
codes), **honest** (approximations are labeled, not hidden).

## Install

```bash
# with uv (recommended)
uv venv && uv pip install -e .

# or plain pip
pip install -e .

# optional: MCP server (`codemap serve --mcp`)
pip install -e '.[mcp]'

# optional: SCIP export (`codemap export scip`)
pip install -e '.[scip]'
```

Dependencies: `griffe` (structure), `networkx` (query backend), `jedi` (deep call resolution).
Optional extras: `mcp` (Model Context Protocol server), `scip` (protobuf, for SCIP export).

## Quickstart

```bash
# build the canonical graph of a package
codemap build ./yourpkg -o graph.json

# repo-scoped: add consumers (tests/examples) + docs for blast-radius/impact
codemap build ./yourpkg --deep --mode full --consumer ./tests --docs ./docs -o graph.json

# ask about a symbol (JSON by default; --format text for humans)
codemap query analyze_zones --graph graph.json

# reports over the graph
codemap report architecture   --graph graph.json   # layers, coupling, god-objects, cycles
codemap report dependencies   --graph graph.json
codemap report dead-code      --graph graph.json
codemap report impact --symbol MyClass --graph graph.json

# change-set review straight from a diff → risk-sorted dossier
git diff | codemap review - --graph graph.json

# exports (see docs/export.md)
codemap export rag     --graph graph.json -o chunks.jsonl
codemap export mermaid --graph graph.json --mkind class
codemap export vault   --graph graph.json -o vault/
codemap export scip    --graph graph.json -o index.scip   # SCIP index (needs [scip] extra)
codemap export ctags   --graph graph.json -o tags         # universal-ctags tags file

# semantic (concept) search via an opt-in adapter → codemap symbols (needs the tool + opt-in)
codemap semantic "detect swing pivots" --build ./pkg --root pkg

# token-budgeted context pack — most relevant graph slice under N tokens (ranked; --seed to focus)
codemap pack --graph graph.json --budget 2000 --seed analyze_zones

# warm resident process — JSON requests over stdin/stdout (29 ops)
codemap serve --graph graph.json --source-root .

# …or expose the same surface as MCP tools for an AI-agent host (needs [mcp] extra)
codemap serve --graph graph.json --source-root . --mcp
```

## What it answers

- **Structure & API** — public surface, signatures, docstrings, deprecation.
- **Dependencies & architecture** — import cycles, layers + direction/violations, coupling
  (Ca/Ce/instability), god-objects & call-hubs, per-function complexity (cyclomatic / MI)
  blended with structural coupling.
- **Impact / blast radius** — who uses X, across the whole repo (core + tests + docs).
- **Change review** — a diff → the symbols it touches, their callers, signature-change surface,
  touched columns, cross-root consumers, risk rank.
- **Dispatch seams** — registry/factory families and the Protocol each impl satisfies.
- **Dataflow** — producers/consumers of a string-keyed DataFrame column.
- **Semantic search** (opt-in) — a concept query routed to an external adapter, with each fuzzy hit
  resolved to the exact codemap symbol at its location (`codemap semantic`). See [docs/integrations.md](docs/integrations.md).
- **Context pack** — the most relevant slice of the graph under a token budget, ranked by importance or
  by relevance to seed symbols (`codemap pack --budget N [--seed X]`). See [docs/pack.md](docs/pack.md).
- **Interop** — export the graph as a [SCIP](https://scip-code.org/) index (definitions + symbol
  info + inherits/implements relationships) so Sourcegraph, Glean and other SCIP consumers can drive
  go-to-definition, symbol search and type hierarchy over it. See [docs/export.md](docs/export.md).

## How it compares

codemap is **the precise structural leg for index-free AI agents** — it complements embeddings-RAG and
Repomix-style packing rather than competing with them. Its bet is to be the best *deterministic, diffable,
provenance-aware* graph in that slot, and to interoperate outward (SCIP, ctags) instead of locking the graph
away.

> **A code graph an agent can trust: source-only, deterministic, diffable — no index to go stale, no LSP to provision.**

The [research track](research/) measures this against the field hands-on, on a shared benchmark scope. The
[positioning doc](research/positioning.md) is the publication layer — the narrative and the numbers behind the
claims above; [comparison.md](research/comparison.md) is the coverage matrix that backs them.

Honesty is part of the bet: the call graph is a **measured lower bound**, not a guess. [docs/accuracy.md](docs/accuracy.md)
reports it — 100% precision / 100% decidable-recall on a hand-labeled suite, an openly-stated ~60% recall
against *all* true edges (the price of Python's dynamism), and a grep-vs-graph proof that the graph is ~2×
cheaper than grep for impact on unique names, tens of × on polymorphic ones, and no cheaper for locating a
symbol.

## Dogfooding

codemap is validated end-to-end against a real external package. Place a target repo as a sibling and
run the full flow against its package — e.g. `codemap build ../bquant/bquant` (point at the package
directory that holds `__init__.py`, not the repo root) — treating codemap purely as a third-party tool.
The `gaps/` directory records those dogfood runs: each is a pre-registered set of hypotheses, a run on
the live graph, findings, and the milestone that closed them.

## Documentation

- **[DESIGN.md](DESIGN.md)** — product design, the query catalog, v1 boundaries.
- **[docs/export.md](docs/export.md)** — export recipes: RAG, mermaid, Obsidian vault, SCIP + ctags interop.
- **[docs/accuracy.md](docs/accuracy.md)** — measured call-graph accuracy, the honest static ceiling, and
  the grep-vs-graph value proof (both harnesses guarded in CI).
- **[docs/architecture-contracts.md](docs/architecture-contracts.md)** — declare the intended architecture
  in `codemap.toml` and enforce it with `codemap check` (CI gate; codemap dogfoods its own).
- **[docs/api-diff.md](docs/api-diff.md)** — `codemap diff` two snapshots for added/removed/changed symbols
  and API breaking-change detection (release gate + `review --base`).
- **[docs/integrations.md](docs/integrations.md)** — the opt-in router/adapter layer over external tools
  (`codemap route` / `codemap semantic`); license policy; adding an integration.
- **[docs/dead-code.md](docs/dead-code.md)** — graded dead-code candidates (high/medium/low + provenance
  reason) with a `[dead_code]` whitelist and `--min-confidence` filter.
- **[docs/pack.md](docs/pack.md)** — `codemap pack`: PageRank ranking + token-budgeted context slice for
  AI agents (global importance or seed-focused relevance).
- **[docs/attribute-edges.md](docs/attribute-edges.md)** — `accesses` edges: who reads/writes a class field,
  honest field-level `impact` (`accessors`; `unknown` vs `none`).
- **[docs/incremental.md](docs/incremental.md)** — `codemap build --incremental`: recompute only changed
  modules (~12× faster on `--deep`), byte-identical on the fast tier.
- **[research/blog/](research/blog/)** — **the build-story series**: field notes on building
  codemap and measuring it against rival tools (EN + RU). See the section below.
- **[BACKLOG.md](BACKLOG.md)** — milestones M0–M18, the research track (R1), and deferred work.
- **[gaps/](gaps/)** — dogfood runs, coverage analysis, the living [axis register](gaps/dogfood_axes.md).
- **[research/](research/)** — survey of adjacent code-analysis tools and how codemap relates to each
  (integrate / wrap / learn); source of the R1 capability roadmap. See
  **[research/positioning.md](research/positioning.md)** for the publication-layer narrative and
  **[research/comparison.md](research/comparison.md)** for the hands-on coverage matrix.

## Writing — the build-story series

Field notes on building codemap, and on measuring it honestly against the nearest rival
tools. Published here in the repo; every post exists in English and Russian.
**Index: [research/blog/](research/blog/README.md).**

| # | Post | |
|---|------|---|
| 0 | **A code graph an agent can trust** — what codemap is, the bet it makes, and the honest limits. | [EN](research/blog/00-a-code-graph-an-agent-can-trust.md) · [RU](research/blog/00-a-code-graph-an-agent-can-trust.ru.md) |
| 1 | **The competitor wasn't broken. We were.** — I nearly published that a rival's impact analysis was broken. The bug was my `PATH`. | [EN](research/blog/01-the-competitor-wasnt-broken.md) · [RU](research/blog/01-the-competitor-wasnt-broken.ru.md) |
| 2 | **The one that does more — and why that's fine.** — a 1.7 GB hybrid rival that proved the thesis instead of threatening it. | [EN](research/blog/02-the-one-that-does-more.md) · [RU](research/blog/02-the-one-that-does-more.ru.md) |
| 3 | **The competitor that does *less* — and that's why I take it.** — the emptiest coverage row was the most useful find. For its license, not its features. | [EN](research/blog/03-the-one-that-does-less.md) · [RU](research/blog/03-the-one-that-does-less.ru.md) |

New here? Read **1 → 0 → 2 → 3**. Every number in every post reproduces from a
[tool card](research/tools/) or the [comparison hub](research/comparison.md) — measurements,
not verdict.

## License

[MIT](LICENSE).
