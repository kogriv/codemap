# grafema

**Verdict:** *pending — §0 only* · **Card status:** pre-registration committed, no run on the R2 tree yet

**Scope:** `sha256:300e0a010e351d0a91a7e006c3cc18047d7d400c94a525ddbe727f796a5e47d2` (R2 benchmark
`bquant.scope.json` — 280 files, 207 .py / 73 .md, bquant@cb89a24) · run mode: **materialized** from a
fresh `git archive cb89a24` extract (staging verified `== canonical ✓`)

**How to read this card.** §0 holds the expectations, committed before any run on the R2 tree. The
sections after it are what the runs showed, reconciled against §0.

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
  (`E-PLAN-003`); the Python failure appears only with `--verbose`. The "binaries missing" warning in
  the same function stays silent, because Python was never put on the list of needed binaries.
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
