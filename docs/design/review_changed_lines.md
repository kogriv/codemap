# Design — `review` reads changed lines, not hunks; a module constant has readers

**Status:** 🟡 pre-registered (expectations below, committed before code). **Backlog:** R1-C82. **Gap:**
[`gaps/review_module_constant_2026-11-06.md`](../../gaps/review_module_constant_2026-11-06.md).

## The defect

On bquearch `a948d6c` (one line changed: a tuple constant `SURFACE_NAMES`), `codemap review` returns three
symbols: `[high] shared.contracts` with "123 site(s) — check on signature change", an untouched neighbour
`DEFAULT_SURFACE`, and `SURFACE_NAMES` itself at `[low]` with no consumers. Three causes, all measured:

1. the hunk's context lines are read as changed;
2. a module dossier sums the callers and call sites of every member;
3. a bare-name read of a module constant (`x in NAMES`, imported or same-module) produces no edge.

## D1 — changed lines only

`parse_unified_diff` walks each hunk body and keeps the new-file numbers of `+` lines. A run of `-` lines with
no `+` (a pure deletion) anchors a zero-width range at the new-file line where it stood, as the header did
before. Context lines are dropped. The output shape (`[{file, ranges}]`) is unchanged; ranges get narrower.

## D1b — blank and comment lines do not wake the module

A changed line that is blank or a comment (`#…`, after stripping) and lies outside every definition maps to
nothing, not to the module. Inside a definition it still maps to that definition, which is a textual change
of it. The text is available in the diff, so this needs no source read. Hunks passed as ranges (MCP `hunks`)
have no text and keep the module fallback.

## D2 — a module dossier is about the module, not its members

When a changed line is module-level code (an import, a top-level call, an assignment that griffe did not
make an attribute), the dossier for the module:

- `callers` and `call_contract` are empty: a module has no signature;
- `consumers_by_root` counts **direct** references to the module (`references_to(…, include_members=False)`:
  its importers), not every reference into every member;
- the risk comes from those numbers through the same `_risk`;
- the markdown says "module-level code changed — runs on import in N module(s)" instead of a call-site line.

## D3 — `accesses` edges for bare-name reads of module attributes

In `attrflow._own_attr_uses`, an `ast.Name` load inside a function resolves:

- through the module's imports (`from pkg.contracts import NAMES`) to the target, or
- to `{module}.{name}` when the name is a member of the same module.

It is emitted only when the target is an `attribute` node (the existing soundness gate), as
`accesses`, `access: read`, `resolution: "name"`. Function parameters and names bound in the function
(assignment, `for`, `with`, `except`, import, comprehension) shadow and are skipped. A `global NAME` followed
by an assignment is a `write`. Fast tier. Unresolved bare names are not counted: almost every bare name is a
local or a builtin, and counting them would drown the `attr_access` counter.

**Not covered:** reads at module level or in a class body (`OTHER = NAMES + …`). They are not inside a
function, and `accesses` edges have functions as sources. This boundary goes in the docs.

**Graph change:** new `accesses` edges and `attr_access` counts. No new edge type, so the schema stays
**0.13**. **`ANSWER_FORMAT` 5 → 6**, because the review answer's dossier for a module changes meaning (direct
references, not a sum over members) and its markdown line changes.

## Pre-registered expectations

Run on the R1-C82 branch against 0.0.29, graph of bquearch `shared` at `a948d6c` (fast, `--mode full`), diff
`--relative=research a948d6c^ a948d6c`. E1, E2, E3 and E5 fail on 0.0.29, so the list cannot pass if nothing
was done.

| # | Expectation |
|---|---|
| E1 | `review` on that diff lists exactly one symbol, `shared.contracts.SURFACE_NAMES`; neither `shared.contracts` nor `DEFAULT_SURFACE` |
| E2 | Its dossier has consumers: at least the function holding `contracts.py:474` and one function in `gates`; risk not `low` |
| E3 | Fixture: `gate()` (imported name) and `Spec.check` (same module) each get `accesses → pkg.contracts.NAMES` with `resolution: "name"`; a parameter named `NAMES` produces no edge |
| E4 | Fixture: a diff that changes only a comment line between two functions yields 0 symbols and 0 unresolved hunks; a changed import line yields the module, whose dossier has no call-site contract and counts its importers |
| E5 | Across the 30 most recent commits touching `research/shared`: symbols reported ⊆ those of 0.0.29, and every dropped symbol had only context lines in its hunks (checked by script, not by eye) |
| E6 | Graph: nodes identical to 0.0.29; every added edge is `accesses` with `resolution: "name"`; no edge removed. On bquant cf039ef as well |
| E7 | `check` on bquant cf039ef and the bquearch gate: exit 0, output identical apart from the trailer (`answer format 6`) |
| E8 | Full suite passes; the guards for D1, D1b, D2 and D3 go red when each is reverted, and a cosmetic control mutation leaves them green |

Surprises are reported in the reconciliation.

## Amendment after the first run (2026-11-06, before the rerun)

The first acceptance run on 3a3a703 did not meet **E2**. `SURFACE_NAMES` got one reader,
`ModelBundle.__post_init__`, and stayed `low`. The reader I expected in `gates` is not in a function. It is
module-level code that runs on import (`gates.py:209–212`: `from contracts import … SURFACE_NAMES`, then
`if set(SURFACES) != set(SURFACE_NAMES): raise …`). That is the very check bquearch relies on, and the boundary
I wrote down ("not covered: reads at module level or in a class body") cut it off. A boundary that excludes the
case the item came from is not a boundary; it is the defect again.

**D3b.** Bare-name reads in module-level code and in a class body (outside its methods) are `accesses` edges
too. The source is the **module** or the **class** node. In a class body, names bound in the body shadow; at
module level, names resolve through imports and the module's own members as in D3. Same gate: the target must be
an `attribute` node.

**Also from the first run.** The suite caught the new pair `("accesses", "name")` missing from the resolution
table (R1-C39 guard), so the row is added. E5 reported one dropped definition with a changed line inside
(`shared.registry.Registry`, commit b7bc7e0). It is examined in the rerun, not explained away.

**E2 and E5 are re-measured on the D3b commit.** E1, E3, E4, E6 and E7 held on 3a3a703 and are rerun as well.
