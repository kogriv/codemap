# Whole-graph questions

*Why "what is the shape of my system?" is a different kind of question from "where is this
function?" — and why the tools that answer the second one do not answer the first.*

This document is the long form of a distinction that decides what codemap is for. It is written for
someone choosing between code-intelligence tools, and it is grounded throughout in one real run
against one real package, so every number here can be reproduced.

---

## 1. Two kinds of question

Ask a code-intelligence tool something, and your question falls into one of two classes. They look
similar from the outside and are completely different underneath.

### Point questions

You name a starting place, and the tool walks outward a bounded number of steps.

> Where is `analyze_zones` defined? · Who calls `MACDZoneAnalyzer`? · What does this function call? ·
> Show me the source of this class. · What breaks if I change this?

The defining property is that **the answer's cost is proportional to the neighbourhood, not to the
codebase.** The tool starts at one node and expands. A repository of ten million lines answers just
as fast as one of ten thousand, provided the neighbourhood is the same size. That is why these
questions can be served by an index, a vector store, or even a good grep.

### Whole-graph questions

You name no starting place, because there isn't one.

> Is there a dependency cycle anywhere in this project? · Which module is most expensive to change? ·
> Does the code respect the layering I intended? · Where has behaviour concentrated into one class?

These cannot be decomposed into "start here and look around", because the property being asked about
**is a property of the whole graph and of no individual node**. There is no symbol you can point at
whose neighbourhood contains the answer to "is this system acyclic". A cycle is not visible from
inside any file that participates in it — each of those files looks entirely reasonable on its own.

The cost is proportional to the *entire* graph, every time. And the answer changes when a file you
never opened changes.

**Everything in this document is about the second class.**

---

## 2. Why the field converged on the first class

This is not an oversight by other tools. It follows from what they were built to do.

The dominant framing for code intelligence in 2026 is **retrieval for an AI agent**: the agent is
about to write code, it needs the right few hundred lines in its context window, and the tool's job
is to deliver them in one call instead of twenty greps. Measured on that job, the good tools are
genuinely good — the [CodeGraph card](../research/tools/codegraph.md) records a peer answering
architecture questions in 1–4 tool calls with zero file reads, and doing it 9× faster than codemap's
fast tier.

But that framing has a shape, and the shape excludes whole-graph questions:

- **The unit of value is a slice.** "Here is the relevant code" is the deliverable. A cycle is not a
  slice of code; it is a statement *about* code. There is no snippet to return.
- **The consumer is a model with a context budget.** Returning the whole import graph is not helpful
  to an agent — it is 634 edges of noise. The whole-graph answer has to be *computed down* to a
  sentence ("analysis and indicators depend on each other"), and computing it down requires knowing
  what property you were looking for in the first place.
- **The store is optimised for lookup.** A vector index answers "what is similar to this". A
  full-text index answers "where does this string appear". Neither is a data structure over which you
  run a strongly-connected-components pass.

So the tools that win at retrieval ship `search`, `callers`, `callees`, `impact`, `explore` — and
then a `files` command that prints the directory tree.

**A directory tree is not architecture.** It is where you happened to put things. Two files in
adjacent folders may know nothing about each other; two files at opposite ends of the repository may
be welded together. The tree cannot tell you which, because folders are a filing decision and
dependencies are a code fact.

---

## 3. The five whole-graph questions codemap answers

Everything below is verbatim from one command on one package —
`codemap report architecture` over bquant at the frozen benchmark commit (`cb89a24`, 89 core modules,
**634 import edges**). The same run is recorded in the
[R2 benchmark](../research/comparison.md) alongside every competing tool.

### 3.1 Layers — what the system is made of, and which way it leans

Not declared by hand. Derived from the import graph: a *layer* is the component just below the package
root, and the tool counts every edge between them.

```
core 9 modules · data 12 · indicators 16 · analysis 42 · visualization 7 · cli 1

analysis      → core   38 edges
indicators    → core   24
data          → core   13
visualization → core    8
analysis      → indicators  3
```

Read it as a picture: everything leans on `core`, and `core` leans on nothing. That is a healthy
foundation, and it is *stated as a count*, not as an impression. The number matters — "analysis
depends on core" is a fact you could guess; "38 edges" is the size of the coupling, and it is the
thing that changes silently over months.

### 3.2 Violations — where a dependency goes both ways

```
⚠ Layer violations (mutual dependency)
   analysis ↔ indicators
```

`analysis` imports `indicators` three times; `indicators` imports `analysis` once. One edge going the
wrong way, out of 634.

Why one edge is worth naming: a one-directional dependency is **extractable**. You can lift
`indicators` out into its own package, test it in isolation, hand it to another project. The moment
the dependency is mutual, you cannot — pulling `indicators` drags `analysis` behind it, and
`analysis` drags most of the system.

