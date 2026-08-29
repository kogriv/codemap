# Gap — the import map is module-level only, and `architecture` states it as a property

**Found:** 2026-08-28, reported from a second real target as
[issue #11](https://github.com/kogriv/codemap/issues/11) — hours after the same day's
[R1-C28](limit_truncation_2026-08-28.md) shipped the *"always declare what was cut"* rule.
**Backlog:** R1-C29. **Status:** ✅ **closed the same day**, and **verified by the reporter on their own
tree** (§8) — all three levels shipped (`codemap/extract/griffe_extractor.py`, `codemap/query.py`, the
three renderers, `tests/test_r1c29_lazy_imports.py`). §3–§4 carry the corrected measurements.

## 1. What was reported

`report architecture` renders, when the cycle list is empty:

```
## Import cycles: 0

_none — import graph is acyclic._
```

That is an **affirmative property claim**. The import map behind it sees only module-level imports —
a limitation already written down in [`hard_python_robustness_2026-08-25.md`](hard_python_robustness_2026-08-25.md)
as an honest omission of the *extractor*. What was never written down is what it does to the
*consumers*: on the reporter's target, 47 core modules, **29 module pairs are linked only by a
function-local import — 26% of the intra-core import graph — and `architecture` reported 0 cycles
where an AST walk over all imports finds 2.**

Both of those cycles are closed by a function-local import, which is not a coincidence and is the
sharpest part of the report:

> a function-local import is what developers use to break a cycle, so the edges the tool cannot see
> are exactly the edges most likely to close one. **The blind spot is anti-correlated with the
> question.**

## 2. Reproduced, including the asymmetry

The reporter's three-file case, run against `831d7fc`:

```python
# pkg/leaf.py            CONST = 42;  def helper(x): return x + 1
# pkg/user_module_level.py
from leaf import CONST, helper
def go(x): return helper(x) + CONST
# pkg/user_lazy.py
def go(x):
    from leaf import CONST, helper      # same statement, inside a function
    return helper(x) + CONST
```

```
calls    pkg.user_lazy.go         -> pkg.leaf.helper
calls    pkg.user_module_level.go -> pkg.leaf.helper
imports  pkg.user_module_level    -> pkg.leaf
                                       ← no imports edge for user_lazy
```

**Within one statement the call resolves and the import does not.** So this is not "local imports are
unsupported" — the behavioural tier already understands them. Only the import map is built
module-level-only, and every consumer of that map inherits the gap in silence.

## 3. And it is not their codebase — it is ours too, on the flagship target

The report is from a flat-layout project. The obvious question is whether the benchmark target this
whole research track measures on is affected. Measured on `bquant` (88 modules):

| | |
|---|---:|
| intra-package import edges | 277 |
| of them **function-local** | **35 (13%)** |
| cycles codemap reported | **1** |
| cycles present counting all imports | **41** |

So the number this project has been publishing — *"codemap finds the one cycle"* — was a **lower bound
at 2.4% recall**, and nothing in the answer said so. That claim had been repeated in the README, in
[`docs/whole-graph-questions.md`](../docs/whole-graph-questions.md), and in a blog post, in each case as
evidence of precision.

**The first version of this section said 9, not 41 — and that was our own arithmetic being wrong in the
same direction twice.** The ad-hoc AST scan written to check the tool anchored a relative import inside a
package `__init__.py` at the *parent* package instead of the package itself, so `from .candlestick import
…` in `bquant/analysis/__init__.py` resolved to `bquant.candlestick` and vanished. A scan written in
fifteen minutes to audit a tool was less careful than the tool, and it under-counted the very thing it
was auditing. Corrected, the independent scan and the fixed extractor agree **exactly**: 41 elementary
cycles, same 41 sets, 1 of them eager — which is now an acceptance test rather than a footnote.

## 4. What this does to the CodeGraph comparison — the honest version

The same day, this project measured a peer's library-only cycle finder at **136 cycles where codemap
reports 1**, and published that as a precision win. Computing both sides against the all-imports truth
set instead:

| | reported | of the 41 true ones found | precision | recall |
|---|---:|---:|---:|---:|
| codemap, before this fix | 1 | 1 | **100%** | **2.4%** |
| CodeGraph (library API) | 136 | 13 | **10%** | **32%** |
| codemap, after this fix | 41 | 41 | **100%** | **100%** |

Neither tool answers this question well. They over-report from name-resolved call edges and say
nothing; **we under-report from an unread class of import and phrase the result as a property.**
Ours is the smaller error and the worse framing: a false positive costs the reader a check, a
confident "acyclic" costs them the question.

The comparison is not wrong in a way that flatters us by accident, either — the peer's approach walks
call edges, and the call tier *does* see function-local imports (§2). That is precisely why it finds
13 of 41 where we found 1. The mechanism we criticised is the mechanism that gave it recall.

## 5. Decision

Three levels, and the first two ship together because they are the same commitment as R1-C28 —
*an answer must say what it could not see*.

1. **Count and declare, always.** ✅ `import_map: {module_level: N, function_local: M}` on
   `architecture` and `report dependencies`, **whether or not M is zero** — the same rule, and for the
   same reason, as the `limit` block. (Shipped as `function_local` rather than `function_local_skipped`:
   level 3 landed with it, so they are no longer skipped.)
2. **Never phrase an unverified property as verified.** ✅ `_none — import graph is acyclic._` is now
   `_none found in the eager import graph._` plus the counts, in all three renderers that carried the
   sentence (`architecture.py`, `audit.py`, `livingdocs.py` — one sentence copied three times, which is
   why the guard test greps the shipped source for the word rather than asserting on three outputs).
   Ninth application of *`unknown` is never rendered as `none`*, and the first where the confident
   answer was a **safety property** rather than an empty list.
3. **Then actually resolve them.** ✅ Collected by codemap's own AST pass (griffe carries neither) and
   tagged on the edge as `extras.scope = "function"`. Two decisions the level-3 work forced, neither of
   which was obvious from the report:

   - **A cycle now has two kinds, and they are reported separately.** `import_cycles()` stays the
     *eager* graph, because "import cycle" means "breaks at import time" and a lazy import is the
     accepted fix for exactly that — folding them together would report someone's remedy as their bug.
     The rest surface as **"dependency cycles closed only by a function-local import"**: not an
     import-time failure, and still real coupling, because neither module can be extracted without the
     other. On bquant that is 1 and 40.
   - **A class-body import is eager, not lazy.** It runs at class-definition time, i.e. at import time.
     griffe records it no more than the function-local kind (measured, not assumed), so it is collected
     too — as `scope="module"`, where it can close a genuine import cycle.

   Everything except cycles — coupling, layers, dependents, orphans — uses the **complete** map. A
   dependency is a dependency; only the import-order question cares where it was written.

Rejected: dropping the affirmative sentence and saying nothing. Silence is what produced this.

## 6. Acceptance

All met (`tests/test_r1c29_lazy_imports.py`, 12 tests):

- ✅ The reporter's three-file case yields an `imports` edge for `user_lazy`, carrying
  `scope: "function"`, and an ordinary import is not mislabelled as one.
- ✅ No renderer contains the word "acyclic" in a *printed* string — enforced by parsing codemap's own
  source and ignoring docstrings, because the defect was one sentence copied into three files and the
  next copy would not be caught by asserting on today's three.
- ✅ `import_map` is emitted with `function_local: 0` on a tree that has none.
- ✅ The lazy cycle is reported as a lazy cycle and **not** as an import cycle; an eager cycle still is
  one, and is not double-counted as lazy.
- ✅ **Whole-set agreement:** on bquant the fixed tool's 41 cycles are the *same 41 sets* an independent
  AST scan finds — set equality, not just an equal count.
- ✅ README / `whole-graph-questions.md` / the CodeGraph card / comparison / post 6 carry the corrected
  numbers.

## 7. What this does not cover

- `import *`, conditional imports under `if TYPE_CHECKING:` and `importlib` — separate blind spots,
  already listed in [`hard_python_robustness_2026-08-25.md`](hard_python_robustness_2026-08-25.md).
- Whether a lazy import *should* count as a layer violation in `check`. It is a real dependency and a
  deliberate cycle-breaker at once; the contract may want to treat it as its own class. Not decided
  here — level 3 must expose the distinction, not resolve the argument.
- The reporter's second finding (that `impact` is *more* precise than grep because it excludes
  docstring/comment/string mentions) needs no action; it is recorded because a confirmation is
  evidence too.

