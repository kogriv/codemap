# Design — Say only what is checked: CI, package metadata, and a gate that cannot pass silently

**Status:** ✅ **shipped** (2026-08-27, no schema change).
**User docs:** [../ci.md](../ci.md),
[../hard-python.md](../hard-python.md#syntax-newer-than-the-interpreter-you-run-on).
**Decisions resolved:** D1 = **`>=3.11`** (measured, not bought back with a dependency); D2 = **the two
conditions are separated, and `check` exits 2 on a contract it could not read**; D3 = version-gated tests
**plus** a property test that runs everywhere; D4 = **GitHub Actions only**; D5 = four jobs, each pinned to a
claim someone can read in the repo; D6 = **0.0.3**, the series stays `0.0.x`; D7 = the distribution is
**`codmap`** while the command, import and repository stay `codemap` — and **publishing itself remains the
owner's to trigger**.
**Motivates:** gap [unverified_claims_2026-08-27](../../gaps/unverified_claims_2026-08-27.md).
**Backlog:** M20 (CI + metadata), R1-C27 (the honesty fix, D2).
**Related design:** every entry in the "confident nothing" line — [attribute_edges](attribute_edges.md),
[flat_layout](flat_layout.md), [source_visible_references](source_visible_references.md),
[hard_python_robustness](hard_python_robustness.md). D2 is the seventh application of the same rule, and the
first one aimed at the tool's own configuration rather than at a target's source.

The project's principles are stated in three files a user reads — README ("deterministic", "512 tests
green"), CONTRIBUTING ("keep the full suite green"), `pyproject.toml` (`>=3.10`). None was enforced by
anything but habit, and the first time one was measured it turned out to be false. The milestone's rule:
**a claim in the repository is either checked by CI or removed.**

**Guiding invariants (unchanged):** source-only, deterministic, resolved-or-honestly-flagged, closed edge
vocabulary, `extras` open-ended.

---

## D1 — What does `requires-python` become?

**Recommended: `>=3.11`.**

Measured (gap §1): 3.12 / 3.13 / 3.14 fully green; 3.11 fails only the four tests that need a 3.12 *parser*
for a 3.12-syntax fixture; 3.10 fails those four plus nine that need `tomllib`.

- **Alternative rejected: keep `>=3.10` and add `tomli` for `python_version < "3.11"`.** It works, and it is
  the wrong trade. codemap has exactly three runtime dependencies, and the principle that keeps it
  installable anywhere is that the list stays short. Spending a dependency to buy back an interpreter whose
  upstream support ends in October 2026 — on a tool with no released users on it — is paying rent on a
  version nobody has. Should someone actually ask for 3.10, this is a two-line change and the decision can be
  revisited with a real reason behind it.
- **Alternative rejected: `>=3.12`, matching what is green today.** Truthful but needlessly narrow: 3.11
  passes everything except assertions about a fixture, and the fixture's failure is a *property of any
  interpreter* (D3), not a defect of 3.11. Declaring 3.12 would encode a test-suite artifact as a product
  limit.

The number is only worth changing because CI will now hold it: the matrix runs 3.11–3.14 on every push, so
the day 3.11 genuinely breaks, the metadata is wrong for one commit rather than for a release.

## D2 — A file that will not parse is not a file that is absent

**Recommended: separate the conditions, and let the gate fail.**

Three loaders (`arch.load_contract`, `integrations.gate.load_config`, `serve.audit.load_dead_code_whitelist`)
collapse `OSError`, `ValueError` and `ModuleNotFoundError` into one silent empty result, which each caller
then renders as *"No `[architecture]` contract found — nothing to enforce"*, exit 0. Deleting one `]` from a
contract that reports 14 violations turns it into a green build (gap §2).

The tolerance is kept — nothing raises, nothing wedges, a bad file never breaks a plain build. What changes
is that the tool **says which of the three things happened**:

```python
# codemap/tomlio.py — one place, since the shape was copied three times
def read_toml(path: Path) -> tuple[dict, str | None]:
    """Return (data, error). On any failure data is {} and error is a human reason."""
```

`ArchitectureContract` and `IntegrationConfig` each gain `error: str | None`; the whitelist loader returns
`(items, error)`. `is_empty()` is untouched and still means "no rules" — callers ask `.error` first, because
"could not read" and "read, and it was empty" are different answers and must not share a branch.

**Exit code: 2, the same as a violation.** Not a new code.

- The exit status answers one question — *may the pipeline proceed?* — and for an unreadable contract the
  answer is no, exactly as for a broken one.
- A **new** code would be the silent-pass bug wearing a new hat: every existing `if rc == 2` in someone's
  pipeline would sort an unreadable contract into the success branch. Reusing 2 fails safe for scripts that
  already exist; inventing 3 fails open.
- `--require-contract` keeps its own meaning (absent contract → error), and now cannot be satisfied by a file
  that failed to parse.

**Alternative rejected: raise from the loader and let callers catch.** It puts the burden on seven call
sites, three of which are library entry points where an exception would violate "a bad opt-in list must never
break a plain build".

**Alternative rejected: route this through `diagnostics.py`.** That channel is *derived from a graph* and
computed on read (R1-C25/D5). A config file the tool could not parse is not a property of the graph, and
faking it into one would make `diagnostics()` depend on the filesystem.

## D3 — The four interpreter-bound tests

**Recommended: gate them on the interpreter, and add a property test that runs everywhere.**

`tests/fixtures/hardpkg/pep695.py` uses PEP 695 syntax (3.12+). On 3.11 two extraction assertions cannot
hold, and two more fail *because R1-C23 is working* — the file goes to `provenance.inputs.skipped` with
`reason: "syntax"` and diagnostics raise `unread_inputs`, so "a clean tree says nothing" is correctly false.

Skipping the four with `sys.version_info` is right but insufficient: it would leave the behaviour that
*matters* — the tool naming source it cannot parse — untested on the very interpreters where it fires. So a
new test asserts the **property** on every version: a file whose syntax the running interpreter rejects is
reported with a reason and never silently dropped. On 3.12+ it writes its own too-new fixture to a temp dir
to make the condition happen.

- **Alternative rejected: drop the PEP 695 fixture.** It is the only coverage of 3.12 syntax, and the tool is
  going to meet 3.12 code.
- **Alternative rejected: run CI only on 3.12+ so the question never arises.** That is choosing not to know,
  which is the habit this whole milestone exists to end.

This makes explicit a property that has always been true and was written down nowhere: **codemap parses a
target with the `ast` of the interpreter it runs on.** A 3.11 codemap cannot fully read a 3.12 target — and,
since R1-C23, says so per file with a reason. That goes in the docs, not just in a test.

## D4 — Where CI lives

**Recommended: GitHub Actions only.**

The repository pushes to two mirrors (`origin` fans out to GitHub and GitLab), which invites a symmetrical
`.gitlab-ci.yml`. Rejected: issues, the issue templates and every bug report this project has received live
on GitHub; GitLab is a push mirror for reach, not a place work happens. Two pipelines would mean two places a
red build can hide and two files to keep in step, for one machine's worth of signal. If the GitLab mirror
ever becomes where someone reports something, this is a file to copy, not a decision to relitigate.

## D5 — What CI actually asserts

**Recommended: four jobs, each pinned to a claim that exists in the repo today.** A job that does not
correspond to something the project *says* is a job nobody will maintain.

| Job | The claim it holds | Failure means |
|-----|--------------------|---------------|
| `tests` (matrix 3.11–3.14) | README "512 tests green"; `requires-python` (D1) | a regression, or the metadata is lying again |
| `determinism` | README "deterministic (canonical sorted JSON, no timestamps — diffable)" | the headline property is gone |
| `wheel` | that the *shipped artifact* installs and runs — never checked before (gap §3) | packaging is broken for everyone but the author |
| `interop` | ctags/SCIP export compatibility, whose two tests have skipped in every run this project has ever made (gap §4) | an interop claim was never true |

`determinism` builds the same input twice in one job and byte-compares, which is the honest scope: it proves
the build is a function of its input on one machine. It deliberately does **not** compare across runners or
across commits — the R1-C22-f1 episode was a *moving input*, and a cross-run comparison would re-create
exactly that false signal. The provenance block (R1-C25) is what makes the two builds legible when they do
differ, and it is asserted to be identical too.

`wheel` runs the built package from a directory containing no codemap source, which is also the only place
`provenance.tool` takes its no-checkout branch (no `commit`, no `dirty`, never the string `"unknown"`). That
path shipped in R1-C25 and had never once been executed until this milestone measured it.

**Not built: publishing on tag.** See D7.

## D6 — Version

**Recommended: 0.0.2 → 0.0.3, and the series stays `0.0.x`.**

Metadata correctness, a dependency-free honesty fix and CI do not make a feature release, and the owner's
call is explicit: no jump to `0.1.x` yet. `0.1.0` should mean "published under a name, with an API someone
outside can rely on" — neither is true today, and inflating the number ahead of that would be its own small
dishonesty in a milestone about not making unchecked claims.

## D7 — The name, and publishing

**Resolved (2026-08-27): the distribution is `codmap`. Everything else stays `codemap`.**

`codemap` is taken on PyPI (`codmap` verified free: 404 against the project API, versus 200 for `codemap`).
The owner chose `codmap`, having heard the objection that a name one letter from an existing one is
typo-prone; that is their call to make and it is made.

Only the *distribution* moves. The command, the import and the repository stay `codemap`, which is the
common resolution for a taken name and keeps every existing doc, script and muscle-memory intact. The seam a
reader hits — `pip install codmap`, then `codemap build` — is stated in README's first install line rather
than left to be discovered.

**The rename has one non-obvious consequence, and it is a provenance one.** `provenance.py` looked up its
own version with `importlib.metadata.version(TOOL_NAME)`. Renaming the distribution would make that raise
`PackageNotFoundError`, which the existing handler turns into `None` — so the version would have vanished
from every graph, silently, and two graphs built by different releases would have become indistinguishable
again. That is exactly the gap R1-C25 was built to close, reopened by a packaging change. So the two names
are now separate constants with separate jobs:

- `TOOL_NAME = "codemap"` — the identity written into every graph. It does not move: changing it would make
  every existing 0.12 graph incomparable with a new one over a packaging detail.
- `DIST_NAME = "codmap"` — what `importlib.metadata` is asked about, and nothing else.

Two tests hold the pair: one asserts the version actually resolves (a silent `None` is the regression), the
other asserts `DIST_NAME` still matches `pyproject.toml`'s `name`, since nothing else keeps two files in
step.

**Published, on the owner's instruction, 2026-08-27:**
[`codmap` 0.0.3](https://pypi.org/project/codmap/0.0.3/). Built from a clean tree at the pushed commit,
`twine check` PASSED on both artifacts, uploaded with twine. Verified the way everything else in this
milestone was: installed from PyPI into a clean venv, run from a directory containing no codemap source —
31 nodes, 41 edges, schema 0.12, `provenance.tool` = `{"name": "codemap", "version": "0.0.3"}` with no
commit, which is the correct no-checkout answer. The page carries `license_expression: MIT`, five project
URLs, twelve classifiers and `requires_python >=3.11`.

**0.0.4 published 2026-08-29:** [`codmap` 0.0.4](https://pypi.org/project/codmap/0.0.4/), schema **0.13**.
Same procedure, from a clean tree at the pushed commit `45de657`; `twine check` PASSED on both artifacts.
Verified from PyPI in a clean venv, in a directory containing no codemap source: schema 0.13,
`provenance.tool` = `{"name": "codemap", "version": "0.0.4"}` with no commit — the correct no-checkout
answer — plus the two behaviours the release exists for, checked on a built graph rather than assumed: a
call through a function-local import to a **re-exported** name resolved on the fast tier (R1-C30/f1), and a
consumer symbol carrying a `file` (R1-C31).

**0.0.5 published 2026-08-31:** [`codmap` 0.0.5](https://pypi.org/project/codmap/0.0.5/), schema **0.13**
(unchanged). Same procedure, from a clean tree at the pushed commit `9523dc1`; `twine check` PASSED on both
artifacts. A correctness release — R1-C33/34 (the declared signature, and the parameter kind it had been
dropping), R1-C35 (a gate that did not say where it looked), R1-C36 (a build that could analyse a different
package with the same name).

Verification was chosen to match what the release fixes: a clean venv outside any checkout, and the build
run **from a working directory containing a package with the same name as the target** — the condition
under which 0.0.4 answers about the wrong code. On the published wheel: the graph describes the directory it
was given and contains nothing from the shadowing one, carries no absolute paths (D5), renders
`run(target: str, *args, verbose: bool = False, **opts) -> bool` with the markers intact, hands back
`constructor: __init__(self, name: str, *, retries: int = 3) -> None` on the class dossier, and `check`
names the absolute `codemap.toml` it searched and says the miss exits 0.

One step is worth recording because it is a step: bumping `pyproject.toml` made
`test_the_declared_version_matches_pyproject` fail, since an editable install caches its metadata and still
reported 0.0.4. That is the guard added for 0.0.4 doing exactly its job — `uv pip install -e .` refreshes it.
A release procedure that skipped the reinstall would ship a package whose own metadata disagreed with its
source.

**And the release found one of its own.** `codemap/__init__.py` declared `__version__ = "0.0.2"` while
0.0.3 was on PyPI — a literal that had drifted a release behind, stamping the wrong version into every SCIP
index and ctags file. Graphs were unaffected, and the reason is the interesting part: `provenance` asks
`importlib.metadata` (D2 above) instead of reading the literal, so the one place the number *had* to be
right never consulted the copy that was wrong. The literal now reads the same source, and two tests hold
it: the two agree, and the installed metadata matches `pyproject.toml`. A version in two files is the same
shape as a scope in two files (M19) or a debounce with its own notion of change (M3.2-f1) — one source, or
it drifts.

**Releases stay manual — decided, not deferred (2026-08-27).** A tag-triggered workflow with a trusted
publisher was offered and declined; releases are cut by hand, the way 0.0.3 was:

```bash
git status --short                  # must be empty, on the pushed commit
uv build
.venv/bin/twine check dist/*
.venv/bin/twine upload dist/*       # ~/.pypirc, [pypi]
# then verify from PyPI into a clean venv, and tag vX.Y.Z (use `git tag -F`, not -m:
# backticks inside double quotes are command substitution to the shell)
```

At this cadence the automation would be scaffolding around an act performed a few times a year, and CI
already covers what a release workflow would mostly be re-checking — the suite on four interpreters, and
a wheel built, installed and run outside the source tree.

### A note on `pip show`, so nobody "fixes" it later

`pip show codmap` prints an empty `License:` and `Home-page:` under **pip < ~25**. Nothing is missing:
the metadata carries `License-Expression: MIT` and five `Project-URL` entries (verified on the published
artifact), and **pip 26.2 renders both correctly** — `Home-page` resolved from `Project-URL: Homepage`,
and the licence under its real field name. It is a display gap in older pip, not a packaging defect.

Making those two lines non-empty on old pip would mean *reverting the metadata*: PEP 639 forbids pairing
`License-Expression` with the deprecated free-text `License` or a `License ::` classifier, and `Home-page`
is not settable from a modern `[project]` table at all. That is going backwards on the standard to please
a superseded pip. `Author:` is blank in every pip version for the same benign reason — PEP 621 collapses
`authors = [{name, email}]` into `Author-email: kogriv <…>`, which is where the name is.

What *is* in scope: making the PyPI page truthful the moment there is one — license expression, project
URLs, classifiers, keywords, author — and rewriting README's **Install** section, which today shows only
`pip install -e .`, i.e. instructions to clone, on the page whose whole purpose is installing without
cloning.