And this is exactly the finding no point query can produce. Open the file containing that single
backward import and it looks completely ordinary: one import at the top, used a few lines down. The
defect is not in the file. It is in the pair, and the pair is only visible from above.

### 3.3 Cycles — where the code closes a loop

```
Import cycles: 1
   analysis.zones.pipeline → analysis.zones.cache → analysis.zones.pipeline
```

`pipeline` imports `cache`, `cache` imports `pipeline`. In Python this is the classic source of
failures that look like magic: the import works or explodes depending on which module Python reached
first, moving a line fixes it, moving it back breaks it again, and the traceback points somewhere
irrelevant.

The mechanically important part: a cycle is the textbook whole-graph property. Finding it is a
strongly-connected-components pass over the entire import graph. There is no seed symbol from which
this answer expands, and there is no partial version of it.

### 3.4 Coupling — what a change actually costs

Two counts per module: **Ca** (how many modules depend on it) and **Ce** (how many it depends on).

```
core.logging_config     Ca 94  ·  Ce 1   ·  I 0.01
data.samples            Ca 54  ·  Ce 4   ·  I 0.07
analysis.zones.models   Ca 37  ·  Ce 1   ·  I 0.03
core.exceptions         Ca 31  ·  Ce 0   ·  I 0.00
```

`Ca 94` is not an adjective. It says: **an incompatible change in `logging_config` reaches
ninety-four modules.** That is the difference between "I'll fix it before lunch" and "this needs a
branch, a plan and a full run" — and you know which one *before* you start, not after the test suite
tells you.

`I = Ce/(Ca+Ce)` is the instability ratio, 0 to 1. Low means "many depend on me, I depend on few" —
a foundation, which *should* be stable and hard to change. High means "I depend on many, few depend
on me" — a leaf, which should be easy to change. The pathology this exposes is a module with a low
`I` that keeps changing anyway: a foundation being treated like a leaf.

### 3.5 Concentration — where behaviour piled up

```
God-object candidates (≥ threshold methods): 14
   visualization.zones.ZoneVisualizer        35 methods · ΣCC 456 · maxCC 66
   core.nb.NotebookSimulator                 23 methods · ΣCC 50  · maxCC 5
   analysis.zones.pipeline.ZoneAnalysisPipeline  20 methods · ΣCC 72 · maxCC 8

Most complex functions:
   ZoneVisualizer._create_plotly_zones_on_price   CC 66 · MI 12.5 · 264 sloc
   ZoneFeaturesAnalyzer.extract_zone_features     CC 59 · MI  9.2 · 392 sloc
```

**CC** (McCabe cyclomatic complexity) counts independent paths through a function — roughly, its
branches. **MI** (Maintainability Index) is a 0–100 composite where higher is better.

`CC 66` means sixty-six independent paths through one function. You cannot test it exhaustively —
you would need sixty-six cases — and you cannot safely change it, because you cannot hold sixty-six
paths in your head at once.

Note what the pairing buys: `NotebookSimulator` has 23 methods but `maxCC 5`. Many methods, each
simple — that is a *facade*, and it is fine. `ZoneVisualizer` has 35 methods and `maxCC 66` — many
methods, one of them a monster. Method count alone would have flagged both equally and told you
nothing. Complexity alone would have flagged the function without telling you it sits inside the
class with the most surface area. The two together separate "large" from "dangerous".

---

## 4. Describe, then enforce

A report is a snapshot, and a snapshot decays. The second half of the capability turns the
description into a rule:

```toml
# codemap.toml
[architecture]
layers = ["cli", "visualization", "analysis", "indicators", "data", "core"]
independent = [["indicators", "data"]]
```

`codemap check` reads that, walks the same import graph, and exits non-zero naming every edge that
breaks it. Your intended architecture stops being tribal knowledge in someone's head and becomes a
thing CI fails on. Full reference: [architecture-contracts.md](architecture-contracts.md).

This pairing is the point. `report architecture` tells you the shape you *have*; the contract records
the shape you *want*; `check` is the gate that keeps them from drifting apart. Neither half is much
use alone — a report nobody re-reads is decoration, and a contract with no way to see the current
state is a guess.

---

## 5. The second unmatched capability: argument-level call contracts

Layers and cycles are the clearest example, but they are not the only question in this family. A
second one comes up constantly and is answered nowhere else measured.

**"I want to change this function's signature. What exactly has to change with it?"**

Every tool can tell you *who* calls a function. That is a point query, and they all do it well. What
they do not tell you is **how** each caller calls it:

`call_contract` is a **serve/MCP operation**, not a CLI subcommand — reach it through
`codemap serve` (line-delimited JSON), the `call_contract` MCP tool, or folded into a diff review by
`codemap review`, which assembles it per touched symbol. On `analyze_zones` it returns, per caller:

```
presets.analyze_macd_zones                 1 call site  · 1 positional · no kwargs · no splat
presets.analyze_rsi_zones                  1 call site  · 1 positional · no kwargs · no splat
MACDZoneAnalyzer.analyze_complete_modular  1 call site  · 1 positional · no kwargs · no splat
examples.02_macd_zone_analysis.main        4 call sites · 1 positional · no kwargs · no splat
examples.02a_universal_zones.main          9 call sites · 1 positional · no kwargs · no splat
```

The difference is operational. "Twenty places use this" sends you to read twenty files. "Every caller
passes exactly one positional argument, and here are the two that pass keywords" tells you whether
adding a parameter is safe *without opening anything*. It is the difference between a list of
addresses and an actual answer.

This requires parsing every call site's argument shape and aggregating it per caller — again, not
something a retrieval index stores, because it is not a snippet anyone would want returned.

---

## 6. The evidence that this is a real gap

Four tools have now been measured hands-on on the shared benchmark scope. Three of them ran on
byte-identical input — the same 280 files, verified by content hash
(`scope_id sha256:300e0a01…`) — so those rows are exact rather than approximate. The fourth,
graphlens, was measured before the scope harness existed, on a near-identical staging of 285 files
(the same tree plus five generated `docs/_build` files); its card says so. Full matrix and per-tool
cards: [research/comparison.md](../research/comparison.md).

| | symbol lookup | callers | impact | **argument contract** | **layers / cycles** |
|---|---|---|---|---|---|
| **codemap** | ✅ | ✅ | ✅ | **✅** | **✅** |
| [CodeGraph](../research/tools/codegraph.md) (68k ★) | ✅ | ✅ | ✅ | ✖ | ✖ |
| [GitNexus](../research/tools/gitnexus.md) | ✅ | ◐ | ✅ | ✖ | ◐ cycles + clusters, no layers/coupling |
| [graphlens](../research/tools/graphlens.md) | ✅ | ✅ | ✅ | ✖ | ✖ |
| [cocoindex-code](../research/tools/cocoindex-code.md) | ◐ | — | — | — | — |

Two of the five columns are unfilled by every peer, including the most-adopted tool in the field.
That is not a claim about quality — several of these tools beat codemap outright on speed, language
coverage and setup. It is a claim about **shape**: they were built to answer point questions, and
they answer them well.

---

## 7. Who this is for

The honest framing is that these two classes of question have two different consumers.

**Point questions serve the agent mid-task.** It is writing code right now; it needs the right lines
in its window; it wants them in one call. Retrieval tools are built for exactly this and are very
good at it.

**Whole-graph questions serve the author deciding what to do.** Can I extract this module into its
own package? What will this refactor actually cost? Where is the debt concentrated? Is the design I
described in the README still the design in the code? These are not "show me the code" questions —
they are "what shape is the system I have built" questions, and they are asked *before* any code gets
written, by a person, or by an agent doing planning rather than typing.

codemap serves both, but the second is where it is alone.

---

## 8. Honest limits

The report is a measurement, and measurements have edges. What it does **not** tell you:

- **It is the import graph, not the runtime.** A module imported behind a conditional, or reached
  only through a plugin registry, participates differently at runtime than the static edge suggests.
  The call graph has its own openly stated recall ceiling — see [accuracy.md](accuracy.md).
- **"Layer" is a convention until you declare it.** Absent a contract, a layer is the component
  directly under the package root. If your project groups differently, the derived layers are
  arithmetic on the wrong grouping. Write the contract and the guessing stops.
- **Cycles here are *import* cycles.** Mutual recursion between functions inside one module is a
  different phenomenon and is not what this counts.
- **Ca/Ce count modules, not weight.** One module importing another for a single constant scores the
  same edge as one built entirely on top of it.
- **CC and MI are heuristics with known blind spots.** They measure branching and volume, not whether
  the code is *good*. A long, flat, boring function scores badly and may be perfectly clear.
- **It cannot tell you whether your architecture is right.** It tells you what your architecture *is*,
  and — if you write a contract — whether it still matches what you said you wanted. Whether what you
  wanted was wise is not a graph property.
- **Python only.** Every peer in the table above covers more languages. This is a deliberate trade,
  recorded in [DESIGN.md](../DESIGN.md).

---

## See also

- [architecture-contracts.md](architecture-contracts.md) — the enforcement half (`codemap check`).
- [accuracy.md](accuracy.md) — what the call graph's numbers are worth, measured.
- [research/comparison.md](../research/comparison.md) — the full coverage matrix, hands-on.
- [research/positioning.md](../research/positioning.md) — the narrative layer, including build-story
  #6, where this distinction was measured against the field's most-adopted tool.
