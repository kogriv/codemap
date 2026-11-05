# Design — a root that is not a directory is refused, not skipped

**Status:** 🟡 pre-registered (expectations below, committed before code). **Backlog:** R1-C84. **Gap:**
[`gaps/missing_root_accepted_2026-11-05.md`](../../gaps/missing_root_accepted_2026-11-05.md).

## The defect

On `main` (bed0daf), `codemap build pkg --consumer nope`, `--docs nope`, `--consumer pkg/core.py` (a file) and
`--consumer tests,examples` (two roots in one string) all exit 0. The scanners return early on
`not root_dir.is_dir()`, and the provenance still lists the root under `roots.consumers` as if it had been read.
`codemap scope` takes the same paths and is just as silent.

## D1 — refused before anything is built

New `root_problems(consumers, docs) -> list[str]` in `extract/roots.py`. It runs once per root and reports:

- a root that does not exist: "`--consumer nope`: no such directory";
- a root that exists but is not a directory: "`--consumer pkg/core.py`: not a directory";
- a missing root that contains a comma and whose parts all exist is treated as a list given in one string:
  "`--consumer tests,examples`: no such directory — looks like a list; pass the flag once per root:
  `--consumer tests --consumer examples`".

Callers:
- `build`, `scope` and `watch` call it **first**, before the core extraction and before `--deep` spends minutes.
  Each problem is printed as `error: …` on stderr, the command exits **2**, and no graph is written: an existing
  `-o` file is left untouched;
- `extract_repo` calls it as well and raises `ValueError` listing every problem. A library caller gets the same
  refusal, and the CLI check cannot drift away from what the extractor accepts;
- `refresh` replays the recorded `build` argv, so a root deleted since the last build is refused there too. No
  extra code is needed for that, and E4 checks it.

The scanners keep their `is_dir()` guard: it is now unreachable from the public paths, and dropping it buys
nothing.

**Not refused:** an empty directory. A root such as `scripts/` that is momentarily empty is legal; the graph
simply has nothing from it. That boundary is stated in the docs, not enforced.

**Exit code 2** matches the other input refusals (`--repeat`, an unreadable contract). No answer format or
schema change: the graph of a valid build does not change.

## Pre-registered expectations

Run on the R1-C84 branch, before the release. Each of E1–E4 fails on bed0daf, so the list cannot pass if
nothing was done.

| # | Expectation | Where it is heard |
|---|---|---|
| E1 | `build pkg --consumer nope -o g.json` exits 2; stderr names `nope` and says "no such directory"; when `g.json` already existed, its bytes are unchanged | test + manual |
| E2 | `--consumer tests,examples` where both exist exits 2, with the hint `--consumer tests --consumer examples`. A missing comma path whose parts do not all exist gets no hint | test |
| E3 | `--docs nope` exits 2; `--consumer pkg/core.py` exits 2 with "not a directory" | test |
| E4 | `scope pkg --consumer nope` exits 2; `watch pkg -o g.json --consumer nope` exits 2 before its first build; `refresh` of a graph whose consumer root was deleted exits nonzero and names the root | test |
| E5 | The check runs before the core extraction: with `extract` monkeypatched to fail, the refusal still comes out as the refusal | test |
| E6 | `extract_repo(core, consumers=("nope",))` raises `ValueError` naming `nope` | test |
| E7 | An existing empty directory as a root is accepted: exit 0, as before | test |
| E8 | Valid builds are unchanged: the fast-tier repo graph of codemap itself (`--consumer tests --docs docs --mode full`) and of bquant cf039ef (four consumers, `docs`) are byte-identical to bed0daf's | manual, stand |
| E9 | The full suite passes; the guards for E1, E2, E3 and E5 go red when the fix is reverted, and a cosmetic control mutation leaves them green | mutation run |

Surprises — anything not listed above — are reported in the reconciliation.
