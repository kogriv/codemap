# My tool reported 464,109 import cycles. Every one of them was real.

*On the next package it reported one cycle, and that one did not exist. Two adjacent failures in an afternoon:
a true number that means nothing, and a false number that means everything. Every assertion passed both times —
which is the part of this that is about me and not about the packages.*

---

I build [codemap](https://github.com/kogriv/codemap), a static analyzer that turns a Python package's source
into a deterministic, diffable graph for agents — no index to go stale, no language server to provision. Its
pitch is trust, and for two months the failure mode I hunted was the tool answering **"nothing"** where the
truthful answer is **"I don't know."**

This post is about a failure mode I was not hunting, because no test I own can fail on it: the answer is
**correct and worthless**.

I found it by running the same questions I always run against code that neither I nor my users wrote.

## The list I wrote before the run

Every run whose result will be presented as evidence carries **pre-registered expectations** in this project:
what must hold, what I expect to break, and a stop rule — committed *before* the run, reconciled after, with
anything unlisted reported separately as a surprise. The point is that a green run proves only that nothing
crashed.

Three targets, each a frozen checkout, each breaking a different assumption that both of my existing dogfood
trees share (they are both code written by me, for consumers written by me):

| target | the shape I had never fed it |
|---|---|
| **pytest** `src/_pytest` (78 py) + `src/pytest` (2 py) | the public façade and the implementation are two different top-level packages; a hook system of **52 `def pytest_*`** that nobody calls by name |
| **attrs** `src/attr` (13 py, **9 `.pyi`**) + `src/attrs` (6 py) | stubs next to the code — the public API is described in `.pyi`, not only in `.py`; classes are finished at runtime by a decorator |
| **Pillow** `src/PIL` (97 py) | compiled modules with no Python source (`from . import _imaging as core`); plugin registration as an **import side effect** — `register_open` in **46 files** |

Six controls (things that must hold), five predictions (things I expected to fail). The score:

- **One control failed, on the first target.** `codemap build attrs/src/attrs` → exit code 1,
  `error: Could not resolve alias attrs.field pointing at attr.field`. No graph at all, from a six-file
  package whose entire job is re-exporting from a sibling.
- Determinism held on unseen input: two builds byte-identical on all three; `check` under four hash seeds
  gave one md5 each (`PIL` `fe6bbfad4c` ×4, `attr` `57f2bd1fb8` ×4) — and that control was **not empty**,
  because `PIL` had cycles to render (1 hard + 110 lazy + 11 type-only) and `attr` had 10.
- Entry points were non-empty on both libraries — `PIL` 467, `attr` 60 — which is the control for a bug I
  had fixed two days earlier.
- **Two of my five predictions were simply wrong**, and wrong in the direction that matters: I predicted the
  `.pyi` files would be *silently ignored* — the exact defect class I had spent a month closing. They were
  not ignored. They were read as **full modules** (`PIL` 97 `.py` + 8 `.pyi` = "105 core modules"), which
  turned out to be worse.

And then four findings that were not on the list at all. This post is about two of them.

## 464,109 cycles, all of them real

Three trees of comparable size, one command:

| tree | modules | hard cycles | lazy | type-only |
|---|---|---|---|---|
| codemap | 52 | 0 | 0 | 0 |
| bquant (the consumer) | 92 | 0 | 9 | — |
| **`_pytest`** | **78** | **1080** | **95 001** | **464 109** |

Nothing here is wrong. `_pytest` really does contain a dense knot of mutually-importing modules, and every one
of those cycles is a real cycle in a real import graph. The report took **1632 lines and 10.3 s** to print
twenty of them.

Those are not *large* numbers. They are **combinatorial** ones. Two mutually-dependent modules make one cycle;
a third module in the same knot multiplies the paths through it. `nx.simple_cycles` enumerated half a million
cycles so that a report could show a page of them — and the reader's action, in every one of those 464,109
cases, is the same single action: **break the knot.**

The metric had survived every run I ever made, because both of my trees are nearly acyclic. 0, 0, 9 — a count
is a perfectly good answer when the answer is small. Change the shape of the input and the same definition
stops meaning what it used to mean, without ever becoming false.

One expectation came back **inverted**, in the same output. I had predicted some undeclared default limit would
bite at 78 modules. There is no undeclared limit: the two *less* severe lists truncate at 20 and say so
(`_… 94981 more_`, `_… 464109 more_`). It is the **most** severe list — hard cycles, the one a reader must act
on — that prints in full. 1080 lines of it.

## The guard that refused the fix

The repair is not a smaller number, it is a different unit. The unit of the answer is now the **knot** — a
strongly connected component: *here are N modules that cannot be separated, here is one example cycle, and here
is the edge it is closed by.*

My first version of that did exactly what I just described, and **a guard test went red.**

The test was written two weeks earlier, for what I still consider the worst bug anybody has reported against
this tool. A consumer
measured their own repository and found that `report architecture` printed **"Import cycles: 0 — none — import
graph is acyclic"** on a tree with **two real cycles**
([#11](https://github.com/kogriv/codemap/issues/11)). My import map was module-level only; **26% of their
intra-package import graph was invisible to it**, and the invisible part was function-local imports — which is
precisely what developers use to break a cycle. The blind spot was anti-correlated with the question, and the
omission surfaced in an operation whose output reads as a *safety property*.

Both of their cycles ran through the same module. So when I fixed that, I pinned the property the answer had to
keep: **two loops that share a module are two problems**, and breaking one does not make the other go away.
Strongly connected components glue exactly those two loops into one blob.

So the test refused the fix, and it was right. The fix now carries **cycle rank** — `E − V + 1`, the number of
*independent* loops in the knot. It is linear to compute, it does not explode, and it degrades in the right
direction:

```
bquant   9 lazy cycles  →  1 tangle, 10 modules,  9 independent loops
attr    10 hard cycles  →  1 tangle,  9 modules, 10 independent loops
_pytest       1080      →  1 tangle, 19 modules, 57 independent loops
```

Where the old count meant something, the new number **equals** it. They diverge precisely where the old one
stopped meaning anything. The report on `_pytest` went from **1632 lines and 10.35 s to 137 lines and 0.40 s**,
and the architecture gate from 1080 lines of one violation to one line plus the membership.

What I keep coming back to about this: **I was about to swallow a cycle for the second time, from the opposite
end.** Two weeks ago it was the edges — I could not see the function-local imports, so two cycles read as
zero. Today it would have been the grouping — I could see every edge and would have reported one problem where
there were two. Same property violated, opposite mechanism, and nothing in the second attempt resembled the
first.

The only reason the second attempt failed loudly is that I had written the first one down as a **property**
rather than as a fix. "Cycles must be enumerated, not summarised per blob" was a sentence I could not have
justified in the abstract — on that day it was just what the repair happened to do. As a test it outlived the
repair and refused its replacement. [Post 8](08-eight-of-twelve.md) counted that four of my last five defects
were found by consumers, not by me; this is the compounding version of the same fact — a consumer's report from
two weeks ago doing the reviewing.

## One cycle, and it did not exist

The same run, the next package. `PIL` reported exactly **one** hard import cycle in 105 modules:

```
PIL.ImageFont → PIL._imagingft → PIL.ImageFont
```

Hard cycles are my flagship number — the one thing in the architecture report that is unambiguously
actionable, because a hard cycle is the kind that can break at import time. The second half of this one comes
from the line `from . import ImageFont, _imaging` in **`_imagingft.pyi`**.

A `.pyi` is a declaration file. Python never imports it, never executes its imports, and does not know it
exists; type checkers and IDEs read it. And `_imagingft` is a C extension — there is no Python import there to
break in the first place. So the flagship number, on this target, was **100% false positive.**

The mechanism was three answers to one question, living in three places, each of them a deliberate decision
made at a different time:

| place | what a `.pyi` was | when that was decided |
|---|---|---|
| extractor | a module like any other (griffe merges the stub next to the module) | hard-Python robustness work |
| input manifest | not an input at all (`DEFAULT_INCLUDE = ("*.py", "*.md")`) | scope / input identity work |
| dead-code | excluded — a declaration has no body, so it cannot be dead | the same day as the extractor rule |

That is the same class of defect [post 8](08-eight-of-twelve.md) is about — one concept, several places, no
place aware of the others — except all eight instances I counted there were about an **answer**, and this one
is about the **input**. Nothing in that audit could have found it: it asked every operation what its answer
narrows. It never asked what the *input* was.

The second breakage was quieter and, I think, more interesting. Stubs in the graph but not in the manifest
means the input identity does not describe the input the graph was built from, and the tool **says so, in
plain words**: *"read the input identity as unknown — and with it `--incremental` and `watch`."* Honest. Also
useless: on any tree that ships stubs, incremental rebuild and file watching silently degrade to "I don't
know" and the declaration is the only thing you get. **Declaring a defect does not discharge it** — a rule I
believed I already held, and had apparently only tested where declaring *was* the fix.

`.pyi` imports are now a fourth import scope (`module` · `function` · `type_checking` · **`stub`**), and the
cycle classes stay grouped by **consequence** rather than by mechanism, so a stub-closed cycle joins the class
that never executes. Measured on the frozen checkouts, both versions:

| | before | after |
|---|---|---|
| `PIL` hard import cycles | **1** (built out of a stub) | **0** |
| `PIL` never-executed cycles | 11 | **12** — the cycle moved to its own class |
| `PIL` `import_map` | 262 module-level | 259 module-level + **3 `.pyi`** |
| `PIL` manifest warning | on every answer | gone |
| `query _imaging` dossier | looked like any module | carries `"stub": true` |
| **`_pytest` (78 modules, no stubs)** | — | nodes and edges **byte-identical**, same `scope_id` |

That last row is the control for the promise, and it needed its own frozen tree: my first attempt used codemap
and the consumer package, and **both moved between the measurements** — one by my own edits, one by a
teammate's commit. Comparing before and after across a moving input is the exact trap
[post 4](04-the-determinism-test-that-was-right.md) is about, and I walked into it again while writing the fix
for something else.

## The most confident grade was 63% wrong

Two more findings from the same afternoon, more briefly.

`report dead-code` on `PIL` returned **50 orphan modules (48% of the package)** and **63 symbols graded
`high`** — my most confident grade. The wording is a claim of fact:

```
PIL.BmpImagePlugin.BmpImageFile._open — no inbound calls, references, or decorators
```

**40 of those 63 override a base-class method that has an inbound call recorded in the same graph.**
`BmpImageFile` inherits `ImageFile.ImageFile`, whose `_open` is called by `ImageFile.__init__` via
`self._open()`. The template method — about the most ordinary shape in object-oriented Python — and on it,
63% of my most confident grade was false. The data needed to grade it correctly was already in the graph: 191
`inherits` edges.

An override now cannot be graded `high`. If the ancestor is called, it is `low` — *"reached by dispatch, not by
name"*; if the ancestor is dead too, it is `medium` with the reason named. `PIL` **63 → 15**; codemap
**31 → 31**, the consumer **2 → 2**, because neither of my trees contains the shape, which is why a month of
dogfooding never produced it.

The first version of that fix stopped at the nearest ancestor, and in a three-link chain the middle link is
itself an override with no inbound calls of its own — so it graded a live method `medium`. Its own guard test
caught that before the commit, which is the only reason it is a footnote here instead of a release note.

## The fixture that passed with the fix removed

The façade crash (the control that failed, E1) came out of `griffe.load` itself: merging a `.pyi` resolves
aliases, and an alias into a package that has not been loaded raises. The sibling an alias points at is now
loaded into the same collection and the load retried; if it is not on the path, the error is mine and names
the package, instead of a stranger's traceback. The sibling does **not** enter the graph.

And the same shape produced a confidently wrong answer next door: `report api-surface` on the `pytest` façade
printed **"1 public symbols across 1 modules"** over an `__init__.py` containing **90 lines of re-exports**.
The build had warned — *"0 import edges … read as unknown, not a clean bill of health"* — on stderr, and the
warning never reached the report that is about façades. Now a public alias to an outside definition is an
`export` edge, the report says **"88 more re-exported from outside this root"** and adds that it did not judge
them, and the build's diagnostics travel with it. On codemap and the consumer: 0 external re-exports, not one
new edge.

The rule this bought is the one I would keep if I could keep only one thing from the day.

My guard test for that crash **passed with the fix mutated off.** Every guard in this project is
mutation-verified — revert the fix, the test must go red, because a test that passes on the defect is not a
test. This one stayed green, which means my fixture did not carry the defect: reproducing the crash needs
`@overload` declarations in the stub over a name the runtime module merely aliases, which is exactly what
`attrs/__init__.pyi` has and exactly what my hand-written fixture did not. Rewritten, the mutation takes down
the whole file.

**A fixture is a claim too, and it has to be verified against the old version.** That is now the fourth rule
in my release procedure, and every one of the four was bought with a specific error.

## The lesson

**Measurement cannot tell a true number from a meaningful one.**

The method this whole series rests on is *measure, never assert* — every claim in every post here carries a
number and a link. It is a good method and it has no opinion about this class of defect. 464,109 was measured.
1632 lines were measured. "Layers (105)" over 105 modules, the fourth finding I have not described, was
measured and formally correct: a layer is the first path segment under the root, `PIL` has no subpackages,
therefore every module is its own layer, and the section presents that as an architectural overview. The
assertions were green, the artifact was byte-stable, the schema was untouched, the guards were satisfied, and
the answer was garbage.

What found it was not a new question. It was the same questions asked of a **new shape** of input.
[Post 5](05-the-second-repository.md) drew that lesson about defects — a month of dogfooding along eleven
pre-registered axes on one tree, then a second tree produced seven issues in forty-eight hours, and the
conclusion written down was *the target is a shape, not a sample.* This round says the same thing one level
up, about the **definitions**: a metric is only known to be meaningful on the shapes you have fed it. Mine had
been fed two, and both were written by me.

Four findings, none of them on the pre-registered list, all four closed the same day: override grading, `.pyi`
as a fourth import scope, the façade, and the knot. Two releases, 0.0.19 and 0.0.20, suite **938 → 972**, and
the graph schema **0.13 untouched for a ninth consecutive release** — which is the only reason four repairs of
this size could ship in a day as answer-layer changes rather than as a migration.

The pre-registration earned its keep by being wrong in public: one control down, two predictions confirmed, two
refuted, one inverted, and four surprises. A list of expectations is not a forecast to be proud of. It is the
thing that makes "I was surprised" a claim I cannot revise afterwards.

## The honest limits of this story

- **Three packages are three shapes, not a sample of the ecosystem.** Every conclusion above is "on these
  three", and I have no idea what a fourth shape holds. The only honest prediction I will make is that it
  holds something.
- **Fast tier only.** The deep tier is a sample by construction and is declared as such; it was not part of
  this run except where a question is meaningless without it.
- **No target was edited**, so reproducibility across a *changing* tree — the thing the consumer's gate
  actually does — was not tested here.
- **The simple-cycle count is now gone on purpose.** Anybody who wants it can compute it from the knot's
  membership; the tool no longer offers it, and that is a deliberate loss of information.
- **The knot's internal structure is not computed.** Which single edge, removed, breaks it cheapest is the
  minimum feedback arc set — NP-hard, and I will not promise it.
- **Stubs outside the package are out of scope** (`types-*` distributions, a separate `stubs/` tree), and a
  `.pyi` that **disagrees** with its `.py` is still read as a union, unchecked. What a C extension does
  remains unknowable to a source-only tool; the stub describes the interface and that is all.
- **"63% of my most confident grade was false" is one package's number.** Pillow's plugin architecture is
  unusually template-method-heavy. The defect is general; the ratio is not.
- **Four of the four findings did not reproduce on either of my own trees.** That is the finding — and it also
  means the fixes are guarded by fixtures I wrote after seeing the defect, plus two third-party checkouts
  pinned by commit, and not by a corpus.

---

*codemap is MIT, source-only, and does not import the code it analyses. Schema 0.13, 972 tests, 31 warm
operations (28 exposed as MCP tools):*

```bash
pip install codmap         # the distribution; the command and the import are `codemap`
codemap build ./yourpkg --deep -o graph.json
codemap check --graph graph.json        # architecture contracts, with what it did not judge
```

*If it tells you something confidently empty about your repo — or something confidently enormous — that's a
bug and I'd like the issue. This whole post came from pointing it at three packages I had nothing to do with.*

*Previous post: [Eight of my last twelve bug fixes were the same bug.](08-eight-of-twelve.md)*
