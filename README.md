# codemap

**A static analyzer that turns a Python package's source into a queryable code graph.**
It reads source only — no runtime import — so it works on any package and stays decoupled from
the code it analyzes. One canonical, deterministic graph store → many renders: API surface,
dependency/architecture audit, RAG chunks, an Obsidian vault, mermaid diagrams, change-set review,
and a **SCIP index** for interop with Sourcegraph / Glean and other precise-code-intelligence tools.

[![CI](https://github.com/kogriv/codemap/actions/workflows/ci.yml/badge.svg)](https://github.com/kogriv/codemap/actions/workflows/ci.yml)

**Status:** 🟢 M0–M20 implemented + research track (R1/R2) — schema 0.13, **634 tests with no failures on
Python 3.11–3.14** ([in CI](docs/ci.md): the full suite including the dogfood pass, a determinism check, a
wheel smoke test, and ctags/SCIP interop against the real CLIs), warm serve surface with 31 ops (28 exposed
as MCP tools), and SCIP export. See **[DESIGN.md](DESIGN.md)** (product design &
v1 boundaries), **[BACKLOG.md](BACKLOG.md)** (roadmap), and **[research/](research/)** (tool landscape).

## Why it exists

Docs describe code and CLIs call code; without a parsed map of the code both are done blind. codemap
builds that map as **facts**: modules, classes, functions, the public API surface, import/inherit/
export edges, best-effort call edges, registry-family `implements` links, string-key column dataflow,
and per-call argument contracts — then answers questions over it.

Design principles: **source-only** (static `ast`/`griffe`, never imports the target), **deterministic**
(canonical sorted JSON, no timestamps — diffable), **CLI-AI-first** (JSON by default, stable exit
codes), **honest** (approximations are labeled, not hidden).

## Point questions and whole-graph questions

Most code-intelligence tools answer **point questions** — you name a symbol and they walk outward a
few steps. *Where is this defined? Who calls it? What breaks if I change it?* The answer's cost
scales with the neighbourhood, not the repository, which is why an index or a vector store can serve
it. The field is good at this, and several tools are faster at it than codemap.

**Whole-graph questions** have no starting symbol, because the property being asked about belongs to
the graph and to no node in it:

> Is there a dependency cycle anywhere? · Which module is most expensive to change? · Does the code
> still respect the layering I intended? · Where has behaviour concentrated into one class?

A cycle is invisible from inside every file that participates in it — each one looks perfectly
reasonable alone. You cannot seed the question, and there is no partial answer.
`codemap report architecture` computes all of them in one pass; on the dogfood target (88 modules,
**715 import edges**) that is:

```
layers         core 9 · data 12 · indicators 16 · analysis 42 · visualization 7 · cli 1
               analysis → core 38 edges · indicators → core 22 · data → core 13
violation    ⚠ analysis ↔ core             — one backward edge, written inside a function
cycle          pipeline → cache → pipeline  — the classic Python import-order landmine
lazy cycles    40 more, closed only by a function-local import — not import-time failures,
               still mutual coupling: neither module can be extracted without the other
coupling       core.logging_config  Ca 96   — a breaking change here reaches 96 modules
concentration  ZoneVisualizer 35 methods, worst function CC 66 / MI 12.5
```

That single layer violation is worth its line: it is reached only through an import written *inside a
function*, so until [R1-C29](gaps/import_map_module_level_2026-08-28.md) codemap could not see it and
reported the architecture as clean. A gate you can walk around by making the import lazy is not a gate.

Then [`codemap check`](docs/architecture-contracts.md) turns the shape you *want* into a CI gate, so
description and intent cannot drift apart.

Four rival tools have now been measured hands-on on the same benchmark scope — three of them on
byte-identical input verified by content hash, the fourth (graphlens) on a near-identical staging that
predates the harness — including the field's most-adopted tool at 68k stars. **All four answer the point
questions. None answers these on a surface a caller can reach** — nor the related "how does each caller
actually *pass* its arguments" (`call_contract`) — because a slice of source is the wrong shape for the
answer.

That sentence used to end at "None answers these", and a second pass over the 68k-star tool made it
narrower: its *importable library* does carry a cycle finder, reachable from neither its CLI nor its MCP
tools and called nowhere in its own source. Measured on the same tree it reports **136 cycles**; codemap
reports **1**. Scoring both against the truth set — every intra-package import, function-local ones
included — is less flattering than that sounds:

| | reported | of the 41 real ones | precision | recall |
|---|---:|---:|---:|---:|
| codemap, that morning | 1 | 1 | 100% | **2.4%** |
| the peer's library API | 136 | 13 | 10% | 32% |
| codemap, after R1-C29 | 41 | 41 | 100% | 100% |

Theirs over-reports because it walks name-resolved call edges — a `dict.get` becomes a call into an
unrelated class. **Ours under-reported because its import map was module-level only**, and it phrased
that as *"import graph is acyclic"* — a property claim over a partial map, which is the worse of the two
errors even though it was the smaller one. Both halves of that came from
[#11](https://github.com/kogriv/codemap/issues/11), filed off a different target and fixed the same day
([R1-C29](gaps/import_map_module_level_2026-08-28.md)). The lesson is sharper than the win: a
whole-graph answer inherits every flaw of the graph it is computed from, **including the edges that
graph never read** — and the tool cannot be the judge of its own recall.

**→ [docs/whole-graph-questions.md](docs/whole-graph-questions.md)** — the full argument, every number
above reproduced from one run, and the honest limits.

## Install

**Python 3.11+** — the range is measured on 3.11–3.14 in CI, not assumed ([docs/ci.md](docs/ci.md)).

> **The distribution is `codmap`; everything else is `codemap`.** `codemap` was already taken on
> PyPI, so you install `codmap` — and then the command, the import and this repository are all
> spelled `codemap`, as they always were.

```bash
pip install codmap             # then: codemap build ./yourpkg

# optional: MCP server (`codemap serve --mcp`)
pip install 'codmap[mcp]'

# optional: SCIP export (`codemap export scip`)
pip install 'codmap[scip]'
```

Or straight from source: `pip install git+https://github.com/kogriv/codemap`.

Working on codemap itself, from a clone:

```bash
uv venv && uv pip install -e '.[mcp,scip]'    # or: pip install -e '.[mcp,scip]'
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

# warm resident process — JSON requests over stdin/stdout (31 ops)
codemap serve --graph graph.json --source-root .

# …or expose the same surface as MCP tools for an AI-agent host (needs [mcp] extra)
codemap serve --graph graph.json --source-root . --mcp

# keep it current while you work: source → incremental rebuild → the warm server reloads
codemap watch ./pkg -o graph.json &
codemap serve --graph graph.json --watch
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

Where the comparison actually lands, after four hands-on cards: peers are **faster**, cover **more
languages**, and several are **easier to install**. What none of them answers is the whole-graph
class — architecture, layers, cycles, coupling — and per-call argument contracts. That is the
substance behind "complements rather than competes", written out in
**[docs/whole-graph-questions.md](docs/whole-graph-questions.md)**.

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
- **[docs/whole-graph-questions.md](docs/whole-graph-questions.md)** — **start here for what codemap is
  *for*.** Point questions vs whole-graph questions, why the field answers only the first class, the
  five questions codemap answers with a real run behind each, and the honest limits.
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
  modules (~12× faster on `--deep`), byte-identical on the fast tier; plus the automatic
  `codemap watch` + `serve --watch` loop (save → answerable in ~8 s on a real package at the defaults,
  of which 4.3 s is the rebuild).
- **[docs/test-mapping.md](docs/test-mapping.md)** — `codemap tests <symbol>`: which tests exercise a
  symbol, as runnable pytest node ids, with the measured distance cutoff and an `unknown` that never
  pretends to be "untested".
- **[docs/hard-python.md](docs/hard-python.md)** — what the extractor does with metaclasses, dynamic
  classes, star imports, quoted annotations, `.pyi` stubs and symlinked trees; and the conditions where it
  warns instead of answering.
- **[docs/provenance.md](docs/provenance.md)** — the `provenance` block: which tool, which tier, which
  input tree built a graph; what stays in the sidecar; the schema-mismatch warning and `diff`'s
  comparability check.
- **[docs/flat-layout.md](docs/flat-layout.md)** — flat module directories (sibling imports, no
  `__init__.py`): labelled `resolution="flat"` edges, and the empty-import-graph warning that stops a
  vacuous graph from reading as a clean one.
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
| 4 | **My determinism test went red. The tool was fine.** — the input was moving under it, and the artifact could not say so. How the graph learned to name what built it. | [EN](research/blog/04-the-determinism-test-that-was-right.md) · [RU](research/blog/04-the-determinism-test-that-was-right.ru.md) |
| 5 | **A month of dogfooding. Then one more repository found seven bugs in two days.** — eleven pre-registered axes, all asked of one tree. What was missing was not an angle but a shape. | [EN](research/blog/05-the-second-repository.md) · [RU](research/blog/05-the-second-repository.ru.md) |
| 6 | **I measured the 68,000-star competitor. It was faster than mine. That wasn't the finding.** — four rivals, and the same two columns empty in all of them. | [EN](research/blog/06-two-empty-columns.md) · [RU](research/blog/06-two-empty-columns.ru.md) |

New here? Read **1 → 0 → 2 → 3 → 4 → 5 → 6**. Every number in every post reproduces from a
[tool card](research/tools/) or the [comparison hub](research/comparison.md) — measurements,
not verdict.

## License

[MIT](LICENSE).
