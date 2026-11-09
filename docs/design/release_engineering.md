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

**0.0.6 published 2026-09-01, and 0.0.7 two hours later:** [`codmap` 0.0.6](https://pypi.org/project/codmap/0.0.6/)
and [`codmap` 0.0.7](https://pypi.org/project/codmap/0.0.7/), schema **0.13** (unchanged, and unlike 0.0.5
no rebuild is needed — nothing in either release changes what a graph says). Same procedure, from a clean
tree at the pushed commits `c8350ea` and `364fd76`, CI green on all seven jobs before each upload,
`twine check` PASSED on all four artifacts.

**The verification found a defect in the release it was verifying, for the second release running.** The
rule that produced it is worth stating as a rule, because it has now paid twice: *verify the scenario the
release exists for, not the fact that the package installs.* For 0.0.5 that meant building from a directory
holding a same-named package. For 0.0.6, whose only new behaviour is a warm server noticing that the
installed distribution has moved past it, it meant starting a server on the published wheel, upgrading the
installation underneath the running process, and asking `stats`. Nothing came back.

`Session._tool_drift` read the installed side through `tool_version()` — `lru_cache`d, and first called at
import by `codemap/__init__.py`, the same call that sets `codemap.__version__`. Both sides were one cached
value; `tool_restart_needed` was unreachable in every process. The suite was green because its tests either
pass two versions in as arguments or patch `codemap.__version__` to force a disagreement the real code
cannot produce — the arithmetic proven, the reachability never asked. 0.0.6's own headline was *a check that
has never been fed the thing it must reject is not a check*, and this is what shipped under it.

0.0.7 fixes it (R1-C38-f1): `provenance.installed_version()` reads the metadata fresh per call, while
`tool_version()` keeps its cache because a build must stamp one version into everything it writes. Verified
on the published 0.0.7 wheel by the same scenario end to end — server started under 0.0.7, installation
changed to 0.0.6 underneath it, and both `stats` and `reload` returned
`tool_restart_needed {running: 0.0.7, installed: 0.0.6}`. Also checked, as before: schema 0.13,
`provenance.tool` = `{"name": "codemap", "version": "0.0.7"}` with no commit (the correct no-checkout
answer), no absolute paths, and signatures rendering their `*`, `/` and `**` markers.

Both tags were written after the fact, `v0.0.6` naming its own supersession. A release that is corrected
within the day is still a release someone may have installed.

**0.0.8 published 2026-09-02:** [`codmap` 0.0.8](https://pypi.org/project/codmap/0.0.8/), schema **0.13**
(unchanged). Same procedure from a clean tree at the pushed commit `8d9c138`, CI green before the upload,
`twine check` PASSED on both artifacts, tag `v0.0.8` written with `-F`.

The release exists for one fix (R1-C41): in git mode the input manifest enumerated the tracked set while
the extractor walked the filesystem, so an untracked or gitignored module was in the graph, absent from
`scope.files`, and did not move `scope_id`. So the scenario to verify was not "does it install" but *does a
file that is not in the index reach the manifest, and does the identity move when it does* — driven on the
published wheel, in a clean venv outside any checkout, over a throwaway git repo: the untracked module came
back in the manifest with `tracked: false`, `scope_id` moved, and `--incremental` recomputed it
(`1 module(s) recomputed`, the new symbol present) where the same sequence had answered `unchanged: 0`.
The gitignored module stayed out and was named by the warning.

**And the half that a fix like this must also prove: that nothing moved for everyone else.** `scope_id` is
an identity other people pin — the research benchmark pins one, and the second target verifies its graphs
against a recorded manifest. So both published wheels were installed side by side and pointed at the same
clean tree: 0.0.7 and 0.0.8 returned the byte-identical `sha256:11851fa9…`. The change is inert wherever
nothing is untracked, which is the only way this fix could ship without invalidating every pinned id in
circulation. Third release running, the verification is what decided whether the release was finished.

**And the release found one of its own.** `codemap/__init__.py` declared `__version__ = "0.0.2"` while
0.0.3 was on PyPI — a literal that had drifted a release behind, stamping the wrong version into every SCIP
index and ctags file. Graphs were unaffected, and the reason is the interesting part: `provenance` asks
`importlib.metadata` (D2 above) instead of reading the literal, so the one place the number *had* to be
right never consulted the copy that was wrong. The literal now reads the same source, and two tests hold
it: the two agree, and the installed metadata matches `pyproject.toml`. A version in two files is the same
shape as a scope in two files (M19) or a debounce with its own notion of change (M3.2-f1) — one source, or
it drifts.

**0.0.9 published 2026-09-02, hours after 0.0.8:** [`codmap` 0.0.9](https://pypi.org/project/codmap/0.0.9/),
schema **0.13** (unchanged). Same procedure from the pushed commit `b21dff1`, CI green, `twine check` PASSED,
tag `v0.0.9` written with `-F`.

This one is a release whose entire content is **disclosure**, which makes the verification question sharper
than usual: not "does it install" and not even "does the fix work", but *does the artifact now say the thing
it was silent about*. On the published wheel, outside any checkout: a `--deep` build prints the note with the
measured numbers and a fast build prints nothing; `diff` of two deep graphs prints the noise floor above the
verdict — on stderr and in the rendered markdown — and `diff` of two fast graphs prints neither. Both halves
were checked, because a disclosure that fires everywhere is as wrong as one that never fires.

Worth recording about the upload itself: `twine upload` exceeded the shell timeout and the command was
reported as failed. It had not failed — the release was on PyPI. The check is the index, not the exit code of
the client, and the same rule applies as to the release scenario: verify the state of the world, not the
report of the tool that changed it.

**0.0.10 published 2026-09-03:** [`codmap` 0.0.10](https://pypi.org/project/codmap/0.0.10/), schema
**0.13** (unchanged). Same procedure from the pushed commit `a392928`, CI green, `twine check` PASSED on
both artifacts, tag `v0.0.10` written with `-F`.

Second release in a row whose whole content is disclosure, and the verification question is sharper again,
because this one **changes the bytes of every graph, not only of the graphs it warns about**:
`provenance.incremental` is written by every build. So the two halves had to be checked against each other,
from PyPI, in clean venvs outside any checkout:

- **It fires where it should.** An incremental `--deep` build reports `incremental: true` and prints the
  `incremental_deep_splice` note — on stderr *and* rendered into a report read from the stored graph. A full
  deep build reports `false` and prints nothing. The fast tier stays silent on both counts. And 0.0.9 on the
  same tree has **no such key at all**, which is the case the field exists to distinguish: absent is
  *unknown*, not *full*.
- **It is inert where it has nothing to say.** 0.0.9 and 0.0.10 pointed at the same tree on the fast tier
  (byte-stable, so the comparison is meaningful there and is not on deep) came back with the same
  `scope_id` — `sha256:e0e64d52d0e6da7b0` — the same 2869 nodes / 8408 edges, and **byte-identical apart
  from that single key**. Third release running, this half is what decides whether a release is finished:
  `scope_id` is an identity other people pin.

Also worth recording: the version endpoint answered before the sdist appeared in it. The first read of
`pypi.org/pypi/codmap/0.0.10/json` listed only the wheel; seconds later it listed both. The rule from 0.0.9
holds in the other direction too — check the index rather than the client, and check it until it is
*complete*, not until it is non-empty.

**0.0.11 published 2026-09-04:** [`codmap` 0.0.11](https://pypi.org/project/codmap/0.0.11/), schema
**0.13** (unchanged). Same procedure from the pushed commit `4c11930`, CI green, `twine check` PASSED on
both artifacts, tag `v0.0.11` written with `-F`. The index listed both files on the first read this time.

The first release in a while whose content is a *capability* rather than a disclosure — `--repeat N` — and
still one that changes the bytes of every graph by a key (`provenance.samples`). Verified from PyPI, two
clean venvs (0.0.10 and 0.0.11), one pinned tree, both directions:

- **Inert where it has nothing to say.** Fast tier, 0.0.10 against 0.0.11: the same `scope_id`
  (`sha256:1740f432c6a705af1`), the same 2868 nodes / 8407 edges, byte-identical in nodes and edges; the
  provenance differs in exactly `samples` (`{"runs": 1}`, absent in 0.0.10) and the tool version. Fast
  stderr empty on both. `--repeat 2` without `--deep` exits 2 with its reason.
- **It does what it says where it should.** Deep tier: 0.0.10 prints the old "one run in three" note,
  0.0.11 prints "126 of 168 full builds (75 %)" and names `--repeat`. `--deep --repeat 2` **from the
  installed wheel** — the case that checks the spawned sampling worker is importable outside a checkout —
  ran in 76 s, wrote `samples: {"runs": 2, "unstable": 1}`, and the one `seen` edge is the measured probe.
  `report dead-code` on a package with a method defined twice shows the "Shadowed definitions — certain"
  section under 0.0.11 and nothing under 0.0.10.

Nothing new to record about the procedure itself; the one lesson of the day belongs to the measurement
side and is in the gap — repeating the jedi layer inside one process is not the regime whose share was
measured, so the flag costs an interpreter per sample.

**0.0.12 published 2026-09-04:** [`codmap` 0.0.12](https://pypi.org/project/codmap/0.0.12/), schema
**0.13** (unchanged). Same procedure from the pushed commit `311456d`, CI green, `twine check` PASSED on
both artifacts, tag `v0.0.12` written with `-F`.

No new graph bytes this time — the content lives in the answer envelope, the incremental path and the
CLI — so the two halves were checked accordingly, from PyPI, in clean venvs:

- **Inert where it has nothing to say.** Fast tier, 0.0.11 against 0.0.12 on the pinned tree: the same
  `scope_id`, the same 2868 nodes / 8407 edges, provenance identical apart from the tool version.
- **It does what it says.** `impact` on a ghost id: 0.0.11 carries no `resolved` block, 0.0.12 carries
  `{input, id: null, found: false, …}`; `query` by a full id opens a dossier with one match. `build --deep
  --repeat 2 --incremental`: 0.0.11 exits 2, 0.0.12 builds the base (86 s, two interpreters), a real tick
  recomputes 11 modules in 20 s with `samples: {runs: 2}` and `incremental: true`, and a request with
  `--repeat 3` over that chain restarts it from a full build with `runs: 3`.

One lesson for the procedure, the mirror of 0.0.10's: the JSON endpoint listed both files on the first
read, and `uv pip install codmap==0.0.12` still found no such version for the next minute or so — the
**simple index** the installer reads lags the JSON API. The verification's first run failed on nothing but
that, and everything downstream of the install failed with it. Read the index the *installer* reads, and
retry the install itself, not the endpoint.

**0.0.13 published 2026-09-06:** [`codmap` 0.0.13](https://pypi.org/project/codmap/0.0.13/), schema
**0.13** (unchanged). Same procedure from the pushed commit `58cd849`, CI green, `twine check` PASSED on
both artifacts, tag `v0.0.13` written with `-F`.

This one changes graph bytes — one value of an open field — so the check from PyPI, clean venvs, 0.0.12
beside 0.0.13 on the pinned reporter's tree, was the byte-diff itself:

- **Exactly the promised edge.** 2965 nodes identical; 8617 edges of which one differs —
  `zones.cache → zones.pipeline`, `{}` under 0.0.12 and `{"scope": "type_checking"}` under 0.0.13;
  provenance identical apart from the tool version.
- **The gate the issue was about.** The reporter's contract with `no_cycles = true`: 0.0.12 ❌ one cycle,
  "9 not judged"; 0.0.13 ✅, "10 not judged … 1 import(s) under `TYPE_CHECKING` read as never running";
  the architecture line reads 271 / 26 under 0.0.12 and 270 / 26 / 1 under 0.0.13.
- **The merge path is alive.** `build --deep --repeat 2` on a two-module tree writes
  `samples: {runs: 2, unstable: 0}`.

The simple index served the version on the first install attempt this time; the retry loop from 0.0.12's
lesson stayed in the script and was not needed.

**0.0.14 published 2026-09-07:** [`codmap` 0.0.14](https://pypi.org/project/codmap/0.0.14/), schema
**0.13** (unchanged). Same procedure from the pushed commit `2f61e54`, CI green, `twine check` PASSED on
both artifacts, tag `v0.0.14` written with `-F`.

No graph bytes move this time — the release changes how cycles are *classified*, so the check from PyPI,
clean venvs, 0.0.13 beside 0.0.14 on the pinned reporter's tree, compared verdicts rather than bytes:

- **The graph is untouched.** 2965 nodes and 8617 edges identical in both directions, provenance the same
  apart from the tool version.
- **The classification moved.** `report architecture`: 0.0.13 prints one section, "closed only by a
  non-eager import … 10"; 0.0.14 prints two, 9 function-local and 1 under `if TYPE_CHECKING:`.
- **The rules follow it.** With `no_cycles` + `no_lazy_cycles`, 0.0.13 names 10 cycles including the
  `TYPE_CHECKING` pair; 0.0.14 names 9 and leaves that pair to `no_type_only_cycles`, which refuses it
  (exit 2) when added. With `no_cycles` alone, the scope line splits 10 into "9 … and 1 …".

A procedure note, not a tool one: the verification script appended `no_lazy_cycles = true` to a contract
that already declared it `false`, and both versions answered *"Contract not read — nothing was enforced"*
with exit 2. That is R1-C27 working exactly as designed — a contract that would not parse must not read as
a contract that does not exist — but it cost a rerun. Build a modified contract by **replacing** the line,
never by appending a second copy.

**0.0.15 published 2026-09-07:** [`codmap` 0.0.15](https://pypi.org/project/codmap/0.0.15/), schema
**0.13** (unchanged). Same procedure from the pushed commit `e513a36`, CI green, `twine check` PASSED on
both artifacts, tag `v0.0.15` written with `-F`.

One line of output, so the check from PyPI was that line, on a tree where the rule **passes** — and the
first run measured the wrong thing: the dogfood tree *has* a type-only cycle, so the rule fails there and a
passing line never prints. Repeated on a two-module tree that has none:

```
0.0.14   only no_type_only_cycles   ✅ Contract satisfied. Rules enforced: .
0.0.15   only no_type_only_cycles   ✅ Contract satisfied. Rules enforced: no_type_only_cycles.
0.0.14   all three rules            ✅ … Rules enforced: no_cycles, no_lazy_cycles.
0.0.15   all three rules            ✅ … Rules enforced: no_cycles, no_lazy_cycles, no_type_only_cycles.
```

Graph bytes on the pinned tree: 2965 nodes and 8617 edges, symmetric difference empty, provenance the same
apart from the tool version. **Procedure lesson:** when the fix lives in the *passing* branch, the
verification tree must be one where the rule passes — a red tree exercises the other branch and answers
nothing. Same shape as R1-C37, met in a release check rather than a test.

**0.0.16 published 2026-09-07:** [`codmap` 0.0.16](https://pypi.org/project/codmap/0.0.16/), schema
**0.13** (unchanged, fifth release running). Same procedure from the pushed commit `48d032f`, CI green,
`twine check` PASSED on both artifacts, tag `v0.0.16` written with `-F`. The first release since 0.0.12
that comes from our own reading rather than a neighbour's issue.

The release note claims the graph does not move, so the check from PyPI was exactly that claim, made with
**both published versions on one tree** — not with the working copy:

```
0.0.15 / 0.0.16 on the same 4-module tree:  nodes identical, edges identical
                                            schema 0.13 → 0.13; only `provenance` differs
0.0.16  report impact --symbol work         "Flows reached (1 of 1)" · `pkg.entry.main` — step 2
0.0.15  the same command                    no such section
0.0.16  report behavior                     "by route grade: **exact** 2"
0.0.15  the same report                     no such line
```

**Procedure lesson (small, and it costs a minute of doubt):** the first `uv run --with codmap==X.Y.Z`
after an upload answers *"there is no version X.Y.Z"* from uv's **cached** index — indistinguishable, at a
glance, from an upload that failed. `--refresh` resolves it. Check the version's PyPI page before
concluding anything about the upload.

**0.0.17 published 2026-09-12:** [`codmap` 0.0.17](https://pypi.org/project/codmap/0.0.17/), schema
**0.13** (unchanged, sixth release running). Same procedure from the pushed commit `985928e`, CI green,
`twine check` PASSED on both artifacts, tag `v0.0.17` written with `-F`. Three defects, all from one
consumer message on issue #19 — and the first release cut because a consumer was *blocked*: the `diff`
defect made their release gate fire on test churn, and their gate installs from PyPI.

Checked from PyPI with **both published versions on one four-module tree with a consumer root**, because
all three claims are behavioural and one is about the artifact:

```
nodes identical, edges identical; schema 0.13 -> 0.13; only `provenance` differs

R1-C50  report impact --symbol work      0.0.16: "Flows reached (0 of 0 entry point(s))"
                                         0.0.17: "Flows reached (1 of 1 entry point(s))"
R1-C52  diff, after a new PUBLIC         0.0.16: "1 added" -> usage.script.brand_new_test_helper
        function added in the consumer   0.0.17: "0 added" + "Not judged: 3 public symbol(s) in `usage`"
R1-C51  callers(min_confidence=exact)    0.0.16: envelope carries no filter block
        over `serve`                     0.0.17: {"min_confidence": "exact", "returned": 1, "total": 1,
                                                  "dropped": 0, "by_grade": {"exact": 1}}
```

**Procedure note, worth keeping:** 0.0.16 printed **"0 of 0 entry point(s)"** on that tree — not "1 of 1
with nothing reached". The verification tree has to contain the *shape* of the defect (a public head
called only from a consumer root), and building it revealed the released behaviour was a notch worse
than the issue described. Same lesson as 0.0.15's, from the other end: the tree, not the command, is
what decides whether a check can see anything.

**0.0.18 published 2026-09-12:** [`codmap` 0.0.18](https://pypi.org/project/codmap/0.0.18/), schema
**0.13** (unchanged, seventh release running). Same procedure from the pushed commit `7071b33`, CI green,
`twine check` PASSED on both artifacts, tag `v0.0.18` written with `-F`.

Two items, and the verification tree had to carry the **shape of both** — a three-module lazy cycle for
R1-C54 and a subscript-plus-dict-literal column pair for R1-C53:

```
nodes identical, edges identical; schema 0.13 -> 0.13; only `provenance` differs

R1-C54  check under 8 hash seeds   0.0.17: 3 distinct renderings (5 / 2 / 1)
                                   0.0.18: 8 of 8 identical
R1-C53  columns (serve)            0.0.17: bare list, no block
                                   0.0.18: filter {basis: subscripted_only, returned 1,
                                           total 2, dropped 1}
        communities (serve)        0.0.17: bare list, no block
                                   0.0.18: scope {root: core, judged 5, not_judged {}}
```

**This is the release whose own procedure was the defect's second victim.** R1-C54 arrived because the lab
compared two versions' output on one tree — exactly what this section prescribes — and a rendering that
moved with the hash seed read as a behavioural change. They re-measured within one version before drawing
the conclusion; the procedure did not tell them to. It does now: **when a release claim is about output
text, compare it under a fixed `PYTHONHASHSEED` — or several — not once per version.** The suite carries
that as a guard since R1-C54, so the procedure inherits it rather than relying on memory.

**0.0.19 published 2026-09-12:** [`codmap` 0.0.19](https://pypi.org/project/codmap/0.0.19/), schema
**0.13** (unchanged, eighth release running). Same procedure from the pushed commit `825355c`, CI green,
`twine check` PASSED on both artifacts, tag `v0.0.19` written with `-F`.

Three items, and every one of them came from **someone else's code**: the axis-B4 run over pytest, attrs
and Pillow. So the verification tree had to carry three shapes at once — a private override of a called
base, a `.pyi` closing a cycle with a `.py`, and a facade package whose stub carries `@overload`
declarations over an alias into a sibling:

```
                     0.0.18 (published)                    0.0.19 (published)

R1-C55  dead-code    JpegReader._open — high,               low, "overrides
                     "no inbound calls, references,          verifypkg.base.Reader._open, which
                      or decorators"                         has 1 inbound call(s) — reached by
                                                             dispatch, not by name"

R1-C56  architecture ## Import cycles: 1                    ## Import cycles: 0
                     read 3 module-level                    read 2 module-level + 1 `.pyi`;
                     (the cycle is a stub's import)         the cycle is in "closed only by an
                                                            import that never runs": 1

R1-C57  api-surface  error: Could not resolve alias         builds; "1 public symbols across 2
        (facade)     facade.Reader pointing at              modules; 1 more re-exported from
                     verifypkg.base.Reader                  outside this root" + "not judged here"
                     → no graph at all
```

**The procedure rule that earned its keep this time.** Two of the three claims are about *text*, so the
whole comparison ran under a fixed `PYTHONHASHSEED` — the rule 0.0.18 bought with R1-C54. And the
**fixture** had to be built to carry the defect, which is where the work was: the first version of the
facade fixture did not crash 0.0.18 at all, because that crash needs `@overload` declarations in the stub
over a name the runtime module only aliases. A verification tree that does not reproduce the defect
verifies nothing, and it is easy to believe it does.

**0.0.20 published 2026-09-12:** [`codmap` 0.0.20](https://pypi.org/project/codmap/0.0.20/), schema
**0.13** (unchanged, ninth release running). Same procedure from the pushed commit `58bcb63`, CI green,
`twine check` PASSED on both artifacts, tag `v0.0.20` written with `-F`.

One item (R1-C58), and it **changes the shape of an answer consumers read**, so it shipped alone rather
than folded in. Two fixtures, because the claim has two halves — the unit, and what the unit preserves:

```
                                   0.0.19 (published)        0.0.20 (published)

7-module dense knot                ## Import cycles: 115     1 tangle(s), 7 module(s),
(21 edges, every path a cycle)                               15 independent loop(s)

two loops sharing one module       ## Import cycles: 2       1 tangle(s), 5 module(s),
                                   both listed                2 independent loop(s)

flat package (no subpackages)      ## Layers (6)             + "layer = module here:
                                   no note                     …a statement that there is
                                                               none to report"
```

**The second fixture is the one that matters**, and it is there because a guard demanded it. A knot of
five modules with two loops is where "one tangle" could hide that there are two problems; the
independent-loop count is what keeps the old number's meaning, and on small knots it *equals* the old
number (2 → 2). Verifying only the dense fixture would have shown the explosion cured and said nothing
about what the cure cost.

**0.0.21 published 2026-09-26:** [`codmap` 0.0.21](https://pypi.org/project/codmap/0.0.21/), schema
**0.13** (unchanged, tenth release running), **`ANSWER_FORMAT` 1** — introduced here. Same procedure from
the pushed commit `9a9fc99`, CI green, `twine check` PASSED on both artifacts, tag `v0.0.21` written
with `-F`.

Two items (R1-C62, R1-C63), and they ship together because both change the gate's output and a consumer
should read one notice rather than two. Verified from PyPI under a fixed `PYTHONHASHSEED`, on trees
carrying the shape of each defect — a contract whose every name is fictional, and a contract whose names
all exist:

```
                                   0.0.20 (published)        0.0.21 (published)

phantom contract, 3 fictional      ✅ layered (3),            ✅ layered (3 declared,
layers named in 3 rules            independent (1),             0 applicable), … + the
                                   forbidden (1)                three names listed

same file + no_phantom_rules       exit 0 (unknown key)      exit 2, the three names
                                                              as the violation

sound contract (fixture)           —                         one added line: the trailer
consumer's live tree               exit 0                    exit 0, one added line
graph on the same tree             —                         nodes and edges hash
                                                              identical, 0.13 → 0.13
```

**The sound-contract rows are the ones worth having measured.** R1-C62's whole promise is that a contract
naming only things that exist does not change at all, and 0.0.20 is why that promise needed a
measurement rather than a claim: that release moved the text for everyone, and the consumer had to be
told by hand. The only movement here is the R1-C63 trailer, which is the mechanism that replaces the
hand-written note — and it is stated as a cost in the changelog rather than buried.

**0.0.22 published 2026-10-15:** [`codmap` 0.0.22](https://pypi.org/project/codmap/0.0.22/), schema
**0.13** (unchanged, eleventh release running), **`ANSWER_FORMAT` 2** — only `pack` changed shape. Same
procedure from the pushed commit `695e8f0`, CI green, `twine check` PASSED on both artifacts, tag
`v0.0.22` written with `-F`.

Five items (R1-C59, R1-C60, R1-C64, R1-C65, R1-C66). The two `pack` items are the reason for the
format bump and for shipping together: one changed what the answer says about its seed, the other what
a seeded pack contains, and a consumer should see one format number move once. Verified from PyPI
against 0.0.21 under `PYTHONHASHSEED=7`, on a tree carrying every defect — checked on 0.0.21 first, as
the fourth rule asks:

```
                                   0.0.21 (published)        0.0.22 (published)

pack --seed seed                   caller rank 0.0 — in the  caller rank 0.117, tests
(caller → seed → helper, a test)   pack only as filler        reached, `walk: both`
pack --seed no_such_symbol         exit 0, the global pack   exit 1, refused
pack --direction uses              unknown argument          exit 0, no caller, no test
doctor                             unknown command           exit 0, griffe OK, jedi OK
diff, 7 of 38 `calls` cut          silent                    calls 38 → 31 (−18.4 %) named
dead-code, one nested def          no line                   the blind-spot line names it
graph on the same tree             —                         nodes and edges hash identical
consumer's live tree, check        exit 0                    exit 0, one line: format 1 → 2
build -o over a 0.0.21 graph       —                         silent (nothing was lost)
```

**The first row needed a better question than the one first asked.** "Is the caller in the pack?" is
*yes* on 0.0.21 too: with no cut by reachability, an unlimited budget topped the pack up with every
symbol at rank 0, the caller among them. The defect is visible in the rank, not in the presence — which
is R1-C65's fourth defect showing up in its own release check.

**The second consumer was never told (found 2026-10-15).** bquearch calls `codemap` from its own gate
(`scripts/codemap_gate.sh`, `uv run --with codmap==X`, the version on one line) and pins **0.0.17**.
0.0.18–0.0.22 were announced to bquant only: a note of ours said the lab did not depend on `codmap`,
because the grep read their `pyproject.toml` and the pin lives in a script. Before telling them, their
gate is run on a copy of their tree at `1c34925`, with both published versions and
`PYTHONHASHSEED=7`. The expectations below are written before the run:

- **E1, clean tree.** exit 0 on 0.0.17 and on 0.0.22, so the verdict does not move.
- **E2, text.** The diff of `check` adds the trailer `_answer format 2 · schema 0.13_`. If the lab has
  function-local cycles, the cycle line is also reworded as tangles (0.0.20). Nothing else changes. If
  the two outputs are byte-identical, the run did not reach two versions. That is the
  nothing-was-done control.
- **E3, mutation.** Their own recipe: a lazy `scenario_scoring` import inside
  `state_calib.open_leg_outcome_label`, on a copy named `shared`. It gives exit 2 on both versions,
  with both chains named.
- **E4, graph.** The `imports` edge sets are identical across the two versions. The full graph may
  differ only through 0.0.19's re-export and override changes; `.pyi` files under `research/shared`: 0.
  Any difference is named.
- **Where a refusal could be heard: R1-C62** (0.0.21). A contract rule that covers nothing stops
  counting as enforced. If their contract names a layer the graph lacks, 0.0.22 says so, and that would
  be the one change in substance.

Reconciled after the run. The tree is `1c34925`, both versions come from PyPI, `PYTHONHASHSEED=7`.

```
                         0.0.17                       0.0.22
clean tree, check        exit 0                       exit 0, + `_answer format 2 · schema 0.13_`
mutation, check          exit 2, two chains listed    exit 2, one chain + "tangle of 3" naming zcast
graph, clean / mutation  3044 nodes, 7814 / 7815 edges    identical node and edge sets
`imports` edges          233 / 234                    identical
```

E1, E2 and E4 hold. On E4 the result is stronger than predicted: the whole graph is identical, not only
its `imports` edges. R1-C62 is silent. Their contract carries no layer rules, only the three cycle
rules, so it has nothing to name. **E3 holds on the exit code but not word for word.** Their recipe
asks for "exit 2, both chains named". 0.0.22 lists one example chain and names `zcast` as a member of
the tangle. That is the 0.0.20 unit of a cycle (R1-C58), and it was announced to bquant. The lab was
never told, and their check is written against the old wording. The notice says so.

**A surprise in my own harness.** The first pass printed `exit=0` for the mutation, beside a report
saying the rule was broken. The cause: `echo "… $(basename $T) exit=$?"` runs a command substitution
before `$?` is read, so the substitution reset it to 0. The report and the exit code disagreed, and the
report was right. Exit codes now come from `rc=$?` on the line right after the command.

**0.0.23 — the release check, pre-registered before the upload (2026-11-03).** Five items (R1-C68–C72);
schema **0.13** unchanged; **`ANSWER_FORMAT` 2 → 3**. Both versions are installed from PyPI into clean
environments, with `PYTHONHASHSEED=7`. One fixture tree carries the form of every defect, and it is run
on 0.0.22 **first**, to show that the defects are visible there (rule 4).

| | tree form | 0.0.22 (expected) | 0.0.23 (expected) |
|---|---|---|---|
| R1-C68 | `import pkg.analysis.b` in `pkg/core/a.py`; `forbidden core → analysis` | exit 0, "Contract satisfied" | exit 2, `pkg.core.a → pkg.analysis.b` named |
| R1-C69 | `forbiden = [...]` | exit 0, "No `[architecture]` contract found" | exit 2, "not a valid contract", `forbiden` named |
| R1-C70 | graph built, then a forbidden import added; `check --graph` | exit 0, no word about the graph | exit 2, "behind its source tree" |
| R1-C71 | `import pkg.analysis.b` + `pkg.analysis.b.f()` | no `calls` edge | `calls` edge to `pkg.analysis.b.f` |
| R1-C72 | `pkg/logging.py` + `import logging` in `a.py` + `from pkg import a` in `b.py` | `imports` `a → pkg.logging`, `resolution: flat` | no such edge |
| format | any markdown answer | `_answer format 2 · schema 0.13_` | `_answer format 3 · schema 0.13_` |

**Consumers, before they are told:**
- **bquant** (its live tree, `codemap check --build bquant` from its own `codemap.toml`): exit 0 on both
  versions, and the text differs by the trailer alone.
- **bquant graph:** `imports` and every edge identical. Nodes differ only in `extras.calls` counters, by
  R1-C71's measured shift (external +38, unresolved −36, dynamic −2 at `8efa112`).
- **bquearch** (its gate on a copy of its tree): the verdict is unchanged. The text differs by the
  trailer alone; their contract holds only cycle rules, so R1-C69 has nothing to refuse.
- If either text diff is empty, the run did not reach two versions. That is the nothing-was-done
  control.

**Addendum before the consumer runs: both consumers call `check --graph`, not `--build`.** The bullets above,
and what I told the owner before the release, assumed `check --build`. That was not read from their trees.
In fact:
- bquearch's `scripts/codemap_gate.sh` builds `research/shared` into a temporary file (relative name,
  `--mode full`) and runs `check --graph … --require-contract`;
- bquant documents `codemap check --graph .codemap/graph.json`.

So R1-C70 reaches both. The danger is a *false* "behind", which would turn their gates red: the recipe
read wrongly (`--mode full`, a relative path, a temporary directory), or the scope resolved differently.
Added expectations for the form they actually run, written before it runs:
- **bquearch gate** (a copy of `aa5c02a`, the gate script with only the version changed): exit 0 on both
  versions. 0.0.23 says "The graph matches its source tree". The text diff is that line and the trailer,
  nothing else.
- **bquant** (`build bquant -o .codemap/graph.json`, then `check --graph .codemap/graph.json`): exit 0 on
  both; diff = the currency line + the trailer.
- **Control for the new failure mode:** the same bquearch copy with a forbidden import added after the
  build gives exit 2 on 0.0.23, "behind". If it said "current", the check would be blind.

**0.0.23 published 2026-11-03:** [`codmap` 0.0.23](https://pypi.org/project/codmap/0.0.23/), schema **0.13**
(unchanged, twelfth release running), **`ANSWER_FORMAT` 3**. Same procedure from the pushed commit
`06fdc65`, CI green on 3.11–3.14, `twine check` PASSED on both artifacts, tag `v0.0.23` written with `-F`.
Reconciled from PyPI, `PYTHONHASHSEED=7`, on the stand inside the shared core-slot accounting:

```
                         0.0.22 (published)                 0.0.23 (published)
R1-C68 import a.b.c      exit 0, "Contract satisfied"       exit 2, the edge named
R1-C69 forbiden = [...]  exit 0, "No contract found"        exit 2, "not a valid contract", `forbiden`
R1-C70 stale --graph     exit 0, no word                    exit 2, "behind its source tree"
R1-C71 pkg.analysis.b.f  no calls edge                      calls → pkg.analysis.b.f
R1-C72 logging twin      imports a → pkg.logging (flat)     none
trailer                  _answer format 2 · schema 0.13_    _answer format 3 · schema 0.13_
bquant --build           exit 0                             exit 0, diff = trailer only
bquant --graph (doc'd)   exit 0                             exit 0, diff = currency line + trailer
bquant graph             —                                  edges identical; nodes differ only in
                                                            extras.calls (external +38, unresolved −36,
                                                            dynamic −2: R1-C71's measured shift)
bquearch gate (aa5c02a)  exit 0                             exit 0, diff = currency line + trailer
bquearch control         —                                  content changed after the build: exit 2, "behind"
```

Every expectation holds, the added ones included.
- The fixture was run on 0.0.22 first, and every defect showed there (rule 4).
- The control used a neutral line appended to a module, not a forbidden import. That is enough for the
  currency check, which is what it controls; the contract rule itself is covered by R1-C68's row.

**Two of my own mistakes, both caught before anyone was told:**
- **The owner was told that both consumers run `check --build`.** They run `check --graph`, so R1-C70
  reaches them. The danger was a false "behind" turning their gates red. Measured: it does not; both read
  "matches its source tree".
- **The first fixture pass on 0.0.23 answered "no version of codmap==0.0.23"** for its first two calls:
  the index cache just after the upload, a trap already on record. Re-run with `--refresh`, it gives the
  table above.

**0.0.24 — the release check, pre-registered before the upload (2026-11-03).** Two items (R1-C73, R1-C74);
schema **0.13** unchanged; **`ANSWER_FORMAT` 3 → 4** (`report behavior` names the whole and its parts).
Same procedure: both versions from PyPI into clean environments, `PYTHONHASHSEED=7`, the fixture tree run on
0.0.23 **first** (rule 4). The fixtures are the forms of the unit tests, so a fixture that shows nothing on
0.0.23 is a fixture that does not carry the defect, and the row fails.

| | tree form | 0.0.23 (expected) | 0.0.24 (expected) |
|---|---|---|---|
| R1-C73 | `codemap --version` | exit 2, argparse asks for a command | exit 0, exactly `codemap 0.0.24 · answer format 4 · schema 0.13` (no `@commit`: an installed wheel has none) |
| R1-C74 two bodies | `f` defined in both branches of an `if`, bodies with 2 and 1 calls of `h` | `f`'s `calls.out` = 1, the last body | `calls.out` = 3 |
| R1-C74 namesake | `def lookup` nested in `M.closure`, beside a method `M.lookup` | a `calls` edge `M.lookup → target`, which `M.lookup` never makes | no such edge; `M.closure → target`, `via: nested`; `M.lookup` `calls.out` = 0 |
| R1-C74 class body | `class C:` with `X = h()` | no `calls` edge from `C`, no counter on `C` | `calls` edge `C → h`; `C` carries `calls` |
| report | `report behavior` on that tree | heading "Call-site resolution (N sites in M functions)" | "Call-site resolution (N call sites)" plus the parts line |
| format | any markdown answer | `_answer format 3 · schema 0.13_` | `_answer format 4 · schema 0.13_` |

**Consumers, before they are told:**
- **bquant** (its tree at today's `7e33039`): `check --build bquant` and the documented `build` + `check --graph`
  both exit 0 on both versions; the text diff is the trailer alone. The currency line is in both.
- **bquant graph** (at `8efa112`, where R1-C74's acceptance was measured): `imports` identical. `calls` edges: **+16,
  every one from a class node, 0 removed**. Nodes identical outside the `extras` keys `calls`, `calls_nested`,
  `calls_shadowed`, and **one** node whose existing `calls` value changes (the node with two bodies).
- **bquearch** (its gate on a copy of its tree at `72f73f3`, the gate script with only `CODMAP_VERSION` changed,
  0.0.23 → 0.0.24): exit 0 on both; the text diff is the trailer alone. Their contract holds cycle rules over
  `imports`, which R1-C74 does not touch.
- **Nothing-was-done control:** if any consumer's text diff is empty, the run did not reach two versions.
- **bquearch's pin is theirs to raise.** They are told after the upload, with the format change named.

**0.0.24 published 2026-11-03:** [`codmap` 0.0.24](https://pypi.org/project/codmap/0.0.24/), schema **0.13**
(unchanged, thirteenth release running), **`ANSWER_FORMAT` 4**. Same procedure from the pushed commit
`e7a69dd`: suite 1125 passed / 3 skipped, CI green on 3.11–3.14, `twine check` PASSED on both artifacts.
Reconciled from PyPI, `PYTHONHASHSEED=7`, inside the shared core-slot accounting:

```
                         0.0.23 (published)                         0.0.24 (published)
R1-C73 --version         exit 2, "arguments are required: command"  exit 0, codemap 0.0.24 · answer format 4 · schema 0.13
two bodies               f calls.out = 1                            3
namesake                 M.lookup → target (false), out 1           M.closure → target via nested; M.lookup out 0
class body               no edge from C, no counter                 C → h; C carries calls (out 1)
report behavior          "(2 sites in 6 functions)"                 "(5 call sites)" + "3 in function bodies, 1 in
                                                                    nested functions, 0 at module level, 1 in class bodies"
trailer                  _answer format 3 · schema 0.13_            _answer format 4 · schema 0.13_
bquant --build (7e33039) exit 0                                     exit 0, diff = trailer only
bquant --graph           exit 0                                     exit 0, diff = trailer only
bquant graph (8efa112)   —                                          imports identical; calls +16 (all from class nodes),
                                                                    −0; other edges identical; nodes identical outside
                                                                    the counter keys; 1 node's calls changed
                                                                    (ZigZagSwingStrategy.deviation, the property with a setter)
bquearch gate (72f73f3)  exit 0                                     exit 0, diff = trailer only
```

Every expectation holds. The fixture was run on 0.0.23 first, and every defect showed there (rule 4). The
fixture's 5 call sites on 0.0.24 are the source's 5 `ast.Call`s; 0.0.23 counted 2 of them.

**Two things of my own, both caught before anyone was told:**
- **The first fixture pass called `report pkg --root .`**, which is not the command's form (`report <kind>
  --graph`). It exited 2 on 0.0.23 and printed nothing to compare. Fixed in the script, re-run on 0.0.23
  before the upload, and the table above is from the corrected script.
- **The first 0.0.24 pass hit the index cache again** ("no version of codmap==0.0.24") on its first calls,
  though the script passes `--refresh-package`. Later calls in the same pass already got 0.0.24. After
  `uv cache clean codmap` the whole fixture ran on 0.0.24 and gives the table. The consumer runs in that
  pass were on 0.0.24 throughout: their trailer says format 4.

**0.0.25 — the release check, pre-registered before the upload (2026-11-04).** One item (R1-C75); schema
**0.13** and **`ANSWER_FORMAT` 4** unchanged. The first release decided by the codemap session under the
owner's delegation of 2026-11-04 (recorded in a kogriv/codemap issue for this release). Same
procedure: both versions from PyPI, `PYTHONHASHSEED=7`, the fixture run on 0.0.24 first (rule 4).

| | tree form | 0.0.24 (expected) | 0.0.25 (expected) |
|---|---|---|---|
| R1-C75 | `from pkg.indicators import LibraryManager` + `LibraryManager.create_indicator()` | no `calls` edge, `unresolved` 1 | `calls` edge to `…manager.LibraryManager.create_indicator`, `resolved` 1 |
| version | `codemap --version` | `codemap 0.0.24 · answer format 4 · schema 0.13` | `codemap 0.0.25 · answer format 4 · schema 0.13` |
| trailer | any markdown answer | `_answer format 4 · schema 0.13_` | the same |

**Consumers, before they are told:**
- **bquant** (its tree at today's HEAD, `check --build bquant` and `build` + `check --graph`): exit 0 on both,
  and the text output is **byte-identical**. The format did not move, so an empty diff is the expectation
  here, not a sign that nothing ran.
- **The nothing-was-done control** is therefore the graph. On bquant `8efa112`, 0.0.25 has exactly R1-C75's
  6 extra `calls` pairs and counters +6/−6, and nothing else differs. If the graphs are identical, the run
  did not reach two versions.
- **bquearch** (its gate on a copy of its HEAD, `CODMAP_VERSION` changed only): exit 0 on both,
  byte-identical output.

**0.0.25 published 2026-11-04:** [`codmap` 0.0.25](https://pypi.org/project/codmap/0.0.25/), schema **0.13**,
**`ANSWER_FORMAT` 4**, both unchanged. From the pushed commit `8571123`: CI green on 3.11–3.14, the suite at the
fix commit 1127 passed / 3 skipped, `twine check` PASSED on both artifacts. Reconciled from PyPI,
`PYTHONHASHSEED=7`, inside the shared slot accounting:

```
                         0.0.24 (published)                    0.0.25 (published)
R1-C75 fixture           no calls edge, unresolved 1           calls → …LibraryManager.create_indicator, resolved 1
--version                codemap 0.0.24 · answer format 4 …    codemap 0.0.25 · answer format 4 · schema 0.13
trailer                  _answer format 4 · schema 0.13_       the same
bquant (aca0718)         --build, --graph exit 0               exit 0; text byte-identical on both
bquant graph (8efa112)   —                                     calls +6, exactly R1-C75's predicted pairs; −0;
                                                               counters +6/−6; nodes identical outside counters
bquearch gate (1f119da)  exit 0                                exit 0; output byte-identical
```

Every expectation holds. The fixture was run on 0.0.24 first and showed the defect (rule 4). **One slip,
known:** the first 0.0.25 `--version` call in the consumer pass hit the index cache again ("no version of
codmap==0.0.25"), though the script had just run `uv cache clean codmap`. The build in the same pass already
got 0.0.25. A re-run a minute later gave the table's line. So the cache-clean is not enough right after an
upload, and waiting is.

**0.0.26 — the release check, pre-registered before the upload (2026-11-04).** One item (R1-C76); schema
**0.13** and **`ANSWER_FORMAT` 4** unchanged. Decided by the codemap session under the owner's delegation
(kogriv/codemap issue for this release). Fixture run on 0.0.25 first (rule 4), `PYTHONHASHSEED=7`.

| | tree form | 0.0.25 (expected) | 0.0.26 (expected) |
|---|---|---|---|
| R1-C76 | `[architectur]` with a rule the tree breaks | exit 0, "No `[architecture]` contract found" | exit 2, names `[architectur]` and `[architecture]` |
| R1-C76 control | the same rule under `[architecture]` | exit 2, 1 rule broken | the same |
| version | `codemap --version` | `codemap 0.0.25 · …` | `codemap 0.0.26 · answer format 4 · schema 0.13` |

**Consumers:** bquant (HEAD) and bquearch (HEAD): exit 0 on both versions, output byte-identical, graphs
identical too. Neither has a near-miss table, so the fixture row and the version line are the
nothing-was-done controls.

**0.0.26 published 2026-11-04:** [`codmap` 0.0.26](https://pypi.org/project/codmap/0.0.26/), schema 0.13,
`ANSWER_FORMAT` 4. From `1f156f6`: suite at the fix commit 1133 passed / 3 skipped, CI green on 3.11–3.14,
`twine check` PASSED. Reconciled from PyPI:

```
                         0.0.25 (published)                       0.0.26 (published)
[architectur] + rule     exit 0, "No [architecture] contract"     exit 2, "Contract not read", names both tables
[architecture] + rule    exit 2, 1 rule broken                    the same
--version                codemap 0.0.25 · …                       codemap 0.0.26 · answer format 4 · schema 0.13
bquant (f9d4f2b)         exit 0                                   exit 0; output byte-identical; graph identical
bquearch gate (ecbb16b)  exit 0                                   exit 0; output byte-identical
```

Every expectation holds. The index-cache slip happened a third time: the first `--version` call failed even
after a 60 s wait inside the script, and the call in the same pass's next line already got 0.0.26. A separate
call a few minutes later gave the line above. The rule from now on: verify the version line last, in its own
call.

**0.0.27 — the release check, pre-registered before the upload (2026-11-05).** Three items (R1-C77, R1-C78,
R1-C79); schema **0.13** and **`ANSWER_FORMAT` 4** unchanged. Decided by the codemap session under the owner's
delegation. Fixture run on 0.0.26 first (rule 4), `PYTHONHASHSEED=7`. Fixture `pkg`: `data/d.py` imports
`core.c`, `core/c.py` imports `analysis.a`; fixture `gp`: `high/h.py` imports `mid.m`, `mid/m.py` imports
`high.h`.

| | tree form | 0.0.26 (expected) | 0.0.27 (expected) |
|---|---|---|---|
| R1-C78 | `pkg`, `{from="data", to="analysis", indirect=true}` | exit 2, "Contract not read", unknown key `indirect` | exit 2, "`data` must not reach `analysis`", witness `pkg.data.d → pkg.core.c → pkg.analysis.a` |
| R1-C78 control | `pkg`, the same item without `indirect` | exit 0, `forbidden (1)` | the same |
| R1-C79 | `gp`, `layers = ["high", "mid", "high", "low"]` | exit 2, `layered`, the **legal** edge `gp.high.h → gp.mid.m` named | exit 2, "Contract not read", "`layers` repeats `high`" |
| R1-C79 control | `gp`, `layers = ["high", "mid", "low"]` | exit 2, `layered`, `gp.mid.m → gp.high.h` | the same |
| version | `codemap --version` | `codemap 0.0.26 · …` | `codemap 0.0.27 · answer format 4 · schema 0.13` |

**Consumers:** bquant (HEAD) and bquearch (HEAD): exit 0 on both versions, output byte-identical. Neither uses
`indirect` or repeats a name, so the two fixture rows and the version line are the nothing-was-done controls.

**0.0.27 published 2026-11-05:** [`codmap` 0.0.27](https://pypi.org/project/codmap/0.0.27/), schema 0.13,
`ANSWER_FORMAT` 4. From `b4ab0aa`: suite at the release commit 1177 passed / 3 skipped (1180 collected), CI green
on 3.11–3.14, `twine check` PASSED. Reconciled from PyPI:

```
                          0.0.26 (published)                          0.0.27 (published)
pkg, indirect = true      exit 2, "Contract not read", key `indirect`  exit 2, `data` must not reach `analysis`, witness d → c → a
pkg, without indirect     exit 0, forbidden (1)                        the same
gp, layers repeats high   exit 2, the LEGAL gp.high.h → gp.mid.m named exit 2, "Contract not read", `layers` repeats `high`
gp, valid layers          exit 2, gp.mid.m → gp.high.h                 the same
--version                 codemap 0.0.26 · …                           codemap 0.0.27 · answer format 4 · schema 0.13
bquant (cf039ef)          exit 0                                       exit 0; output byte-identical
bquearch gate (703696d)   exit 0                                       exit 0; output byte-identical
```

Every expectation holds. The index cache struck a fourth time, on the first fixture: the first call of the pass
exited 1 with no output, the next calls already ran 0.0.27. Re-run alone, it gave the line above; the version
line was checked last, in its own call.

**0.0.28 — the release check, pre-registered before the upload (2026-11-05).** One item (R1-C80); schema **0.13**
unchanged, **`ANSWER_FORMAT` 4 → 5**. Fixture: `pkg/core.py` (`act`, `wrap → act`), `tests/test_a.py` with
`_helper → act`, `test_direct → act`, `test_through_helper → _helper`, `test_far → wrap`; repo-scoped, `--mode full`.

| | tree form | 0.0.27 (expected) | 0.0.28 (expected) |
|---|---|---|---|
| R1-C80 | `tests act` | `test_direct` only; no "more" line | `test_direct`, then "… 2 more test(s) at distance 2" |
| R1-C80 | `tests act --all-bands` | error: unknown option | `test_direct` (1), `test_far` and `test_through_helper` (2) |
| R1-C80 | `--format json` | no `next_band` key | `next_band: {distance: 2, count: 2}` |
| version | `codemap --version` | `codemap 0.0.27 · answer format 4 · schema 0.13` | `codemap 0.0.28 · answer format 5 · schema 0.13` |

**Graph (E0):** the fast graph of bquant `cf039ef` is byte-identical across two builds of 0.0.28; against 0.0.27,
nodes are identical, core-to-core edges are identical, and only `resolution: "local"` edges inside consumer roots
are added. On deep, one extra core edge appeared in a single build
(`ZoneAnalysisPipeline._validate → ModelValidationResult.to_dict`). I expect it to be deep-tier sampling, not this change:
in two more deep builds of 0.0.28 it is present in some and absent in others, or absent in both. If it is present in
every 0.0.28 build and absent from every 0.0.27 build, it is this change, and the release stops.
**Consumers:** `check` on bquant (`cf039ef`) and bquearch (`703696d`): exit 0, output byte-identical apart from the
trailer, which reads answer format 5.

**0.0.28 published 2026-11-05:** [`codmap` 0.0.28](https://pypi.org/project/codmap/0.0.28/), schema 0.13,
`ANSWER_FORMAT` 5. From `04fa363`: suite 1186 passed / 3 skipped (1189 collected), CI green on 3.11–3.14, `twine check`
PASSED. Reconciled from PyPI and the stand:

```
                         0.0.27                                      0.0.28
tests act                test_direct; no "more" line                 test_direct; "… 2 more test(s) at distance 2"
tests act --all-bands    error: unrecognized arguments               test_direct (1), then distance 2
--format json            no next_band key                            next_band {distance: 2, count: 2}
--version                codemap 0.0.27 · answer format 4 · …        codemap 0.0.28 · answer format 5 · schema 0.13
bquant (cf039ef)         exit 0                                      exit 0; identical apart from the trailer
bquearch gate (703696d)  exit 0                                      exit 0; identical apart from the trailer
graph, bquant fast       —                                           byte-identical across two builds; vs 0.0.27: nodes and
                                                                     core edges identical, +1107 edges, all `local`
deep edge _validate → to_dict   absent (0.0.27, one build)           present in one 0.0.28 build, absent in the other
```

Every expectation holds. The deep edge is sampling: present in one 0.0.28 build and absent in another, which is the
outcome written down as "not this change". The index cache struck again, and this time it was not cured by a first call alone: two
calls with `--refresh-package` were needed before uv saw 0.0.28. Every call in the verification now carries that flag.

**0.0.29 — the release check, pre-registered before the upload (2026-11-05).** Two items (R1-C84, R1-C83); schema
**0.13** and `ANSWER_FORMAT` **5** unchanged. Fixture: `pkg/core.py` (`act`), `tests/test_a.py` (`test_a → act`), an
`examples/` directory; a graph built with `--consumer tests` whose sidecar is then given a `roots_base` that does not
exist (a graph built elsewhere).

| | tree form | 0.0.28 (expected) | 0.0.29 (expected) |
|---|---|---|---|
| R1-C84 | `build pkg --consumer nope` | exit 0 | exit 2, "`--consumer nope`: no such directory" |
| R1-C84 | `build pkg --consumer tests,examples` | exit 0 | exit 2, hint `--consumer tests --consumer examples` |
| R1-C83 | `tests act` from the repo root, foreign sidecar | "1 of 1 path(s) could not be located" | no such caveat; "built in … not on this machine" |
| R1-C83 | `tests act --source-root fix` from the parent | error: unrecognized arguments | `pytest fix/tests/test_a.py::test_a` |
| version | `codemap --version` | `codemap 0.0.28 · answer format 5 · schema 0.13` | `codemap 0.0.29 · answer format 5 · schema 0.13` |

**Graph:** the fast repo graph of bquant `cf039ef` (four consumers, `docs`) is identical between the two versions
apart from `provenance.tool`. **Consumers:** `check` on bquant (`cf039ef`) and bquearch (`703696d`): exit 0, output
byte-identical (same answer format, so the trailer matches too).

**0.0.29 published 2026-11-05:** [`codmap` 0.0.29](https://pypi.org/project/codmap/0.0.29/), schema 0.13,
`ANSWER_FORMAT` 5. From `6c802d7`: suite 1204 passed / 3 skipped (1207 collected), CI green on 3.11–3.14, `twine check`
PASSED. Reconciled from PyPI:

```
                                   0.0.28                                     0.0.29
build --consumer nope              exit 0                                     exit 2, "`--consumer nope`: no such directory"
build --consumer tests,examples    exit 0                                     exit 2, hint `--consumer tests --consumer examples`
tests act, repo root, foreign      "1 of 1 path(s) could not be located"      "the graph was built in … not on this machine"
tests act --source-root fix        error: unrecognized arguments              pytest fix/tests/test_a.py::test_a
--version                          codemap 0.0.28 · answer format 5 · …       codemap 0.0.29 · answer format 5 · schema 0.13
bquant graph (cf039ef, fast)       —                                          identical apart from provenance.tool
bquant check / bquearch gate       exit 0                                     exit 0; byte-identical, trailer included
```

Every expectation holds. Two things are not covered by that table. The consumer trees on the check machine are
copies without `.git`, so their commits could not be printed; they are the same directories as the 0.0.28 check.
CI on the fix commit (a305b1d) went red on the README test count. The rule written after 0.0.27, "update the count
in the same commit as the suite", was broken again; 6c802d7 carries the right number. The index cache needed two
calls again.

**0.0.30 — the release check, pre-registered before the upload (2026-11-06).** One item (R1-C82); schema **0.13**
unchanged, **`ANSWER_FORMAT` 5 → 6**. Tree: bquearch `a948d6c`, graph of `shared` (fast, `--mode full`), diff
`git diff --relative=research a948d6c^ a948d6c`, which changes one line, the tuple `SURFACE_NAMES`.

| | tree form | 0.0.29 (expected) | 0.0.30 (expected) |
|---|---|---|---|
| R1-C82 | `review` on that diff | 3 symbols; `[high] shared.contracts`, "123 site(s) — check on signature change" | 1 symbol, `[medium] SURFACE_NAMES`, consumers `{'core': 2}` |
| version | `codemap --version` | `codemap 0.0.29 · answer format 5 · schema 0.13` | `codemap 0.0.30 · answer format 6 · schema 0.13` |

**Graph:** node ids identical to 0.0.29, no edge removed, every added edge `accesses` with `resolution: "name"`
(bquearch `shared` and bquant `cf039ef`). **Consumers:** `check` on bquant and the bquearch gate: exit 0, output
identical apart from the trailer, which reads answer format 6.

**0.0.30 published 2026-11-06:** [`codmap` 0.0.30](https://pypi.org/project/codmap/0.0.30/), schema 0.13,
`ANSWER_FORMAT` 6. From `3a4a52a` (code identical to `e3a49ec`, whose suite ran 1217 passed / 3 skipped, 1220
collected), CI green on 3.11–3.14, `twine check` PASSED. Reconciled from PyPI:

```
                               0.0.29                                          0.0.30
review, bquearch a948d6c       3 symbols; [high] shared.contracts,             1 symbol; [medium] SURFACE_NAMES,
                               "123 site(s) — check on signature change"       consumers {'core': 2}
--version                      codemap 0.0.29 · answer format 5 · …            codemap 0.0.30 · answer format 6 · schema 0.13
graph, bquearch shared         —                                               node ids equal; 0 removed; +681, all accesses/name
graph, bquant cf039ef          —                                               node ids equal; 0 removed; +301, all accesses/name
bquant check / bquearch gate   exit 0                                          exit 0; identical apart from the trailer (format 6)
```

Every expectation holds.

**0.0.31 — the release check, pre-registered before the upload (2026-11-06).** One item (R1-C81); schema **0.13**
unchanged, **`ANSWER_FORMAT` 6 → 7**. Tree: bquearch `703696d`, graph as in their MCP script (`shared`, `--deep
--mode full`, four consumers).

| | tree form | 0.0.30 (expected) | 0.0.31 (expected) |
|---|---|---|---|
| R1-C81 | `implementers PathForecaster` | `[]` | the 6 menu forecasters |
| R1-C81 | `tests KnnRecursiveForecaster.band` | `unknown`, 0 tests | answered; `test_a_rows_scenarios_…` and `test_gate_and_runtime_…` at distance 1, `low`, with the dispatch caveat |
| version | `codemap --version` | `codemap 0.0.30 · answer format 6 · schema 0.13` | `codemap 0.0.31 · answer format 7 · schema 0.13` |

**Consumers:** `check` on bquant and the bquearch gate: exit 0, output identical apart from the trailer (format 7).

**0.0.31 published 2026-11-06:** [`codmap` 0.0.31](https://pypi.org/project/codmap/0.0.31/), schema 0.13,
`ANSWER_FORMAT` 7. From `221445e` (code identical to `dfcbfe7`, whose suite ran 1225 passed / 3 skipped, 1228
collected), CI green on 3.11–3.14, `twine check` PASSED. Reconciled from PyPI on bquearch `703696d` (deep, their
four consumers):

```
                                   0.0.30                    0.0.31
implementers PathForecaster        []                        KnnAdaptive, KnnPath, KnnRecursive, KnnStrata, MdnLegs, QuantileBand
tests KnnRecursiveForecaster.band  unknown, 0 tests          low, 16 tests; test_a_rows_… and test_gate_and_runtime_… at
                                                             distance 1, low; the dispatch caveat
--version                          … answer format 6 …       codemap 0.0.31 · answer format 7 · schema 0.13
bquant check / bquearch gate       exit 0                    exit 0; identical apart from the trailer (format 7)
```

Every expectation holds. The first probe of `implementers` printed `[]` for both versions. My script read a
`query` dossier key that does not exist; through the `implementers` op (argument `protocol`), the result is the
table above.

**0.0.32 — the release check, pre-registered before the upload (2026-11-06).** Two items (R1-C87, R1-C88);
schema **0.13**, **`ANSWER_FORMAT` 7 → 8**.

| | tree form | 0.0.31 (expected) | 0.0.32 (expected) |
|---|---|---|---|
| R1-C87 | bquearch `a948d6c`, graph from `research/`, plain `git diff` → `review` | "0 changed symbol(s)", exit 0 | `[medium] shared.contracts.SURFACE_NAMES`, suffix-mapping line, exit 0 |
| R1-C87 | a diff of one foreign Python file | exit 0 | exit 2 |
| R1-C88 | bquearch `703696d`, deep: `tests KnnPathForecaster.member_values --all-bands` | `unknown`, 0 tests | `test_zone_scale.test_scale_neighbours_…`, `low` |
| version | `codemap --version` | `… answer format 7 …` | `codemap 0.0.32 · answer format 8 · schema 0.13` |

**Consumers:** `check` on bquant and the bquearch gate identical apart from the trailer (format 8).

**0.0.32 published 2026-11-06:** [`codmap` 0.0.32](https://pypi.org/project/codmap/0.0.32/), schema 0.13,
`ANSWER_FORMAT` 8. From `5bbe37f` (code identical to `709f89c`, whose suite ran 1233 passed / 3 skipped, 1236
collected), CI green on 3.11–3.14, `twine check` PASSED. Reconciled from PyPI:

```
                                       0.0.31                       0.0.32
review, plain git diff (a948d6c)       0 changed symbol(s), exit 0  [medium] shared.contracts.SURFACE_NAMES, exit 0
review, a foreign Python file only     exit 0                       exit 2
tests KnnPathForecaster.member_values  unknown                      low; test_scale_neighbours_are_the_band_neighbours
--version                              … answer format 7 …          codemap 0.0.32 · answer format 8 · schema 0.13
bquant check / bquearch gate           exit 0                       exit 0; identical apart from the trailer (format 8)
```

Every expectation holds.

**0.0.33 — the release check, pre-registered before the upload (2026-11-06).** Two items (R1-C85, R1-C89);
schema **0.13**, **`ANSWER_FORMAT` 8 → 9**. Tree: bquant, a clone at `d9a2a4f` and `cf039ef`.

| | tree form | 0.0.32 (expected) | 0.0.33 (expected) |
|---|---|---|---|
| R1-C85 | served graph built at `d9a2a4f`, tree at `cf039ef`, any op | no `currency` field | `currency.status == "behind"`, `changed: 4` |
| R1-C85 | the same, rebuilt at `cf039ef` | no field | `current` |
| R1-C89 | `review` of `cf039ef^..cf039ef` (docs only) | 0 symbols, 3 unresolved | `changed_docs`: `evaluation.md`, `trading.md`; 0 unresolved |
| version | `codemap --version` | `… answer format 8 …` | `codemap 0.0.33 · answer format 9 · schema 0.13` |

**Consumers:** `check` on bquant and the bquearch gate identical apart from the trailer (format 9).

**0.0.33 published 2026-11-06:** [`codmap` 0.0.33](https://pypi.org/project/codmap/0.0.33/), schema 0.13,
`ANSWER_FORMAT` 9. From `c7a7e6a` (code identical to `93afcd0`, whose suite ran 1246 passed / 3 skipped, 1249
collected), CI green on 3.11–3.14, `twine check` PASSED. Reconciled from PyPI:

```
                                         0.0.32                      0.0.33
served graph d9a2a4f over tree cf039ef   no currency field           currency: behind, changed 4
rebuilt at cf039ef                       no currency field           currency: current
review cf039ef^..cf039ef (docs only)     0 symbols, 3 unresolved     changed_docs: evaluation.md, trading.md; 0 unresolved
--version                                … answer format 8 …         codemap 0.0.33 · answer format 9 · schema 0.13
bquant check / bquearch gate             exit 0                      exit 0; identical apart from the trailer (format 9)
```

Every expectation holds.

**0.0.34 — the release check, pre-registered before the upload (2026-11-06).** Two items (R1-C86, R1-C90);
schema **0.13**, **`ANSWER_FORMAT` 9 → 10**. Trees: a git fixture with the package in `research/shared`; bquant
`d9a2a4f` / `cf039ef`.

| | tree form | 0.0.33 (expected) | 0.0.34 (expected) |
|---|---|---|---|
| R1-C86 D0 | fixture: edit under `research/shared`, `build --incremental` | `[incremental] unchanged` | `[incremental] incremental` (or `full` on a tiny package), graph equals a full build |
| R1-C86 D1 | bquant `cf039ef`, `build --incremental --consumer … --docs docs` after a one-module edit | `[note] --incremental was not applied …` | `[incremental] incremental: N module(s)` |
| R1-C90 | bquant graph built at `d9a2a4f`, recipe `cwd` missing, cold `query` from a `cf039ef` clone | nothing on stderr | `[warning] … is behind its source tree …` |
| version | `codemap --version` | `… answer format 9 …` | `codemap 0.0.34 · answer format 10 · schema 0.13` |

**Consumers:** `check` on bquant and the bquearch gate identical apart from the trailer (format 10).

**0.0.34 published 2026-11-06:** [`codmap` 0.0.34](https://pypi.org/project/codmap/0.0.34/), schema 0.13,
`ANSWER_FORMAT` 10. From `5ff1722` (code identical to `d95c116`, whose suite ran 1261 passed / 3 skipped, 1264
collected), CI green on 3.11–3.14, `twine check` PASSED. Reconciled from PyPI:

```
                                            0.0.33                              0.0.34
edit under research/shared, --incremental   [incremental] unchanged             [incremental] incremental
bquant repo build --incremental, 1 edit     --incremental was not applied       [incremental] incremental: 2 module(s)
graph from d9a2a4f, recipe gone, cold query stderr empty                        [warning] … is behind its source tree
--version                                   … answer format 9 …                 codemap 0.0.34 · answer format 10 · schema 0.13
bquant check / bquearch gate                exit 0                              exit 0; identical apart from the trailer (format 10)
```

Every expectation holds.

**0.0.35 — the release check, pre-registered before the upload (2026-11-09).** One item (R1-C91); schema
**0.13**, **`ANSWER_FORMAT` stays 10**. Trees: a fixture repo with a test-module helper; bquant's graph at `cf039ef`
built by 0.0.34.

| | tree form | 0.0.34 (expected) | 0.0.35 (expected) |
|---|---|---|---|
| D1 | bquant graph, `stats` `confidence.by_grade` | `unknown: 1107` | no `unknown`; `exact` + 1107 |
| D3/D4 | the same graph with `provenance.tool.version` set to `0.0.99`, cold `query … --graph` | stderr empty | one `[warning] … built by codemap 0.0.99 …` line; stdout identical |
| version | `codemap --version` | `codemap 0.0.34 · answer format 10 · schema 0.13` | `codemap 0.0.35 · answer format 10 · schema 0.13` |

**Consumers:** `check` on bquant and the bquearch gate identical apart from the version.

**0.0.35 published 2026-11-09:** [`codmap` 0.0.35](https://pypi.org/project/codmap/0.0.35/), schema 0.13,
`ANSWER_FORMAT` 10. From `5e550e8` (code identical to `b784d0c`, whose suite ran 1270 passed / 3 skipped, 1273
collected), CI green on 3.11–3.14, `twine check` PASSED. CI on `b784d0c` itself was red: the README test count was
not updated in the fix commit, the third time this rule was broken (0.0.27, 0.0.29). The release commit carries
the count. Reconciled from PyPI:

```
                                            0.0.34                              0.0.35
bquant graph (cf039ef, built by 0.0.34)     exact 9053, unknown 1107            exact 10160, no unknown
same graph stamped 0.0.99, cold query       stderr empty                        one [warning] … built by codemap 0.0.99 …
  stdout                                    2379 bytes                          identical to the unstamped read
--version                                   codemap 0.0.34 · answer format 10   codemap 0.0.35 · answer format 10 · schema 0.13
bquant check / bquearch gate                exit 0                              exit 0; identical apart from the version
```

Every expectation holds.

**0.0.36 — the release check, pre-registered before the upload (2026-11-09).** One item (R1-C92); schema
**0.13**, **`ANSWER_FORMAT` stays 10**. Tree: a six-module fixture, graph from state 0 next to the sidecar from
state 1, then an edit.

| | tree form | 0.0.35 (expected) | 0.0.36 (expected) |
|---|---|---|---|
| D1 | mismatched pair, `build --incremental` | `[incremental] incremental: 1 module(s)`, edge `f1 → f3` missing | `[incremental] full … (the sidecar describes another build than the graph)`, equal to a full build |
| reason | a 0.0.35 graph and sidecar, `build --incremental` with 0.0.36 | — | `[incremental] full: 0 module(s) recomputed (builder-changed)` |
| version | `codemap --version` | `codemap 0.0.35 · answer format 10 · schema 0.13` | `codemap 0.0.36 · answer format 10 · schema 0.13` |

**Consumers:** `check` on bquant and the bquearch gate identical apart from the version.

**0.0.36 published 2026-11-09:** [`codmap` 0.0.36](https://pypi.org/project/codmap/0.0.36/), schema 0.13,
`ANSWER_FORMAT` 10. From `affe643`. The release commit `0c4bcc0` was red in CI: a test written for R1-C91 named
the reader's version as the literal `0.0.35`. After the version bump the fixture graph was stamped 0.0.36 and
read as newer. The stand run had passed because it ran before the bump. The test now reads the version from the
graph (`affe643`, test-only); CI green on 3.11–3.14, `twine check` PASSED. Reconciled from PyPI:

```
                                            0.0.35                              0.0.36
graph 0 + sidecar 1, edit, --incremental    [incremental] incremental: 1 module [incremental] full … (the sidecar describes another build than the graph)
  edge f1 → f3                              missing                             present
0.0.35 pair, --incremental by 0.0.36        —                                   [incremental] full: 0 module(s) recomputed (builder-changed)
--version                                   codemap 0.0.35 · answer format 10   codemap 0.0.36 · answer format 10 · schema 0.13
bquant check / bquearch gate                exit 0                              exit 0; identical apart from the version (stand, 6798a3c)
```

Every expectation holds.

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

**The release note names two versions, not one (R1-C63, from 0.0.21).** `SCHEMA_VERSION` says whether
the *artifact* moved; `ANSWER_FORMAT` says whether the *answer* did. 0.0.20 is the reason: the graph was
byte-identical and the gate's output changed completely, which on a consumer's text diff is
indistinguishable from the defect they had filed four days earlier — where the text moved between runs of
one version and nobody had decided anything. The note said it, because I wrote it by hand. Now the answer
says it. So: if `ANSWER_FORMAT` was bumped, the note says so **and** says what changed shape; if it was
not, the note says the answer format is unchanged, which is the more common and more reassuring line. The
suite's pinned hash over the rendered surfaces refuses to let the shape move silently, but it cannot tell a
structural change from a reworded one — that judgement stays the releaser's, and it is the reason the pin
prints both options in its failure message rather than a single instruction.

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
