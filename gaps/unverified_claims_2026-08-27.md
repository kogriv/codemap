# codemap — gap: the claims the project makes about **itself** are the ones nobody checks

**Date:** 2026-08-27
**Source:** not a dogfood run and not an outside report — a **release-readiness measurement**, taken before
deciding whether the tool can be published at all. The question asked was narrow ("is the packaging
complete?"); the answer was that the packaging states things that are false, and that one of them was false
because of a defect of the project's own signature class.
**Type:** honesty — **turned inward**. Every gap in this register so far has been the tool making a confident
claim about its *target*. This one is the project making confident claims about *itself*: `requires-python
>= 3.10`, "512 tests green", "keep the full suite green", "deterministic". Each is stated in a file a user
reads. None of them is checked by anything except me, by hand, on one interpreter, in one directory.
**Related:** the whole "confident nothing" series — [attribute_impact_gap](attribute_impact_gap_2026-08-22.md)
(`risk:"none"`), [flat_layout_gap](flat_layout_gap_2026-08-24.md) (0 imports rendered as a clean bill of
health), [hard_python_robustness](hard_python_robustness_2026-08-25.md), [deep_tier_regression](deep_tier_regression_2026-08-25.md).
§2 below is the seventh instance of the same rule.
**Design:** [docs/design/release_engineering.md](../docs/design/release_engineering.md).
**Backlog:** M20 (release engineering), R1-C27 (the honesty fix in §2).
**Status:** ✅ **closed same day** (2026-08-27, no schema change).

---

## 1. `requires-python = ">=3.10"` is false

Never verified, because there has never been a second interpreter. Measured across the full declared range,
each in a clean venv, running the same suite from the same commit (`b87814b`):

| Python | Result |
|--------|--------|
| 3.10.19 | **13 failed**, 499 passed, 2 skipped |
| 3.11.14 | **4 failed**, 508 passed, 2 skipped |
| 3.12.3 | 512 passed, 2 skipped ✅ |
| 3.13.11 | 512 passed, 2 skipped ✅ |
| 3.14.2 | 512 passed, 2 skipped ✅ |

The 13 decompose cleanly into two causes, and only one of them is a defect:

- **9 failures — no TOML parser.** `tomllib` is stdlib from 3.11. Every TOML-configured feature is affected:
  the architecture contract (`codemap check`, 5 tests), the dead-code whitelist, the integrations gate, the
  gitnexus router. See §2 — the failures are the *symptom*; the defect is bigger than 3.10.
- **4 failures — the fixture uses syntax the interpreter cannot parse.** `tests/fixtures/hardpkg/pep695.py`
  is written in PEP 695 syntax (3.12+). Two of the four are extraction assertions that genuinely cannot hold;
  **the other two are R1-C23 working exactly as designed** — the file lands in `provenance.inputs.skipped`
  with `reason: "syntax"` and diagnostics raise `unread_inputs`, so `test_a_clean_tree_says_nothing` fails
  *because the tree is honestly not clean*. The tool is right and the tests assume a 3.12 interpreter.

That second cause is not a bug, but it is an **undocumented property**: codemap parses target source with the
`ast` of the interpreter it is running on, so it can only read syntax that interpreter understands. A 3.11
codemap cannot fully read a 3.12 target — and says so, per file, with a reason. Nothing in the docs tells a
user to run codemap on a Python at least as new as the code they point it at.

## 2. The same `except` that tolerates a broken file also swallows "I have no parser"

Three loaders — `arch.load_contract`, `integrations.gate.load_config`, `serve.audit` (whitelist) — share a
shape:

```python
try:
    import tomllib
    data = tomllib.loads(path.read_text(encoding="utf-8"))
except (OSError, ValueError, ModuleNotFoundError):
    return ArchitectureContract()          # …and the caller reports "no contract found"
```

Two very different conditions are collapsed into one silent empty result:

- `ModuleNotFoundError` — **the interpreter cannot do this class of work at all.** Not per-file, not
  per-user: every TOML feature is off, everywhere, forever, on that machine.
- `ValueError` — **the user's file has a typo.** `tomllib.TOMLDecodeError` subclasses `ValueError`.

The second is not a 3.10 curiosity. It is live on **every supported Python**, and it is worse than it sounds,
because `check` exists to be a CI gate. Measured on codemap's own graph with a contract it really violates:

```
$ cat codemap.toml
[architecture]
layers = ["extract", "query", "serve"]

$ codemap check --graph cm.json --root .
❌ **1 rule(s) broken.**
## `layered` — 14 import(s) point up the layer stack (extract → query → serve)
exit: 2
```

Now delete one character — the closing `]`:

```
$ codemap check --graph cm.json --root .
_No `[architecture]` contract found in codemap.toml — nothing to enforce._
exit: 0
```

**A typo in the contract turns the gate green.** The file is right there on disk; the tool read it, failed to
parse it, and reported its own inability as the user's absence of intent. This is the same rule as
`risk:"none"` (#1), the flat-layout health report (#5), the dead-code `high` band (#7) and R1-C23: *`unknown`
must never be rendered as `none`.* The docstrings even say the quiet part — "a broken toml must not wedge
`check`" — and the tolerance is defensible. Reporting nothing while doing it is not.

`gate.py` already knew: its docstring reads "Uses the stdlib `tomllib` (3.11+)". The knowledge existed in a
comment and never reached the metadata or the user.

## 3. The shipped artifact was never installed

`codemap` has always been used from its own source tree via `pip install -e .`. Measured now, for the first
time — build both distributions, install the wheel into a clean venv, run it from a directory containing no
codemap source:

- **Wheel builds and installs clean.** 54 files, `codemap` + dist-info only, no test leakage.
- **It runs.** `codemap build tests/fixtures/hardpkg` → 59 nodes, 94 edges, schema 0.12, exit 0.
- **R1-C25 behaves correctly from a wheel** — `provenance.tool` is `{"name": "codemap", "version": "0.0.2"}`
  with no `commit` and no `dirty`, which is the designed answer outside a git checkout (never the string
  `"unknown"`). This is the first time that path has been exercised at all; it was right.
- **sdist includes `tests/`**, so a downstream packager can run the suite. It also includes `codemap.egg-info`.

So the artifact is sound. What it *says* is not:

| Metadata | State |
|----------|-------|
| `Requires-Python` | `>=3.10` — **false** (§1) |
| License | `License-File: LICENSE` only — no `License-Expression`, no classifier. Machine-readably, the wheel states no license at all, though `LICENSE` is MIT |
| `Project-URL` | **absent** — a PyPI page with no link to source, issues or docs |
| Classifiers | **absent** — no development status, no Python versions, no topic, no audience |
| Keywords | **absent** |
| Author / Maintainer | **absent** |
| Long description | the README — whose **Install** section shows only `pip install -e .`, i.e. instructions to clone, on the page whose entire purpose is installing without cloning |

## 4. Two interop claims are verified nowhere

`readtags` and `scip` — the real external CLIs the ctags and SCIP exports claim compatibility with — are not
on this machine, so both tests skip. They have skipped in every run this project has ever made. The claim
"the SCIP index is readable by Sourcegraph-class tooling" rests on a test that has never executed.

These are the two skips in every row of §1's table.

## 5. What has actually been holding the line

Me, manually, on one interpreter. The README says "512 tests green"; CONTRIBUTING says "Keep the full suite
green" — a rule with no enforcement anywhere. And the honest limit of the fix matters:

**CI would not have caught this project's most instructive failures.** The determinism flake (R1-C22-f1) came
from a moving input, the two lying before/after measurements came from a wrong `sys.path` and a stale
baseline, the truncated `gaps/README.md` came from my own patch script. Every one needed a person to notice
something looked wrong. CI catches a *different* class — the regression, the second interpreter, the artifact
nobody installed — and it is worth having for exactly that class, not as a claim to have automated judgement.

## 6. Result

Closed the same day.

- **§2 fixed (R1-C27):** the three loaders distinguish the two conditions. A malformed file is **named, with
  the parse error**, and the surrounding operation reports it instead of rendering absence; a missing parser
  is a separate, equally loud message. `codemap check` no longer exits 0 on a contract it could not read —
  it exits 2 with the reason. (The tolerance itself is kept: nothing raises, nothing wedges.)
- **§1 answered (M20):** `requires-python` is now **`>=3.11`**, which is measured, not assumed. 3.10 is not
  bought back with a `tomli` dependency — see design D1. The four interpreter-bound tests are gated on the
  interpreter's own version, and §1's property is documented.
- **§3, §4 covered by CI (M20):** the matrix runs the suite on 3.11–3.14, a job builds the wheel and smoke-runs
  it outside the source tree, a job builds the graph twice and byte-compares it, and `readtags`/`scip` are
  installed so the two interop tests finally execute.
- **Metadata completed (M20):** license expression, URLs, classifiers, keywords, author; README's install
  section rewritten for a reader who has not cloned anything.

**And CI earned its place on the first run**, by failing — on something nobody was looking for. All four
`tests` jobs died in collection: `ModuleNotFoundError: No module named 'tests'`. Four modules do
`from tests.frozen import frozen`, which needs the repo root on `sys.path`; `python -m pytest` puts it
there and the plain `pytest` console script does not. The suite passed the way CONTRIBUTING documents it
and failed the way most people type it — reproducible locally in one line once the machine had told me
where to look. Fixed with `pythonpath = ["."]`.

Small in consequence, exact in shape: **an unchecked claim diverges from reality precisely where nobody
tried it**, which is this document's whole thesis arriving from the other direction. (`interop` failed
too, on `go install` — scip's `go.mod` carries `replace` directives, so that install path refuses; the
published binary is used instead.)

The second run then caught the thing this document had accused *others* of. It reported a comfortable
`474 passed, 55 skipped` — against `528 / 2` locally. **Fifty-three of those skips were the dogfood
tests**: a tenth of the suite analyses a real external package that the tests expect beside the
checkout, and a fresh runner has no such sibling. A green run made of skips, in the very milestone that
wrote "a green run made of skips is not a pass" about someone else's job. The target is now checked out
— pinned to a commit, because its API is what the assertions encode and following its HEAD would be a
moving input — and the job fails if those tests skip anyway. One genuine failure surfaced alongside:
a test that contradicted its own module's docstring by requiring a third-party binary to be installed,
which passed on a developer machine that happened to have it and failed the first time it ran anywhere
else.

**Acceptance.** Run `33072689687`: all seven jobs green. `tests` on each of 3.11–3.14 — 527 passed,
3 skipped (the optional external CLIs). `interop` — **19 passed, 0 skipped**: the ctags and SCIP tests
executed for the first time in this project's history, against real `readtags` and `scip` v0.9.0.