## 8. Verified on the reporting tree — and it found a cycle the report had missed

The reporter rebuilt at `beef4c9` on their own target (flat layout, 47 core modules) and confirmed:

| | before | after |
|---|---:|---:|
| intra-core `imports` edges | 84 | **113** |
| of them tagged `scope: "function"` | — | **29** |
| pairs linked *only* by a function-local import, and missing | **29 of 29** | **0 of 29** |

29 is exactly the count their own AST measurement had produced, so the two agree on the input, not just
on the shape.

**And codemap reported three lazy cycles where the issue had claimed two.** The third is real, verified
line by line: two module-level hops and one function-local hop closing it. Their scan had collected DFS
back-edges rather than enumerating simple cycles, so a 3-node cycle vanished once its nodes were
coloured. Re-run with a proper enumeration: exactly 3, the same 3 sets — set equality again, on a second
tree, independently.

**That is the second audit script in one day that was less careful than the tool it audited**, in
opposite directions: ours mis-anchored relative imports inside a package `__init__` and under-counted
41 down to 9; theirs collected back-edges and under-counted 3 down to 2. Neither error was in a graph
algorithm anyone would call hard. The lesson is not "write better scripts" — it is that **a check is only
worth what its own verification is worth**, and the cheap check that agrees with your prior is the one
that never gets verified. The regression test now pins the property that made codemap right here
(enumerate every elementary cycle, not one representative per strongly-connected blob), using their
3-node shape plus a second cycle sharing a node.

