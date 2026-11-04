# import-linter

**Verdict:** set after the run (§0.6) · **Feeds:** set after the run · **Card status:** pre-registration only.
Nothing below §0 has been run.

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
