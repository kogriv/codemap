# CI — what is checked, and what is deliberately not

codemap's CI lives in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) and runs on every
push to `main`, every pull request, and on demand.

It was added late, in [M20](../BACKLOG.md), under a rule worth stating because it decides what
belongs here: **a claim in the repository is either checked by CI or removed.** Every job below
names a sentence someone can read in the README, in CONTRIBUTING or in `pyproject.toml`. A job that
no longer defends a claim is a job to delete, not to maintain.

The rule arrived the honest way. The first thing measured was `requires-python = ">=3.10"`, which
had never been checked because there had never been a second interpreter — and it was false. See
[the gap](../gaps/unverified_claims_2026-08-27.md).

## The jobs

| Job | Holds | Notes |
|-----|-------|-------|
| `tests` | README's "tests green"; `requires-python` | matrix over **3.11, 3.12, 3.13, 3.14**, `fail-fast: false` so one version's break does not hide another's |
| `determinism` | README's "deterministic (canonical sorted JSON, no timestamps — diffable)" | builds `./codemap` twice, `cmp`s the bytes |
| `wheel` | that the shipped artifact installs and runs | builds both distributions, installs the wheel into a clean venv, runs it from a directory with no codemap source |
| `interop` | the ctags and SCIP exports are readable by the real tools | installs `readtags` and `scip`, and **fails if they are missing** rather than letting the tests skip |

## Two scoping decisions worth knowing

**`determinism` runs the fast tier only.** Not an oversight. R1-C9 measured that the deep (jedi)
tier is *not* byte-stable — two full deep builds of the same tree differ by a couple of edges. That
limit is documented in [provenance.md](provenance.md) and in the backlog; asserting deep determinism
in CI would be this milestone making exactly the kind of unchecked claim it exists to end.

**It compares two builds in one job, not across runs.** The determinism test that taught this
project the most (R1-C22-f1) went red because the *input* moved under it, not because the tool was
non-deterministic. A cross-run or cross-commit comparison would manufacture that same false signal
on a schedule. Freeze the input, then compare — the same discipline the tests use via
`tests/frozen.py`, and the reason the graph carries a [provenance block](provenance.md) at all.

**`interop` refuses to pass by skipping.** `tests/test_r1c2_ctags.py` and `tests/test_scip_export.py`
skip when `readtags` / `scip` are not on `PATH`, which on a development machine is always — so they
had never executed at all. The job installs both and asserts they are present before running pytest,
because a green run made of skips is the same silence this project keeps fixing elsewhere.

## What CI does not catch

Worth being plain about, since a badge invites the opposite assumption. The most instructive
failures in this project's history would all have sailed through:

- a determinism test going red because a neighbouring process was editing the target (R1-C22-f1);
- a before/after measurement that lied because griffe resolved the package name from `sys.path`
  rather than the given `search_paths`, so the "old" tool analysed its own source;
- a second one that lied because the baseline predated the edit being measured;
- a patch script that silently truncated a document.

Each needed a person to look at a number and find it implausible. CI holds a different and narrower
line: the regression, the interpreter nobody tried, the artifact nobody installed.

## Running the same checks locally

```bash
pytest -q                                   # the suite (~2 min)

codemap build ./codemap -o /tmp/g1.json     # determinism, the fast tier
codemap build ./codemap -o /tmp/g2.json
cmp /tmp/g1.json /tmp/g2.json && echo deterministic

python -m build                             # the artifact
python -m venv /tmp/v && /tmp/v/bin/pip install dist/*.whl
cd /tmp && /tmp/v/bin/codemap build <some-package> -o /tmp/g.json
```

The interop job needs `universal-ctags` and the [scip](https://github.com/sourcegraph/scip) CLI; with
neither installed the two tests skip locally, which is expected and is the reason CI installs them.