Their confirmation also settled §7's open question in the only honest way: they have no `[architecture]`
contract, so nothing to gate. Both facts stand — a gate you can walk around by making an import lazy is
not a gate, *and* their three lazy imports exist precisely to avoid an import-time break, so gating them
would punish the fix. Whoever writes a contract has to reconcile those two; the default must not decide
it for them.

## 9. What it cost, and the regression that nearly shipped with it

griffe discards its own AST, so seeing these imports means parsing each module a second
time. The first implementation did that for every module containing the word `import`
(nearly all of them) **and** walked every function's subtree separately, which is
quadratic in nesting. Measured on a 90-module package: the cold fast build went from
**~7.8 s to ~10.4 s**, a ~30% regression I had not measured before writing the docs.

Two fixes, both cheap:

- one pre-order descent carrying the current scope, instead of a walk per function;
- a **tight gate before the parse**: `^[ \t]+(?:from|import)\s` — an *indented* import.
  A module-level import is never indented, so the ordinary file (imports at the top and
  nowhere else) is never re-parsed. Same discipline as the existing `import *` gate, and
  the same guarantee: the gate only decides whether to look, so the answer stays exact.

After both, on the structural pass measured in-process, 7 runs each:

| | median | min | max |
|---|---:|---:|---:|
| before R1-C29 | 2.02 s | 1.65 | 2.22 |
| after, with the gate | **2.35 s** | 2.08 | 3.53 |

**+0.33 s, ~16% of the structural pass** — the honest price of the feature. Whole-build
timings on this machine vary by ±30% run to run, so they are not a usable instrument at
this resolution; that is why the number above is the isolated pass and not the wall clock
of `codemap build`. Stating the noisier number would have been easier and would have meant
nothing.

---

## 10. The other half: the *call* layer had the same blind spot (R1-C30)

R1-C29 closed the **import map**. Call resolution was left exactly as it was, and the
reporter's own three-file example separated the two cleanly:

```python
# user.py
def go(x):
    from leaf import helper
    return helper(x)
```

| tier | `calls user.go -> leaf.helper` |
|---|---|
| `--deep` (jedi) | ✅ |
| fast (default) | ✖ |

That asymmetry is why the issue read as "the tool can see it, the map cannot": on deep it
was true. On **fast** — the default tier, and the one `codemap watch` runs in a loop —
both halves were blind, and the graph a `watch` loop keeps warm was the poorer one.

### The measurement

An independent AST walk over both dogfood targets, counting names bound by an import
written inside a function and the call sites that use them:

| tree | modules | functions with a local import | internal names bound | call sites through them |
|---|---:|---:|---:|---:|
| bquant | 88 | 58 | 46 | 45 |
| codemap | 51 | 45 | 65 | 62 |

Not a corner case on either tree, and denser on codemap itself than on the target it was
found against — `_cmd_*` handlers import their implementation locally to keep CLI startup
cheap, which is the same "deliberate laziness" pattern the issue was about.

### The constraint, which is the whole design

A name imported inside `go` is bound in `go`'s scope and nowhere else. Merging these into
the module-level map would resolve `helper(x)` in a **sibling function that never imported
it** — recall bought with exactly the false-edge shape this project holds against tools
that walk name-matched call edges (`dict.get` resolving into an unrelated class, gap §4).
So the map is per function, with two rules taken from Python's own scoping rather than from
convenience:

