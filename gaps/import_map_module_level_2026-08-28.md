# Gap — the import map is module-level only, and `architecture` states it as a property

**Found:** 2026-08-28, reported from a second real target as
[issue #11](https://github.com/kogriv/codemap/issues/11) — hours after the same day's
[R1-C28](limit_truncation_2026-08-28.md) shipped the *"always declare what was cut"* rule.
**Backlog:** R1-C29. **Status:** ✅ **closed the same day** — all three levels shipped
(`codemap/extract/griffe_extractor.py`, `codemap/query.py`, the three renderers,
`tests/test_r1c29_lazy_imports.py`). §3–§4 carry the corrected measurements; the issue stays open
until the reporter confirms on their own tree.

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
