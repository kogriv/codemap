# Gap — the import map is module-level only, and `architecture` states it as a property

**Found:** 2026-08-28, reported from a second real target as
[issue #11](https://github.com/kogriv/codemap/issues/11) — hours after the same day's
[R1-C28](limit_truncation_2026-08-28.md) shipped the *"always declare what was cut"* rule.
**Backlog:** R1-C29. **Status:** 🔴 open.

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
whole research track measures on is affected. Measured, by AST over `bquant` (88 modules):

| | |
|---|---:|
| intra-package import edges, all | 266 |
| of them **function-local** | **35 (13%)** |
| cycles codemap reports | **1** |
| cycles present counting all imports | **9** |

So the number this project has been publishing — *"codemap finds the one cycle"* — is a **lower
bound at 11% recall**, and nothing in the answer said so. That claim had been repeated in the README,
in [`docs/whole-graph-questions.md`](../docs/whole-graph-questions.md), and in a blog post, in each
case as evidence of precision.

## 4. What this does to the CodeGraph comparison — the honest version

The same day, this project measured a peer's library-only cycle finder at **136 cycles where codemap
reports 1**, and published that as a precision win. Computing both sides against the all-imports truth
set instead:

| | reported | of the 9 true ones found | precision | recall |
|---|---:|---:|---:|---:|
| codemap | 1 | 1 | **100%** | **11%** |
| CodeGraph (library API) | 136 | 6 | **4%** | **67%** |

Neither tool answers this question well. They over-report from name-resolved call edges and say
nothing; **we under-report from an unread class of import and phrase the result as a property.**
Ours is the smaller error and the worse framing: a false positive costs the reader a check, a
confident "acyclic" costs them the question.

The comparison is not wrong in a way that flatters us by accident, either — the peer's approach walks
call edges, and the call tier *does* see function-local imports (§2). That is precisely why it finds
6 of 9 where we find 1. The mechanism we criticised is the mechanism that gave it recall.

## 5. Decision

Three levels, and the first two ship together because they are the same commitment as R1-C28 —
*an answer must say what it could not see*.

1. **Count and declare, always.** The AST walk already visits function-local import nodes to decide
   not to use them; counting them is free. `architecture` (and `check`, and `report dependencies`,
   and anything reading `imports`) carries `import_map: {module_level: N, function_local_skipped: M}`
   **whether or not M is zero** — the same rule, and for the same reason, as the `limit` block.
2. **Never phrase an unverified property as verified.** `_none — import graph is acyclic._` becomes
   `_no cycles found in the resolved import graph — M function-local import(s) were not resolved._`
   The same edit applies to `livingdocs.py:154` ("Import graph is acyclic.") and to any other
   affirmative phrasing over a partial map. This is the ninth application of *`unknown` is never
   rendered as `none`*, and the first where the confident answer is a **safety property** rather than
   an empty list.
3. **Then actually resolve them.** Feed function-local `import` / `from X import ...` into the import
   map the way they already feed the call tier, tagged so a consumer can tell a lazy import from a
   module-level one (they are not the same fact: one runs at import time, one does not). Bigger, and
   worth doing *after* 1–2 land, because the declaration protects every future consumer while a fix
   protects one release.

Rejected: dropping the affirmative sentence and saying nothing. Silence is what produced this.

## 6. Acceptance

- The three-file reproducer yields an `imports` edge for `user_lazy` (level 3), and before that, a
  non-zero `function_local_skipped` count in `architecture` (levels 1–2).
- `report architecture` on a graph with unresolved local imports never contains the word "acyclic".
- The block is emitted with `function_local_skipped: 0` on a codebase that has none.
- A guard test that fails if a renderer states an import-graph property without consulting the block.
- README / `whole-graph-questions.md` / the CodeGraph card / post 6 carry the corrected numbers
  (§3–§4), because they currently publish the uncorrected ones.

## 7. What this does not cover

- `import *`, conditional imports under `if TYPE_CHECKING:` and `importlib` — separate blind spots,
  already listed in [`hard_python_robustness_2026-08-25.md`](hard_python_robustness_2026-08-25.md).
- Whether a lazy import *should* count as a layer violation in `check`. It is a real dependency and a
  deliberate cycle-breaker at once; the contract may want to treat it as its own class. Not decided
  here — level 3 must expose the distinction, not resolve the argument.
- The reporter's second finding (that `impact` is *more* precise than grep because it excludes
  docstring/comment/string mentions) needs no action; it is recorded because a confirmation is
  evidence too.
