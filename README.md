# codemap

**A static analyzer that turns a Python package's source into a queryable code graph.**
It reads source only — no runtime import — so it works on any package and stays decoupled from
the code it analyzes. One canonical, deterministic graph store → many renders: API surface,
dependency/architecture audit, RAG chunks, an Obsidian vault, mermaid diagrams, change-set review.

**Status:** 🟢 M0–M16 implemented — schema 0.9, **123 tests green**, warm serve surface with 21 ops.
See **[DESIGN.md](DESIGN.md)** (product design & v1 boundaries) and **[BACKLOG.md](BACKLOG.md)** (milestones).

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
```

Dependencies: `griffe` (structure), `networkx` (query backend), `jedi` (deep call resolution).

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

# exports
codemap export rag     --graph graph.json -o chunks.jsonl
codemap export mermaid --graph graph.json --mkind class
codemap export vault   --graph graph.json -o vault/

# warm resident process — JSON requests over stdin/stdout (21 ops, MCP-mappable)
codemap serve --graph graph.json --source-root .
```

## What it answers

- **Structure & API** — public surface, signatures, docstrings, deprecation.
- **Dependencies & architecture** — import cycles, layers + direction/violations, coupling
  (Ca/Ce/instability), god-objects & call-hubs.
- **Impact / blast radius** — who uses X, across the whole repo (core + tests + docs).
- **Change review** — a diff → the symbols it touches, their callers, signature-change surface,
  touched columns, cross-root consumers, risk rank.
- **Dispatch seams** — registry/factory families and the Protocol each impl satisfies.
- **Dataflow** — producers/consumers of a string-keyed DataFrame column.

## Dogfooding

codemap is validated end-to-end against a real external package. Place a target repo as a sibling and
run the full flow against its package — e.g. `codemap build ../bquant/bquant` (point at the package
directory that holds `__init__.py`, not the repo root) — treating codemap purely as a third-party tool.
The `gaps/` directory records those dogfood runs: each is a pre-registered set of hypotheses, a run on
the live graph, findings, and the milestone that closed them.

## Documentation

- **[DESIGN.md](DESIGN.md)** — product design, the query catalog, v1 boundaries.
- **[BACKLOG.md](BACKLOG.md)** — milestones M0–M16 and deferred work.
- **[gaps/](gaps/)** — dogfood runs, coverage analysis, the living [axis register](gaps/dogfood_axes.md).
- **[research/](research/)** — (planned) survey of adjacent tools and how codemap relates to them.

## License

[MIT](LICENSE).
