# Design — the gate probe battery: the questions asked of import-linter, asked of `codemap check`

**Status:** 🟡 pre-registered (2026-11-05), not run. **Backlog:** R1-C77. **Gap:**
[`gaps/forbidden_direct_only_2026-11-05.md`](../../gaps/forbidden_direct_only_2026-11-05.md) §4. **Source:** the
import-linter card ([`research/tools/import-linter.md`](../../research/tools/import-linter.md) §0.4), whose 19 gate
probes found three silent passes there. The same kind of question found R1-C76 here.

## Why

Every hole found in `codemap check` so far was found by accident: a consumer's tree, a question written for
somebody else's gate. import-linter passes every import shape I threw at it, and its maturity is the one
thing I said codemap lacks. This turns that comparison into a standing test: one fixture, one change per
probe, one predicted exit code per probe, kept in the suite.

## The fixture

Package `gp` with layers `high > mid > low` (`gp/high/h.py`, `gp/mid/m.py`, `gp/low/l.py`, `__init__.py`
everywhere) and `codemap.toml`:

```toml
[architecture]
layers = ["high", "mid", "low"]
```

Each probe is a fresh copy with **one** change, run as `codemap check --build gp --root <copy>`. Exit codes
are codemap's: 0 = satisfied (or no contract), 2 = a rule broken or a contract that could not be read, 1 =
`--require-contract` with no contract (`SystemExit`).

## D1 — the battery lives in the suite

`tests/test_r1c77_gate_probe_battery.py`, one parametrized case per probe, each asserting the exit code and,
where the prediction names one, the line that must be heard. A probe whose measured answer is a defect is
**not** written as a passing test of the defect: it is marked `xfail(strict=True)` with the R1-C number of its
fix, so fixing it turns the suite red until the mark is removed.

## D2 — a silent pass found here is fixed under its own number

The battery records; it does not fix. Each defect it finds gets a backlog entry, a design note if the fix is
not one line, and its own mutation-verified test. If a probe's prediction is wrong because my reading of
codemap was wrong, and codemap's answer is right, the prediction is reported as wrong and the test asserts
codemap's answer.

## Pre-registered predictions (committed before the first run)

Confidence: **H** I have read the code path or an existing test pins it; **M** I expect it from how the
extractor works but have not checked; **L** a guess.

### Import shapes (layers rule; the change is in `gp/low/l.py` unless named)

| probe | change | predicted | conf. |
|---|---|---|---|
| P0c | none | exit 0, "Contract satisfied" (**control**) | H |
| P0 | `from gp.high import h` at module level | exit 2, `layered`, edge `gp.low.l → gp.high.h` (**control**) | H |
| P1 | the same inside a function | exit 2 | H |
| P2 | the same under `if TYPE_CHECKING:` | exit 2 | H |
| P3 | `import gp.high.h` | exit 2 | H |
| P4 | in `gp/low/__init__.py`: `from ..high import h` | exit 2 | M |
| P5 | `from gp import high` (a submodule through its package) | exit 2 | **L** — the edge may land on `gp` (the root, no layer) |
| P6 | `from .. import high` | exit 2 | **L** — same question, relative |
| P7 | `import gp.high.h as hh` | exit 2 | H |
| P8 | `from gp.high.h import *` | exit 2 | M |
| P9 | the import inside `try: … except ImportError:` at module level | exit 2 | M |
| P10 | the import in a class body | exit 2 | M |
| P11 | `if sys.version_info >= (3, 8):` around the import | exit 2 | M |
| P12 | the import inside a function nested in a method | exit 2 | M |
| P13 | `import gp.high` then `gp.high.h.X` in a function | exit 2 | M |
| P14 | `importlib.import_module("gp.high.h")` | exit 0 — a static tool cannot see it; **documented limit**, not a defect (import-linter is blind to it too) | H |

### Contract shapes

