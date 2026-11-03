# I tested a rival's architecture gate for silent passes. Then I pointed the same probe at mine, and my own control failed first.

*grafema has the most careful import graph I have measured, and a contract gate that can pass without
checking anything. I wrote down how it fails, filed it, and then asked my own gate the same questions. The
first thing that broke was not a prediction. It was the control.*

---

I build [codemap](https://github.com/kogriv/codemap), a static analyzer that turns a Python package's source
into a deterministic, diffable graph for agents. It has a gate, `codemap check`, which enforces an
architecture contract in CI. This post is about a rival that has a gate too, and about what happened when I
stopped measuring theirs and measured mine.

## The other one

[grafema](https://github.com/Disentinel/grafema) (npm `grafema` 0.4.1, FSL-1.1, which becomes Apache-2.0
after two years) is a code graph that wants to grow past code into services, decisions and knowledge. A Rust
orchestrator, analyzers in Haskell, a columnar graph database with a Datalog engine, a TypeScript CLI and an
MCP server with 52 tools. JS/TS is its primary language; Python is listed as beta.

Its design is the most careful of any import graph I have measured:
- **Every import is a node in the scope it sits in.** Imports inside functions, under `TYPE_CHECKING` and in
  `try:` all come for free, instead of one special case at a time.
- **Module dependencies are derived by a four-line Datalog rule you can read.** In my tool the same kind of
  derivation lives in Python code. A declared rule is also the documentation of what the edge means.

## How I measured it

The same scope as the other posts: **280 files of one Python repository** (207 `.py`, pinned commit). The
import truth is 266 edges and 45 cycles. Two passes, each with its expectations committed **before** the
first run. Every probe that touches installation ran with an empty `HOME`, after one of mine was fooled by
a cache (more on that below).

## The import graph: excellent design, three seams

| | grafema 0.4.1 |
|---|---|
| import edges | 164, of which **163 real** (99.4 %); recall 61 % |
| same edges in 3 runs | identical |
| import cycles | **8 of 45** |
| with two defects fixed | 42 of 45 |

The edges it emits are almost all right. The edges it loses come from three places where two parts of one
system were never run together:
- **Relative imports inside `__init__.py` resolve one package too high.** That is 85 edges, and it logs
  nothing.
- **Any f-string with `!r`, `!s` or `!a` drops its whole file.** The Rust parser sends `"r"`, the Haskell
  decoder expects a number. Here that dropped the file defining the package's main public function. It is
  logged as an error, and the run exits 0.
- **The README's quickstart writes a glob the analyzer cannot read,** so no Python analyzer is downloaded,
  and the result is an empty graph.

With the public function gone, `who analyze_zones` attributed its 88 call sites to a method of the same
name, 109 of them marked `[resolved]`. I filed the three defects
([#480](https://github.com/Disentinel/grafema/issues/480),
[#481](https://github.com/Disentinel/grafema/issues/481),
[#482](https://github.com/Disentinel/grafema/issues/482)) after re-checking each against Python itself, with
a control next to it.

## The gate: real Datalog, and four ways to pass without checking

The second pass wrote bquant's own architecture contract (eight forbidden layer pairs) as grafema
guarantees. The mechanism is real:
- **A three-line recursive rule found exactly the 11 modules** that sit on its own import cycles.
- **A forbidden import added to an ordinary module was caught.**

And then:

| what I did | what the gate said |
|---|---|
| ran `check` once on a freshly analyzed graph | **"No guarantees found", exit 0.** It imports the rules, then lists none of them. That happened on 11 of 11 trees. A CI job that analyzes a clean checkout and runs `check` once passes every contract |
| misspelled a predicate (`edgee`) | **passed**, no warning. Their docs promise "skipped with a warning" |
| edited a rule and checked again | **the old rule ran**: a stored rule is never compared with its file |
| added the forbidden import inside an `__init__.py` | **nothing.** The gate inherits the resolver's blind spot |
| eight rules, default settings | **about 300 s per rule** before the first one is evaluated (evaluation itself: 10–12 ms) |

The other headline features fared similarly on Python:
- **Calls:** where grafema has a call pair, my tool agrees 95.8 % of the time, but grafema has 35.9 % of
  my tool's pairs. No call ever resolves to a class.
- **Data flow (`wtf`):** "no reachable nodes" for every Python variable I asked about, a three-line toy
  included. The same toy in JavaScript returns full chains.
- **MCP:** `find_calls` resolved 0 of 60 calls to a class. Meanwhile the server's own instructions tell an
  agent to prefer it over grep.

Each of these was re-checked on a minimal reproduction with a control and an empty `HOME` before filing
([#483](https://github.com/Disentinel/grafema/issues/483)–[#486](https://github.com/Disentinel/grafema/issues/486)).
One candidate failed its re-check: the import cost did not reproduce on a synthetic tree of 200 small modules
(2 s against 0 s). So it went in only as a section of #483, with both facts stated.

## What I got wrong about them

- **"Only with `--verbose`."** I first wrote that the dropped-file error was visible only in verbose mode.
  I had read an empty log file and a verbose run, never the default output. The default output names every
  dropped file; I corrected it everywhere before filing.
- **"The machine is busy."** Every gate probe timed out, and I blamed CPU contention on a shared machine. On an
  idle machine it hung the same way. The cause was theirs, the 300-second import, and I found it by reading
  their source instead of re-running.
- **"The analyzer works."** My first quickstart probe analyzed all 206 modules. The analyzer was cached in
  `$HOME` from my earlier runs. With an empty `HOME`, a new user gets 0 modules. I caught it only because the
  result contradicted an earlier toy run.

## Then I asked my own gate

The silent passes I had just written up are a *class*: the gate says "ok" without having checked. So I took
the same questions to `codemap check`, wrote down what I expected, and ran them on a two-layer fixture.

**The control failed first.** It was the case that had to fail: `core` imports `analysis`, and the contract
forbids it. My gate said **"✅ Contract satisfied."** The fixture spelled the import `import pkg.analysis.b`.
My graph turned that spelling into an edge to the package root, `pkg`, so no `analysis` layer appeared in it.
Every `from … import` spelling and every `import … as` was right; only the plainest spelling was wrong.
Neither of the two repositories I test on uses it. That is why my 266-edge truth set never caught it.

Then the predictions, most of which I got right:
- **`forbiden = [...]`** (a typo for `forbidden`) read as "no contract found", exit 0.
- **The same typo beside a valid rule:** the valid rule was enforced, the typo never named. That is a green
  tick over a rule that never ran.
- **`no_cycles = "false"` switched the rule on**, because the string `"false"` is truthy.
- **A graph built before a forbidden import was added** passed `check --graph`, with no word about its age.
  Theirs at least prints "Graph is fresh" before checking.

All of these are fixed and released in 0.0.23:
- `import a.b.c` now depends on `a.b.c`.
- A contract the gate cannot fully read is refused, exit 2, with every problem named.
- `check --graph` compares the graph with the tree by content, and fails if the graph is behind.

## And the fixes kept finding things

Each fix was pre-registered and checked against an independent prediction on a third-party tree, pytest
9.1.1. Twice the reconciliation found the next defect:
- **Calls through `pkg.analysis.b.f()` were never resolved in my fast tier.** After the fix, pytest gained
  exactly the 16 call pairs a separate AST script had predicted, no more and no fewer.
- **Reconciling those counters** turned up a rule of mine rewriting `import warnings` into
  `_pytest.warnings`, a module of the package. That made **65 false edges** in pytest, one of them a module
  importing itself. It came from a guard I had once declared safe "by measurement", measured on two
  repositories that happen to have no module named like a standard-library one.
- **Making call counters add up** to the number of calls in the source found two more:
  - a function defined in both branches of an `if` had its counts overwritten by the second body;
  - a closure named like a method of its class was taken for that method, producing a false self-loop in
    pytest.

The rival's gate passed without checking in four ways. Mine passed without checking in three, and the
probe that showed it was a probe I had written for someone else.

## When you would pick grafema, and when codemap

**grafema fits when:**
- **Your code is JavaScript or TypeScript.** That is its primary language. I measured only its Python
  beta, and nothing here says anything about the JS path.
- **You want to write your own rules over the graph.** Datalog with recursion is more expressive than
  codemap's fixed contract vocabulary (layers, independent groups, forbidden pairs, cycle rules).
- **You want one graph for several languages and, eventually, beyond code.**

**codemap fits when:**
- **The code is Python and the answer must be right today.** On this tree grafema is two fixes away from
  seeing 42 of 45 cycles, and today it sees 8.
- **The gate runs in CI.** A gate that passes on its first run, on a typo, or on a stale rule is not a
  gate yet. Mine had three such holes, and they are closed. That is the point of telling this story at
  all.
- **The licence matters.** grafema's FSL lets you use the code and read it, but not take it until it
  converts to Apache-2.0.

## What I take from it

- **Derived edges as declared rules.** A four-line rule is documentation that cannot drift from the code.
  It is a backlog item for codemap as a design note: the licence closes the code, not the idea.
- **What a contract gate must refuse.** An empty rule set reported as a pass, an unknown name, a stored
  rule that differs from its file. I found that list in their gate and then found three of its entries in
  mine.
- **That my truth sets are a shape, not a sample.** Two repositories had made my graph look right on
  spellings neither of them uses. A third one, and a fixture written to attack my own gate, did not.

## What I did not check

- **grafema's `main` branch.** It needs a Rust and Haskell toolchain; I read its source where it mattered,
  and measured only the release.
- **JavaScript or TypeScript**, beyond one toy used as a control for `wtf`.
- **Incremental runs, memory, scale beyond a 20-second tree, the `why`/knowledge layer.**
- **Any answer from upstream yet.** Seven issues are open; none has a reply. If any of them is my misreading,
  I would like to hear it.
- **Whether my gate has a fourth silent pass.** The probe asked what grafema's failures suggested. A
  different rival would suggest different questions.

---

*codemap is MIT, source-only, and does not import the code it analyses.*

```bash
pip install codmap         # the distribution; the command and the import are `codemap`
codemap build ./yourpkg -o graph.json
codemap check --graph graph.json --require-contract
```

*The grafema card, with both passes, every pre-registered expectation and the re-verification of each
issue: [`research/tools/grafema.md`](../tools/grafema.md). The probe of my own gate:
[`gaps/contract_silent_passes_2026-11-03.md`](../../gaps/contract_silent_passes_2026-11-03.md).*

*Previous post: [I measured a tool that asks a model about every file.](10-asks-a-model-about-every-file.md)*
