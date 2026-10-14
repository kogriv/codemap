# I measured a tool that asks a model about every file. On my scope, mine won — and the scope is the caveat.

*jevgrep builds no index and no graph: it walks a repository and asks a classifier one yes/no question per
file. On the questions I asked it found almost everything, for cents. My tool had the same answers in half a
second, exactly. That is the unremarkable part. The useful part is the list of what each of them cannot see.*

---

I build [codemap](https://github.com/kogriv/codemap), a static analyzer that turns a Python package's source
into a deterministic, diffable graph for agents. This post puts it next to the most different tool I have met
so far, and tries to say, as plainly as I can, **when you would pick the other one.**

## The other one

[jevgrep](https://github.com/dzhng/jevgrep) (`@dzhng/jevgrep` 0.8.0, MIT) answers *"which files should a
coding agent read for this question"*. It has no index, no embeddings, no graph, no build step. It walks the
tree in four stages, and at each stage it sends source to a model and gets back a **probability per declared
yes/no question** — no text generation. The model is Jev, a hosted "decision" model; the tool needs a provider
key and sends the files it considers to that provider.

Install is three packages, 7 MB, 7 seconds. That is the lightest install of any tool I have measured on
this scope, and it is a real advantage.

## How I measured it

The same scope as the other cards in this series: **280 files of one Python repository** (207 `.py`, 73 `.md`,
pinned commit), five questions, and a ground truth computed from my own graph at file level. Three things I did
to keep myself honest:

- **The expectations were written first.** Eight predictions, four controls (one of them: the credential never
  appears in any output), and a stop rule at $3.50 of spend — committed *before* the first paid request.
- **It was the real model.** Seventeen searches against the unmodified tool through a provider, **$1.14**
  in total by the provider's own meter.
- **The truth is mine.** That is a circularity and I will come back to it: the "answer key" comes from the
  tool I am comparing against.

| # | question | codemap truth (files) |
|---|---|---|
| T1 | where is `analyze_zones` defined | 2 (a function and a same-named method) |
| T2 | which files call `MACDZoneAnalyzer` | 22 |
| T3 | what depends on `MACDZoneAnalyzer` | 29 |
| T4 | what breaks if the signature of `analyze_zones` changes | 49 |
| T5 | architectural layers, import cycles | not a file set |

## The result

| | jevgrep (real Jev) | codemap |
|---|---|---|
| **T1** defined where | both definitions found, at ranks 1 and 2, among 36 files returned; the name's ambiguity is not mentioned | both returned **with `ambiguous` declared** and the signatures |
| **T2** callers | **21 of 22** in all six runs; 26–27 files returned, precision 0.78–0.81; misses one test | 22 files |
| **T3** dependants | **25 of 29** (tests 19/19, scripts 2/2, examples 1/1, **docs 3/7**); 48 files, precision 0.52 | 29 files, split by root |
| **T4** signature change | **26 of 49** (tests 8/8, examples 9/9, research 6/6, **docs 2/24**); **no argument shape anywhere** | 49 files, and per call site `posargs` / `kwargs` / `splat` |
| **T5** layers, cycles | a ranked list of 156–163 files, **silently** — no layer or cycle vocabulary, no statement that this is not what was asked | 8 layers, 0 hard cycles, 3 lazy tangles |
| time per question | 18–75 s (94–311 s with `--concurrency 1`) | 0.5–0.9 s after a 10 s fast build (2 min deep, with consumers and docs) |
| cost per question | $0.026–0.15 | 0 |
| same question twice | not byte-identical, even serialised — **which** files carry their source changes between runs | byte-identical on the fast tier; the deep tier is a sample and says so |
| needs a key / network | yes — **source files leave the machine** | no |

On this scope, on these questions, **codemap is more exact, faster, free, repeatable and offline.** I did not
expect the model-judged search to come as close as it did.

## What I predicted wrongly

I wrote eight predictions down before running. Three failed, and all three failed in the tool's favour.

- **I expected a haystack.** *"Which files call X?"* I predicted recall above 0.9 and **precision below 0.5**
  — the answer lists more than 44 files. It returned 26–27, precision 0.8. A person can act on that list.
- **I expected it to cost what the bytes said.** It cost less: $0.026–0.15 per search, mostly under my floor.
- **I expected a warm repeat to be nearly free.** It cost 47% of the cold one and was **not a replay** — the
  list was the same and the set of files carrying source blocks changed. `analyzer.py`, one of the two real
  definitions, went from "source below" to "locations only" between two runs of one question.

## The caveat that matters: the truth is mine

"Codemap is exact" is, in this table, **circular**: the ground truth is codemap's own graph, so the table
measures how closely jevgrep agrees with codemap, and says nothing about whether codemap is right.

The independent check is a different card, same tree: three implementations that share no code — codemap, a
tree-sitter graph and a SCIP index — gave **58 (codemap), 58 (tree-sitter) and 60 (SCIP)** callers of the same class, and the SCIP
result contained codemap's set exactly, plus two intra-class calls. That is the evidence that the key itself is
sound for T2. For T3–T5 I have no second implementation, and the table should be read with that in mind.

And the scope is the other half of the caveat. **I chose it, and it is my tool's home ground**: Python, a
package with an import graph, five questions each containing the exact name of a symbol. A symbol name in the
question is the best case for a graph and the easiest case for a text-matching model alike. I did not ask
jevgrep a question without a name in it — *"where do we normalise time zones"* — and I did not measure it.

## When you would pick jevgrep, and when codemap

This is the part I would want from someone else's post.

**jevgrep fits when:**

- **The tree is not Python.** codemap reads Python source (and Markdown, for documentation links) and nothing else. jevgrep has grammars for Go and Rust,
  TypeScript through the compiler, and a text fallback for everything else.
- **You do not want a build step.** Point it at a directory and ask. Nothing to go stale, nothing to
  rebuild, no parser to provision.
- **The question is a sentence, not a symbol** — plausibly, and that is the case I did not measure.
- **It is a one-off.** A few cents and a minute, once, on a repository you will not analyse again.

**codemap fits when:**

- **The answer must be right and repeatable.** Same input, same bytes, in a CI job, in a diff.
- **The question is about structure** — blast radius with edges, a call contract, layers, cycles. On T4 the
  model-judged search returned 26 of 49 files and **zero** information about how any of them calls the
  function. On T5 it answered a different question without saying so.
- **The code must not leave the machine.** jevgrep's own README tells you to choose a search root you
  *intend to send*.
- **You ask many questions.** The build is paid once; after it, a question is free and takes less than a
  second.
- **Documents are part of the question.** jevgrep found 3 of 7 and 2 of 24 documents; it found code almost
  completely. If your dependants include documentation, that is where it is weakest.

The two are not substitutes. One is a **starting set of files to read**; the other is **an answer you can
build a check on**. For *"put the right files in front of an agent"* both work, and jevgrep does it for
cents with no setup. For *"what breaks if I change this"* only one of them is answering that question.

## What I take from it

Nothing in the code. The mechanism is remote and paid; my thesis is the opposite trade — local, free,
deterministic, offline — and adopting any part of theirs would cost exactly that.

Two things in the *discipline*, though, and I am glad I looked:

- **Their `doctor` checks the model's semantics, not its connectivity.** It sends a synthetic input whose
  correct answer is known and refuses a backend that connects and answers wrongly — a stub that answered
  `0.0` was rejected. codemap checks that its dependencies *import*; it does not check that they still
  resolve a known fixture correctly. That is now a backlog item, small, cheap, and the best thing this
  measurement produced.
- **They disclose a failure.** When a request fails the answer says `discovery incomplete`, quotes the
  provider's message and counts the failed requests. I had written, from the first runs, that the tool does not
  say what it did not reach. That is not true of failures, and it was my reading, not theirs.

## What I did not check

- **One repository, five questions, one seed per cell.** Not a ranking of judges and not a claim about any
  other tree, language or size.
- **Questions without a symbol name.** The case I expect to favour jevgrep, and the one the table cannot speak
  to.
- **What an agent does with either answer.** That is the metric their own headline reports; it needs an agent
  in the loop and is a project of its own.
- **How much was uploaded.** I measured it against a local stand-in and the stand-in walks far more of the
  tree than a real model does, so the figure does not transfer. With the real model I only know the bill.
- **Why documents are found so poorly.** The numbers are there; whether it is the question put to a Markdown
  file, the preview it yields, or the model, I did not separate.
- **A reading from my own first phase.** Early on, with a local stand-in in place of the model, I recorded
  a scheduling effect in their client. It was an artifact of that stand-in — it answered each request as a
  whole where the client batches differently from run to run — and it is retracted in the card. Everything
  in the table above was measured with the real model, which never used the stand-in.

---

*codemap is MIT, source-only, and does not import the code it analyses.*

```bash
pip install codmap         # the distribution; the command and the import are `codemap`
codemap build ./yourpkg --deep -o graph.json
codemap query --graph graph.json analyze_zones
```

*The card with every number, the pre-registered expectations and the per-run files:
[`research/tools/jevgrep.md`](../tools/jevgrep.md). If I misread jevgrep on a question it was designed for,
I would like to hear it.*

*Previous post: [My tool reported 464,109 import cycles. Every one of them was real.](09-true-and-worthless.md)*
