# I measured whether my graph finds the right context four times. The fourth measurement found a hole in my tool instead.

*`pack` is the part of codemap that hands an agent a budgeted slice of a code graph. It had been tested for
determinism and for budget, never for usefulness. So I measured it against git history, then in both directions,
then with an agent in the loop, then on a benchmark someone else built. One measurement changed the product.
Three said no. And the crashes in the last one led to a security defect in my own analyzer.*

**codemap build-story · post 14** · [Русская версия](14-four-measurements-and-a-hole.ru.md) · [Series index](README.md) · [The repo](https://github.com/kogriv/codemap)

---

I build [codemap](https://github.com/kogriv/codemap), a static analyzer that turns a Python package's source
into a deterministic, diffable graph for agents. Most of this series measures other people's tools. This post
measures the feature of mine that is easiest to sell and was the hardest to show working.

`pack` answers "what should an agent read for this task": give it seed symbols and a token budget, and it
returns the graph's most relevant symbols, ranked, cut to the budget. Every test I had checked that it was
**stable** (same input, same bytes) and **within budget**. None checked that it pointed anywhere useful.

Every measurement below had its expectations written and committed before the run, and each one is published
as it came out.

## V2: git as the oracle

The cheapest honest question: if a commit changed a file of the package, then the other files changed by the
same commit are files the person needed for that change. The graph is built at the commit's **parent**, so no
method sees the change itself. 108 commits of one repository, pinned, all of them, no sample.

Six methods ranked candidate files from the same seed (the most-changed package file):

| method | recall@10 | recall@10 on `tests/` (n = 53) |
|---|---|---|
| `pack` | 0.189 | **0.000** |
| `pack` without a seed | 0.203 | 0.000 |
| `impact` (who uses the seed) | 0.332 | 0.308 |
| `impact` + `pack`, interleaved | **0.366** | 0.179 |
| `grep` for the seed's top-level names | 0.354 | **0.512** |
| random | 0.056 | 0.072 |

`pack` lost to a free `grep`, and on tests it scored **exactly zero over 53 commits**. That zero was not noise.
It was the design: `pack` walked from the seed to what the seed *uses*. Tests use the seed. They could never be
in the pack.

One of my five predictions failed outright: I expected the seed to help, and on average it did not (0.189 with
it, 0.203 without). And one exploratory number kept me from writing `pack` off: of the files that reached any
method's top ten, **47 were found only by `pack`**, more than `grep` (41) or `impact` (17) found alone.

## V3: both directions, and a rule that decided the product

The obvious fix is to walk both ways. The danger is obvious too: I designed four two-way variants *after* seeing
V2's table, on the same repository. That is fitting, and the pre-registration said so. The protection was a
second repository, codemap itself, 83 commits, where no metric had been looked at: pick the best variant once, on
the first repository, then check it on the second without swapping.

The decision rules were written before the run. The variant ships if it beats `pack` by at least 0.10 on the
first repository with an interval above zero, and by at least 0.05 on the second. It becomes the default if the
top of the list does not get worse. And a paid agent test (V4) opens only if it beats `grep` with confidence on
**both** repositories.

| | first repository | holdout |
|---|---|---|
| two-way − old `pack`, recall@10 [95 % CI] | **+0.226** [+0.153, +0.301] | **+0.397** [+0.321, +0.475] |
| two-way − `grep` | +0.061 [−0.019, +0.141] | +0.212 [+0.129, +0.296] |
| recall@5, two-way vs old `pack` | 0.235 vs 0.169 | 0.424 vs 0.166 |

Recall doubled on one repository and tripled on the other, and the top of the list got better, not worse. By the rule written in advance, two-way became the default for a seeded `pack` in **0.0.22**. That is the
one positive result in this post, and it is a product change.

The same rule closed the next door. Against `grep` on the first repository the interval included zero. A
difference you cannot see on 108 commits will not show up on a dozen agent tasks either. **V4 stayed closed.**

One surprise belongs here: on the first repository `impact`+`pack` and `grep` tied (+0.011), and on the second
the graph method won by 0.188. V2's headline, "`pack` loses to `grep`", was a statement about that repository, not about the method.

## V4: the door I walked through anyway

Three weeks later I proposed the agent test, and I did not say that our own rule had closed it. That was caught
before any run. The owner reopened the door on purpose, and the pre-registration opens with that sentence,
because a measurement that slips past its own decision rule is exactly what this project refuses everywhere else.

It was framed as a **pilot**: it estimates cost, spread and how often the protocol breaks, and claims nothing about
`pack`. The agent got a checkout at a commit's parent and the commit message, and had to name the files the
commit changed. 20 tasks, 2 arms, 2 repeats, headless, with a hard stop at $50.

**Pilot 1: `pack` offered as a tool.** 80 runs, $5.08. Recall 0.392 without `pack`, 0.395 with it. And the line
that decided it: **the agent called `pack` once in 40 runs.** In the other 39 it used `Grep`, `Glob` and `Read`.
The +0.003 was a difference between two arms that did the same thing, which is exactly the outcome one of the
expectations had been written to catch.

One more number from that pilot I cannot explain away: precision fell from 0.805 to 0.676 in the arm where `pack`
was almost never called. The only other difference between the arms was one extra paragraph in the prompt
describing the tool. The paragraph alone changed what the agent named.

**Pilot 2: `pack` handed over.** The owner chose the next protocol: put `pack`'s output into the prompt, and give
the other arm `grep` output over the same names, cut to the same length. 80 runs, $5.58.

| | grep context | pack context |
|---|---|---|
| recall | 0.402 | 0.375 |
| precision | 0.728 | 0.724 |
| share of the answer present in the context | 68.8 % | 67.6 % |

Paired over tasks: −0.027, seventeen tasks equal, three lower with `pack`, **none higher**. Both contexts held
the same share of the answer; `pack` spread it over more files (a median of 94 against 50).

I also made a counting error here, caught before it was written down. My first count of "did the agent use its
context" read **0 of 40** for `pack`, because I matched file paths, and `pack` lists symbols by dotted id. Mapped
to files, it is 23 of 40. Which is a finding about the product in itself: asked a question whose answer is files,
`pack` answers in symbols, and the agent has to translate.

## RepoBench: the first oracle I did not build

Every oracle so far came from my own repositories. [RepoBench](https://github.com/Leolty/repobench) (Liu et al.,
ICLR 2024) did not: each row is a file cut just before a line, plus the in-repository definitions the file imports.
One candidate is the definition the next line uses. The task is to rank it first. No model involved; every number
re-derives from pinned dataset, clone and codemap revisions. 300 eligible rows per split, from 448 repositories
drawn.

| ranker | first use of a name | a later use |
|---|---|---|
| codemap's seeded rank | 0.183 | 0.270 |
| random | 0.203 | 0.200 |
| "an imported name not used yet" | **0.350** | 0.117 |
| "the most recently used name" | 0.117 | **0.500** |

On first uses the graph is at chance. A one-line rule doubles it. On later uses "most recent" doubles it again.
Where the graph beats chance, a rank without any seed does the same, so the seed adds nothing measurable. The one
expectation I was least sure of, that the graph would at least break the cheap rule's ties well, failed too.

The control is what makes this a result and not a broken harness. Built on the *untruncated* file, the graph's
accuracy on first uses rises by 0.197: the scoring is wired to the graph, and what the graph knows about the line
is the line itself. **The rank is not worth tuning for this task.** That stands as a negative result. No rescoring,
no subset chosen afterwards.

## The rows I almost did not read

The result table was done. Below it sat the attrition table: why rows dropped. One line said codemap's build
**crashed** on 8 rows of 5 repositories. A build should degrade, not crash, so I took the crashes apart.

Three were a base class re-exported from a package that was not installed. One was a refusal with the wrong
wording. The fifth was labelled "a non-UTF-8 source file". It was not a source file. It was `md.cp38-win32.pyd`,
a compiled Windows extension sitting beside its `md.py` in a vendored library, and codemap had tried to read it as
text.

Why would a source-only analyzer open a compiled module at all? Because it asks [griffe](https://mkdocstrings.github.io/griffe/)
to load the package, and griffe's default is `allow_inspection=True`. For a module it cannot read from source, a
`.so`, a `.pyd`, or a `.pyc` lying beside the package, griffe **imports** it and inspects the live object. Importing
an extension runs its initialisation code. Importing a `.pyc` runs the module body.

My README said: *"source-only … never imports the target"*. A two-file package with a `.pyc` that writes a marker
file on import proved otherwise. The marker appeared under codemap 0.0.10, 0.0.20 and 0.0.36, on the fast tier and
with `--deep`. Vendored `site-packages` and `venv/` directories inside repositories are common, so this was not an
exotic tree. Running codemap on an untrusted tree that contained such a file ran that file.

On the measurement machine the extension itself could not load: it was built for Windows. Whether the import fell
through to anything else on that tree I did not reconstruct. Either way, what stood between the tree and code
execution was the platform tag, not my tool.

Fixed in **0.0.37**: every load passes `allow_inspection=False`, no layer reads a non-`.py` file as source, and a
compiled module without source is listed as not loaded instead of disappearing. **If you run codemap on code you
do not trust, upgrade.**

## The sentence I wrote without measuring

There was one more thing in that reconciliation, and it was mine. Only 35 % of drawn rows survived, and the largest
drop was "the file is not inside a regular package". In the surprises I wrote: *codemap cannot build such a
repository at all.*

I had not measured that. The drop was my harness's own criterion: it built only a regular package around the file
and never handed codemap the rest. The next day I took twelve of those repositories and built them from the root.
**All twelve built**, in 1–31 seconds.

The sentence was struck through in place and corrected. But the probe found two real holes: a directory without
`__init__.py` inside a package (which Python imports happily) was skipped, and an import like
`from engine.dataset import get` pointed at `engine` instead of `engine.dataset`. Fixed in **0.0.38**. On the twelve
repositories: unread files 59 → 0, modules 632 → 707, import edges that reach the exact module **28 → 694**.

## What four measurements add up to

- **One product change.** Two-way `pack`, shipped by a rule written before the run.
- **Three answers of no.** `pack` did not beat `grep` with confidence, an agent did not choose it, and handed to an
  agent it did not help more than `grep` output of the same size. On RepoBench the rank was at chance.
- **One security fix and one layout fix**, neither of which anyone was looking for.

What I can honestly say about `pack` today: it is deterministic, it walks both ways, and on co-change it finds
files nobody else finds. I cannot show that it makes an agent better at anything. Where you would reach for it,
a name-based `grep` is a strong, free baseline, and on these tasks I could not beat it with confidence.

## The lesson I would reuse

**A measurement that fails to show usefulness still pays, through what the harness breaks on.** The table I
wanted said "no". The rows that did not make it into the table found a defect that mattered more than any number
in it. Read the attrition table before the result table.

And: **a sentence in a surprises section is a claim like any other.** It needs a measurement or the words
"not measured". Mine had neither, and it was the one line of that reconciliation a reader would have quoted.

## What I did not check

- **Whether `pack` helps a model complete code.** RepoBench measured the rank `pack` orders by, without a model.
  The paid half stays closed, and nothing here gives a reason to open it.
- **Any agent other than one model, one harness, one prompt.** The pilots are pilots: 20 tasks each.
- **The deep tier.** V2 and V3 used the fast graph only.
- **Budgets in tokens.** Lists were scored whole; recall@5 and @10 stand in for the top of a budget.
- **Other authors' repositories in V2–V4.** Both git oracles come from my own projects, with my habit of changing
  a file together with its test.

---

*codemap is MIT, source-only, and since 0.0.37 that is a tested property rather than a sentence in the README.*

```bash
pip install -U codmap      # the distribution; the command and the import are `codemap`
codemap build ./yourpkg -o graph.json
```

*Every expectation, written before its run: [V2](../pack_usefulness.md), [V3](../pack_direction.md),
[V4](../pack_agent_pilot.md), [RepoBench](../repobench_context.md). The defects:
[compiled modules](../../gaps/build_imports_compiled_modules_2026-11-10.md),
[repository roots](../../gaps/root_builds_lose_modules_and_targets_2026-11-10.md). Measured your tool and I got it
wrong, or found a number here that does not reproduce? Open an issue.*

*Previous post: [The reference gate agreed with my graph to the last edge.](13-the-reference-gate.md)*
