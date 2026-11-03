# Design — `check --graph` says whether the graph is the tree it judges

**Status:** ✅ **shipped** (2026-11-03, no schema change), with acceptance reconciled below. Pre-registered in f433b7b before any code. **Motivates:** gap
[contract_silent_passes_2026-11-03](../../gaps/contract_silent_passes_2026-11-03.md), row P6.
**Backlog:** R1-C70.

## The defect, measured in the probe

`codemap build pkg -o g.json` on a clean tree. Then a forbidden import is added to the source.
- `codemap check --graph g.json` answers "✅ Contract satisfied", exit 0, and says nothing about the
  graph's age.
- `check --build pkg` on the same tree exits 2.

The verdict is correct for a tree that no longer exists, and nothing says so. grafema prints "Graph is
fresh" before its own `check`. Theirs is a check we lack, and its absence is the silent pass.

Everything needed is already recorded:
- the graph carries its input identity, `provenance.scope_id` (R1-C25);
- the sidecar beside it carries the build recipe, `argv` + `cwd` (M18);
- `resolve_scope` is the build's own definition of "the input", already reused by `watch`.

## D1 — re-derive the scope from the recorded recipe, compare `scope_id`

`graph_currency(graph_path, graph)` returns one of:
- `{"status": "current", "scope_id": …}`;
- `{"status": "behind", "recorded": …, "current": …, "added": n, "removed": n, "changed": n}`.
  The counts come from `diff_scopes` against the manifest in the sidecar;
- `{"status": "unknown", "reason": …}`, when there is no sidecar or recipe, the recorded `cwd` is
  gone, the graph has no `provenance.scope_id`, or the scope cannot be resolved.

The recipe is parsed for the arguments that decide the scope, and the scope is resolved exactly as
`build` resolves it (`path`, `--consumer`, `--docs`, relative to the recorded `cwd`). That way "the
same input" means the same thing in both places.

- **Rejected: compare mtimes.** A checkout, a `touch` or a copy changes mtimes without changing the
  input, and an edit restored by hand keeps a new mtime. `scope_id` is the content.
- **Rejected: re-hash only the files listed in the sidecar.** That misses a new module, and a new
  module is how an undeclared layer or a new forbidden import usually arrives.

## D2 — behind is a failure (exit 2), unknown is named, current is named

- **behind.** Exit 2, through the same channel as a violation or an unreadable contract. A verdict
  about a tree that no longer exists does not answer "may the pipeline proceed?" for this one.
  - The rule verdict is still printed below, labelled as being about the recorded tree.
  - `--allow-stale` restores the verdict's own exit code. The "behind" line stays.
- **unknown.** Named, with the reason; the exit code is the verdict's. A graph shipped without its
  sidecar is a legitimate artifact, and refusing it would break every `check --graph` on one. But
  "not checked" is said, never left as an absence (R1-C28).
- **current.** One line saying so. Then "current" is a statement, and the absence of the line can
  never be read as "current".
- **`--build`.** No line: the graph is built from the tree in the same process. Output is
  byte-identical to today.

JSON (`build_check`) gets a `graph_currency` field, always present:
- `{"status": "built_now"}` under `--build`;
- the dict above otherwise.

`ok` is false when the status is `behind` and staleness was not allowed. The MCP `check` op computes
the same thing from the graph path the session was started with.

- **Rejected: warn only (exit 0).** That is the defect with a footnote added: the pipeline proceeds
  on a verdict about another tree.
- **Rejected: rebuild automatically.** `check` is a gate, not a build. `codemap refresh` exists, and
  the message names it.

## Pre-registered acceptance (committed before the code)

Fixture builds run locally. The bquant runs and the suite go to the stand, in the shared core-slot
accounting.

- **S1, the probe's P6.** Build, then add `from pkg.analysis import b` to `pkg/core/a.py`, then
  `check --graph`.
  - Exit 2.
  - The output says the graph is behind its source, with "1 changed", and names `codemap refresh`
    and `--build`.
  - The rule verdict (satisfied, about the recorded tree) is still shown.
- **S2, control.** The same without the edit: exit 0, and one line saying the graph matches its source.
- **S3.** S1 with `--allow-stale`: exit 0 (the recorded tree satisfies the contract), and the "behind"
  line is still there.
- **S4.** S1 with the sidecar deleted: exit 0, and "graph currency not checked: no build recipe beside
  the graph".
- **S5.** A new file `pkg/core/c.py` instead of an edit: behind, "1 added".
- **S6.** `check --build` output is byte-identical before and after the change, on the fixture and on
  bquant (`8efa112`).
- **S7, MCP.** A session over S1's graph with the source edited: `graph_currency.status == "behind"`
  and `ok: false`.
- **S8, cost.** bquant, `check --graph` on a current graph: the added time is under 1 s (median of 3).
- **S9, bquant.** `check --graph` on a graph just built: exit 0, and the currency line says current.
- **S10, mutation.**
  - With `graph_currency` forced to "current", S1 exits 0 again (a test goes red).
  - With the exit-code branch removed, S1 exits 0 (a test goes red).

At least one expectation fails if nothing is done: S1 exits 0 today (measured in the probe).

## Acceptance reconciled (2026-11-03)

| | expected | measured | |
|---|---|---|---|
| S1 | exit 2, "behind", "1 changed", names `refresh` and `--build`, verdict still shown | so | holds |
| S2 | exit 0, "matches its source" | so | holds |
| S3 | `--allow-stale`: exit 0, line kept | so | holds |
| S4 | no sidecar: exit 0, "currency not checked: no build recipe beside the graph" | so | holds |
| S5 | new file: behind, "1 added" | so | holds |
| S6 | `--build` byte-identical, fixture and bquant | fixture: no currency line. bquant: identical output, exit 0 both | holds |
| S7 | MCP `behind`, `ok: false` | so | holds |
| S8 | bquant `check --graph` adds < 1 s | median 0.49 s before, 0.49 s after (3 runs each). The scope resolves through git and costs nothing visible | holds |
| S9 | bquant, a fresh graph: exit 0, "current" | so | holds |
| S10 | both mutations red | both red. With the code reverted (before the move below), 11 of 12 tests fail; the one that passes is the `--build` "no line" test | holds |

Suite: 1091 passed, 3 skipped (1079 + 12).

**Surprises, both changed the design text above:**
- **D1 said the recipe would be parsed with codemap's own `build_parser()`.** It cannot be: the
  function first lived in `freshness`, which sits below `cli` in codemap's own layer contract. A
  narrow parser reads only `path`, `--consumer` and `--docs`, and a test pins that it agrees with
  `build_parser` on three argvs.
- **The first placement broke codemap's own contract.** `freshness → scope` points up the stack,
  and the dogfood test `test_codemap_satisfies_its_own_architecture_contract` caught it in the
  suite. The function moved to `codemap/serve/currency.py`, a layer allowed to import both. It is the
  same kind of slip as the defects this work fixes, caught by the gate this work hardens.
