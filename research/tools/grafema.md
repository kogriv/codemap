# grafema

**Verdict:** learn (strong) for the design; the Python product, as measured, is not usable ·
**Feeds:** R1-C39 (reason on the edge), R1-C13 (labels on the edge), derived edges as declared rules
(new, §Разбор) · **Card status:** hands-on — import graph and T1–T3 on the full R2 tree, 0.4.1 from npm

**Scope:** `sha256:300e0a010e351d0a91a7e006c3cc18047d7d400c94a525ddbe727f796a5e47d2` (R2 benchmark
`bquant.scope.json` — 280 files, 207 .py / 73 .md, bquant@cb89a24) · run mode: **materialized** from a
fresh `git archive cb89a24` extract (staging verified `== canonical ✓`)

> The design is the most careful of any import graph measured here. Every import becomes a node in
> the scope it sits in, so imports inside functions, under `TYPE_CHECKING` and in `try:` are all read.
> Module dependencies are derived by a four-line Datalog rule you can read. Of 164 edges, 163 are real,
> and three runs are identical. Then three defects in the Python path take it from **42** visible import
> cycles to **8** of 45:
> - relative imports inside `__init__.py` resolve one package too high (85 edges);
> - any f-string with `!r`, `!s` or `!a` drops its whole file, `pipeline.py` among them, logged as an
>   error but at exit 0;
> - the README's quickstart loads no Python analyzer at all, and never says why.
>
> With the public `analyze_zones` gone, `who`/`impact` attribute its 88 call sites to a method of the
> same name and mark them `[resolved]`.

**How to read this card.** §0 holds the expectations, committed before any run on the R2 tree
(1119ba0), with an addendum before the T1–T3 probe (597c28f). §1–§2 are what the runs showed,
reconciled against them. The comparison, the разбор and the verdict come last.

## Identity

