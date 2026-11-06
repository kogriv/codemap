# Design — a diff path is placed in the graph by a unique suffix, or named as not placed

**Status:** 🟡 pre-registered (expectations below, committed before code). **Backlog:** R1-C87. **Gap:**
[`gaps/review_diff_path_base_2026-11-06.md`](../../gaps/review_diff_path_base_2026-11-06.md).

## The defect

`review` matches a diff's file path to the graph by exact string. A diff is relative to the git root, while a
graph is relative to the common parent of its build roots. When those differ (bquearch builds from
`research/`), nothing matches, and the answer is "0 changed symbol(s)" with every hunk filed under "unresolved
(module-level / unknown file)".

## D1 — exact, then a unique suffix in either direction

For each file in the diff:

1. if it is a file of the graph, it is used as written;
2. otherwise, the graph files it ends with at a `/` boundary (`research/shared/contracts.py` →
   `shared/contracts.py`, the diff longer), together with those that end with it (`shared/x.py` →
   `research/shared/x.py`, the graph longer). Exactly one candidate means the file is placed there, and the answer
   records the mapping. More than one is ambiguous: nothing is guessed, and the candidates are named.

This lives in `build_review`, so the CLI and the MCP `review` op behave alike.

## D2 — what was not placed is said, apart from module-level hunks

- `summary.unplaced_files`: Python files of the diff that are not in the graph, each `{file, candidates}`
  (candidates non-empty only when ambiguous). `summary.skipped_files`: non-Python files not in the graph (a
  README, a TOML), which a code graph is not expected to hold. `summary.mapped_paths`: `{diff path: graph
  path}` for D1 step 2.
- `unresolved_hunks` keeps one meaning: hunks in files that **are** in the graph whose lines name no symbol.
- Markdown: when any Python file is unplaced, a bold line goes right under the heading: "**N Python file(s) in
  the diff are not in this graph — nothing in them was reviewed**: …", with the hint to build over them or check
  the diff's path base. When paths were mapped, one line says so. Otherwise the output is as before.

## D3 — nothing placed at all is a refusal (CLI)

If the diff holds Python files and **none** of them is placed, `codemap review` exits **2**. Zero symbols would
otherwise read as "nothing touched". A partial placement exits 0 with the D2 line. A diff with no Python files
exits 0 and says how many files it skipped.

**`ANSWER_FORMAT` 7 → 8**: the review summary gains fields, and `unresolved_hunks` narrows in meaning. Schema
unchanged.

## Pre-registered expectations

Run on the R1-C87 branch against 0.0.31. E1, E2, E4 and E5 fail on 0.0.31, so the list cannot pass if nothing
was done.

| # | Expectation |
|---|---|
| E1 | bquearch `a948d6c`, graph from `research/`, diff with repo-root paths: one symbol `shared.contracts.SURFACE_NAMES` (as with `--relative`), `mapped_paths = {"research/shared/contracts.py": "shared/contracts.py"}`, exit 0 |
| E2 | Fixture, the other direction: graph paths `research/pkg/m.py`, diff path `pkg/m.py` → placed and mapped |
| E3 | Fixture: two graph files match a suffix → `unplaced_files` names the file with both candidates; nothing reviewed from it |
| E4 | A diff touching only a Python file absent from the graph: `review` exits 2 and names it; the same diff plus one placed file exits 0 with the bold D2 line |
| E5 | A hunk on a module-level line of a placed file is still in `unresolved_hunks`; a hunk in an unplaced file is not |
| E6 | A diff whose paths match exactly (the R1-C82 `--relative` diff): markdown identical to 0.0.31 apart from the trailer; no `mapped_paths` entries |
| E7 | A diff of only non-Python files: exit 0, `skipped_files` lists them, no D2 warning |
| E8 | Full suite passes; guards for D1 (both directions, ambiguity), D2 and D3 go red when reverted; a cosmetic control stays green |

Surprises are reported in the reconciliation.
