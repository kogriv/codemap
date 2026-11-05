# Design — the `pytest` line of a graph built elsewhere: try the current directory, or take `--source-root`

**Status:** 🟡 pre-registered (expectations below, committed before code). **Backlog:** R1-C83. **Gap:**
[`gaps/foreign_graph_paths_2026-11-05.md`](../../gaps/foreign_graph_paths_2026-11-05.md).

## The defect

`codemap tests` rewrites graph-relative test ids into paths that run from the current directory (R1-C31). The
only base it tries is `roots_base` from the build sidecar. For a graph built on another machine or in another
checkout, that directory does not exist here:

- run from the repo root, the line is right and the caveat still says "1 of 1 path(s) could not be located";
- run from anywhere else, the line is wrong and there is no flag to say where the root is.

`report dead-code` reads `getattr(args, "source_root")`, but the parser has no such flag. Its whitelist is
always read from the current directory.

## D1 — `--source-root DIR` on `tests` and `report`

The directory the graph's paths are relative to on this machine. It has the same name and meaning as
`serve --source-root`. When given, it is the only base tried. A path that does not exist under it is printed
as stored, and the caveat names `DIR`: the user said where the root is, and a fallback past that would hide a
wrong `DIR`.

On `report`, it is where `codemap.toml` is read for `[dead_code].whitelist`, as on `serve`.

## D2 — without the flag: the sidecar's directory, then the current one

Bases are tried in order: the sidecar's `roots_base` when it is a directory on this machine, then the current
directory. Each path is rewritten against the first base under which **that file exists**, so the R1-C31 rule
holds: nothing is printed that was not checked.

- **Every path found: no caveat.** If the sidecar's directory is missing here and the current directory
  supplied the paths, one note says so: "the graph was built in `X`, which is not on this machine; paths
  located from the current directory".
- **Some path found nowhere:** the caveat lists the bases tried and suggests `--source-root`.
- **No sidecar:** the current directory is the only base. The old caveat ("run from there, or rebuild…")
  appears only when a path is not found.

The JSON answer is unchanged. Its `node_id` stays graph-relative, which is the portable form; only the local
`pytest` line is rewritten.

## Pre-registered expectations

Run on the R1-C83 branch. E1, E2, E4a and E7 fail on a305b1d, so the list cannot pass if nothing was done.

| # | Expectation |
|---|---|
| E1 | Foreign sidecar, run from the repo root: line `pytest tests/test_a.py::test_a`, and no "could not be located" caveat; the note names the foreign build directory |
| E2 | Foreign sidecar, run from the parent with `--source-root c84`: line `pytest c84/tests/test_a.py::test_a`, no caveat |
| E3 | `--source-root` pointing at a directory without the file: printed as stored, and the caveat names that directory; the current directory is not tried |
| E4 | No sidecar: (a) from the repo root, no caveat; (b) from the parent, a caveat that suggests `--source-root` |
| E5 | Local graph with a valid sidecar, run from the parent: `pytest c84/tests/test_a.py::test_a`, no caveat, as before |
| E6 | `tests --format json` is byte-identical with and without `--source-root` |
| E7 | `report dead-code --source-root DIR`, run from elsewhere, applies the whitelist in `DIR/codemap.toml` |
| E8 | The full suite passes; the guards for E1, E2, E3 and E7 go red when the fix is reverted, and a cosmetic control mutation leaves them green |

Surprises are reported in the reconciliation.