- an **enclosing function's** import is inherited — a closure really does see it;
- a **class body's** import is not visible inside its methods, so it is not collected here
  (it remains an eager dependency, and the import graph records it as one since R1-C29).

Order within a body is not modelled: an import at the bottom of a function resolves a call
above it. Same approximation the module-level map already makes.

### Result, checked against an independent tier

Fast tier, both targets, and every new edge verified against a **deep build from the
previous commit** — jedi's answer, computed by code this change never touched:

| tree | `calls` before | after | new | confirmed by deep | lost |
|---|---:|---:|---:|---:|---:|
| bquant | 962 | 986 | +24 | **24 / 24** | 0 |
| codemap | 442 | 502 | +60 | **60 / 60** | 0 |

84 of 84. The deep∖fast gap narrowed from 600 to 576 edges on bquant and from 225 to 165
on codemap (−27%); the fast∖deep direction did not move, i.e. nothing was invented that
jedi disagrees with. `references` edges — the same name map feeds the "used as a value"
layer (R1-C22 D1) — grew by 9 and 1.

The banded **dead-code report did not change** on either tree, and that is worth stating
rather than implying the improvement: its bands cover private functions and orphan modules,
and none of the ten new references landed on one. What did change is narrower and sharper —
**three symbols went from zero inbound edges to one**: `PandasTALoader`, `TALibLoader`, and
codemap's own `DebouncedPoller`. Before this change, `codemap query DebouncedPoller` on
codemap's own graph returned no `used_by` block at all: the only code that constructs it
imports it inside `_cmd_watch`, to keep CLI startup cheap. The watcher shipped the day
before looked, in this project's own graph, used by nothing.

The micro-suite gained `c11_local_import`, whose second function calls the same bare name
*without* importing it: the cheap way to win this recall shows up there as a precision
loss, not as a better score. Suite recall over all true edges: fast 57.1% → **64.7%**,
deep 60.0% → **66.7%**, precision unchanged at 100% on both.

### Cost

No extra parse — the behavioral pass already has the module's AST — and the same
indented-import gate as §9, now shared between the two passes instead of written twice.
36 of 88 bquant modules and 17 of 51 codemap modules pass that gate. Measured in-process,
the map build against the behavioral pass in the same runs: **3.3%** of it on bquant,
**4.1%** on codemap. Absolute times are not quoted: the machine was loaded (load average
18) while these ran, so the ratio is the honest instrument and the wall clock is not.

### What this does *not* cover

- `import pkg.leaf` (dotted, unaliased) followed by `pkg.leaf.other()` stays unresolved on
  fast — the receiver is an attribute chain, not a name, which is a pre-existing limit of
  the fast resolver at module level too, not something this change introduced. `import
  pkg.leaf as lf` resolves.
- `from x import *` inside a function binds names that cannot be enumerated statically; the
  dependency is on the `imports` edge, the call stays unresolved rather than guessed.
- A class-body import still resolves no calls anywhere, by the scoping rule above.

---

## 11. The residual — and the thing underneath it (R1-C30-f1, issue #13)

