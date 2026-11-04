# Design — a call through a class name that came in by a package re-export

**Status:** ✅ **shipped** (2026-11-04, no schema change, `ANSWER_FORMAT` unchanged), with acceptance reconciled below. Pre-registered in 5a1dec6 before any code. **Backlog:** R1-C75. **Found by:** the Graphify card
([`research/tools/graphify.md`](../../research/tools/graphify.md) §1). Graphify linked
`LibraryManager.create_indicator(...)` to its method, and codemap did not.

## The defect

On a minimal tree, measured on `main` (e7a69dd):

```
pkg/indicators/__init__.py          from .library.manager import LibraryManager
pkg/indicators/library/manager.py   class LibraryManager: create_indicator (classmethod), load_all (staticmethod)

direct.py   from ....indicators.library.manager import LibraryManager; LibraryManager.create_indicator()  → edge ✓
viare.py    from ....indicators import LibraryManager;                LibraryManager.create_indicator()  → none, unresolved
absre.py    from pkg.indicators import LibraryManager;                LibraryManager.create_indicator()  → none, unresolved
```

Same call, same class: whether it resolves depends on whether the import names the defining module or
the package that re-exports it. A bare `LibraryManager()` through the same re-export **does** resolve: the
`ast.Name` branch of `_resolve` follows the re-export. The `ast.Attribute` branch does not.

**Why.** For `Head.a1…ak()`, the R1-C71 loop starts at `cur = imports[Head]`, here
`pkg.indicators.LibraryManager`, and follows a re-export only for each `cur + "." + part`. The head itself
is never followed. `pkg.indicators.LibraryManager` is no node, and `(pkg.indicators.LibraryManager,
create_indicator)` is no re-export, so the chain dies on its first hop. When the head is a module, as in
every R1-C71 case, the head is a node and nothing is lost. A re-exported **class** is the one shape that
falls through.

## D1 — follow the head before the parts

`cur = _follow_reexport(imports[Head])`, then the existing loop over the parts. `_follow_reexport` returns
its argument unchanged when the argument is a node or names no re-export. So every chain that resolved
before resolves to the same target, and only a head that is no node changes.

Kept as it is:
- the soundness guard (`_tally` makes an edge only onto a node);
- `len(parts) == 1` answers whatever it lands on;
- a deeper chain that lands on no node falls through to the dynamic/unresolved rules.

Not in scope, and stays unresolved: a method inherited from a base class of the re-exported class (no node
`Class.method`), and the deep tier, which uses jedi.

## D2 — no schema change, no answer-format change

New `calls` edges and counters moving from `unresolved` to `resolved`. No output changes shape.
`ANSWER_FORMAT` stays 4.

## Independent prediction

[`research/bench/r1c75/predict_reexported_head.py`](../../research/bench/r1c75/predict_reexported_head.py)
reads only the package's source. It does not import codemap. It is derived from R1-C71's predictor, with the
same binding, aliasing and landing rules, R1-C74's caller attribution, and this scope: a chain whose root
is bound to an internal target that is no definition and no module, but lands on one through re-exports.

| tree | sites | predicted edges |
|---|---|---|
| bquant `8efa112` | 6 | 6 (`IndicatorFactory.create` ×2, `ZoneDetectionRegistry.get`, `LibraryManager.create_indicator` ×2, `LibraryManager.ensure_loaded`) |
| codemap `e7a69dd` (package source) | 0 | 0 |
| `_pytest` 9.1.1 | 8 | 8 (`ExceptionInfo.from_exception`/`from_current`/`for_later`, `ParameterSet._parse_parametrize_args`/`_for_parametrize`) |

## Pre-registered acceptance (committed before the code)

Before = `main` at e7a69dd; after = the fix. Fast tier, `PYTHONHASHSEED=0`, the same trees.

- **A1, fixture.** On the tree above, `via_reexport` gets edges to `create_indicator` and `load_all`, and
  `absolute_reexport` gets one to `create_indicator`. `direct` is unchanged. Each function's counter reads
  `resolved` = its call count.
- **A2, edges.** On each of the three trees, the new `calls` pairs are **exactly** the predicted pairs minus
  those already present before. **No** `calls` edge disappears or changes its extras. **No** other edge
  type changes.
- **A3, counters.** Per tree, the sum of `resolved` rises by the number of predicted sites, and `unresolved`
  falls by the same number. No other counter moves. bquant +6/−6, codemap 0/0, `_pytest` +8/−8.
- **A4, codemap on itself.** The graph of codemap is byte-identical before and after, apart from
  `provenance`. Nothing to predict there, so it is the nothing-changes control.
- **A5, nodes.** Outside `extras.calls`, every node is identical.
- **A6, mutation.** Reverting D1, the new unit test fails on A1's assertions. A cosmetic mutation (a
  renamed local) leaves it green.
- **A7, cost.** bquant fast build within ±10 %, alternating runs on an idle stand.

At least A1, A2 and A3 fail if nothing is done.

## Acceptance reconciled (2026-11-04)

Fix in 903466d. Before = the package source of e7a69dd; after = 903466d. Fast tier, `PYTHONHASHSEED=0`,
stand, inside the shared slot accounting. Suite 1127 passed / 3 skipped; CI green on 3.11–3.14.

| | expected | measured | |
|---|---|---|---|
| A1 fixture | edges for `via_reexport` (2) and `absolute_reexport` (1); `direct` unchanged; counters all resolved | as expected; `LibraryManager()` through the re-export unchanged too | holds |
| A2 bquant | new pairs = predicted 6, none removed, no other edge type | +6, all 6 predicted, 0 removed, 0 extras changed | holds |
| A2 codemap | 0 | 0 | holds |
| A2 `_pytest` | new pairs = predicted 8 | +8, all 8 predicted, 0 removed | holds |
| A3 counters | bquant +6/−6, codemap 0, `_pytest` +8/−8 | bquant +6/−6; codemap 0; `_pytest` **+7/−7 in `calls` and +1/−1 in `calls_nested`** | holds once both counter keys are counted (below) |
| A4 codemap graph | identical outside provenance | identical | holds |
| A5 nodes | identical outside `extras.calls` | `_pytest`: one node differs in `calls_nested` | **fails as written**, by my wording (below) |
| A6 mutation | reverting D1 fails the test; a cosmetic mutation does not | 1 failed / 1 passed on the revert; 2 passed on the renamed local | holds |
| A7 cost | bquant fast build within ±10 % | five alternating pairs: old 8.70–8.94 s, new 8.69–8.76 s | holds |

**A3 and A5, read.** One of `_pytest`'s eight sites sits in a function nested in
`FixtureManager.pytest_generate_tests`. Since R1-C74 such a call is counted on its owner under
`calls_nested`, not `calls`. The prediction attributed the site to that owner, correctly, but my wording of
A3 and A5 named only `calls`. The conservation is exact over both keys: 8 sites moved from `unresolved` to
`resolved`. A5 should have said "outside the counter keys", as R1-C74's acceptance did. It is left failing as
written.

The two bquant calls Graphify had and codemap lacked (`LibraryManager.create_indicator` in `zigzag.py` and
`combined.py`) are among the six.
