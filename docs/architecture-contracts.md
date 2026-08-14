# Architecture contracts (`codemap check`)

`report architecture` *describes* the system — layers, cycles, coupling. A contract
turns that description into a **gate that fails CI**: you write the intended
architecture down once, and any import that breaks it is a non-zero exit naming the
offending edges. This is the import-linter / ArchUnit move, over codemap's graph.

## The contract

Declared in `codemap.toml` under `[architecture]` (the same file the integration
gate reads). All rules operate on the **core** module import graph — consumer roots
(tests, examples, scripts, research) are never subject to layering. A *layer* is the
component just under the package root (`pkg.<layer>…`), the same notion
`report architecture` uses.

```toml
[architecture]
# Ordered top → bottom. A layer may import only layers *below* it.
layers = ["cli", "visualization", "analysis", "indicators", "data", "core"]

# Groups whose members must not import one another (either direction).
independent = [["indicators", "data"]]

# Hard bans regardless of layering: `from` must not import `to`.
forbidden = [
  { from = "core", to = "analysis" },
]

# The import graph must be acyclic.
no_cycles = true

# Every core module's layer must appear in `layers` above — catches a new,
# undeclared top-level package slipping in.
exhaustive = false
```

| Rule | Fails when | Reports |
|---|---|---|
| `layers` | an import points *up* the ordered stack | the offending `importer → imported` edges |
| `independent` | two layers in a group import each other | the edges between them |
| `forbidden` | a declared `from → to` import exists | the edges |
| `no_cycles` | the import graph has a cycle | the cycles |
| `exhaustive` | a core module's layer isn't declared in `layers` | the undeclared layers |

Rules that reference a layer not present in the graph are **inert** — you can write
the contract ahead of the code. An absent or malformed `codemap.toml` yields an
empty contract (a no-op success), so a broken file never wedges the gate; use
`--require-contract` to make "no contract" a failure instead.

## Running the gate

```bash
# exit 0 if the contract holds, 2 if it is broken (so CI fails on it)
codemap check --graph graph.json
codemap check --build ./yourpkg                 # or build fresh
codemap check --graph graph.json --root .        # where codemap.toml lives (default: cwd)
codemap check --graph graph.json --require-contract   # fail if no [architecture] block
```

A clean run is one quiet line; a broken run names every edge to fix:

```
# Architecture check — `bquant`

❌ **2 rule(s) broken.**

## `layered` — 1 import(s) point up the layer stack (cli → visualization → analysis → indicators → data → core)

- `bquant.indicators.macd` → `bquant.analysis.zones.models`

## `no_cycles` — 1 import cycle(s)

- bquant.analysis.zones.pipeline → bquant.analysis.zones.cache → bquant.analysis.zones.pipeline
```

_(That is a real finding on bquant: `indicators` reaching **up** into `analysis`, and
a `pipeline ↔ cache` import cycle — `analysis` and `indicators` are mutually
dependent, so no strict ordering of the two is clean. The gate surfaces exactly the
edges to cut.)_

## In an agent loop (`check` over MCP / serve)

The same gate is a serve op and an MCP tool, so an agent can ask **"did my edit
break the architecture?"** after a change:

```jsonc
// serve (line-delimited JSON)
{"op": "check", "args": {"root": "."}}
// → {"ok": false, "violations": [{"rule": "layered", "summary": "…",
//                                 "edges": [["pkg.a.m", "pkg.b.m"]]}]}
```

Over MCP it is the `check` tool (`{ok, violations:[{rule, summary, edges}]}`). Pair it
with `review` (what a diff touches) for a before/after health check around an agent's
change.

## CI example

```yaml
# .github/workflows/arch.yml
- run: pip install codemap-graph        # or your install
- run: codemap check --build ./yourpkg --require-contract
```

The step fails (exit 2) the moment an import breaks the declared architecture.
Deterministic — same graph + same contract ⇒ same result.
