# A code tool with 86,000 stars lets a model write the graph. On nine files the model wrote the prose and not one relationship. The stars are still right.

*Understand-Anything turns a repository into a knowledge graph that model subagents write, with an onboarding
tour on top. Its deterministic layer is as honest as it claims and sees none of the 45 import cycles in my test
tree. With a model in the loop it produced summaries, layers and a tour, and not a single call edge. Then I asked
why it has so many stars, and the answer was not in my benchmark.*

**codemap build-story · post 15** · [Русская версия](15-the-model-wrote-the-prose.ru.md) · [Series index](README.md) · [The repo](https://github.com/kogriv/codemap)

---

I build [codemap](https://github.com/kogriv/codemap), a static analyzer that turns a Python package's source into
a deterministic, diffable graph for agents. This series measures the tools nearest to it on one shared tree.
This one I measured in October and did not write up, and a review of the series found the gap. The numbers are
from then; the stars are from today.

## A different kind of tool

[Understand-Anything](https://github.com/Egonex-AI/Understand-Anything) (MIT) had **86 314 stars** when I
measured it, and has 93 392 now. At the time that was more than any tool I had measured (Graphify, a month
later, has more). It is also built on a different bet from everything else in this series.

It is not an indexer. It is a skill for coding agents: `/understand` is a seven-phase script that an agent
follows. Scripts do the rule-shaped parts, file inventory, the import map, the list of functions and classes.
Model subagents write the rest: `calls` and `depends_on` edges, layers, a guided tour, plain-English summaries.
The result is a JSON file and an interactive dashboard.

The authors explain in their own source why the scripts exist: runtime models *"produced inconsistent,
regex-only scripts with sparse coverage"*. I liked that before I measured anything. It is a trace of a
measurement left in the code.

## The deterministic layer: honest, and blind where it matters

Reading the source before the run, I wrote down two predictions. The Python extractor walks only the
top-level children of a module, so imports inside a function, under `if TYPE_CHECKING:` or inside `try:` are
never read. And `from .. import Name`, where `Name` lives in the package's `__init__.py`, resolves only to a
submodule, so it never reaches the file it actually executes.

The tree is the one every card in this series uses: 280 files, 207 of them Python, with a truth of 266
module dependencies and 45 import cycles. No model was called.

| | Understand-Anything | truth |
|---|---|---|
| import edges inside the package | 216, of which **215 real** (99.5 %) | 266 |
| module-level edges found | 215 of 240 | |
| edges from imports inside functions | **0 of 25** | |
| import cycles | **0** | **45** |
| four runs | one digest, byte-identical | |

Both predictions held, and every one of the 25 missed module-level edges is one of the two causes: 10
`from .. import Name` lines and 15 imports under a module-level `try:`. The one "false" edge is the truth's
convention, not their error: `from .visualization import charts` does execute the package `__init__.py`, and my
graph records only the deepest module.

The number that matters is the zero. On this tree **every cycle closes through an import that is not at the top
of a module**. Lazy imports are how this codebase breaks its import loops. A graph that skips them does not just
get smaller. It reports "acyclic" about a tree with 45 cycles.

Could the model fix it later in the pipeline? The file-analyzer agent's instructions say: *"use
`batchImportData[filePath]` directly … Do NOT attempt to re-resolve imports from source"*, and require the count
of import edges to equal the map's. The blind spot of one script becomes the blind spot of the system, by
instruction. (Their issue #692 reports a run where agents went past that and recovered edges with their own
parser. So it can happen, against the design rather than by it.)

## With a model in the loop

The deterministic layer is the part I can measure without spending. The model layer is the product. So the
owner chose a model (Sonnet 5.5), and I ran a pilot: one package of the tree, 9 files, 4 019 lines, in a
sandbox, headless, with a hard cap of $10. Expectations committed first, as always.

The first attempt stopped at a human gate, as designed: the skill generates an ignore file and waits for
confirmation. The second answered the gate in advance and ran to the end in **108 seconds, for $0.71**
(the API-price equivalent the host reports).

What it wrote: 102 nodes, a 7-step tour, 4 layers, summaries, and 198 edges: 12 `imports`, 93 `contains`,
93 `exports`.

What it did not write: **a single `calls`, `inherits` or `depends_on` edge.** codemap finds four cross-file call
pairs in those nine files (the cache module calls the config and the logging setup; the performance module
calls the cache and the logging setup). None of them appears. Everything beyond the imports mirrors the deterministic structure.

I had predicted at least one call edge with 80 % precision. That prediction failed outright.

And one more thing I did not predict. The orchestrator **shortened the pipeline on its own** and said so in its
final report: it built the layers and the tour itself instead of dispatching the architecture, tour and review
agents, replaced the review with "an inline structural check", and wrote some summaries "from names and line
ranges, not source". Three of the seven phases' agents never ran. The skill's design was not what ran; the model
decided what the run would be. To its credit, it told me.

Extrapolated by a rule fixed before the run, a full run on this tree costs at least **$9–12** in API terms.

## The question my benchmark could not ask

So by the measure of this series, the tool answers none of the structural questions: who calls this, what breaks
if this changes, where the cycles are. And it has more stars than almost every tool that does.

That is not a contradiction. It means I asked it the wrong question. What it produces is what a newcomer to a
codebase asks first: *give me a tour*, *what is this module for*, *how does the Dockerfile relate to the code*.
Its graph has `configures`, `deploys`, `migrates` and `documents` edges, putting the operational files on the
same map. None of that is a query answer, and all of it is wanted. codemap answers questions. This tool explains a
codebase. The stars say which one more people want, and I would rather know that than not.

## The defect I reported, and how fast it went

The `from .. import Name` miss had a three-file reproduction, and on the owner's decision I filed it as
[#727](https://github.com/Egonex-AI/Understand-Anything/issues/727). Within a week a community contributor sent
a fix ([#728](https://github.com/Egonex-AI/Understand-Anything/pull/728)), and it was merged on 22 October. The
other half, imports inside functions and under `try:`, was already reported as their #692, with a patch in a
comment. I measured that patch on my tree instead of filing a duplicate: it recovers 41 of the missing edges and
13 of the 45 cycles; adding the ten `from ..` lines on top gives all 45. #692 is still open, and I have not
re-measured the current version.

## What I take, and what I would do differently

**Take: the symbol-loss gate.** Before an incremental update is published, their script classifies every
function, class and method that disappeared against the old and new source. Only confirmed deletions pass;
"still present" and "unknown" block publication. My incremental build discloses that it may be carrying an old
miss. Theirs refuses to publish a loss it cannot explain. That is the better contract, and I read it from source
only; it goes into my backlog for the next time incremental builds are touched.

**Do differently: read imports wherever they occur, and label the scope.** A lazy import is still a dependency,
and on this tree it is the whole cycle structure.

**Do differently: never forbid a consumer to check its producer.** The instruction not to re-resolve imports is a
reasonable choice for consistency, and it is the single line that turns 25 missed edges into a system-wide
"no cycles".

## What I did not check

- **The full tree with a model.** The pilot covered 3 % of it, once. Enough to price it and to see that it added
  no relationship there; not enough to judge it at scale or across runs. On a larger tree the orchestrator might
  not skip phases.
- **The quality of the summaries and the tour**, which is the product. Not scored, beyond the model's own
  admission that some summaries were written without reading the source.
- **Any other model, any other language,** the dashboard, speed at scale.
- **The current version.** Every figure is from commit f2d0164 (October). #727 is fixed since; #692 is not.

---

*codemap is MIT and source-only. It answers structural questions about Python and does not explain your codebase
to you; if that is what you need, this post is a pointer to the tool that does.*

*The Understand-Anything card, with every expectation written before its run:
[`research/tools/understand-anything.md`](../tools/understand-anything.md). Measured your tool and I got it wrong?
Open an issue.*

*Previous post: [I measured whether my graph finds the right context four times.](14-four-measurements-and-a-hole.md)*
