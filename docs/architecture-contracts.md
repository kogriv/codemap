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

# The import graph must be acyclic *at import time* — the eager graph (see below).
no_cycles = true

# Also gate the coupling a lazy import hides: cycles closed only by an import written
# inside a function. Off by default; the reason is below.
no_lazy_cycles = false

# And the third kind: cycles closed only by an import under `if TYPE_CHECKING:`, where the
# modules name each other's types and have no runtime dependency at all. Off by default.
no_type_only_cycles = false

# Every core module's layer must appear in `layers` above — catches a new,
# undeclared top-level package slipping in.
exhaustive = false
```

| Rule | Fails when | Reports |
|---|---|---|
| `layers` | an import points *up* the ordered stack | the offending `importer → imported` edges |
| `independent` | two layers in a group import each other | the edges between them |
| `forbidden` | a declared `from → to` import exists | the edges |
| `no_cycles` | the **eager** import graph has a cycle | the cycles |
| `no_lazy_cycles` | a cycle is closed only by a function-local import | those cycles |
| `no_type_only_cycles` | a cycle is closed only by an import under `if TYPE_CHECKING:` | those cycles |
| `exhaustive` | a core module's layer isn't declared in `layers` | the undeclared layers |

Rules that reference a layer not present in the graph are **inert** — you can write
the contract ahead of the code. An absent or malformed `codemap.toml` yields an
empty contract (a no-op success), so a broken file never wedges the gate; use
`--require-contract` to make "no contract" a failure instead.

## What `no_cycles` judges — and what it says it did not

`no_cycles` gates the **eager** import graph: imports that actually run at import time.
A cycle closed only by an import written *inside a function* does not fail it, because
that import is the accepted way to break an import cycle — failing a build for applying
the remedy would be worse than the disease. Neither does a cycle closed only by an import
under `if TYPE_CHECKING:` — that import never runs at all, and it is the other standard
idiom for the same problem. Both scopes are carried on the edge (`extras.scope`:
`function` / `type_checking`, and since R1-C56 also `stub`) and every one of them is counted
in `import_map`, zero included. What is
recognised is narrow on purpose: `if TYPE_CHECKING:`, `if typing.TYPE_CHECKING:`, their
`not` form (which swaps the branches) and the `else` branch (which runs). A compound test
such as `if TYPE_CHECKING or X:` is *not* read and stays eager — a condition the tool
cannot read is judged strictly, never leniently
([R1-C48](../gaps/type_checking_imports_2026-09-06.md), from
[issue #18](https://github.com/kogriv/codemap/issues/18): the gate was red on the dogfood
target's one such import, and nothing short of rewriting correct code could turn it green).

### Three kinds of cycle, and which rule judges which

A cycle is classified by the **weakest import scope that closes it**
([R1-C49](../gaps/type_only_cycles_2026-09-07.md), the second half of issue #18):

| kind | closes with | what it means | rule |
|---|---|---|---|
| eager | module-level imports alone | breaks at import time | `no_cycles` |
| lazy | needs a function-local import | runtime coupling; the lazy import is a way *around* `no_cycles` | `no_lazy_cycles` |
| type-only | needs an import that **never runs**: `if TYPE_CHECKING:`, or one written in a `.pyi` | the modules name each other's types and have **no runtime dependency at all** | `no_type_only_cycles` |

The partition is by requirement, not by presence: a pair that also imports each other at
run time stays *lazy* however many type imports run between them, so a tree cannot launder
runtime coupling into the type layer by adding one.

**A `.pyi` is the second mechanism of the third kind (R1-C56).** Python never executes a stub,
so none of its imports run — including the ones that name the module importing it. Measured on
Pillow, whose *only* "hard" cycle in 105 modules was `ImageFont → _imagingft → ImageFont`, the
way back being a line in `_imagingft.pyi`, a declaration for a module written in C. Nothing
there can break on import; classifying it as eager made the project's most actionable number
100 % false positive on that tree. The edge keeps the mechanism (`extras.scope = "stub"`, and
`import_map` counts it always, zero included), while the cycle class groups by consequence —
what a reader needs is whether the import can break. Every report prints all three counts,
zero included, and `check`'s scope line names whichever kinds *this* contract did not gate.

`no_lazy_cycles` deliberately does **not** cover the third kind. It exists against a lazy
import used to walk around `no_cycles` — a runtime dependency that was merely deferred —
and the typing idiom is not that. The consumer who runs both rules had a tree that could
not satisfy them and keep `if TYPE_CHECKING:` at all; that is the defect R1-C49 fixes.

But a gate that judges a subset must not let the reader conclude more than it checked.
A passing run therefore always states its scope:

```
✅ **Contract satisfied.** Rules enforced: no_cycles.

_`no_cycles` judged **the eager import graph only** — imports that run at import time.
Not judged: **48** cycle(s) closed only by a function-local import (runtime coupling —
`no_lazy_cycles = true` gates them) and **1** closed only by an import under `if TYPE_CHECKING:`
(no runtime dependency at all — `no_type_only_cycles = true` gates them). `report architecture`
lists them. 1 import(s) under `TYPE_CHECKING` read as never running._
```

The line is printed even when the count is zero (as `"nothing was left out"`, not as an
absence), and the structured payload carries the same under `scope`. This came from a
second real target running the gate on a tree with 48 such cycles and reading
*"Contract satisfied. Rules enforced: no_cycles"* as acyclicity — the same property claim
over a partial view that [R1-C29](../gaps/import_map_module_level_2026-08-28.md) had just
removed from the *report*, reappearing in the *gate*. Their summary is the one to keep:
**it did not fail on an unexpected violation; it failed to fail where violations exist.**

`no_lazy_cycles = true` takes the other position — *a gate you walk around by making the
import lazy is not a gate* — and both positions are defensible, which is exactly why this
is a switch the contract owner sets rather than a default chosen for them. With it on,
nothing is left unjudged and the disclaimer disappears.

## Running the gate

The contract file is **always** `codemap.toml`, read from `--root` (default: the current
directory). There is no `--config` flag — point `--root` at the directory that holds the
file. On a miss, `check` prints the absolute path it looked in, because "not found in
codemap.toml" is what you already assumed; *which* `codemap.toml` is the part you need.

```bash
# exit 0 if the contract holds, 2 if it is broken (so CI fails on it)
codemap check --graph graph.json
codemap check --build ./yourpkg                 # or build fresh
codemap check --graph graph.json --root infra/   # the dir holding codemap.toml (default: cwd)
codemap check --graph graph.json --require-contract   # a missing contract is a failure
```

**Use `--require-contract` in CI.** A missing or empty `[architecture]` block is a
deliberate no-op success — a project without a contract must not fail — which means the
one run nobody reads, the green one, can be a step that enforced nothing. The flag turns
that into a failure, and `check` says so on every miss:

```
_No `[architecture]` contract found in `/repo/codemap.toml` — nothing to enforce, and this
exits 0. Use `--require-contract` to make a missing contract a failure, or `--root DIR` if
the file lives elsewhere._
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
- run: pip install codmap               # the distribution; the command is `codemap`
- run: codemap check --build ./yourpkg --require-contract
```

The step fails (exit 2) the moment an import breaks the declared architecture.
Deterministic — same graph + same contract ⇒ same result.
