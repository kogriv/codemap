# Design — `forbidden` with `indirect = true`: no chain of imports from one layer to another

**Status:** ✅ **done** (2026-11-05, fix 5b4d1f6, no schema change, `ANSWER_FORMAT` unchanged), acceptance reconciled below. Pre-registered in 312c104, oracle in e466ee1. **Backlog:** R1-C78. **Gap:**
[`gaps/forbidden_direct_only_2026-11-05.md`](../../gaps/forbidden_direct_only_2026-11-05.md). **Reference:**
import-linter's `forbidden` contract, which forbids chains by default (`allow_indirect_imports = False`);
measured in [`research/tools/import-linter.md`](../../research/tools/import-linter.md).

## The defect

`forbidden = [{from = "data", to = "analysis"}]` judges one edge. A chain `data → core → analysis` passes it.
In a tree with a strict, fully declared `layers` stack the chain is caught anyway, edge by edge. Outside one
(plugins, side packages, a `utils` that no layer names) it passes green, and "`data` must not depend on
`analysis`" cannot be written at all.

## D1 — opt-in per item: `indirect = true`

```toml
forbidden = [
    { from = "core", to = "analysis" },                    # one edge, as today
    { from = "data", to = "analysis", indirect = true },   # no path at all
]
```

The default stays direct. Changing what `forbidden` means would change the verdict of every consumer's
existing contract on the day they bump the pin, which is the R1-C48 lesson: a release that changes a verdict
nobody asked to change. `indirect = false` is the same as leaving it out.

## D2 — which graph

The same graph the direct rule reads: the **core** import graph, **every import scope** (module level,
function-local, `if TYPE_CHECKING:`). A chain through a lazy import is a dependency the rule is about; a
contract that wants only the eager graph can say so later (D8). Every core module may sit inside a chain,
including modules of the `from` and `to` layers themselves and modules of undeclared layers. Same-layer edges
count (`data.a → data.b → analysis.x`). Consumer roots (tests, examples) are never in a chain: they are
outside layering for every rule.

## D3 — what is reported

One violation per broken item, rule `forbidden`, summary
"`data` must not reach `analysis`, directly or through other modules: N module(s) of `data` reach it".

- `edges`: the **entry edges**: each import `u → v` with `v` in `to`, `u` outside `to`, and `u` reachable
  from `from` (a direct `from → to` edge is one of them). These are the places the dependency enters the
  forbidden layer.
- `modules`: one **witness chain** per entry edge, written `a → b → … → v`: a shortest chain from some
  module of `from` to `u`, then `v`. Ties go to the lexicographically smallest chain, so the answer is
  deterministic. More than 25 chains: the first 25 and "… N more".

Why entry edges rather than every chain: the number of chains grows with every module that imports into the
path, and the reader needs the places to cut, plus one proof for each. The chain says *how far the damage
reaches*, which is the part import-linter answers better today; the entry edge says *which line to change*,
which is the part codemap answers.

## D4 — schema

`forbidden[i]` accepts the keys `from`, `to`, `indirect`. `indirect` must be a boolean; anything else is a
problem under R1-C69 (exit 2, nothing enforced). Before R1-C78, `indirect` is an unknown key and refused,
so no contract written for the new version can be silently half-read by an old one.

## D5 — applicability unchanged

An indirect item is applicable when both names exist, as a direct one is (R1-C62). Whether a chain is
possible is not asked.

## D6 — no answer-format change

For a contract without `indirect`, every answer is byte-identical: `RENDERED_SHA` and the satisfied line
(`forbidden (n of n applicable)`) do not move. The chain answer appears only for a contract that opts in,
under the existing `edges`/`modules` fields. `ANSWER_FORMAT` stays 4. If the run shows any existing answer
moving, that is a defect of this change, not a reason to bump.

## D7 — the satisfied line names the kind

When at least one item is indirect, the enforced-rules line reads `forbidden (n of n applicable, k indirect)`.
A reader of a green run must be able to tell which kind of rule held (the R1-C49-f1 rule: every enforced
rule names itself). For a contract with no indirect item, the line is unchanged (D6).

## D8 — not now

- an eager-only chain option (`scopes = ["eager"]`);
- `indirect` for `independent` groups;
- `protected` (only the listed layers may import this one): the same graph walk in the other direction;
  separate entry when someone needs it.

## Pre-registered acceptance (committed before the code)

The independent oracle for chains is **grimp** (`find_shortest_chain`): no shared code with codemap, and its
graph matched codemap's truth set on this tree 266 of 266 edges.

- **A1** toy `pkg` (`data/d.py` imports `core.c`, `core/c.py` imports `analysis.a`):
  `{from="data", to="analysis", indirect=true}` → exit 2, entry edge `pkg.core.c → pkg.analysis.a`, chain
  `pkg.data.d → pkg.core.c → pkg.analysis.a`. The same item without `indirect` → exit 0.
- **A2** the middle import function-local; under `if TYPE_CHECKING:` → exit 2 each.
- **A3** the chain goes through `pkg/utils/u.py`, `utils` not in any rule, `layers` declared without it →
  exit 2.
- **A4** a consumer root (`tests/`) that imports both ends does not create a chain → exit 0.
- **A5** two chains of length 2 and 3 into the same entry edge → the length-2 one is reported; two equal
  chains → the lexicographically smaller; two runs byte-identical.
