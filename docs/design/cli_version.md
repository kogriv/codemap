# Design — `codemap --version`

**Status:** ✅ **shipped** (2026-11-03), with acceptance reconciled below. Pre-registered in ccc6b6e before any code. **Backlog:** R1-C73.

## The gap

`codemap --version` answers `the following arguments are required: command` (exit 2). I met this in
the 0.0.23 release check, and bquant reported it independently. The version was visible only through
`importlib.metadata` or the `provenance.tool` block of a built graph. A consumer that pins a version has
no one-line way to ask the installed tool which one it is.

## D1 — one source: the identity the graph records

`--version` prints what `provenance.tool_identity()` returns, the same function that stamps
`provenance.tool` into every graph. The CLI and the artifact therefore cannot disagree. It also prints
the two answer-level versions a consumer diffs:

```
codemap 0.0.23 @06fdc65 · answer format 3 · schema 0.13
```

- `@commit` and `(dirty)` appear only when known, exactly as in `provenance.tool`. A wheel installed
  outside a source tree has no commit (R1-C25) and prints none.
- If no distribution is installed (run from a bare source tree), it says `version unknown (not installed
  as a distribution)`, not an empty or invented number.
- It is computed only when the flag is given. `tool_identity()` asks git, and no other command should pay
  for that. So it is a custom argparse action, not `action="version"` with a string built when the parser
  is.

## Pre-registered acceptance (committed before the code)

- **V1, editable install from this repo.** `codemap --version` exits 0 and prints
  `codemap 0.0.23 @<HEAD short> · answer format 3 · schema 0.13`. `(dirty)` is added when the tree is
  dirty. The version and commit equal `provenance.tool` of a graph built in the same environment.
- **V2, the wheel installed outside the source tree** (built locally into a fresh venv):
  `codemap 0.0.23 · answer format 3 · schema 0.13`, with no commit.
- **V3.** `codemap --version build x` prints the version and exits 0: the flag wins, as in argparse.
- **V4.** `codemap` with no arguments still exits 2 with the usage error. The flag did not make the
  subcommand optional.
- **V5, cost.** `codemap stats --graph g.json` does not call `tool_identity()`. A test patches it to
  raise and expects the command to succeed.
- **V6, mutation.** With the action printing a fixed string, the test comparing `--version` against
  `importlib.metadata` and `provenance.tool` goes red.

At least one expectation fails if nothing is done: V1–V3 all exit 2 today.

## Acceptance reconciled (2026-11-03)

| | expected | measured | |
|---|---|---|---|
| V1 | `codemap 0.0.23 @<HEAD> · answer format 3 · schema 0.13`, `(dirty)` when dirty; equal to `provenance.tool` | `codemap 0.0.23 @ccc6b6e (dirty) · answer format 3 · schema 0.13` with `cli.py` uncommitted; a graph built in the same env records `{version: 0.0.23, commit: ccc6b6e, dirty: true}` | holds |
| V2 | the wheel outside the tree, no commit | `codemap 0.0.23 · answer format 3 · schema 0.13` from a fresh venv | holds |
| V3 | `--version build x` → version, exit 0 | so | holds |
| V4 | no arguments → exit 2 | so | holds |
| V5 | `stats --graph` does not call `tool_identity()` | **there is no `stats` command in the CLI** (it is a serve op); measured instead on `query` and `report`, which pass with it patched to raise | holds, on the commands that exist |
| V6 | a fixed string goes red | red. With `cli.py` reverted, 4 of 6 tests fail; the 2 that pass are V4 and V5, which hold before and after | holds |

**Surprise, my own:** V5 named a CLI command that does not exist. It was written from memory of the serve op, not read from the parser. The intent (no other command pays for the identity) is measured on two real commands instead.