- **Repo:** [Disentinel/grafema](https://github.com/Disentinel/grafema) (created 2026-01-19), site
  grafema.dev. 35 ★ (2026-11-02). In our curated intake (`research/05_curated_sources.md`) it is the one
  entry the curator singled out.
- **License:** FSL-1.1-Apache-2.0. The source is available, use is free, and it converts to Apache-2.0
  after two years. It is not an open-source licence today: code cannot be taken into codemap.
- **Version measured:** npm `grafema@0.4.1` (2026-06-14), the latest release. `main` is 109 commits
  ahead (last commit 2026-08-16) and is not built for this card: it needs a Rust and Haskell toolchain.
  Where `main` matters, it is read from source and labelled so.
- **Stack:** a Rust orchestrator; per-language analyzers and resolvers in Haskell (Python: rustpython
  parser, then `grafema-python-analyzer` and `python-resolve`); a custom columnar graph database (RFDB)
  with a Datalog derive engine and a Cypher subset; a TypeScript CLI and an MCP server with 40+ tools.
- **Install:** `npm i grafema@0.4.1`. The npm package carries the orchestrator and the RFDB server for
  Linux x64. Per-language analyzers are downloaded from GitHub releases on first use into
  `~/.grafema/bin`.

## What it is

A graph of the codebase that the authors want to extend past code: services, decisions, knowledge.
The README lists call graph, data flow (forward and backward), control flow, effect propagation,
symbolic execution and cross-language links; queries go through CLI verbs (`who`, `wtf`, `why`,
`tldr`), Datalog rules, Cypher and MCP. Python is listed as **Beta**: parse, analyze and resolve "full",
dataflow "partial". JS/TS is the primary language.

## 0. Pre-registration (committed before any run on the R2 tree)

### 0.1 What was learnt before measuring

Everything here comes from the source at the `v0.4.1` tag and from a two-file toy package. Nothing
here was run on the R2 tree.

**The README's two-command quickstart cannot analyze a Python project on 0.4.1.**
- `grafema init --yes` and `grafema analyze --quickstart` both write the include list as a single
  brace glob: `"**/*.{js,…,py,…}"`, and `"**/*.{py}"` when only Python is found
  (`packages/cli/src/utils/quickstart.ts:110`).
- `analyze` decides which analyzer binaries to download by matching the config text against
  `/\*\.(\w+)/g` (`ensureLanguageBinaries` in `packages/cli/src/commands/analyzeAction.ts`). That
  pattern cannot read past the `{`, so no extension is recognised and only the JS/TS pair is fetched.
- The orchestrator then fails to spawn `grafema-python-analyzer` for every Python file. On the toy:
  4 nodes (`FILE`, `DIRECTORY`), no `MODULE`, exit 1. The run fails on two JS rule packs
  (`E-PLAN-003`). The default output does show `ERROR … Failed to spawn grafema-python-analyzer` once per
  file, but nothing names the cause. The "binaries missing" warning in the same function stays silent,
  because Python was never put on the list of needed binaries. *(Corrected 2026-11-02 in §5: this line
  first said the failure showed only with `--verbose`.)*
- Both functions are unchanged on `main`, read from source on 2026-11-02.
- **Workaround used for every measurement below:** a config whose include list is the plain glob
  `"**/*.py"`. With it, the toy gives `MODULE` ×3, `IMPORTS_FROM`, `CALLS`, `DEPENDS_ON`, exit 0, and
  `python-resolve` is downloaded.

**How module dependencies are built** (read from source):
- The Python analyzer emits an `IMPORT` node with `IMPORT_BINDING` children for every import
  statement, attached to the enclosing scope. Statements inside functions and blocks are therefore
  walked too.
- `python-resolve` turns each binding into an `IMPORTS_FROM` edge:
  - `from foo import bar` is looked up as `(foo, bar)` in a name index of `FUNCTION`, `CLASS` and
    `VARIABLE` nodes, plus `IMPORT_BINDING` nodes acting as re-exports;
  - failing that, as the submodule `foo.bar`;
  - failing both, the binding is dropped with no record.
- The stdlib Datalog rule `depends.dl` derives `MODULE → MODULE DEPENDS_ON` from any `IMPORTS_FROM`
  between two files, whatever scope the import sits in.

**A probable defect in relative imports inside `__init__.py`** (from source, not yet run).
- `resolveRelativeImport` takes the importer's module path from `fileToModulePath`, which strips
  `.__init__`. So `pkg/sub/__init__.py` becomes `pkg.sub`.
- It then drops `level` components: `from .m import x` there resolves to `pkg.m`. Python resolves it
  to `pkg.sub.m`, because inside a package's `__init__` the single dot is the package itself.
- Ordinary modules are right: `pkg/sub/a.py` is `pkg.sub.a`, and dropping one component gives
  `pkg.sub`.
- The function is identical on `main`. Its tests cover relative imports from ordinary modules only.

**Query surface quirks met on the toy:**
- A Datalog conjunction written as in the CLI's own `--help` (`edge(X, Y, "CALLS")`) is refused with
  `rule clause missing terminating '.'`.
- With the `.` added, the same text runs as a fact query and returns `[]`, although the edge exists.
- Only the rule form (`dep(X, Y) :- edge(X, Y, "DEPENDS_ON").`) and Cypher return rows. The harness
  uses Cypher.
- `check --list-guarantees` lists none.
- The 0.4.1 Linux package ships an `rfdb-server` that reports itself as **0.4.0**, and every command
  warns about the version mismatch.

### 0.2 Procedure

- Tree: the R2 staging tree, copied fresh for every run. A `.grafema/config.yaml` with
  `include: ["**/*.py"]` and `root: ..` is written into it, then `grafema analyze --clear`.
- Edges: Cypher `MATCH (a:MODULE)-[:DEPENDS_ON]->(b:MODULE) RETURN a.file, b.file`. Only
  `bquant/**.py → bquant/**.py` edges are scored. The mapping is `bquant/x/y.py` → `bquant.x.y`, and
  `…/__init__.py` → the package. Self-edges are dropped.
- Truth: codemap on the same tree, module→module `imports` edges, split by the `scope` extra; cycles
  enumerated with `nx.simple_cycles`. It is the same definition as the CodeGraph and Understand-Anything
  cards.
- Harness: `research/bench/grafema.py`, committed with the results.

### 0.3 Controls (the measurement is void if C1 or C2 fails, or C3's positive cases fail)

- **C1** — the staging tree verifies `== canonical ✓`. Already true when this was written.
- **C2** — the truth reproduces: 266 edges (240 module-level, 25 function, 1 type_checking) and
  45 cycles. Of the 266, **87 start in a package `__init__.py`**, and only **9** of the 45 cycles need
  no such edge. Already true when this was written.
- **C3** — a fixture package, analyzed the same way. Each line is one edge and its expected outcome.
  - **C3a**, positive: top-level `from pkg.b import f` in `pkg/a.py` gives an edge a→b.
  - **C3b**, positive: top-level `from .c import g` in `pkg/a.py` gives an edge a→c.
  - **C3c**: a function-local `from .d import h` in `pkg/a.py` gives an edge. This is predicted, not a
    control.
  - **C3d**: `if TYPE_CHECKING: from .e import T` gives an edge. Predicted.
  - **C3e**: `try: from .f import k` gives an edge. Predicted.
  - **C3f**: `from . import NAME` in `pkg/a.py`, with `NAME` defined in `pkg/__init__.py`, gives an
    edge a→pkg. Predicted.
  - **C3g**: `from .m import x` in `pkg/sub/__init__.py`, with `x` defined in `pkg/sub/m.py`, gives
    **no** edge. This is the `__init__` defect.
  - **C3h**: the same form, where `pkg/m2.py` exists one level up and defines the same name, gives an
    edge to **`pkg.m2`**, the wrong module.
  - **C3i**: `from pkg.sub import x` in `pkg/user.py`, with `x` re-exported by `pkg/sub/__init__.py`,
    gives an edge user→sub. Predicted.

  If C3a or C3b fails, the harness or the setup is wrong and nothing below is read.

### 0.4 Predictions for the R2 tree

- **P1, coverage.** Every one of the 89 `bquant/**.py` files gets a `MODULE` node.
- **P2, scopes.** At least 20 of the 25 function-scope edges are found, and the 1 type_checking edge
  is found.
- **P3, `__init__`.** Fewer than half of the 87 truth edges that start in a package `__init__.py` are
  found.
- **P4, cycles.** grafema's graph hits between 5 and 20 of the 45 truth cycles: well above
  Understand-Anything's 0, well below 45.
- **P5, precision.** At least 85 % of grafema's bquant→bquant edges are truth edges. C3h is the reason
  this is not 95 %.
- **P6, determinism.** Three runs on fresh copies give the identical edge set.
- **P7, the quickstart defect.** `grafema analyze --quickstart` on a fresh copy of the tree gives no
  `MODULE` node and exit ≠ 0.

At least one of P3, P4 and C3g fails if the `__init__` defect is not real.

### 0.5 Decision rules

- **R1.** If C3g or C3h holds and P3 holds, the `__init__` resolution is a confirmed defect, with a
  minimal reproduction. If P7 holds, so is the quickstart one. Filing either upstream is the owner's
  call.
- **R2.** If P4's hit count is below 45, the card says which edges the missed cycles lack, by class:
  `__init__`-relative, re-export, other.
- **R3.** The verdict is set after the run. It cannot be `wrap` or `integrate` whatever the numbers:
  the licence forbids taking code, so the best possible outcome is `learn (strong)`.

### 0.5a Addendum — T1–T3, written after the import run and before this probe (2026-11-02)

The import run (§1) showed that `bquant/analysis/zones/pipeline.py` and `presets.py` have no `MODULE`
node. Expectations for the symbol questions, on the same config:

- **T1.** `MACDZoneAnalyzer`, a class in `indicators/macd.py`, is found. The method
  `UniversalZoneAnalyzer.analyze_zones` in `analyzer.py` is found. The top-level function
  `analyze_zones` in `pipeline.py` is **not** found, because its file was never analyzed.
- **T2.** `grafema who MACDZoneAnalyzer` returns fewer references than codemap's. `who analyze_zones`
  returns only references that resolve to the method, or none.
- **T3.** `grafema impact analyze_zones` cannot report the public function's blast radius, since the
  function does not exist in its graph.

These are descriptive probes. No decision rule hangs on them beyond the T-columns of the comparison
table.

### 0.6 What this card will not establish

- Data flow, control flow, effects, symbolic execution. They are grafema's distinguishing claims,
  but there is no truth set for them on this tree. They are described from source, not measured.
- JS/TS behaviour, its primary language.
- `main` behaviour beyond what is read from its source.
- The MCP server, `why` and the knowledge layer.

## 1. Hands-on — the import graph on the R2 tree

Harness `research/bench/grafema.py`. Raw results, with paths removed, are in
[`bench/grafema_results.json`](../bench/grafema_results.json). Stand: Linux x64, Node 22.

**Fixture C3, before the tree.** Every line came out as predicted:

| case | edge | present |
|---|---|---|
| C3a top-level absolute | `pkg.a → pkg.b` | yes |
| C3b top-level relative | `pkg.a → pkg.c` | yes |
| C3c function-local | `pkg.a → pkg.d` | yes |
| C3d `if TYPE_CHECKING:` | `pkg.a → pkg.e` | yes |
| C3e `try:` | `pkg.a → pkg.f` | yes |
| C3f `from . import NAME` | `pkg.a → pkg` | yes |
| C3g relative, inside `pkg/sub/__init__.py` | `pkg.sub → pkg.sub.m` | **no** |
| C3h same form, a namesake one level up | `pkg.sub → pkg.m2` | **yes, wrong module** |
| C3i re-export through a package `__init__` | `pkg.user → pkg.sub` | yes |

**The tree, three runs on fresh copies:**

```
analyze                    exit 0, 20.2–21.2 s each, 206 MODULE nodes of 207 .py files
edge set                   identical in all 3 runs (sha256 ed23087f…)
bquant → bquant edges      164, of them 163 in the truth (precision 99.4 %), recall 163 / 266 = 61 %
by truth scope             module 146 / 240 · function 17 / 25 · type_checking 0 / 1
edges out of a package     2 of 87
  __init__.py
import cycles              8 of 45 hit, 0 false
```

**The one edge outside the truth** is `bquant.cli → bquant.visualization`, from
`from bquant.visualization import charts`. Python executes the package `__init__` first, so the
dependency is real. The truth attributes it to `visualization.charts`, and grafema to the package.
It is the same convention gap Understand-Anything's single extra edge fell into.

**All 103 missed truth edges, classified:**

| class | edges | cause |
|---|---:|---|
| relative import inside a package `__init__.py` | 85 | **defect A**, resolves one level too high (C3g) |
| from or into `zones/pipeline.py` or `zones/presets.py` | 16 | **defect B**, both files never analyzed |
| `analyzer → analysis.timeseries` | 1 | the imported name `ZoneRegressionAnalyzer` does not exist in that package. It is a broken import in bquant@cb89a24 itself, inside a function, and grafema drops an unresolved name without a record |
| `cli → visualization.charts` | 1 | attribution, see above |

So P2's shortfall (17 of 25 function-scope edges, 0 of 1 `TYPE_CHECKING`) is not about scope at all.
The 8 missing function-scope edges are 6 × defect A, 1 × defect B and the broken import. The one
`TYPE_CHECKING` edge points into `pipeline.py`. Scope handling itself is right, as C3c–e show.

**Defect B, found on the tree.**
- The Python analyzer refuses `bquant/analysis/zones/pipeline.py` and `presets.py` with
  `decode error: … .conversion: parsing Int failed, expected Number, but encountered String`.
- They are the only two files in the tree with an f-string conversion (`{x!r}`). Checked with `ast`
  over all 207 files.
- Minimal reproduction, four files:
  - `f"{y!r}"` and `f"{y!s}"` drop the file;
  - `f"{y}"` and `f"{y:>8}"` do not.
- The run still exits 0. The default output logs one `ERROR … Python analyzer failed … decode error`
  line per file and ends `Analysis complete … errors=N`. `coverage` counts the files, but as
  "Unsupported — no indexer available", which is the wrong reason. No query answer mentions them.
  *(Corrected in §5: this line first said the refusal was printed only under `--verbose`. That came
  from reading an empty `--log-file` and a verbose run, never the default output.)*

**What fixing each defect would give**, by putting the classified missing edges back:

| | edges | cycles hit |
|---|---:|---:|
| as measured | 163 | 8 / 45 |
| defect A fixed | 248 | 25 / 45 |
| defect B fixed | 179 | 9 / 45 |
| **both fixed** | 264 | **42 / 45** |

The last three cycles need the two edges that are not defects (the broken import and the attribution).

**The quickstart (P7), probed twice.**
- The first probe ran on the same machine after the three runs. It analyzed everything (206 modules,
  exit 0), because the Python analyzer was already cached in `~/.grafema/bin` from those runs. That
  was a flaw in the harness, not a property of the tool.
- Re-run with an empty `HOME`, as a new user would have it:
  - `analyze --quickstart` wrote `include: "**/*.{py}"`;
  - it downloaded only `grafema-analyzer` and `grafema-resolve`;
  - it finished with **exit 0 and 0 `MODULE` nodes** over the 207 Python files.

**T1–T3, on the analyzed tree** (addendum §0.5a):

- **T1.** `MACDZoneAnalyzer` is found (`bquant/indicators/macd.py:48`), and so is the method
  `UniversalZoneAnalyzer.analyze_zones`. The top-level `analyze_zones` is not, because its file was
  dropped.
- **T2.** `who MACDZoneAnalyzer` lists **83** call sites, each marked `[resolved]` (23) or
  `[unresolved]` (60): an honest per-site label.
- **T2/T3 on `analyze_zones`: the confident wrong answer.**
  - `who analyze_zones` lists **118** callers, **109 marked `[resolved]`**.
  - `impact analyze_zones` reports **93** direct callers and 0 transitive, all of them against the
    method `UniversalZoneAnalyzer.analyze_zones`.
  - The tree has **10** attribute calls `….analyze_zones(…)` and **88** bare calls `analyze_zones(…)`
    of the public function, as in `from bquant.analysis.zones import analyze_zones` →
    `analyze_zones(df)` (checked by hand at `examples/02a_universal_zones.py:220`).
  - With the function missing, the name fell through to the only definition left. Nothing in the answer
    says so: there is no ambiguity flag and no "file failed to analyze".
- **T3** is direct-only on both symbols: "0 transitive callers". Callers are listed as `MODULE` ids,
  one row per call site.

## 2. Reconciliation with the pre-registration

| | expected | measured | |
|---|---|---|---|
| C1 | canonical staging | ✓ | holds |
| C2 | 266 edges, 45 cycles, 87 from `__init__`, 9 cycles without them | ✓ | holds |
| C3a–b | positive controls | both present | holds |
| C3c–f, C3i | present | all present | holds |
| C3g | no edge | no edge | holds — defect A |
| C3h | edge to the wrong module | present | holds — defect A misbinds |
| P1 | 89 of 89 bquant modules | **87** | **fails** — defect B, not foreseen |
| P2 | ≥ 20 of 25 function, 1 of 1 TC | **17, 0** | **fails** — every miss is A, B or the broken import |
| P3 | < half of 87 | 2 | holds |
| P4 | 5–20 of 45 cycles | 8 | holds |
| P5 | ≥ 85 % precision | 99.4 % | holds |
| P6 | identical across 3 runs | identical | holds |
| P7 | 0 `MODULE` and exit ≠ 0 | 0 `MODULE`, **exit 0** | half: the graph is empty as predicted, and the exit is worse than predicted |
| T1 | class ✓, method ✓, function ✗ | as expected | holds |
| T2 | fewer refs than codemap; `analyze_zones` → method or none | 83 refs for the class; 109 "resolved" callers of the method | the class count was not compared row by row; the method half holds, and in the worse form |
| T3 | no blast radius for the public function | the method's radius is reported instead | holds, and in the worse form |

**Decision rules.**
- **R1.** Defect A is confirmed (C3g, C3h, P3), and so is the quickstart defect (P7). Defect B is new
  and confirmed on four files. Each has a minimal reproduction. Filing upstream is the owner's call;
  nothing has been filed.
- **R2.** Done above. Of the 37 missed cycles, 34 come back when A and B are fixed.
- **R3.** Verdict below.

### Surprises

- **S1 — defect B.** Not predicted. It removes the file that defines the project's flagship API, and
  the run exits 0. The per-file `ERROR` lines are in the analyze output, and nothing in the graph or in
  the answers carries them.
- **S2 — the harness contaminated its own quickstart probe** through the analyzer cache in `$HOME`.
  It was caught because the result contradicted the toy run. The clean probe uses a fresh `HOME`.
- **S3 — a broken import in bquant itself.** `analysis/zones/analyzer.py:99` imports
  `ZoneRegressionAnalyzer` from `bquant.analysis.timeseries`, a stub that does not define it. It sits
  inside a function, so it fails only when that path runs. It is fixed in current bquant: at `8efa112` the import reads
  `from bquant.analysis.statistical.regression import ZoneRegressionAnalyzer`, where the class is
  defined. Checked by reading, 2026-11-02.
- **S4 — silent empty answers in the query layer.** The Datalog fact form `edge(X, Y, "T").` returns
  `[]` on a graph that has the edge. The help text's own example without the dot is refused.
- **S5 — the npm package ships `rfdb-server` 0.4.0** inside the 0.4.1 release, and every command warns
  about the mismatch. It is harmless here, but it is the same kind of drift as defect A: two parts of one
  release that were never run together.

### What this card does not establish

Everything in §0.6, plus: whether defect A or B is fixed in `main` by behaviour (both functions read
unchanged, but `main` was not built); the class-level T2 set against codemap row by row; macOS.

## Coverage vs codemap

| | grafema 0.4.1 (Python) | codemap |
|---|---|---|
| T1 defs | ◐ — right where a file is analyzed; the files defect B drops have no definitions at all | ✅ |
| T2 callers | ◐ — per-site `[resolved]`/`[unresolved]`, an honest design; a missing definition is replaced by a namesake without a flag | ✅ |
| T3 impact | ◐ — direct callers only, no transitive closure | ✅ |
| T4 sig-change | ✖ — not offered for Python | ✅ |
| T5 arch | ◐ — the design reads every import scope; defects A and B leave 8 of 45 cycles | ✅ |
| determinism | ✅ — identical edge sets in 3 runs | ✅ |
| failure reporting | ◐ — a refused file is logged as `ERROR` at exit 0 and counted by `coverage` under the wrong reason, but no answer carries it; defect A logs nothing; a fact query returns `[]` | ✅ — a refused file is named at build ("missing, not absent") |

## Разбор

- **What we'd take.**
  - **Derived edges as declared rules.** `DEPENDS_ON` is four lines of `depends.dl` that anyone can
    read and argue with. In codemap the same kind of derivation lives in Python code. A declared rule
    is also the documentation of what the edge means. A backlog candidate: the licence closes the code,
    not the idea.
  - **An import is a node in its own scope.** That is why function-local, `TYPE_CHECKING` and `try:`
    imports come for free rather than one by one. codemap makes the same distinction through
    `extras.scope` on the edge; in grafema it is graph structure, and where an import sits can be
    queried.
  - **A label on every call site** (`[resolved]` / `[unresolved]`). The same idea as R1-C13 and R1-C39:
    honesty at the edge, not only in the answer.
- **What their failures teach. This matters more than what we would take.**
  - All three defects are one kind: two parts of one system never run together.
    - `quickstart.ts` writes a glob that `analyzeAction.ts` cannot read.
    - The Haskell decoder expects `conversion` as a number, and the parser sends a string.
    - `resolveRelativeImport` is right for a module and wrong for an `__init__`, and the tests cover
      only the module.
    - The 0.4.1 package ships a 0.4.0 server.
  - None of them stops the run or reaches an answer. Defect A logs nothing. Defect B and the
    quickstart log per-file `ERROR` lines and still exit 0 (the quickstart exits 1 only when an unrelated
    JS rule pack also fails). A fact query returns an empty list. When a definition goes missing, the name falls through to a namesake and the answer says
    `[resolved]`.
  - Our check on the same failure class: given a file with a syntax error, codemap prints
    `1 input file(s) produced no module (1 syntax): pkg/broken.py … missing, not absent`, and it parses
    an f-string with `!r`. **Not checked:** whether that warning reaches every MCP answer it affects,
    as CodeGraph's `warnings` do, or only the build output. A backlog candidate, to be settled by a
    probe rather than by belief.
- **What we'd do differently.** Never let an answer about a symbol replace a missing definition with a
  namesake without a flag. codemap answers with `resolved.ambiguous` here, but that is a claim about our
  code, not a measurement on this card.

## Verdict & backlog effect

**learn (strong) for the design; the Python product, as measured on 0.4.1, is not usable.** The
architecture is the most careful seen in R2: every import scope is read, derivations are declared
rules, there is a per-site resolution label, and the edge set is deterministic. On a real Python
package, three integration defects hide 37 of 45 import cycles and replace the flagship function with
a namesake. None of it stops the run or reaches an answer. The licence (FSL) rules out `wrap` and `integrate` in any case.

**Backlog effect:**
- **New candidate:** derived edges declared as readable rules. A design note, not code.
- **New candidate:** a probe that a file the parser refuses is named in every MCP answer it affects,
  not only in the build output.
- **Feeds R1-C39 / R1-C13:** a second independent tool that labels resolution per site.
- **Upstream:** filed 2026-11-02 on the owner's decision, after the re-verification in §5:
  [#482](https://github.com/Disentinel/grafema/issues/482) (A, `__init__` relative imports),
  [#480](https://github.com/Disentinel/grafema/issues/480) (B, f-string conversion),
  [#481](https://github.com/Disentinel/grafema/issues/481) (quickstart glob).

## 5. Re-verification before filing — pre-registration (2026-11-02)

The owner decided to file the three defects, after one more check that we have them right. This
section is written before that check. What is new compared with §1:
- **Python itself is the reference**, not codemap: `sys.modules` after an import, and `py_compile`.
- **Every run uses a fresh `HOME`** and a fresh directory, so no cached analyzer or database survives.
- **A positive control stands next to every defect,** in the same tree.

Read from source before the check: in `main`, Python imports still go through `python-resolve`, and its
`resolveRelativeImport` is unchanged. The derive builtin `relative_import_resolve` (`builtin.rs`) is
documented as "the exact port" of that function and is used by no pack yet. The conversion mismatch is
the Rust serializer (`python_parser.rs`, `"s"`/`"a"`/`"r"`) against the Haskell field
(`peFvConversion :: !Int`), identical on both refs. The tracker has 13 issues, none about Python.

Expectations:

- **V-A1.** `pkg/sub/__init__.py: from .m import x`. Python loads `pkg.sub.m` (`'pkg.sub.m' in
  sys.modules`). grafema has no `DEPENDS_ON pkg.sub → pkg.sub.m`.
- **V-A2, control.** `pkg/sub/a.py: from .m import x` in the same tree. grafema has `pkg.sub.a →
  pkg.sub.m`.
- **V-A3.** With `pkg/m.py` also defining `x`, Python still does not load `pkg.m`. grafema has
  `pkg.sub → pkg.m`.
- **V-B1.** `!r`, `!s` and `!a` each drop their file. `f"{y}"` and `f"{y:>8}"` keep theirs. All five
  files compile under `py_compile`. `analyze` exits 0, and without `--verbose` it prints no line that
  names a dropped file.
- **V-Q1.** With a fresh `HOME`, `analyze --quickstart` on a Python-only project writes a brace glob,
  downloads no Python analyzer and yields 0 `MODULE` nodes. Its output contains no warning about
  missing Python binaries.
- **V-Q2, control.** The same fresh `HOME` and project with `include: ["**/*.py"]` yields every
  `MODULE`.

If any control fails, the matching issue is not filed until it is understood.

### 5.1 Re-verification reconciled

Fresh `HOME` and a fresh directory for every scenario, grafema 0.4.1, Python 3.12 as the reference.

| | expected | measured | |
|---|---|---|---|
| V-A1 | Python loads `pkg.sub.m`; grafema has no `sub → sub.m` | `pkg.sub.m` loaded, `pkg.m` not; no such edge | holds |
| V-A2 | control `sub.a → sub.m` present | present | holds |
| V-A3 | grafema has `sub → pkg.m`, which Python never loads | `pkg/sub/__init__.py -> pkg/m.py` | holds |
| V-B1 | `!r`/`!s`/`!a` dropped, `{y}`/`{y:>8}` kept, all compile, exit 0 | exactly so | holds |
| V-B1 | no line of the default output names a dropped file | **6 lines do**: one `ERROR … decode error` per file, plus `errors=3` | **fails — my earlier claim was wrong** |
| V-Q1 | brace glob, no Python analyzer, 0 `MODULE`, no warning | brace glob, no analyzer, 0 `MODULE`. `ERROR … Failed to spawn grafema-python-analyzer` per file, and the cause is never named | half: the defect holds, "no warning" does not |
| V-Q2 | control with `**/*.py` finds every module | 3 of 3, Python analyzer downloaded | holds |

**What changed in the card because of this check:**
- The claim that defect B and the quickstart failure were visible "only with `--verbose`" was wrong.
  It came from reading an empty `--log-file` and a verbose run, and never the default output. Corrected
  in §0.1, §1, the coverage table, the разбор, `comparison.md` and the backlog.
- The accurate account:
  - Defect A logs nothing at all.
  - Defect B logs one `ERROR` per file and exits 0. `coverage` counts the files as "Unsupported — no
    indexer available", the wrong reason. No query answer carries it: `who g` says "no callers found",
    and `query g` lists only the two analyzed definitions.
  - The quickstart logs a spawn failure per file and never names the cause.
- The quickstart's exit code is not a property of the defect. On the three-file project it exits 1,
  because two JS rule packs fail with `E-PLAN-003` ("per-rule output estimate … exceeds
  max_materialized"). On the bquant tree it exited 0. That pack failure is not understood and is not
  part of any issue.

**Still holds unchanged:** all three defects, their minimal reproductions, the counts on the tree (8 of
45 cycles; 42 with A and B fixed), and the `analyze_zones` misattribution. They are ready to file. *Filed: #482 (A), #480 (B), #481 (quickstart).*

## 6. Second pass — pre-registration (2026-11-02)

The first pass measured the import graph in depth. It left grafema's own headline claims untouched:
guarantees, calls, data flow and MCP. Same tool, tree, config and stand. A fresh `HOME` is used for
every probe that touches installation.

### 6.1 Guarantees: a Datalog contract against `codemap check`

bquant's own architecture contract (`codemap.toml`: eight forbidden layer pairs) is written as grafema
guarantees, one per pair, of the form:

```
violation(X) :- node(X, "MODULE"), attr(X, "file", F), starts_with(F, "bquant/core/"),
                edge(X, Y, "DEPENDS_ON"), attr(Y, "file", G), starts_with(G, "bquant/analysis/").
```

On cb89a24 the truth breaks the contract in exactly three places, and all three are in grafema's
measured edge set. So the prediction is exact, not a range:

- **G1, clean tree.** `check` exits 1 and names exactly these three:
  - `core.config → analysis.zones.strategies.registry` (function scope);
  - `indicators.macd → analysis.zones` (function scope);
  - `indicators.macd → analysis.zones.models`.
- **G2, a mutation in an ordinary module.** Add a top-level `from bquant.analysis.zones import models`
  to `bquant/data/loader.py`. A fourth violation appears, `data.loader → analysis.zones.models`.
  `codemap check` names it too.
- **G3, the same mutation inside a package `__init__.py`.** Add `from ..analysis.zones import models` to
  `bquant/data/__init__.py`. grafema reports **no** new violation, because of defect A; `codemap check`
  reports it. So a contract gate inherits the resolver's blind spot.
- **G4, a rule with a typo.** The predicate `edgee(...)` instead of `edge(...)`, on the clean tree. The
  guarantee **passes** with 0 violations and exit 0. Their docs say an unknown predicate makes the
  rule be "skipped with a warning".
- **G5, an edited rule.** `check` runs with rule v1 (G1's first rule). The file is then edited so v1
  can never match, and `check` runs again without re-analysis. The old v1 still runs: `import()` skips
  a guarantee whose node already exists.
- **G6, cycles as a recursive rule.**
  `reach(X,Y) :- edge(X,Y,"DEPENDS_ON"). reach(X,Z) :- reach(X,Y), edge(Y,Z,"DEPENDS_ON").
  violation(X) :- node(X,"MODULE"), reach(X,X).` If the engine accepts multi-clause recursive rules,
  the violations are exactly the **11** modules on grafema's own cycles. If it does not, the card says
  how it refuses.

### 6.2 Calls against codemap

Edges: `MATCH (c)-[:CALLS]->(f) RETURN c.file, f.file`. Only `bquant/** → bquant/**` pairs across
different files are scored, against the same pairs from codemap's `calls` edges on the same tree.
codemap is not ground truth for calls, so this is **agreement**. A sample of 10 disagreements per side
is classified by reading the source.

- **K1.** At least 80 % of grafema's file pairs are also codemap's.
- **K2.** grafema has fewer than 60 % of codemap's file pairs. Expected causes: the dropped
  `pipeline.py`, and names re-exported through package `__init__` files that defect A leaves
  unresolved.
- **K3.** For `MACDZoneAnalyzer`, the files that `who` marks `[resolved]` are a subset of the files
  codemap lists as callers.

### 6.3 Data flow, descriptive

Three `wtf` questions whose answers are read from the source beforehand:

- **D1.** `wtf ALLDATA_DIR` (`core/config.py:19`). The chain should be `DATA_DIR / 'alldata'` →
  `DATA_DIR` → `PROJECT_ROOT` → `Path(__file__).parent…`. Predicted: correct. It is a chain of
  module-level constants.
- **D2.** `wtf removed_rows` (`data/processor.py:133`). It should reach `initial_rows - len(cleaned_df)`,
  then both names' assignments in the same function. Predicted: correct.
- **D3.** `wtf zones_features` (`zones/analyzer.py:151`). It should reach
  `self.features.extract_all_zones_features(zones)`, then the assignment of `self.features` in
  `__init__`. Predicted: partial, stopping at the call or at `self.features`. Their dataflow is
  "partial" for Python.

### 6.4 MCP, descriptive

`grafema-mcp --project <tree>` over stdio: `initialize`, then `tools/list`, then `get_stats` and
`find_calls` for `MACDZoneAnalyzer`.

- **M1.** The server starts and lists at least 25 tools.
- **M2.** `find_calls` agrees with the CLI's `who` count for the same symbol (83).

### 6.5 What the second pass will still not establish

Incremental behaviour, memory and scale beyond one 20-second tree, a build of `main`, JS/TS, `why`
and the knowledge layer, `git-ingest`. They stay "not established" in the card.
