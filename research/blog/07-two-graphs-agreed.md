# Two graphs that share no code agreed exactly. Then one of them disagreed with itself.

*Two implementations with nothing in common — tree-sitter over an embedded graph store, griffe plus jedi
over sorted JSON — returned the same 57 callers, and then the same 78. It is the strongest external check my
tool has ever had. Ten minutes later the same rival's other command answered 30, under a field named
`truncated` that read `false`.*

---

I build [codemap](https://github.com/kogriv/codemap), a static analyzer that turns a Python package's source
into a queryable graph: source-only, deterministic, and labelled wherever it guesses. Its whole pitch is
trust, which leaves one problem I cannot solve from the inside.

**How do I know the numbers are right?** My tests prove the code does what I meant. They cannot prove that
what I meant is what the language does. Every call edge in my graph comes from griffe for structure and jedi
for resolution, glued by my own heuristics, checked against my own expectations. A shared blind spot between
those and my tests would be invisible forever.

The only thing that fixes that is someone else's implementation, built on nothing of mine, asked the same
question about the same code.

## The setup

[OntoIndex](https://github.com/ontograph/ontoindex) (40 ★ at measurement, **AGPL-3.0-or-later**) is a
code-graph engine for agents: tree-sitter parse → symbols, calls, imports, inheritance, routes, doc sections
→ an embedded LadybugDB graph store → Leiden communities → process/flow tracing → BM25 and optional vector
retrieval. TypeScript, 14 languages, a CLI plus 60-odd MCP tools, an HTTP server and a browser UI. It
descends from GitNexus — post 2 of this series — with attribution preserved, and it has been reworked well
past its ancestor.

Not one line of code in common with mine. Different language, different parser, different storage, different
resolution strategy.

Both tools were pointed at the same 280 files — 207 Python, 73 Markdown — of
[bquant](https://github.com/kogriv/bquant) at a pinned commit, materialized into a byte-identical staging
whose content hash the harness re-derived and verified. One detail is worth repeating for anyone doing this:
the live checkout had long since moved past the pinned commit, so the staging was built from
`git archive <commit> | tar -x` into a scratch directory and materialized from **that**. Materializing from
the working tree would have silently produced a different scope, and every number below would have been
comparing two different corpora.

The index: OntoIndex 10 745 nodes / 20 232 edges in 49 s; codemap 4 225 nodes / 11 502 edges in 11.4 s fast,
111 s deep. Those totals are not comparable and the reason is a finding rather than a caveat — their graph
carries markdown heading trees, community membership, process steps and a summary tree, layers I do not model
at all; mine carries 1 007 `column` nodes and 47 `doc` nodes, which they do not. On the part both model —
symbols and calls — they agree far more closely than the totals suggest.

## The agreement

`MACDZoneAnalyzer` has been the probe symbol of this whole research track. codemap says **57 callers**:
months of fixes stand behind that number.

`ontoindex impact MACDZoneAnalyzer --include-tests`, depth-1 CALLS edges, normalized to dotted ids:
**57**. Not approximately — **set-identical**, with nothing on either side alone. Repeated on
`get_sample_data`: **78 against 78**, also set-identical.

Be precise about what that validates. Not that either tool is *complete* — both could miss the same call in
the same way, and a name that never appears as a plain call would be invisible to both. What it does
establish: on a 57-element and a 78-element answer, neither number is one implementation's opinion any more.
Two resolvers with no shared code do not converge exactly by accident.

## The check I nearly skipped

I wrote that paragraph, and then had to check one thing before it was allowed to stand — a day later than I
should have.

The codemap side of that comparison came off a **deep** build, and my own documentation says the deep tier
is not byte-stable: jedi's resolution depends on ordering I do not control, which is why the deep tier is
documented as a *sample*, not a function. A set-identity claim resting on one deep build is resting on a
sample.

So: three deep builds of the pinned scope. The artifacts were indeed **not** byte-identical — one `accesses`
edge out of 12 190 came and went between runs. And the caller sets were **57 and 78 every time, the same
elements**.

The noise is real, and it does not reach the quantity the story is about. Had it reached it, this section
would say something else, and the headline would be gone. The difference between "we got lucky" and "we
checked" is one afternoon, and it is the only thing separating a measurement from a boast.

## The disagreement, inside one product

The same tool has a second command for the same question. `context` is its "360-degree view of a code
symbol", and it carries a block literally named `contextCompleteness` with a `truncated` boolean.

On `MACDZoneAnalyzer`, that boolean reads **`false`** and the list holds **30** callers. Of 57.

On `get_sample_data`: 30 of **78**. Forty-eight callers dropped. `truncated: false`.

Below the cap it is exact — `NotebookSimulator` 28 of 28, `calculate_macd` 6 of 6 — which is precisely what
makes the failure invisible. Nothing in the shape of the response distinguishes "here are all six" from
"here are thirty of seventy-eight".

I spent a while hunting for a rule behind which callers survive: file position, call form, nesting depth.
There is none visible — hits and misses inside one file are syntactically identical, same class, same
indentation. And then the part that makes it sharper: two indexes built from **byte-identical input** return
**different** 30-element subsets of the same 57. Diff two runs over an unchanged repository and callers
appear and vanish.

Over the same graph, their `impact` returns all 57. So this is not a parse limitation or a missing edge. It
is a cap, an unstable order, and a completeness field computed separately from the cut it describes.

## Why this is not a dunk

Because I have shipped this bug's cousin twice.

`search` in codemap truncated at 20 results with nothing in the response saying so. Then a second operation
did the same thing, and I wrote the rule down as a backlog item — *always declare the limit, including when
nothing was cut* — which is now an envelope block `{applied, returned, total, truncated}` that every limited
operation returns unconditionally, computed from the same numbers that did the cutting.

Seeing the third variant in someone else's tool is what taught me what that rule is actually for. My version
of the failure was a **missing** field. Theirs is a **present** one, maintained beside the cut rather than by
it, confidently saying no. That is worse than silence: silence leaves the consumer with an unknown, and a
hand-maintained completeness field converts the unknown into a confident *no*.

## And the graph that reported itself empty

`ontoindex report hubs` — the most-central-symbols view — on a graph of 10 745 nodes:

```
no hubs found (index missing, empty graph, or no connected nodes)
```

Three explanations offered, none of them the real one. The real one is four lines further down, under
`warnings`: the generated Cypher uses `NOT n:Label`, and the vendored store's query parser does not support
label negation. Exit code 0. `--json` returns `"hubs": []`. The same failure in `report surprising-connections`.

Confirmed from outside in one line, using their own `cypher` command:
`MATCH (s) WHERE NOT s:File RETURN count(s)` fails with the identical parser exception, while
`MATCH (s) RETURN count(s)` answers 10 745.

## The uncomfortable part

Here is what makes this card the one I think about most. OntoIndex is **the most careful tool about honesty
I have measured in this entire track.**

Every edge carries how it was resolved and how much to trust it: `CALLS` splits into `same-file` 0.95
(1 082 edges), `import-resolved` 0.9 (2 324) and `global` 0.5 (321) — that last tier being plain
name-matching, exactly the resolution codemap refuses to emit unflagged. Markdown-link imports carry 0.8.
Community membership is stamped `leiden-algorithm`. A caller can ask for `confidence >= 0.9` and get a
high-precision subgraph.

Its `report --help` announces its own lossiness — *"RANKED DISCOVERY VIEW — not a complete impact
analysis… never replaces complete impact output from `ontoindex impact`"* — the JSON carries
`isRankedDiscovery: true`, and the footer routes the reader to the authoritative command. That is my own
"measurements, not verdict" rule applied to command design, and applied better than I apply it.

One file exceeded its 512 KB parse cap. It says so at index time **and in the `warnings` of every
subsequent answer**, with the environment variable that would include it. I record skipped inputs in
provenance and raise a diagnostic; repeating it at every read is stricter than what I do.

And in the same binary: a completeness field that says the opposite of what happened, and a parser error
dressed as an empty result.

That is the lesson worth carrying, and it is about me, not them. **Discipline is not a property a project
*has*. It is a property each answer has to be given, one at a time, by something that checks.** Three places
in that tool had it. The fourth was written by the same people, to the same standard, and nothing caught it
— because what catches it is a test that asks *can this field ever be wrong*, and the absence of exactly
that test is what my own release the same week was about.

## What I took, and what I kept

**Took** — and shipped three days later, in 0.0.16:

- **Per-edge resolution *reason*, with graded confidence.** My edges said *whether* a call resolved, never
  *by what route*. Now they do, as a table keyed by `(edge type, resolution)` carrying the route, the grade
  and a one-line `how`. One deliberate departure: my confidence is an **ordinal** — `exact`, `inferred`,
  `heuristic` — not a number. A 0.5 invites arithmetic the evidence does not support; you cannot average two
  guesses into a three-quarters fact. Naming the route was the borrowable idea, and the float was not.
- **Where in a flow a change first bites.** Their `impact` reports, per affected process, the step at which
  the break first lands. Mine reported who references a symbol. Now it answers "what stops working" by
  walking one reverse BFS from the changed symbol to every entry point — and it names the three ways that
  answer can be partial, rather than presenting it as a function.

**Kept:**

- The `limit` block, always, computed by the thing that did the cutting. Never a second field maintained
  beside it.
- The byte-stable, diffable artifact. Their graph is not reproducible from identical input — 10 745 / 20 232
  against 10 747 / 20 227 nodes and edges across two clean-room stagings, 254 clusters against 256 — and no
  amount of per-edge labelling compensates for that. Their `impact` is set-stable but **order**-unstable:
  384 positional differences between two runs whose sets match exactly, which makes the JSON unusable as a
  diff artifact even when the answer is identical.

**Verdict: learn, strongly — and nothing else.** AGPL-3.0 closes wrapping and integration regardless of
merit: nothing can be vendored into an MIT tool, and serving it would carry network copyleft into anyone's
stack. What it gave me is a better epistemic model and two shipped features.

## The honest limits of this story

- **One repository, one commit, Python only.** Thirteen of their fourteen languages are unmeasured.
- **The agreement is on two symbols**, both of them unique class and function names. A polymorphic name —
  where name-matching goes wrong — would be the interesting probe, and that is a labelled call-site suite I
  have not run against a second tool.
- **Their MCP surface, 60-plus tools, is unmeasured.** Everything here is the CLI, so per-tool caps could
  differ from what I saw.
- **Embeddings were not built** (off by default), so their retrieval quality is untested. `check`, `packs`,
  `wiki`, `export`, `review diff` were read, not exercised.
- **Their cycle output was compared by reading, not by scoring** — six of theirs against forty-five of mine,
  with no independent truth set. The previous card in this track did that scoring properly and it is what
  turned a comfortable comparison into a real finding. The same work is owed here, and I have not done it.
- **Two defaults of theirs are worth a user's attention, not a verdict:** `impact` excludes tests by default
  (55 impacted against 149 with `--include-tests`), and `startLine` is 0-based while named as if it were
  not.

---

*codemap is MIT, source-only, and does not import the code it analyses:*

```bash
pip install codmap         # the distribution; the command and the import are `codemap`
codemap build ./yourpkg --deep -o graph.json
codemap callers yourpkg.module.Thing --graph graph.json
```

*If it tells you something confidently empty about your repo, that's a bug and I'd like the issue. And if
you maintain a tool I measured here and I got it wrong, open one — the last maintainer I filed against fixed
both of my reports on a single day, eleven days after I filed them, which is the best outcome this series has
produced.*

*Previous post: [I measured the 68,000-star competitor. It was faster than mine. That wasn't the finding.](06-two-empty-columns.md)*
