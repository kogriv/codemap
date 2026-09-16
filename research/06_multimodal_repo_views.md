# R1.6 — Multimodal / visual repository views (desk)

A family the R1 map did not have: systems that give a coding agent a **rendered picture** of a repository
subgraph alongside text, and measure the result as an **agent outcome** rather than as graph correctness.
Opened 2026-09-16 by one paper arriving in the field intake; the family around it was found by reading that
paper's baselines.

**Verdict for codemap:** learn-only, desk. **Feeds:** R1-C6 (relevance + token-budgeted pack), R1-C10
(navigator — an open door), R1-C28 (a limit is partiality; declare it), **R1-C61** (new — `pack` has never
been measured for usefulness).

**How this note was read, stated up front.** RepoAtlas v1 was read through the arXiv HTML rendering via a
fetch summary, **not line by line**. Every number below is *as reported by the paper* and is marked so. A
claim from this note must not travel into `positioning.md` or a post until the paper has been read properly —
this note is intake, not measurement. The rule is the one that already governs the tool cards: the card wins
over the narrative, and here we do not even have a card.

---

## 1. RepoAtlas — what it actually builds

**RepoAtlas: Guiding Coding Agents via Evolving Multimodal Repository Views**, arXiv
[2609.16936v1](http://arxiv.org/abs/2609.16936v1) ([HTML](https://arxiv.org/html/2609.16936v1)),
dated 2026-09-15.

A **method, not a tool**: no code link, no license statement, and no Limitations section in what was read.

The mechanism, in its own terms — a **select → project → refresh** loop over a code graph:

| step | what it does |
|---|---|
| **graph** | tree-sitter + static analysis, offline, **no build required**: nodes are modules, classes, callables and variables; typed edges are calls, imports, containment, inheritance |
| **select** | lexical + semantic + trajectory evidence, diffused through the dependency graph by **personalized PageRank**, yielding a connected subgraph under a **fixed budget of 15 nodes / 20 edges** |
| **project** | two *aligned* representations of that subgraph: a **rendered graph image** (force-directed / hierarchical / flowchart, layout chosen by topology and exploration state) **plus** a compact textual index carrying exact symbols and source locations, with "grounding references" tying picture to code |
| **refresh** | reuse or regenerate the view by **agent phase** — Localize / Edit / Test — and on state change that makes it outdated |

Two parts of that are worth separating, because they are not equally interesting to us. The graph and the
budgeted selection are our own territory, arrived at independently. The **rendered image consumed by a
vision-capable model** is not: codemap keeps no model in the loop by design.

## 2. The numbers, as reported

Benchmark: **SWE-bench Verified**. Baselines: mini-SWE-agent, **LocAgent**, **SeeRepo** (the strongest
multimodal baseline — it also supplements text with visual repository subgraphs).

| model | SeeRepo | RepoAtlas | delta, as reported |
|---|---|---|---|
| Qwen3.6-35B-A3B | 60.8 % | **63.1 %** | +2.3 pp |
| MiMo-V2.5 | 66.9 % | **68.0 %** | +1.1 pp |
| Kimi-K2.5 | 68.6 % | **72.4 %** | +3.8 pp |

Headline as stated: **+2.4 points** resolve rate against the strongest multimodal graph baseline, with
**−5.8 %** input tokens and **−7.8 %** model calls on average, "consistent gains across three models of
different families and scales."

**An honest reading of the size, and it is ours, not theirs.** SWE-bench Verified is 500 instances, so
1 pp ≈ 5 instances; the middle row is +1.1 pp ≈ 5–6 instances. No variance, seed count or repeated-run
spread appeared in what was read — which may well be in the paper and simply outside the excerpt. So the
defensible statement today is: *the direction is consistent across three models, and the magnitude on at
least one of them is inside the range where a single run cannot separate method from noise.* Establishing
which requires reading the paper, not quoting it.

## 3. The family the map was missing

`00_landscape.md` (R1.0, August) enumerated categories and standards; `05_curated_sources.md` (R1.5) added
the live product roster. **Neither has a single entry for visual/multimodal repository views**, and none for
SWE-bench-measured agent scaffolds:

- **RepoAtlas** (2026-09-15) — this note.
- **SeeRepo** — visual repository subgraphs alongside textual access; the strongest baseline above, and by
  that fact the incumbent of this family. Not read.
- **LocAgent** — graph-guided localization; a baseline here, previously unlisted for us. Not read.
- **mini-SWE-agent** — the text-only scaffold baseline.

That is a blind spot worth recording as a blind spot: a whole line of work exists whose premise —
*"linear text interfaces hide non-local relations"* — is the premise of our own
[post 06](blog/06-two-empty-columns.md), reached from the opposite end. We concluded that whole-graph
questions have no seed symbol and that peers therefore leave two columns empty; they conclude that the
interface, not the graph, is what loses the non-local structure. Both can be true, and neither was measured
against the other.

## 4. What it confirms for us

**Third independent sighting of personalized PageRank for deciding what an agent sees** — after aider's
repo-map ([R1.1](01_ai_context_repomap.md)) and HippoRAG 2 ([R1.5](05_curated_sources.md)). codemap's
`pack` already ranks by personalized PageRank over usage edges, in pure Python, deterministically
([docs/pack.md](../docs/pack.md), shipped as R1-C6 on 2026-08-22). Three independent arrivals at the same
selection mechanism is the strongest evidence a design decision of ours has received from outside.

It also confirms, from the agent side, that **a budget is the right unit for context** — they impose a fixed
15 nodes / 20 edges; we impose a token budget and fill it greedily by rank.

## 5. What it exposes in us — and this is the uncomfortable half

**`pack` has never been measured for usefulness.** We measured that it is deterministic, that it fits the
declared budget, and that the ranking is reproducible. We have never measured whether an agent given
codemap's pack resolves more issues, spends fewer tokens, or makes fewer calls than the same agent without
it. Outsiders now publish exactly that comparison for their own selection method.

The honest position, and it has two halves that must travel together:

1. **The gap is real.** "The slice fits the budget and is stable" is a property of the artifact, not a claim
   about value. Every value claim we have made for `pack` rests on the mechanism being sensible, which is
   precisely the reasoning style this project rejects everywhere else.
2. **Closing it changes the measurement regime.** Their metric puts a model in the loop: resolve rate
   depends on the model, the scaffold, the prompt and the seed, and it is not reproducible for a reader
   without those models. Our whole evidence base is "same input, same question, checkable answer". A
   SWE-bench-style number would be the first claim in this project that a reader cannot re-derive from a
   frozen tree — and pretending otherwise would be worse than not measuring.

So it is filed as a **door** (R1-C61), with the cost named in advance, and not as a gap to close reflexively.

## 6. What would be worth taking if R1-C10 (navigator) ever opens

- **Refresh keyed to the agent's phase, not only to the query.** Localize / Edit / Test want different
  views of the same graph. That is a genuinely new idea for us: `pack --seed X --budget N` is a function of
  the question, never of where the agent is in its work.
- **Two aligned projections of one selection.** We already have both halves and have never aligned them:
  `pack` is the text projection, `export mermaid --scope` is the diagram. Their "grounding references" —
  picture elements carrying exact symbols and locations — is what would tie ours together, and our
  `%% scope:` line (R1-C51, [post 08](blog/08-eight-of-twelve.md)) is the existing precedent for a diagram
  that declares what it is a view *of*.
- **A budget must be declared in the answer** (R1-C28). Theirs is fixed and tiny — 15 nodes and 20 edges of
  a repository — which makes the declaration more important, not less: a reader of such a view is seeing a
  thumbnail and has no way to know it from the picture.
- **Layout chosen by topology.** Our mermaid export has one layout. On a dense tangle (and we now know what
  those look like — `_pytest`, 19 modules in one knot, [post 09](blog/09-true-and-worthless.md)) one layout
  is not enough to be readable.

## 7. The boundary we share, and the genre difference

Their failure analysis names the same limit we declare: **runtime dependencies are invisible to a static
graph** (dynamic registration, reflection, plugin loading). We closed that shape twice this month — plugin
registration read as dead code, and a stub-closed import cycle that never executes — and both times the
repair was to make the *answer* carry the limit. In a paper, a limit named once in a case study is normal
genre; in a tool, an undeclared limit is the defect
([post 08](blog/08-eight-of-twelve.md), R1-C53). Not a criticism of them — a difference in what the artifact
is obliged to do.

## 8. What this note does not establish

- **Nothing was run.** No code is released in what was read; by the разбор convention this is desk, and the
  "don't assess without running when runnable" rule does not apply because it is not runnable.
- **Numbers are second-hand** — a fetch summary of the HTML rendering of v1, not a line-by-line read. In
  particular the variance question in §2 is open, not answered.
- **SeeRepo and LocAgent were not read at all** — they are listed as a family, with no verdict.
- **One benchmark, three models.** Nothing here says how the method behaves on a repository shaped unlike
  the SWE-bench Verified set, and our own measurements this month are a reminder of what a change of shape
  does to a metric.
- **No license statement was found**, so nothing may be copied from it; ideas read and attributed, as usual.

## 9. Verdict & backlog effect

**learn-only (desk).** Not a competitor: it is a scaffold around an agent, and it makes no claim about graph
correctness — the axis our whole comparison hub is built on. It nonetheless earns a note because it
contributes one confirmation, one blind spot and one uncomfortable gap:

- **R1-C6 confirmed a third time** (personalized PageRank for what an agent sees).
- **R1.0/R1.5 blind spot recorded**: no visual/multimodal view family was in the map (§3).
- **R1-C61 filed**: `pack` has no usefulness measurement, and the door is priced — a model in the loop, and
  the first claim in this project a reader could not re-derive.
- **R1-C10 (navigator) gains concrete design points** if it is ever opened (§6).
