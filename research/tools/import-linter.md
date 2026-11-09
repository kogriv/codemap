# import-linter

**Verdict:** learn (strong): the reference gate. grimp's graph equals our truth exactly (266 / 266 edges,
45 / 45 cycles, 0.11 s), and on bquant's contract the two gates agree on all four trees · **Feeds:** R1-C76
(new, codemap's own: a misspelled `[architecture]` table passes), indirect-chain semantics as a design note ·
**Card status:** hands-on: graph, 19 gate probes, bquant's contract in both gates (§1–§3); 2.15 and `main`

> The import graph is the best measured in this series, and by a margin: grimp reads every scope, so its
> edges are **exactly** codemap's 266, and its cycles exactly the 45. Three builds take 0.11 s each and are
> identical. As a gate it catches everything the codemap probe of post 11 asked: a lazy import, a
> `TYPE_CHECKING` import (with an opt-out), `import a.b.c`, a violation in `__init__.py`, a stale cache.
>
> Three ways it passes without checking, all predicted from its source:
> - **an unknown contract option is ignored:** `exhaustiv = True` is kept, exit 0 (filed,
>   [#392](https://github.com/seddonym/import-linter/issues/392));
> - **a misspelled forbidden module is dropped:** already reported as #386 and fixed on `main`, unreleased;
> - **zero contracts pass:** `[[tool.importlinter.contract]]` (singular) in `pyproject.toml` reads as no
>   contracts, exit 0 (filed, [#393](https://github.com/seddonym/import-linter/issues/393)).
>
> Asked of codemap, the third question found the same hole: a misspelled `[architectur]` table reads as
> "no contract", exit 0, unless `--require-contract` is passed. That is R1-C76.

**Scope:** `sha256:300e0a010e351d0a91a7e006c3cc18047d7d400c94a525ddbe727f796a5e47d2` (R2 benchmark: 280 files,
bquant@cb89a24, materialized and verified `== canonical ✓`) for the import graph; bquant at `aca0718` (its live
tree on 2026-11-04) for the contract comparison.

## Identity

- **Repo:** [seddonym/import-linter](https://github.com/seddonym/import-linter), created 2019-01-27, 1 247 ★,
  73 open issues (2026-11-04). The import graph comes from its sibling library
  [grimp](https://github.com/python-grimp/grimp) (3.18, 2026-10-26, Rust core).
- **License:** BSD-2-Clause.
- **Version measured:** PyPI `import-linter==2.15` (2026-09-04) with `grimp` 3.18.
- **What it is:** the established architecture gate for Python. Contracts in `.importlinter`, `setup.cfg` or
  `pyproject.toml`: `layers`, `forbidden`, `independence`, `protected`, `acyclic_siblings`. `lint-imports`
  exits 1 when a contract is broken. It is the direct neighbour of `codemap check`.

## 0. Pre-registration (committed before any run)

### 0.1 What was learnt before measuring (docs and source of 2.15)

- **Indirect imports count.** `layers` and `forbidden` (by default) forbid chains, not only direct imports.
  codemap's `layers` and `forbidden` judge direct edges. With every module inside a declared layer, an upward
  chain always contains an upward direct edge, so on an exhaustive contract the two should agree.
- **Scopes.** grimp reads every import statement, function-local included. `if TYPE_CHECKING:` imports count
  unless `exclude_type_checking_imports = True`.
- **Unknown contract options are ignored.** `Contract._populate_fields` iterates the contract class's own
  fields and reads each from the options. A key that is not a field is never looked at. So a misspelled
  *optional* key (`exhaustiv`, `ignore_import`, `allow_indirect_import`) is silently dropped, and the contract
  runs without it. A misspelled *required* key fails as "This is a required field".
- **A forbidden module that is not in the graph is dropped.** `forbidden.check` keeps only
  `[m for m in forbidden_modules if m.name in graph.modules]`. A *source* module that is not in the graph
  raises "does not exist", and a missing *layer* fails the contract. A misspelled forbidden **target** inside
  the root package is not caught by either path. The contract then checks nothing and is reported kept.
- **Booleans are strict:** only `true`/`false` (any case). Anything else is a validation error.
- **No general cycle rule.** `acyclic_siblings` checks cycles between siblings of one package only. bquant's
  `no_cycles`/`no_type_only_cycles` have no import-linter equivalent and are not translated.

### 0.2 Procedure

- Stand, inside the shared core-slot accounting; `import-linter==2.15` in a fresh venv, Python 3.12.
- **Graph:** [`bench/import_linter.py`](../bench/import_linter.py) builds grimp's graph of `bquant` on the R2
  tree, three times in fresh interpreters with no cache. It is scored against the same truth as the Graphify
  card: codemap's module imports, 266 edges, 45 cycles. A second build with `exclude_type_checking_imports`
  is recorded.
- **Gate probes:** [`bench/import_linter_probes.sh`](../bench/import_linter_probes.sh), committed with this
  section. A three-layer fixture `gp` (high > mid > low, `containers = gp`), one change and one config per
  probe, `lint-imports --no-cache` except G12.
- **Contract comparison:** bquant's `[architecture]` translated into import-linter (§0.5), both gates run on
  `aca0718` and on three mutations of it.

### 0.3 Predictions — the graph

- **P1.** All 89 truth modules are in grimp's graph.
- **P2.** Precision ≥ 95 % and recall ≥ 95 % against the 266 truth edges.
- **P3.** All 25 function-scope edges and the 1 type_checking edge are found.
- **P4.** At least 40 of the 45 truth cycles are cycles of grimp's graph.
- **P5.** Three builds give the identical edge set.
- **P6.** With `exclude_type_checking_imports`, exactly the type_checking-only edges disappear (truth: 1).

### 0.4 Predictions — the gate (fixture `gp`)

| probe | change | expected |
|---|---|---|
| G0c | none | exit 0, kept (**control**) |
| G0 | `low` imports `high` at module level | exit 1, broken (**control**) |
| G1 | the same import inside a function | exit 1 |
| G2 / G2b | the same under `if TYPE_CHECKING:`; G2b with `exclude_type_checking_imports = True` | G2 exit 1; G2b exit 0 |
| G3 | `import gp.high.h` | exit 1 |
| G4 | the violation in `gp/low/__init__.py` (`from ..high import h`) | exit 1 |
| G5c / G5 | undeclared `gp/extra`; G5c `exhaustive = True`, G5 `exhaustiv = True` | G5c exit 1; **G5 exit 0, no warning** (a silent pass) |
| G6 | `forbiden_modules` (required key misspelled) | exit ≠ 0, "required field" |
| G7c / G7 | real violation `low → high`; G7c `forbidden_modules = gp.high`, G7 `gp.hihg` | G7c exit 1; **G7 exit 0, kept** (a silent pass) |
| G8 | `source_modules = gp.lwo` | exit ≠ 0, "does not exist" |
| G9 | layer `hihg` in the list | exit ≠ 0, "does not exist" |
| G10 | `exhaustive = maybe` | exit ≠ 0, cannot parse |
| G11 | no contract at all | recorded, no prediction |
| G12 | default cache: clean run, then a violation added | first exit 0, second exit 1 |
| G13 | `type = layer` | exit ≠ 0, no such contract type |
| G14 | `root_pakage` | exit ≠ 0 |
| G15 | an `ignore_imports` line that matches nothing | exit ≠ 0 (default alerting is `error`) |

If G0c or G0 does not hold, the fixture or the setup is wrong and nothing below is read. At least G5 or G7
fails if my reading of `_populate_fields` and `forbidden.check` is wrong.

### 0.5 Predictions — bquant's own contract, two gates

Translation of bquant's `codemap.toml`:
- one `layers` contract (`containers = bquant`, the seven layers top → bottom, `exhaustive = True`);
- three `forbidden` contracts: `core` ↛ `analysis`, `indicators`, `data`, `visualization`; `data` ↛
  `indicators`, `analysis`; `indicators` ↛ `analysis`, `visualization`;
- the cycle rules have no equivalent (§0.1).

`codemap check --build bquant` (0.0.25) against `lint-imports`:

| tree | codemap (expected) | import-linter (expected) |
|---|---|---|
| `aca0718` as is | exit 0 | exit 0, all kept |
| M1: `core/config.py` imports `bquant.analysis` at module level | exit 2, layer + forbidden violation | exit 1, layers + core forbidden broken |
| M2: the same import inside a function | exit 2 | exit 1 |
| M3: the same under `if TYPE_CHECKING:` | recorded | exit 1 |

If the two disagree on `aca0718` as is, the card names the module or edge that makes the difference. The
expected source of any disagreement is `exhaustive`: import-linter counts every child of `bquant`, codemap
counts core modules.

### 0.6 Decision rules

- **R1.** If G5 or G7 holds, it is a silent pass with a minimal reproduction. Filing upstream follows the
  same rule as before: re-checked on a minimal tree with a control, after a duplicate search. The owner's
  "Делай все. Полноценно" (2026-11-04) answered a list that put filing with the owner and named this card
  next; I read it as covering this round's filings, and say so in the issue for this card.
- **R2.** The verdict is set after the run. The licence allows any verdict.

### 0.7 What this card will not establish

- `independence`, `protected`, `acyclic_siblings` beyond reading their docs; the `ui` extra.
- Performance on a large codebase.
- grimp's handling of namespace packages and external packages.

## 1. Hands-on

Stand, inside the shared core-slot accounting; `import-linter==2.15` with `grimp` 3.18 in a fresh venv,
Python 3.12. Numbers: [`bench/import_linter_results.json`](../bench/import_linter_results.json).

**The graph (R2 tree).**

```
modules        89 / 89
edges          266, all 266 in the truth: precision 100 %, recall 100 %
  by scope     module 240 / 240 · function 25 / 25 · type_checking 1 / 1
cycles         45 / 45, 0 false
determinism    3 builds, identical; 0.14 / 0.11 / 0.11 s
exclude_type_checking_imports   drops exactly zones.cache → zones.pipeline, the one type_checking edge
```

Two engines that share no code (codemap reads griffe's model and the AST, grimp has a Rust core) produce the
same module graph, edge for edge. That is the strongest external check the truth set has had. It is
corroboration, not proof: both could share a blind spot that this tree does not exercise.

**The gate probes (fixture `gp`).**

| probe | measured |
|---|---|
| G0c / G0 | exit 0 kept / exit 1 broken: the controls hold |
| G1 lazy, G2 `TYPE_CHECKING`, G3 `import gp.high.h`, G4 `__init__` | exit 1, broken, each |
| G2b `exclude_type_checking_imports` | exit 0, kept |
| G5c `exhaustive = True` | exit 1, broken |
| **G5 `exhaustiv = True`** | **exit 0, kept, no warning** |
| G6 `forbiden_modules` | exit 1, "forbidden_modules: This is a required field." |
| G7c `forbidden_modules = gp.high` | exit 1, broken |
| **G7 `forbidden_modules = gp.hihg`** | **exit 0, kept** |
| G8 `source_modules = gp.lwo` | exit 1, "Module 'gp.lwo' does not exist." |
| G9 layer `hihg` | exit 1, "Missing layer in container 'gp': module gp.hihg does not exist." |
| G10 `exhaustive = maybe` | exit 1, "Could not parse a boolean from 'maybe'." |
| **G11 no contract** | **exit 0, "Contracts: 0 kept, 0 broken."** |
| G12 cache on, violation added after a clean run | first exit 0, second exit 1: the cache invalidates |
| G13 `type = layer` | exit 1; the whole message is `layer` (known: #35) |
| G14 `root_pakage` | exit 1; the whole message is `'root_package'` |
| G15 unmatched `ignore_imports` | exit 1, "No matches for ignored import gp.low.l -> gp.hihg.h." |

**bquant's contract, both gates, `aca0718`.**

| tree | `codemap check` 0.0.25 | `lint-imports` 2.15 |
|---|---|---|
| as is | exit 0, satisfied (layered 7, forbidden 8, no_cycles, no_type_only_cycles, exhaustive) | exit 0, 4 kept |
| M1 module-level `import bquant.analysis` in `core/config.py` | exit 2: `layered` 1, `forbidden` core → analysis | exit 1, **4 broken** |
| M2 the same inside a function | exit 2, the same | exit 1, 4 broken |
| M3 the same under `if TYPE_CHECKING:` | exit 2, the same | exit 1, 4 broken |

They agree on every verdict. They disagree on how much one edge breaks. import-linter forbids chains, so
`data → core → analysis` breaks the `data` contract and `indicators → core → analysis` the `indicators` one.
codemap names the one edge that points up. Both are right by their own definition. Theirs tells you how far
the damage reaches; ours tells you which line to change.

## 2. Reconciliation with the pre-registration

| | expected | measured | |
|---|---|---|---|
| P1 | 89 modules | 89 | holds |
| P2 | precision, recall ≥ 95 % | 100 %, 100 % | holds |
| P3 | 25 / 25 function, 1 / 1 type_checking | both | holds |
| P4 | ≥ 40 / 45 cycles | 45 / 45 | holds |
| P5 | identical edge sets | identical | holds |
| P6 | only the type_checking edge drops | exactly that one | holds |
| G0c–G4, G6, G8–G10, G12–G15 | as in §0.4 | as in §0.4 | hold |
| G5 | exit 0, no warning | exit 0, kept | holds: a silent pass |
| G7 | exit 0, kept | exit 0, kept | holds: a silent pass |
| G11 | recorded | exit 0, "0 kept, 0 broken" | a silent pass, see §3 |
| bquant, as is | both exit 0 | both exit 0 | holds |
| M1, M2 | codemap 2, import-linter 1 | as expected | holds |
| M3 | codemap recorded; import-linter 1 | codemap 2; import-linter 1 | holds |

Every prediction held. The two silent passes I predicted from source are real.

### Surprises

- **The graph matched to the edge.** I predicted ≥ 95 %. Two unrelated engines agreeing on 266 of 266 was not
  something I would have dared to write down.
- **A one-edge violation broke four contracts.** Correct under indirect semantics, and worth knowing before
  reading a red CI log.
- **The question I aimed at them caught me.** A misspelled table name is the codemap version of G11.

## 3. Before filing (2026-11-04)

- **Duplicates.** All 163 issues read by title. G7 is
  [#386](https://github.com/seddonym/import-linter/issues/386), closed 2026-10-13, fixed on `main` by
  447ec81 ("Raise an error when a forbidden module does not exist"); the release notes list it under
  "latest". G13's terse message is #35, open. Nothing on unknown options or zero contracts.
- **Re-checked on `main` at e582318** (installed from git), same probes: G5 still exit 0 kept; G7 now exit 1,
  "Module 'gp.hihg' does not exist."; G11 still exit 0.
- **G16, the concrete form of G11**, on `main`: `[[tool.importlinter.contract]]` (singular) in
  `pyproject.toml` gives "Contracts: 0 kept, 0 broken.", exit 0; with `contracts`, exit 1 broken. The INI
  form is tolerant: `[importlinter:contrat:layers]` was still read as a contract.

**Filed 2026-11-04** (the owner's "Делай все. Полноценно"; recorded in kogriv/codemap#23):
[#392](https://github.com/seddonym/import-linter/issues/392) unknown contract options are ignored;
[#393](https://github.com/seddonym/import-linter/issues/393) zero contracts pass. G7 is not filed: it is fixed.

**Maintainer reply, same day:** both accepted as improvements, PRs invited. **PRs opened 2026-11-04** on the
owner's decision: [#395](https://github.com/seddonym/import-linter/pull/395) (#393: `lint_imports` raises
before the graph is built when no contracts are defined) and
[#396](https://github.com/seddonym/import-linter/pull/396) (#392: an option no field recognises is an
`InvalidContractOptions` error, with the closest field suggested; parent-class fields and `id`/`name`/`type`
recognised). Each was checked against the G16/G5 probe (2.15: exit 0; the branch: exit 1 with the message) and
by mutation. One trap found on the way: rich parses `[...]` in error messages as markup, so the #395 message
names the INI section and TOML table without brackets.

**Rebased 2026-11-06** (owner's decision). Upstream merged the drop of Python 3.10 and a Python-versions doc,
so both PRs turned `CONFLICTING`. The only conflict was `docs/release_notes.md`, and both lines were kept. Both
branches were checked against upstream `main` in the same environment: ruff, `ruff format --check` and mypy
were clean, and the set of failing tests was identical to upstream's. That set is seven functional UI tests in
`tests/functional/test_ui.py` that run a subprocess and fail on the check machine on upstream itself. Our new
tests pass (+1 and +6). Both PRs are `MERGEABLE` again. They have had no review yet, and CI has not run for a
first-time contributor.

**Merged 2026-11-06.** #395 at 7f97289, #396 at 74c0be5, both merged by the maintainer; #392 and #393 closed.
Both are in **2.16** (PyPI, 2026-11-06), listed in its release notes.

**Released-package check, pre-registered 2026-11-09** (clean venvs from PyPI, a minimal package, nothing from
our branches):

| # | Expectation |
|---|---|
| P1 | `[[tool.importlinter.contract]]` (singular) in `pyproject.toml`: 2.15 exit 0 "0 kept, 0 broken"; 2.16 exit nonzero, the message says no contracts are defined |
| P2 | a `layers` contract with `exhaustiv = true`: 2.15 exit 0 kept; 2.16 exit nonzero, names `exhaustiv` and suggests `exhaustive` |
| P3 | the same contract spelled correctly: kept, exit 0, on both versions |

**Reconciliation (2026-11-09):**

| # | Result |
|---|---|
| P1 | ✅ 2.15: "Contracts: 0 kept, 0 broken.", exit 0. 2.16: "No contracts found in the configuration." plus where contracts go, exit 1 |
| P2 | ✅ 2.15: "L KEPT", exit 0, the option silently ignored. 2.16: `exhaustiv: Unrecognized option. Did you mean 'exhaustive'?`, exit 1 |
| P3 | ❌ as written, and the fault is in the fixture: `exhaustive` without `containers` is refused on both versions ("not supported for contracts without containers"). That is the same behaviour on both and not a regression. Rerun with `containers = ["gp"]`: kept, exit 0, on both versions |

**Surprise:** P2 on 2.15 shows the defect more sharply than filed. The misspelled option was not just ignored. The
contract it sat in would have been refused if spelled correctly (no `containers`), and instead it was reported
as kept.

## Coverage vs codemap

| task | import-linter 2.15 | codemap |
|---|---|---|
| T1–T4 | — (not its job) | ✅ |
| T5 arch: layers, forbidden | ✅ direct and indirect | ✅ direct |
| T5 arch: cycles | ◐ `acyclic_siblings` only | ✅ eager / type-only / lazy, each a rule |
| T5 arch: independence, protected | ✅ | ◐ independent groups; no `protected` |
| gate refuses a bad contract | ✅ since 2.16 (our #395/#396): unknown options and zero contracts refused; 2.15: ◐ | ◐ unknown keys refused (R1-C69); a misspelled table passes without `--require-contract` (R1-C76) |
| determinism | ✅ | ✅ |

## Разбор

**What to learn.**
- **Indirect semantics.** "No chain from `data` to `analysis`" is a stronger rule than "no edge", and it is
  the rule people usually mean. codemap's `forbidden` could offer it as an option. A design note, not a
  promise.
- **`protected`**, a contract type codemap does not have: only listed modules may import a module.
- **Guidance on a broken contract** (`broken_contract_guidance`): the contract says how to fix itself.

**What not to learn.** Ignoring unknown options. Ours refuses them, since 0.0.23.

## Verdict & backlog effect

**learn (strong).** As a gate, it is the reference: mature, fast, and right on every import shape we asked
about. Its graph confirms codemap's on this tree edge for edge. Its weak spots are configuration typos, two
filed and one already fixed. codemap does not replace it for teams that only need contracts. codemap adds
what import-linter does not try to do: separate cycle rules per import scope, an answer that names the edge,
and the rest of the graph (T1–T4) behind the same artifact.

- **R1-C76 (new, codemap):** a top-level table in `codemap.toml` whose name is close to `architecture`
  (`[architectur]`) is read as "no contract", exit 0. It should be refused like an invalid contract.
- **Design notes:** indirect `forbidden`; a `protected` rule; guidance text on a rule.
