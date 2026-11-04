# The most-starred code graph got my imports right and my cycles wrong. Then it found a hole in mine.

*Graphify has 141,000 stars and the most complete Python import graph I have measured: byte-identical
runs, 99.6 % precision, 90 % recall. Its cycle report saw 2 of the 45 cycles in my test tree. I predicted
why from its source and got it half right. And the comparison found a bug in my own tool.*

---

I build [codemap](https://github.com/kogriv/codemap), a static analyzer that turns a Python package into a
deterministic, diffable graph for agents. This series measures the tools around it on one shared tree.
This time the subject is the largest of them by two orders of magnitude.

## The tool

[Graphify](https://github.com/Graphify-Labs/graphify) (PyPI `graphifyy` 0.9.102, Apache-2.0, Y Combinator
S26) maps a project into a knowledge graph: code, docs, PDFs, images, video. You type `/graphify .` in a
coding assistant, or run `graphify extract` headless, and get `graph.json`, an interactive `graph.html` and a
`GRAPH_REPORT.md` with god nodes, communities and import cycles. Code goes through tree-sitter; everything
else goes through a model.

The README makes claims that can be checked for free:
- the code layer is "deterministic, no LLM, nothing leaves your machine";
- every edge is tagged `EXTRACTED` (explicit in the source) or `INFERRED` (resolved by Graphify);
- an ambiguous name is refused with the candidates listed, exit code 3.

The headline numbers (memory benchmarks, an agent on ERPNext, "80 % fewer tokens" for the cloud product)
need a model and money. I left them out.

## How I measured it

The same tree as the other posts: **280 files of one Python repository** (207 `.py`, pinned commit). The
import truth is 266 module dependencies and 45 cycles. Expectations were committed before the first run,
including one prediction I made by reading Graphify's source.

## The prediction

Graphify builds its graph as an undirected `networkx.Graph`, "for backward compatibility", and restores
edge direction when it writes `graph.json`. An undirected simple graph holds one edge per pair of nodes. If
two files import each other, that is two edges on one pair, and one has to go.

So I wrote down: **every import 2-cycle will lose a direction.** My tree has 14 of them, and 40 of its 45
cycles use at least one such pair. I predicted that Graphify would find between 20 and 31 of the 45.

## What it measured

The code layer is very good:
- **Determinism.** Three runs on fresh copies wrote a byte-identical `graph.json`, in 14 seconds each.
- **Imports.** 241 module dependencies, of which 240 are real: 99.6 % precision. Recall is 90 %. grafema
  had 61 % on the same tree, and Understand-Anything's released extractor 81 %.
- **Callers.** The 23 files that call `MACDZoneAnalyzer` are exactly the 23 my tool lists.
- **Ambiguity.** `explain analyze_zones` exits 3 and names both candidates, as promised.

And then the cycles. With imports read as links, Graphify's graph has **0 of the 45**. Its own report lists
**2**.

That was below my lower bound. So the prediction did not explain it.

## Half right

Two diagnostics, run after the scored run:
- **Two files importing each other at module level.** The default output has one link, and it carries a
  stamp: `reverse_import: true`. With `--no-cluster`, which writes the extraction before the networkx graph
  is built, both links are there. So the direction *is* lost, as predicted. But the authors know (their
  issue #4839). They keep the other direction as a stamp, and their cycle finder reads it. I had read that
  function's docstring and stopped.
- **One import inside a function, and nothing else between the two files.** An edge to the imported
  symbol, and **no** module dependency, with or without `--no-cluster`. This is the extractor, not the graph.

That second one is what happened on my tree:
- 25 of its 266 dependencies are imports inside functions, and not one became a module dependency;
- 13 of the 14 mutual-import pairs close through such an import. That is the ordinary way to break an import
  cycle in Python: move one side into the function that needs it;
- the cycle is still there, and a gate that is supposed to see it does not.

The lost direction cost exactly one edge on my tree. The function-local gap cost 25 edges and nearly every
cycle. I had predicted the wrong cause, and the part I got right was already handled.

## The tags

`EXTRACTED` and `INFERRED` on every link is a design I want: R1-C13 in my backlog asks for exactly that. So
I read the call links where Graphify and my tool disagree.

Of nine `INFERRED` cross-file calls that my tool lacks:
- four are right (`config.validate(...)` resolved to the base class), and my tool misses them;
- one is plausible: a call on whatever a factory returns, which cannot be decided statically;
- four are wrong:
  - three are `raise NotImplementedError(...)` in files that never import the package's own class of that
    name. Python uses the builtin there. Graphify links them to the package class, and two more such calls
    carry `EXTRACTED`, "explicit in the source";
  - one names a class from a module that does not export it, inside `try/except ImportError`.

On a minimal tree the builtin case reproduces, and a function named like a builtin does not. So it is
classes. Exception classes named like builtins are common in Python packages.

## The other direction

Among the call links my tool lacks, the `EXTRACTED` ones were things like
`LibraryManager.create_indicator(...)`. I checked one function: my tool resolved **0 of its 17 calls**.

The class came in through a package re-export:
- `from pkg.indicators import LibraryManager` followed by `LibraryManager.create_indicator()` was unresolved;
- the same call after importing the defining module resolved;
- so did a bare `LibraryManager()` through the same re-export.

My resolver followed re-exports at every step of an attribute chain except the first: when the head of the
chain is itself a re-exported class, the chain died on its first hop.

The fix is one line: follow the head first. A separate script, which reads only the source, predicted
**6** new call edges in my test tree, **0** in codemap itself and **8** in pytest. The fixed build produced
exactly those pairs, no more, none removed. It is released in 0.0.25.

The rival's resolver was right where mine was wrong. I would not have looked there if I had read only the
cases where it was wrong.

## Also worth knowing

`graphify extract` does what the README says: no model, no network. The step it suggests next,
`cluster-only`, names the communities in the report. With no API key set and Claude Code installed, it does
that by calling `claude -p` on your subscription, with the top node names of each community, which are names
from your code. It says so on stderr, and `GRAPHIFY_BACKEND=none` turns it off. It is a deliberate decision,
explained in their source (#4361): they judged a silent fall back to "Community N" worse. I would have made
it opt-in. The README's first line about code still says "fully local".

## When you would pick Graphify, and when codemap

**Graphify fits when:**
- **You want a map, not a gate.** Its import layer is the most complete I have measured, and it covers
  about 40 languages.
- **You want docs, PDFs and code in one graph.** That layer needs a model; I did not measure it.
- **You want determinism without giving up speed.** Fourteen seconds, byte-identical output.

**codemap fits when:**
- **The answer is an architecture verdict.** A cycle report that cannot see lazy imports misses 43 of 45 cycles
  on a codebase that breaks its cycles that way.
- **You need the call contract.** `T4` (what breaks if this signature changes) has no Graphify surface.
- **Python is all you have,** and you want each scope of an import (module, function, `TYPE_CHECKING`) as a
  separate fact.

## What I filed

After re-checking both on minimal trees with controls and an empty `HOME`:
- [#4989](https://github.com/Graphify-Labs/graphify/issues/4989): a builtin used without import is linked to
  a package class of the same name, sometimes tagged `EXTRACTED`.
- A comment on the open [#2447](https://github.com/Graphify-Labs/graphify/issues/2447), which already lists
  "import inside a function body" as a cause. On 0.9.102 the symbol edge now exists, but the module
  dependency still does not, and `## Import Cycles` says "None detected" for a lazy-import cycle. With the
  same import moved to module level, the report finds it.

## What I take from it

- **A prediction from source is a hypothesis about the part of the source you read.** I read a docstring
  that said "from imports_from edges", and the body also read a stamp.
- **Store a fact where every reader will look.** The stamp works for Graphify's own cycle finder. Any other
  consumer that reads links sees one direction.
- **Read the disagreements in both directions.** The rival's correct answers found my bug.

## What I did not check

- The memory and agent benchmarks, the cloud product's "80 %", the non-code layer, the MCP server.
- Languages other than Python.
- Why two of six mutual pairs in my tree got a stamp for their function-local direction and four did not.
- Whether the function-local gap is intended. I found no note on it. If it is, the comment on #2447
  suggests a way to keep the dependency and let the report decide.

---

*codemap is MIT, source-only, and does not import the code it analyses.*

```bash
pip install codmap         # the distribution; the command and the import are `codemap`
codemap build ./yourpkg -o graph.json
codemap report architecture --graph graph.json
```

*The Graphify card, with every pre-registered expectation and the re-check before filing:
[`research/tools/graphify.md`](../tools/graphify.md). The fix to my own resolver:
[`docs/design/reexported_class_calls.md`](../../docs/design/reexported_class_calls.md).*

*Previous post: [I tested a rival's architecture gate for silent passes.](11-the-probe-i-pointed-at-myself.md)*
