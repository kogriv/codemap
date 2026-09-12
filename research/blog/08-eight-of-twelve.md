# Eight of my last twelve bug fixes were the same bug.

*I sorted my closed backlog by cause instead of by place, and twelve bugs collapsed into one. So I audited
the mechanism instead of waiting for instance thirteen — thirty-one operations, one question each. The audit
came out full. A day later a user found the axis it did not have.*

---

I build [codemap](https://github.com/kogriv/codemap), a static analyzer that turns a Python package's source
into a queryable graph for agents. Its pitch is trust, and the failure mode I care about most is not a crash:
it is the tool answering **"nothing"** where the truthful answer is **"I don't know."** A crash announces
itself. A confident empty list does the opposite.

I have been hunting that for two months, and I am reasonably good at it. Which is exactly the problem this
post is about.

## The habit that found it

Every closed backlog item in this project gets a write-up: what the defect was, what the fix decided, what
the guard test is, and what the fix does **not** cover. Nothing unusual — just that the write-ups accumulate
in one file, so they can be read as a set rather than one at a time.

One afternoon I listed the last twelve, sorted by **cause** instead of by the place they were found:

| item | what it was |
|---|---|
| a limit | cut the answer and did not say so |
| a gate | did not name what it had not judged |
| an edge | carried the route it resolved by, but not what that route is worth |
| an empty answer | did not say which kind of empty it was |
| a rule | fired and did not name itself |
| flow emptiness | did not distinguish two very different cases |
| a filter | answered with silence and did not declare itself |
| `diff` | silently judged a root nobody asked about |

**Eight of twelve, one sentence: the answer is narrower than it looks, and it is silent about that.**

And the part that actually stung: **four of the last five had been found by consumers, not by me.** Another
repository using my package, an agent session hitting an empty list, a user raising a pin. Not one of them
looked like a systematic blind spot on its own — each looked like its own small bug, got its own fix, its own
test, its own write-up. Twelve careful repairs in a row, eight of them the same repair.

At which point fixing them one at a time, as somebody trips over each, stops being a strategy and becomes a
symptom.

## The message that was three findings

The trigger arrived the day after a release, from the consumer dogfooding my package, and it was one report
with three things in it ([#19](https://github.com/kogriv/codemap/issues/19)). The headline:

```
fast:  ### Flows reached (1 of 285 entry point(s) in root `core`)
       - ZoneAnalysisPipeline.run — step 3
deep:  ### Flows reached (0 of 252 entry point(s) in root `core`)
       _No entry point reaches it within 5 step(s)._
```

Same tree, same version, same command — the only difference is `--deep`, the tier that resolves *more*. And
the better-resolved graph answers with nothing.

**A library has no entry point, by my definition.** `analyze_macd_zones` is the public function a user calls
to enter that package. It has **43 callers, and all 43 are in `tests`, `examples`, `scripts` and `research`**.
My definition of an entry point required `in_degree == 0` — inbound edges counted regardless of which root
they came from — so a public API stops being an entry point precisely because somebody uses it. Nobody
*inside* the package calls it, which is the signature of a public API, not of unreachable code.

The second mechanism is worse, because it gets worse as the tool gets better. On the deep tier one more call
resolves, the head of the chain moves one step further out, and the whole route lands at distance 6 — past the
default depth of 5. **The more completely the graph resolves, the smaller the set of entry points.** On the
fast tier the answer had been right *by accident*: an unresolved call left the middle of the chain looking
like a beginning.

The other two findings in the same message were a filter answering with silence, and a `diff` judging a root
nobody had asked about. Three findings, one shape — the shape I had just counted eight instances of.

## Auditing the mechanism instead of the instance

So the work was not "fix the report". It was to ask all **31 operations** one question — *what does this
answer narrow, and does it say so?* — with a **closed vocabulary** of narrowing classes, the way the edge
vocabulary in the graph is closed: a new class has to be added to the list deliberately, it cannot arrive
silently.

```
limit        a computed list got cut
filter       a predicate threw records away
scope        only one origin root was judged
bound        the traversal stopped at a depth
tier         the answer is a lower bound (fast vs deep)
edge-class   not all classes of edge were read
definition   the shape of the answer depends on a definition
             that may not fit the target
```

Four undeclared narrowings came out of that pass, and every one was **measured, not suspected**:

- **One operation was hiding the larger half.** `columns` returned **331 keys of 1057** as a plain list. The
  narrowing is deliberate — subscripted keys really are the column-ish set, and dict-literal keys really are
  noise — but the consumer sees 331 and has no way to learn there are 1057. It now carries a `filter` block
  with the basis, the total and the dropped count, and a note on how to get the full set.
- **Community detection judged one root and said nothing.** A deliberate decision in the code since the
  multi-root work ("a consumer's root is not a subsystem of the package"), and nowhere in the answer.
  Invisible on a single-root graph — 91 of 91 — and silent on a multi-root one, where it is 2 of 3.
- **The entry-point list did not name its own definition** — the very definition the report above had just
  forced me to change.
- **`export mermaid --scope` cut a diagram from 144 lines to 47 with no mark at all**, and the result read as
  "the package's class diagram". It now emits a `%% scope:` line: Mermaid ignores `%%` when rendering, so the
  note costs nothing in the picture and is visible in the source, which is what people diff and paste into
  issues.

## The partiality that runs the other way

Three of those column operations read a string-dataflow layer, and their partiality points in the **opposite**
direction from everything else in the list. A literal subscript key is indistinguishable from a dict-literal
key, so the set they return is **larger** than the truth, not smaller.

Calling that a "lower bound" — the label I had — is worse than saying nothing. A consumer who trusts "at
least these" will prune too little and keep dead code alive. It got its own wording instead of borrowing the
label that happened to exist.

## The pass nearly broke the rule it was defending

My first version of the fix added the symbol-dossier operation to the list of partial operations, which stamps
"this answer is a lower bound" on the whole envelope.

That was wrong in the other direction. A dossier is **mixed**: where the symbol is defined, what matched, the
signatures — exact. Only one field, "who uses this", comes from the better-than-nothing call layer. A label on
the envelope would have said the symbol's *definition* was in doubt.

**Over-declaring partiality is the same defect as hiding it, pointed the other way.** The rule it breaks is
the one that makes every other label worth reading: *absence of a label means the answer is exact.* Inflate
the labels and you have destroyed the information content of all of them.

What caught it was a test written a month earlier, for that rule, about different operations entirely. So a
mixed answer now declares **per field** — and it declares at the point where the field is built, so the CLI
dossier carries the same flag as the structured answer.

## Then the axis the matrix did not have

The pass ended with a matrix: 31 operations × 7 classes, not one cell reading "applies and is not declared",
and two guards that read the operations' own source rather than a hand-written list. Suite 918 → 928. Done.

Twenty-four hours later — with the audit written and not yet released — the lab consuming my package raised
their pin to the *previous* release and filed
[#20](https://github.com/kogriv/codemap/issues/20).

The graph was inert exactly as promised: **1904 nodes, 4652 edges**, the entire JSON byte-identical between
versions but for one `provenance.version` string. Verdicts stable, 20 runs out of 20. And the **printed cycle
chains** differed between runs — five runs per version, md5 of the rendered lines:

```
0.0.16:  3d8ea0fb  3d8ea0fb  3d8ea0fb  7c4ee567  a9ae9dc7
0.0.17:  3d8ea0fb  7c4ee567  7c4ee567  a9ae9dc7  a9ae9dc7
```

Three renderings, the same three on both versions. The same cycles **as cycles** — what differs is where the
chain starts.

`nx.simple_cycles` enters a cycle wherever its traversal happens to, and that follows set-iteration order,
i.e. string hashes. My code then sorted the cycles by `(length, contents)`, which **looked** like
canonicalisation and could not be: the sort key moves with the rotation. `["a","b"]` and `["b","a"]` are one
cycle and two keys.

Their diagnosis was correct word for word, so the only thing left to check was the perimeter — and the
perimeter was wider than the report. Under eight hash seeds, **three of seven surfaces** diverged: the
architecture gate they hit, the markdown architecture report, and the **structured JSON** that the MCP
`architecture` tool returns to an agent. The dependency report and the living docs were already stable,
because they print counts rather than chains.

So the fix went in at the source — one helper where cycles are born, rotating each to start at its smallest
node and only then sorting — rather than at the consumer the report pointed at. Canonicalising in the gate
would have cured the complaint and left the machine-readable answer leaking. The guard spawns subprocesses,
because `PYTHONHASHSEED` is read once at interpreter start and cannot be patched from inside the test, and it
checks all seven surfaces including the three that were already stable: a regression in those has to fail too,
or the guard is narrower than the claim it defends.

## The most expensive thing about that bug

It impersonates a behavioural change.

The reporter nearly filed it as one — "the new version renders cycles differently" — and did not, only because
they re-measured within a **single** version before writing their conclusion.

Which is the part that concerns me, not them. My own release procedure verifies every claim in a release note
by installing **both published versions** and comparing their output on one tree. A rotation difference reads,
on exactly that comparison, as a behaviour change. They tripped over it first; the next person to trip over it
would have been me, with the release note already sent.

So the procedure has a new line: **when a release claim is about text, fix the hash seed or sweep several.**
The suite now guards it, so the procedure inherits the check instead of relying on whoever is cutting the
release to remember.

## The other rule this bought

Different bug, same week, same shape. My README said **765 tests**; the suite had 918. A number published as
a claim, with nothing checking it, going quietly stale across five releases.

The fix is six lines of CI that grep the claim out of the README and compare it against the test run's own
summary. And the first time I dry-ran that guard, I fed it a pytest summary I had written **from memory** —
and it passed, on numbers that were not real.

**A guard checked with invented data is not a check.** It is the thing the guard exists to stop, performed by
the person building the guard. Re-run with the real summary, it caught a real mismatch on the first try.

## The lesson

**An audit is complete along the axes it has.** Mine was full — every operation, every class, no undeclared
cell — and it could not find the axis it lacked, because it asked whether an answer *declares* itself and
never whether the answer is the *same twice*. Reproducibility of the answer was not a class, and not an
exception either; it simply was not a question the matrix knew how to ask.

It is now the eighth class, and its declaration is the cross-seed guard. The matrix is fuller and it is not
complete, and I no longer think "complete" is a state an audit can reach — it is a state an audit can reach
*as modelled*.

Three days, three releases — 0.0.16, 0.0.17, 0.0.18 — suite 918 → 938, and the graph schema untouched for the
seventh consecutive release, which is the whole reason these declarations could be added as envelope blocks
instead of a migration.

Both of the defects in this post were found by someone using the tool, not by the person who wrote it. The
count of my own closed items is what made the pattern visible; it did not make the next instance visible. Only
a consumer did.

## The honest limits of this story

- **The audit checked declarations on fixtures and on one live tree**, fast tier. Not on a corpus.
- **Reports declare their narrowings in prose**, and I counted that as declaring. No guard compares that prose
  to behaviour, so on a new kind of report it can simply be forgotten. That is a known hole, written down as
  such.
- **Four export formats narrow nothing by construction**, and that was established by reading the code, not by
  measuring it.
- **Eight hash seeds is a sample, not a proof.** It is enough to catch dependence on hash order — before the
  fix, any two or three of the eight would have caught it — and it is not a demonstration that no seed exists
  that breaks something.
- **Other sources of ordering were not investigated:** the community-detection algorithm's own tie-breaking,
  and jedi's ordering inside the deep tier. The deep tier is not byte-stable by construction, and that promise
  is narrowed separately and deliberately.
- **Eight of twelve is a classification I made of my own bugs.** Someone else grouping the same twelve by
  cause might draw the line at six, or at ten. The count is a tool for noticing, not a statistic.

---

*codemap is MIT, source-only, and does not import the code it analyses:*

```bash
pip install codmap         # the distribution; the command and the import are `codemap`
codemap build ./yourpkg --deep -o graph.json
codemap check --graph graph.json        # architecture contracts, with what it did not judge
```

*If it tells you something confidently empty about your repo — or tells you two different things about the
same graph — that's a bug and I'd like the issue. Both bugs in this post arrived that way.*

*Previous post: [Two graphs that share no code agreed exactly. Then one of them disagreed with itself.](07-two-graphs-agreed.md)*
