# I measured the 68,000-star competitor. It was faster than mine. That wasn't the finding.

*It beat my tool on speed by 9×, matched it on correctness everywhere they overlap, and taught me
something about publishing numbers. The interesting part was two columns that were empty — in its
results, and in every rival's, and for the same structural reason.*

---

I build [codemap](https://github.com/kogriv/codemap), a static analyzer that turns a Python package's
source into a deterministic, queryable graph. Its pitch is trust: source-only, byte-diffable, and
honest about its approximations.

For four months I have been measuring it against the field — one tool at a time, hands-on, on the same
280 files, with the input pinned by content hash so the comparisons are exact rather than
approximate. Three tools in, the cards read like a comfortable story: capable peers, each strong
somewhere, none of them quite doing what I do.

Then I got to the fourth. Seven months old, **68,420 stars, 4,362 forks**, MIT, a Rust kernel with
tree-sitter compiled in, twenty languages, installed by one command. It is not a peer of comparable
weight. It is what a person reaches for *instead of* my tool.

## It measured fair

On the identical 280 files: **1.4 seconds** to index, against my 12.3 seconds on the fast tier and
95.8 on the deep one. Roughly 9× and 68×. Queries in ~0.3 s. Incremental re-sync in **121 ms**, behind
a debounced file watcher I had been deferring for a month on the grounds that I didn't know what it
would cost.

Then the accuracy question — "who calls `MACDZoneAnalyzer`", a symbol I have been probing for months.
It returned 58 symbol-level callers. Mine returned 57. **My 57 were a complete subset of its 58.** Not
"broadly agreed": every single one, same file, same function.

Its one extra was this:

```python
assert isinstance(analyzer, MACDZoneAnalyzer)
```

The symbol is passed as a *value*. Its own `--help` says the command finds functions that **call** the
symbol, so that is a reference counted as a call. Mine keeps the two apart and surfaces it under
`impact` as `type: "references"` instead.

I am not going to dress that up as a win. It is one row in fifty-eight, and it is the same
*function-passed-as-a-value* mechanism that made my own dead-code grading wrong 39% of the time last
month. One tool has had to learn that distinction. The other hasn't needed to yet.

## The half-hour where I was the broken one

The first run of that query returned exactly **20** callers, every one of kind `file`, at line 1. Read
at face value that is a clean finding: *this tool models callers as file-import fan-in, not call
sites.* Publishable. Wrong.

`--limit` defaults to 20. The file-kind rows sort first. The default had cut the answer **exactly
along the line that misrepresents the model** — and the payload says nothing about it: no total, no
`truncated` flag, no echo of the limit. At `--limit 500` you get the 79 entries and the real picture.

Two things saved me, and neither was skill. Twenty is a suspiciously round number. And this is the
second time in this series a default nearly produced a false verdict about someone else's tool — the
first was a rival that silently degraded because its bundled type-checker wasn't on my `PATH`, which
[cost me an afternoon and a retraction](01-the-competitor-wasnt-broken.md).

The rule that caught both is embarrassingly cheap: **when a number looks round, check whether it is a
limit.**

## So I asked my own tool the same question

```
search "zone"   default limit   →    50 hits    envelope: {"ok": true}
search "zone"   limit 5000      →  1259 hits
```

**Fifty of one thousand two hundred and fifty-nine.** No total. No marker. No echo of the limit. And
this is the operation whose own docstring calls it *"the discovery entry point, for an agent that does
not yet know exact names"* — the one whose entire job is to say what exists. It answers with 4% of it
and looks complete.

I have a mechanism for exactly this. Seven operations carry a machine-readable `epistemic: "partial"`
flag meaning *this answer is a lower bound, pair it with grep before you act*. It doesn't fire here,
and it couldn't: it marks partiality of **resolution** — the analyzer couldn't figure something out. A
limit is a second, independent way an answer can be a lower bound, and I had built the marker for only
one of them. `callers` is flagged and takes no limit. `search` takes a limit and is flagged by
nothing.

Eighth application of the same rule in this project's life. First one I found in someone else's tool
first, then turned back on myself.

## The two columns

Here is the part I actually want to write about.

My comparison matrix has a column per capability. After four hands-on measurements, two of them are
empty for every tool but mine:

| | symbol lookup | callers | impact | **argument contract** | **layers / cycles** |
|---|---|---|---|---|---|
| codemap | ✅ | ✅ | ✅ | **✅** | **✅** |
| CodeGraph (68k ★) | ✅ | ✅ | ✅ | ✖ | ✖\* |
| GitNexus | ✅ | ◐ | ✅ | ✖ | ◐ |
| graphlens | ✅ | ✅ | ✅ | ✖ | ✖ |
| cocoindex-code | ◐ | — | — | — | — |

Four independent teams, different languages, different architectures, wildly different scales of
adoption — and the same two gaps. When that happens it is almost never four oversights. It is a
property of the problem.

**\* And that asterisk is the fourth time this post was written wrong.** I filled that cell from the
CLI and the MCP tool list. A tool has as many surfaces as it ships, and this one ships three: there is
an importable library, and the library has `findCircularDependencies()` — reachable from neither of the
other two, and called nowhere in the project's own source. I had measured two thirds of a tool and
written ✖ as though I had measured all of it.

So I ran it. On the same tree it reports **136 cycles. Mine reports 1.** The difference is not tuning.
It walks resolved *call* edges instead of imports, and those edges bind method names without type
inference, so this line —

```python
mapped_timeframe = TIMEFRAME_MAPPING[data_source].get(timeframe, timeframe)
```

— becomes a call into `MemoryCache::get` in a different file, and two files that import in one direction
appear to import in both. Six of six sampled edges into that method are false. One of the 136 "cycles"
runs through a research notebook.

I could have left the ✖ and nobody would have checked. The narrower claim is the one that survives:
**nobody answers these on a surface a caller can reach**, and the single implementation that exists at
all inherits every false edge of the point-question graph it was computed from. That is a better
sentence than the one I had, and I only got it by opening the third door.

**And then, hours later, a bug report from a different project made it the fifth correction.** I had
scored that comparison against *my own answer*, which is the one mistake this whole research track is
supposed to prevent. Scored against every intra-package import instead — including the ones written
inside a function — that tree has **9** cycles, not 1:

| | reported | of the 41 real | precision | recall |
|---|---:|---:|---:|---:|
| mine | 1 | 1 | 100% | **2.4%** |
| theirs | 136 | 13 | 10% | 32% |

My import map is module-level only. A `from x import y` inside a function is invisible to it — and that
is exactly the import a developer writes **to break a cycle**, so the blind spot is anti-correlated with
the question. Worse than the recall: with an empty cycle list my report printed *"import graph is
acyclic"*. Not "none found" — **acyclic**, a property, over a map that had not read a quarter of the
edges on the reporter's target.

So the tally on the question I built the whole positioning argument around is: they over-report and say
nothing; I under-report and call it a guarantee. Their much-criticised mechanism — walking call edges —
is *why* they found thirteen where I found one, because the call tier does see those imports. Mine is the
smaller error and the worse sentence.

**A sixth correction, and this one is the most embarrassing, so it goes in too.** The truth set above
first said *nine*. I had written a fifteen-minute AST scan to audit my own tool, and it anchored relative
imports inside a package `__init__.py` at the wrong package — so `from .candlestick import …` resolved
to a module that does not exist and simply vanished. The script I wrote to check the tool was less
careful than the tool. Corrected, the number is 41, and the fixed extractor and the fixed scan agree on
the same 41 *sets* — which is now an acceptance test, because agreeing on a count is not agreeing.

Fixed by the end of the day. Function-local imports are in the map, tagged. Import cycles stay the
*eager* ones — a lazy import is how you prevent that failure, and calling it a cycle would report the
remedy as the bug — while the cycles that close only through one get their own section: not import-time
failures, still coupling you cannot extract your way out of. And the sentence *"import graph is
acyclic"* is gone from all three renderers that had inherited it.

Then the person who filed the bug rebuilt on the fix and reported back: 29 of 29 previously-missing
dependencies now present, and **three** lazy cycles where their issue had claimed two. The third was
real. Their scan had collected DFS back-edges instead of enumerating simple cycles, so a three-node
cycle disappeared once its nodes were coloured.

So in one day, two people independently wrote a script to audit a tool, and **both scripts were less
careful than the tool** — in opposite directions. Mine mis-anchored relative imports and turned 41 into
9. Theirs collected back-edges and turned 3 into 2. Neither mistake is exotic; both are the kind you make
in the fifteen minutes you have allotted to *checking*, as opposed to the weeks you spent *building*.

The lesson I would keep from the whole episode is not about cycles. **A tool cannot be the judge of its
own recall** — precision it can demonstrate, recall needs something from outside, and I had been
publishing a recall claim with no outside. But the sharper half is the one that cost us both a
correction: **the check is only worth what the check's own verification is worth**, and the cheap check
that agrees with your prior is the one nobody ever verifies.

## Point questions and whole-graph questions

Ask a code-intelligence tool something, and it falls into one of two classes.

**Point questions** name a starting place and walk outward a bounded number of steps. *Where is this
defined? Who calls it? What breaks if I change it?* The defining property: the cost scales with the
neighbourhood, not the repository. A ten-million-line codebase answers as fast as a ten-thousand-line
one if the neighbourhood is the same size. That is why an index, a vector store, or a good grep can
serve them.

**Whole-graph questions** have no starting place, because the property being asked about belongs to
the graph and to no node in it:

> Is there a dependency cycle anywhere? · Which module is most expensive to change? · Does the code
> still respect the layering I intended? · Where has behaviour concentrated into one class?

You cannot seed these. There is no symbol whose neighbourhood contains the answer to "is this system
acyclic". **A cycle is invisible from inside every file that participates in it** — open any one of
them and it is a perfectly ordinary import, used a few lines down. The defect isn't in a file. It's in
the loop, and the loop is only visible from above.

Here is my tool's answer on its own dogfood target — 89 modules, 634 import edges, one command:

```
layers         core 9 · data 12 · indicators 16 · analysis 42 · visualization 7 · cli 1
               analysis → core 38 edges · indicators → core 24 · data → core 13

violation    ⚠ analysis ↔ indicators        one backward edge out of 634
cycle          pipeline → cache → pipeline  the classic Python import-order landmine
coupling       core.logging_config  Ca 94   a breaking change here reaches 94 modules
concentration  ZoneVisualizer  35 methods, worst function CC 66 / MI 12.5
```

Read the violation line again. One edge out of 634 goes the wrong way. While the dependency is
one-directional you can lift `indicators` out — into its own package, into an isolated test, into
another project. The moment it is mutual you cannot: pull `indicators` and `analysis` comes with it,
and `analysis` drags most of the system. That is a fact worth knowing before you plan a refactor, and
there is no file you could have opened to learn it.

## Why the gap is structural, not lazy

The dominant framing for code intelligence right now is **retrieval for an agent**. The agent is about
to write code, it needs the right few hundred lines in its context window, and the tool's job is to
deliver them in one call instead of twenty greps. Measured on that job, these tools are genuinely
good — better than mine, several of them.

But that framing has a shape:

- **The unit of value is a slice of source.** A cycle is not a slice of code. It is a statement
  *about* code. There is nothing to return.
- **The consumer is a model with a context budget.** Handing an agent all 634 edges is not help, it is
  noise. The whole-graph answer must be *computed down* to a sentence — and to compute it down you
  have to know which property you were looking for before you start.
- **The store is optimised for lookup.** A vector index answers "what resembles this". A full-text
  index answers "where does this string occur". Neither is a structure you run a
  strongly-connected-components pass over.

So the retrieval tools ship `search`, `callers`, `impact`, `explore` — and then a `files` command that
prints the directory tree.

A directory tree is not architecture. It is where you happened to put things. Two files in adjacent
folders may know nothing about each other; two at opposite ends of the repo may be welded together.
Folders are a filing decision. Dependencies are a code fact.

## What the measurement cost me

This is the part that makes it a measurement rather than an advertisement.

Before this разбор my differentiator list included speed, permissive licensing, and — implicitly —
being unusually candid about my own numbers. All three came off.

**Speed:** gone, 9× to 68×. **License:** gone, MIT against MIT. **Languages:** gone, twenty against
one.

And the fourth one stung most. That project's README publishes the axis on which its own product
**loses**: its dense one-shot answers leave roughly **80% more retrieval context resident** at the end
of a session than a file-reading agent's do — 67k tokens against 18k on one benchmark — stated
directly beneath the headline win, mechanism explained. It also **retracted its own earlier published
benchmark figures**, after discovering that its control arm had been reaching the tool through Bash in
26 of 28 runs, rebuilt the harness to block its own CLI in *both* arms, and re-published lower numbers.

I had been treating "volunteers the axis where it loses" as something that distinguished me. It
doesn't. The most-adopted tool in my field does it too, and did it before I noticed.

What survives is narrower and, I think, more useful to state: a byte-diffable artifact, provenance by
declared root (calls versus references; core versus docs versus tests), argument-level call contracts,
architecture contracts you can fail CI on, docs as first-class references — and no clock anywhere in
an answer.

That last one isn't rhetorical. Its symbol lookup carries a wall-clock timestamp on every node — set
from `Date.now()` at index time, never read back for any logic — so two builds of byte-identical source
return different bytes. It is precisely the property
[the last post](04-the-determinism-test-that-was-right.md) was about.

And I am **not** filing it as a bug, which is worth explaining, because the temptation was real.
CodeGraph makes exactly one byte-for-byte claim — that its Rust kernel's graphs match its reference
engine's — and that claim holds. Run-to-run reproducibility of an answer is *my* commitment, not its.
Reporting it would be marking someone's homework against a rubric they never signed, and dressing a
difference in values up as a defect is the cheapest way to make a comparison dishonest.

The truncation, on the other hand, went upstream —
[#1639](https://github.com/colbymchenry/codegraph/issues/1639) — because it fails on its author's own
terms rather than mine. I read the source before saying so: the true total sits in scope at the line
that throws it away, and the human-readable output prints the *truncated* count as if it were the
total — `Callers of "X" (20)` when there are 79. More to the point, the flagship tool, the single one
its MCP server exposes by default, already marks its own elisions inline with `+5 more`, `+27 more`.
The honest-partial pattern is already in the codebase. It just isn't on this path.

Writing the minimal repro for that issue corrected me a third time. In a 26-file synthetic project the
rows that survive the cut are all functions, not files — so "the file rows sort first" was never a
property of the tool. It is edge-insertion order, and my target merely happened to order that way. The
mechanism I thought I had found got weaker; the defect got stronger. What a truncated answer drops is
**arbitrary**, which is exactly why the answer has to say it was truncated.

## Who each tool is for

The honest resolution isn't that one class of question is better. It's that they have different
consumers.

**Point questions serve the agent mid-task.** It is writing code right now, it needs the right lines,
it wants them in one call. The retrieval tools are built for that and are very good at it.

**Whole-graph questions serve the author deciding what to do.** Can I extract this module? What will
this refactor actually cost? Where has the debt concentrated? Is the design in my README still the
design in my code? Those get asked *before* any code is written — by a person, or by an agent
planning rather than typing.

I serve both. The second is where I'm alone, and it took measuring four rivals to be able to say that
as a fact instead of a hope.

## The honest limits of this story

- **Four tools is not the field.** Several more are queued, and one of them may fill a column.
- **My architecture report is the import graph, not the runtime.** A module reached only through a
  plugin registry participates differently than the static edge suggests, and my call graph has a
  published recall ceiling of roughly 60% against all true edges.
- **"Layer" is a convention until you declare one.** Absent a contract, a layer is the component
  directly under the package root. If your project groups differently, that arithmetic is on the wrong
  grouping.
- **Complexity numbers are heuristics.** `CC` and `MI` measure branching and volume, not whether code
  is good. A long, flat, boring function scores badly and may be perfectly clear.
- **None of this tells you whether your architecture is *right*.** It tells you what it *is*, and
  whether it still matches what you said you wanted. Whether what you wanted was wise is not a graph
  property.
- **I did not reproduce its headline benchmark** (88% fewer tool calls, 62% fewer tokens across seven
  repos). That needs a two-arm headless agent harness with the CLI blocked in both arms. It is its own
  piece of work, and until I do it I am reporting its claim, not confirming it.
- **One language, one repository, one commit.** Everything above is Python, measured on one target.

---

*codemap is MIT, source-only, and does not import the code it analyses. Schema 0.12, 530 tests on
Python 3.11–3.14, 31 operations of which 28 are exposed as MCP tools:*

```bash
pip install codmap         # the distribution; the command and the import are `codemap`
codemap build ./yourpkg -o graph.json
codemap report architecture --graph graph.json
```

*Measured your tool and got it wrong? Open an issue — it has happened twice in this series already,
and both corrections made the write-up better than the original.*

*Previous post: [A month of dogfooding. Then one more repository found seven bugs in two days.](05-the-second-repository.md)*