| probe | change | predicted | conf. |
|---|---|---|---|
| C1 | `exhaustiv = true` | exit 2, "unknown key `exhaustiv` (did you mean `exhaustive`?)" (R1-C69) | H |
| C2 | `exhaustive = true` and an undeclared `gp/extra/` | exit 2, `exhaustive` names `extra` | H |
| C3 | `forbidden = [{from = "low", too = "high"}]` | exit 2, `forbidden[0]` has unknown key `too`, missing `to` | H |
| C4 | no `layers`; `forbidden = [{from = "low", to = "hihg"}]`; `low` really imports `high` | exit 0, "0 of 1 applicable" disclosed (R1-C62: inert by design; this is import-linter's #386, which they made an error) | H |
| C4b | C4 plus `no_phantom_rules = true` | exit 2, `no_phantom_rules` names `hihg` | H |
| C5 | `layers = ["hihg", "mid", "low"]`, `low` imports `high` | exit 0, "2 of 3 applicable" disclosed (same family as C4) | H |
| C6 | `exhaustive = "maybe"` | exit 2, "`exhaustive` must be true or false" | H |
| C7 | no `codemap.toml` | exit 0, "No `[architecture]` contract found"; with `--require-contract` exit 1 | H |
| C8 | `[architectur]` | exit 2 (R1-C76) | H |
| C9 | `forbidden = {from = "low", to = "high"}` (a table, not a list) | exit 2, "`forbidden` must be a list" | H |
| C10 | `Layers = [...]` (case) | exit 2, unknown key with suggestion `layers` | H |
| C11 | `layers = ["high", "mid", "high", "low"]` (a repeated layer), `mid` imports `high` | **exit 0 — a silent pass.** `rank` is a dict, the second `high` overwrites the first, `high` ranks below `mid`, the upward edge reads as downward. import-linter rejects repeated layers (their #391) | M |
| C12 | `[architecture]` with only `layers = []` | exit 0, reported as "No `[architecture]` contract found" although the table is there; `--require-contract` exit 1 | M |
| C13 | `forbidden = [{from = "low", to = "low"}]` | exit 0; counted applicable although it can never fire (same-layer edges are not cross-layer) | M |
| C14 | `independent = [["low", "low"]]` | exit 0, but **counted applicable**: `applicability` counts members present with repeats, so one layer named twice passes the "at least two" test, for a rule that can never fire | H (read while writing this table) |
| C15 | `forbidden = [{from = "low", to = "high", indirect = true}]` | exit 2, unknown key `indirect` — the R1-C78 key is refused before R1-C78 | H |

### Graph and invocation

| probe | change | predicted | conf. |
|---|---|---|---|
| G1 | `build --out g.json`, then add P0's import, then `check --graph g.json` | exit 2, the graph is behind its tree (R1-C70) | H |
| G1b | G1 with `--allow-stale` | exit 0, the currency line says behind | H |
| G2 | `check --build` on a path that does not exist | exit ≠ 0, an error naming the path | L |
| G3 | `--root` pointing at a directory without `codemap.toml` | exit 0, "No contract found in `<abs path>`" (R1-C35) | H |

## Expected defects

If the predictions hold, the battery finds: **C11** (a repeated layer silently inverts the stack) — a real
silent pass, to be fixed under its own number. **C12**, **C13** and **C14** are wording / applicability questions,
to be judged after the run. **C4/C5** are a design decision already taken (R1-C62) that import-linter took the
other way; the battery records the difference and does not reopen it unless the run shows the disclosure
is missing. **P5/P6** are the probes I know least about; if either is exit 0, it is an extractor gap.

At least P0 fails if the fixture is wrong; at least C11 fails as predicted if my reading of `check_contract` is
right.

## What the battery does not establish

- Anything about the call graph or the other answers: this is the gate only.
- Import shapes that exist in no real tree I have seen (`__import__`, `exec`).
- Behaviour with consumer roots (tests/examples): those are outside layering by design.
