# A month of dogfooding. Then one more repository found seven bugs in two days.

*I had been hunting one specific kind of bug for weeks and was good at it. Then I pointed the tool at a
different repo, and it produced seven of them in forty-eight hours — four about the new repo, and three
that had been sitting in my own package the whole time.*

---

I build [codemap](https://github.com/kogriv/codemap), a static analyzer that turns a Python package's
source into a queryable graph. Its pitch is trust: source-only, deterministic, and **honest about its
approximations** — every guess labelled, never a guess presented as a fact.

Which is why the failure mode I care about most is not a crash. It is the tool answering **"nothing"**
where the truthful answer is **"I don't know."** A crash tells you it failed. A confident empty list does
the opposite.

By late August I had been hunting exactly that for a month, and the hunt was not casual.

## What a month of careful dogfooding looks like

Eleven axes, closed one at a time. Each one a pre-registered angle — hypotheses written down *before* the
run, findings categorised by cause afterwards:

reverse impact ("who uses X, can I delete it") · forward call chains ("what runs when X is called") ·
extension recipes ("add a plugin like this one") · string-key dataflow ("trace this column") · change-sets
("what breaks if I change this signature") · RAG self-sufficiency ("give me a chunk I can act on") ·
reachability and dead code · an agent working through the warm `serve` process · whole-graph architecture
(layers, cycles, god-objects) · diff review ("here's a PR, what should I look at") · soundness
(precision/recall of every approximation).

Twenty-one findings, each closed by a milestone. And the confident-nothing class was the *known enemy*,
already caught three times:

- `impact` on a class attribute returning `risk: "none"` — because attribute nodes had no inbound edges at
  all. Not "no risk". No data.
- `canonical` silently choosing one symbol out of as many as twenty-five when a name was ambiguous, so
  every follow-up question confidently answered about the wrong one.
- 71% of the `column` nodes in the string-dataflow layer turning out to be dict-literal keys, not columns —
  making the aggregate view quietly misleading.

So: not naive, not idle, and specifically looking for this. Then I pointed codemap at a second repository —
a different project of mine, with a real engine, laid out as a **flat directory of sibling modules** rather
than a package.

## The first twenty minutes

Two defects, on the very first build, before I had asked the graph a single question.

**Without an `__init__.py`, it crashed.** griffe classifies such a directory as a namespace package, whose
`filepath` is a `list[Path]` rather than a `Path`. Five separate consumers in my code handed that straight
to `Path()`. Five. The traceback named none of the actual cause.

**With an `__init__.py`, it did something worse — it succeeded.** Zero `imports` edges, exit 0, no warning.
And then every report downstream built a confident story on that emptiness:

```
report architecture  →  "no layer violations"   ✅
                        "the import graph is acyclic"  ✅
report dead-code     →  every module in the live engine listed as an orphan
```

A graph of nothing, rendered as a clean bill of health. This is the exact failure I had spent a month
learning to recognise, and I had shipped it in the most basic form imaginable: a layout my target didn't
happen to have.

## Then it kept going

Seven issues in about forty-eight hours.

| # | What |
|---|------|
| 4 | crash on a directory without `__init__.py` |
| 5 | flat layout: 0 import edges, every module orphan |
| 6 | consumer roots too — `impact` answered *isolated* for every symbol, with 8 files holding real call sites |
| 8 | a diagnostic whose consequence sentence said "derived from that empty import graph" while the graph held 404 edges |
| 7 | `dead-code`'s `high` band wrong 39% of the time |
| 9 | the mirror of #7: a local variable shadowing a function counted as a *reference* to it |
| 10 | `--deep` returning **less** than the free `--fast` tier |

Four of those seven are about the new shape. **Three are bugs the new shape merely made visible** — and
those three are the ones worth your time.

## The one that stung

Issue #7 arrived with a sentence I keep re-reading: *"a working graph is what made this visible."*

Fixing #5 had given that repository a functioning import graph for the first time. The first thing it did
with it was surface a defect that has nothing to do with flat layouts at all.

`report dead-code` grades an uncalled private function **`high`** — meaning "no inbound calls, references
or accesses anywhere". Checked line by line against the source: **20 of 51 `high` candidates were false.
39%.** Through three separate mechanisms:

1. the function passed as a **value** — a dict entry, a `default=` argument;
2. a call at **module level**, outside any function;
3. a call from a **nested `def`**.

And here is the detail that turned a bug report into a lesson: **each package exhibited only two of the
three.** Neither target on its own could have shown me the whole defect.

It reproduced on **codemap's own package**: 46 `high` candidates, 17 of them wrong. That code had been
sitting under my own dogfood, every day, for a month. I had been *reading its output* for a month.

## The one that was pure waste

Issue #10 is the one I'd have been most embarrassed to leave shipped.

codemap has two tiers. `--fast` resolves calls by name. `--deep` runs jedi for real type inference, costs
about a minute, and is supposed to find *more*. On the reporter's target:

```
fast  →  487 call edges, 158 crossing a module boundary
deep  →  336 call edges,   0 crossing a module boundary
```

Zero. The expensive tier was strictly worse than the free one.

The mechanism was not "jedi failed". jedi resolved `from leaf import helper` perfectly, to `leaf.helper` —
and my own check, `full_name.startswith(package + ".")`, read that correct answer as *external* and threw
it away. The same boundary bug I had fixed one layer up a day earlier, unfixed one layer down.

Worse: the two tiers were **mutually exclusive** — jedi ran *instead of* the name resolver, never
alongside. So deep was also silently losing real edges on properly packaged trees: five on codemap, five on
bquant. Anyone who had ever paid the minute had been getting a worse answer, for months, on every target.

## The lesson

**A dogfood target is a shape, not a sample.**

Coverage of *questions* is not coverage of *inputs*. My eleven axes were eleven ways of asking, and all
eleven were asked of one tree, laid out one way. There is no eleventh-and-a-half question that would have
found a flat layout. The missing thing was not an angle; it was a shape.

And note what did *not* change: not a fresh pair of eyes, not a new user with different instincts. Same
author, same habits, same known failure class, same week. **Only the input was new.** That is the
uncomfortable part — I cannot attribute this to someone else being smarter, and neither can you.

The corollary is measured rather than hoped, which matters, because "support more layouts" usually sounds
like a trade:

- the flat-layout fix left bquant's graph **byte-identical** — not one edge moved on the original target;
- the dead-code fix was **additions only**: +364 edge pairs on bquant, **0 removed**;
- making the tiers a union lost **no true edge** anywhere; `calls(deep) ⊇ calls(fast)` now holds.

The second shape cost the first nothing. It didn't trade one target's correctness for another's — it
revealed work that had simply never been done.

The small habit that came out of it, and that I'd hand to anyone building analysis tools: **treat "0 of
anything" as a diagnostic, not a datum.** Zero import edges across two or more modules is not a fact about
the code. It is a fact about your tool. codemap now says so at build time, in `stats`, and in three
separate reports — before any conclusion drawn from that graph is printed.

## The honest limits of this story

- It was **one** second repository, not a corpus. I have no idea what a third shape would find, which is
  rather the point.
- Seven issues is not seven independent discoveries: #6 follows #5, #9 follows #7. Call it four
  independent defects and three follow-ups, if you prefer the strict count.
- The suite went **369 → 512** across this arc. That's the honest measure of how much was missing — and
  not one of those tests would have been written from my own repository.

---

*codemap is MIT, source-only, and does not import the code it analyses:*

```bash
pip install codmap         # the distribution; the command and the import are `codemap`
codemap build ./yourpkg --deep -o graph.json
codemap report dead-code --graph graph.json
```

*If it tells you something confidently empty about your repo, that's a bug and I'd like the issue.
Especially if your layout doesn't look like mine.*

*Previous post: [My determinism test went red. The tool was fine.](04-the-determinism-test-that-was-right.md)*