- **A6** `indirect = "yes"` → exit 2, "must be true or false"; `indirect = false` → the same answer as
  without the key.
- **A7** bquant `aca0718`, its contract as it is → output byte-identical to 0.0.26.
- **A8** bquant `aca0718` with all eight forbidden pairs made indirect: on the tree as it is, and on the
  three mutations of the import-linter card (`core/config.py` imports `bquant.analysis` at module level, inside
  a function, under `TYPE_CHECKING`), the set of broken items equals the set of pairs for which grimp finds a
  chain, and for each broken item the shortest codemap witness has grimp's shortest-chain length. The oracle's
  sets are computed and committed **before** the codemap run (§«Oracle», added in a commit of its own).
- **A9** mutation: removing the indirect branch turns A1–A3 red; a cosmetic change leaves them green.
- **A10** `RENDERED_SHA` and `ANSWER_FORMAT` 4 unchanged; bquearch HEAD byte-identical before and after.

At least A1–A3 and A8 on the mutations fail if nothing is done.

## Oracle (committed before any code)

[`research/bench/r1c78/oracle_grimp_chains.py`](../../research/bench/r1c78/oracle_grimp_chains.py) →
[`oracle.json`](../../research/bench/r1c78/oracle.json), grimp 3.18, bquant `aca0718`, the eight pairs of
bquant's `forbidden`, every import scope:

| tree | pairs with a chain | shortest chain, hops |
|---|---|---|
| as is | none of 8 | — |
| M1 module level | `core → analysis`, `data → analysis`, `indicators → analysis` | 1, 2, 3 |
| M2 function-local | the same three | 1, 2, 3 |
| M3 `TYPE_CHECKING` | the same three | 1, 2, 3 |

So A8 expects: as is, exit 0 with all eight indirect; on each mutation, exactly these three `forbidden` items
broken (plus `layered` for the edge itself), and codemap's shortest witness for them 1, 2 and 3 hops. The
other five pairs stay unbroken: `bquant.analysis` (the package module M1 imports) does not itself import
`indicators` or `data`, so `core → analysis → indicators` is not a chain. Chains run through modules, not
layers: importing a package module does not import its submodules.

Two notes on the oracle itself. grimp's *choice* among equal-length chains changes between runs (the
`data → analysis` witness was `loader`, `generator` and `validator` on M1, M2, M3), so A8 compares lengths,
not chains. And the first oracle run was on the wrong tree: my stand clone did not have `aca0718`, the
checkout failed without stopping the script, and the run reported `4b1fc13`. The JSON names its revision,
which is how it showed; it was re-run on `aca0718` with the same result.

## Acceptance reconciled (2026-11-05)

Code in 5b4d1f6. Suite on the stand at 5b4d1f6: 1176 passed / 3 skipped / **1 failed**, the R1-C49-f1 guard (see
below); green after the fix.

| | expected | measured | |
|---|---|---|---|
| A1 two-hop chain | exit 2, entry edge, witness; direct → exit 0 | as expected | holds |
| A2 function-local / `TYPE_CHECKING` middle | exit 2 each | exit 2 each | holds |
| A3 through undeclared `utils` | exit 2 | exit 2, `layered` silent | holds |
| A4 consumer root | exit 0 | exit 0, but **vacuously**: codemap's graph has no core → consumer edge at all, even for `import helper` with `tests/helper.py` present, so no chain can pass through one and mutating the filter cannot turn the test red. The test now pins that property instead | holds, vacuous by construction |
| A5 shortest, then smallest; stable | as stated | as stated | holds |
| A6 `"yes"` / `false` | exit 2 / as absent | as expected | holds |
| A7 bquant `aca0718` | byte-identical to 0.0.26 | exit 0 both, 6 lines, byte-identical | holds |
| A8 against grimp | the oracle's pairs and hops on four trees | base none; M1, M2, M3: `core→analysis` 1, `data→analysis` 2, `indicators→analysis` 3, **agree on all four** ([`a8.json`](../../research/bench/r1c78/a8.json)) | holds |
| A9 mutation | indirect branch removed → A1–A3 red | A1, A2 ×2, A3, A5 and the structured-answer test red; the tie-break inverted → A5 red; a cosmetic change → all green | holds |
| A10 pins, bquearch | unchanged | `RENDERED_SHA` green; bquearch `a948d6c` exit 0 both, byte-identical | holds |

### Departures from the design, and slips

- **A one-hop witness is not printed.** D3 promised a witness per entry edge; for a direct edge it is the entry
  edge again, and the first rendering showed the same line twice. Only chains longer than the edge are listed.
- **The satisfied line** reads `forbidden (8, 3 indirect)` / `forbidden (8 declared, 5 applicable, 3 indirect)`:
  D7 wrote "n of n applicable", which is not codemap's count format.
- **The R1-C49-f1 guard failed on the new field.** It loops over the contract's fields and treats each as a rule;
  `forbidden_indirect` is a flag on `forbidden` items. It is skipped there, and the skip has its own probe
  (the label with `indirect`), checked by mutation.
- **My bquant clone was on the wrong commit twice.** The stand's clone lacked `aca0718`; `git checkout` failed
  and the script did not stop, so the first consumer comparison and the first oracle run were on `4b1fc13`. The
  acceptance script now refuses to run on any other revision. The numbers above are from `aca0718`.
- **A docs example had an invented number** ("12 module(s)") before the run; replaced with the measured output.