R1-C30 shipped in the morning; the reporting tree measured it the same day and filed the
one case on their tree that survived it ([#13](https://github.com/kogriv/codemap/issues/13)):

```python
# registry.py
from inner import helper   # re-export

# user.py
def go():
    import registry as _r
    return _r.own() + _r.helper()
```

`_r.own()` resolved, `_r.helper()` did not — **same alias, same statement, same line**.
Their framing is the reason it was worth code rather than a doc line: *"the failure is
silent and asymmetric — the neighbouring call on the same line resolves, so nothing in the
output hints that one edge is missing."*

### Reproducing it made it bigger, not smaller

The case is not about the alias, and not about the local import. Written out in all four
import forms, the fast tier dropped **every** call to a re-exported name:

| form | fast, before | deep |
|---|:--:|:--:|
| `from pkg.api import helper` (module level) | ✖ | ✅ |
| `from pkg.api import helper` (inside a function) | ✖ | ✅ |
| `from pkg import api` … `api.helper()` | ✖ | ✅ |
| `import pkg.api as a` … `a.helper()` | ✖ | ✅ |

The first row is the most ordinary shape in Python — a package re-exposing its API from
`__init__.py`. The mechanism is one line of arithmetic: the resolver computes
`pkg.api.helper`, that names no definition (the definition is `pkg.inner.helper`), and the
soundness guard from R1-C13-f2 drops any edge pointing at a non-node. The guard was right;
the lookup was missing. And **the answer was already in the graph** — the structural pass
emits an `export` edge for every re-export, and the call resolver never read it.

That is the third time in this thread the same shape appears: the deep tier looked more
*capable* when it was merely reading something the fast tier had not been told to read.

### Underneath: a flat tree had no re-export edges to follow

The fix would not have reached the reporter at all. R1-C21 taught the `imports` pass to
recognise a bare sibling (`from alpha import X` where `alpha` sits beside the importer);
the **alias** pass was never given the same rule, so on a flat layout every re-export was
filed as external and produced no edge whatsoever. Not one `export` edge in such a tree —
which silently degraded re-export resolution, `where_defined`, and anything reading them,
not only this fix. Same narrow gate as pass B, same `resolution: "flat"` label.

### Result

Both fixtures now answer identically on fast and deep. On the dogfood targets, verified
against the same independent deep reference as §10:

| tree | `calls` after R1-C30 | after f1 | new | confirmed by deep | lost |
|---|---:|---:|---:|---:|---:|
| bquant | 986 | 992 | +6 | 6 / 6 | 0 |
| codemap | 502 | 521 | +19 | 16 / 19 † | 0 |

† the three unconfirmed are calls to `_reexport_index` and `_follow_reexport` — functions
this change *added*, which cannot exist in a reference graph built from the previous commit.
Named rather than rounded away, because "3 unconfirmed" is exactly what a real false-edge
regression would look like at first glance.

`references` grew by 24 and 8 — the same resolver feeds the used-as-a-value layer.
`export` edge counts did not move on either target (488 and 180), which is the flat rule
declaring itself narrow: both are correctly packaged trees, so it fires zero times, exactly
as R1-C21 measured for `imports`.

Micro-suite: `c12_reexport`, whose second function calls a name the re-exporting module does
**not** carry — so following an export edge that exists is rewarded and guessing at a nearby
definition is punished. Suite recall over all true edges: fast 64.7% → **66.7%**, deep
66.7% → **68.4%**, precision unchanged at 100%.

### What is still missed on fast, after both

The reporter's own split of the 50 edges deep still finds and fast does not, on their tree:
**48 are method calls on an instance** — the declared tier limit, not a defect — 1 is a
module-level attribute, and 1 was this. Worth recording that they filed the one that was
ours and explicitly did not file the 48 that were documented.

---

## 12. §7 resolved, by the gate being run on a real tree (R1-C30-f2)

§7 left one question open on purpose: *should a contract be able to gate the cycles that
close only through a lazy import?* The second real target answered it within a day, not by
arguing the question but by running `codemap check` on a tree with 48 of them:

```
# Architecture check — `shared`
✅ **Contract satisfied.** Rules enforced: no_cycles.
```

…while `report architecture`, **on the same graph**, printed `Import cycles: 0 / none found
in the eager import graph` followed by `Dependency cycles closed only by a function-local
import: 48`. Their summary is the finding: *"`check` did not fail on an unexpected
violation. It failed to not fail where violations exist — and that is worse."*

Note what this is. R1-C29 removed the sentence `_none — import graph is acyclic._` from
three renderers because it stated a property the map could not support. One day later the
same claim was found alive in the **gate** — not as a sentence this time, but as an
unqualified ✅ that the reader completes into "acyclic". The presentation layer keeps being
where this project finds these, and a gate is a presentation layer with an exit code.

**Decision.** Three parts, and the middle one is the actual fix:

1. **The gate stays eager.** A lazy import is how the import-order failure is prevented;
   failing a build for applying the remedy would report the fix as the bug. Unchanged.
2. **The disclosure is mandatory.** A passing `no_cycles` now states what it judged and
   what it did not, with the count — and states it at zero too, on the R1-C28 rule that a
   field appearing only when there is something to say cannot be told from a build that
   never reports it. Structured consumers get the same under `scope`.
3. **`no_lazy_cycles = true`** lets the contract owner take the other position — *a gate
   you walk around by making the import lazy is not a gate* — instead of having one picked
   for them. With it on, nothing is unjudged and the disclaimer disappears.

What §7 got right was refusing to pick a default without a live case; what it got wrong was
treating "do not gate" as the whole answer, when the reachable defect was never the gating
— it was the **silence**.
