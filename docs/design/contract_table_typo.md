# Design — a misspelled `[architecture]` table is refused, not read as "no contract"

**Status:** 🟡 pre-registered, before any code. **Backlog:** R1-C76. **Found by:** the import-linter card
([`research/tools/import-linter.md`](../../research/tools/import-linter.md)). Its G11/G16 probe showed that a
configuration whose contracts sit under the wrong table name passes with zero contracts. The same question,
asked of codemap, found the same hole.

## The defect

Measured on `main` (b6d8a17):

```
codemap.toml   [architectur]
               forbidden = [{from="core", to="analysis"}]      # and core does import analysis

codemap check --build pkg                     → "No `[architecture]` contract found in …", exit 0
codemap check --build pkg --require-contract  → exit 1
```

R1-C69 closed the schema *inside* `[architecture]`: an unknown key is refused, with a suggestion. The table
name itself was never checked, so the same typo one level up still passes, unless the caller knew to add
`--require-contract`. bquearch passes it; bquant's gate does too. Neither is protected from this by default.

## D1 — a top-level table whose name is close to `architecture` is refused

In `load_contract`: every top-level key of `codemap.toml` other than `architecture` whose value is a table and
whose lower-cased name is a close match for `architecture` is a problem. The threshold is difflib ratio ≥ 0.8,
which catches `architectur`, `architectures`, `Architecture`, `archtecture` and leaves `integrations` alone.
If there is at least one such table, the contract comes back with `error`, the R1-C27 path: CLI exit 2, MCP
`ok: false`. The error names the table and says that only `[architecture]` is read.

## D2 — the near-miss table is refused even when `[architecture]` is also present

A real `[architecture]` beside an `[architectur]` means somebody wrote rules that will never run. Enforcing
the real one and staying silent about the other is the half-enforced contract R1-C69 already removed.

## D3 — other tables are not checked

codemap reads `[architecture]` and `[integrations]`. Any other table is left alone: the file is ours, but
refusing unknown tables would be a new schema rule with no defect behind it. Only a near miss of the one table
that turns a gate green when it is missing is refused.

## D4 — no answer-format change

The refusal is the existing error path (`_No contract read_` / exit 2), already pinned under format 4. What
changes is which inputs reach it, the same kind of verdict fix as R1-C68. `ANSWER_FORMAT` stays 4. A test
asserts that the rendered pin (`RENDERED_SHA`) is unchanged.

## Pre-registered acceptance (committed before the code)

- **A1.** `[architectur]` with a rule: `check --build` exits 2, the output names `[architectur]` and
  `[architecture]`. The MCP `check` op answers `ok: false` with the same error.
- **A2.** `[Architecture]` and `[archtecture]`: exit 2 each.
- **A3.** `[architecture]` and `[architectur]` together: exit 2 (D2).
- **A4.** Unchanged:
  - a valid `[architecture]`, with the same verdict and byte-identical output;
  - a file with only `[integrations]`, which still reads "No contract found", exit 0, and exits 1 under
    `--require-contract`;
  - no `codemap.toml` at all.
- **A5.** Consumers: bquant (`aca0718`) and bquearch (HEAD) give byte-identical `check` output before and after.
  Neither has a near-miss table.
- **A6.** Mutation: removing D1's check turns the new tests red (A1–A3). A cosmetic change leaves them green.
- **A7.** `RENDERED_SHA` and the suite's other pins are unchanged.

At least A1–A3 fail if nothing is done.
