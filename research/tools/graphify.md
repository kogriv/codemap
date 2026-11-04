# Graphify

**Verdict:** set after the run (§0.5) · **Feeds:** set after the run · **Card status:** pre-registration only.
Nothing below §0 has been run on the R2 tree yet.

**Scope:** `sha256:300e0a010e351d0a91a7e006c3cc18047d7d400c94a525ddbe727f796a5e47d2` (R2 benchmark
`bquant.scope.json`: 280 files, 207 .py / 73 .md, bquant@cb89a24) · run mode: **materialized** from a
fresh `git archive cb89a24` extract (staging verified `== canonical ✓` on 2026-11-04)

## Identity

- **Repo:** [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify), created 2026-04-03,
  default branch `v8`. **141 647 ★, 13 545 forks, 1 642 open issues** (2026-11-04). Y Combinator S26.
  By stars it is the largest tool in this series by two orders of magnitude.
- **License:** Apache-2.0 (with a `LICENSE-MIT` file and a `NOTICE`). Code can be read, learnt from and
  taken with attribution. "graphify" and its logo are marks of Graphify Labs.
- **Version measured:** PyPI `graphifyy==0.9.102` (uploaded 2026-11-03), the latest release. The PyPI
  name has a double `y`; the CLI is `graphify`.
- **Stack:** Python ≥ 3.10; tree-sitter with 30 grammars as hard dependencies (about 40 languages with
  extras); networkx; `rapidfuzz`, `numpy`. An optional MCP server (`[mcp]` extra), Neo4j and FalkorDB
  exporters, LLM backends for the non-code layer (Gemini, Kimi, Claude, OpenAI, DeepSeek, Bedrock,
  Ollama, or the `claude` CLI).
- **Commercial layer:** Graphify Cloud (hosted, "cuts agent token spend by 80%", formal verification,
  Sentry/Jira connectors). Not measured here.

## What it is

`/graphify .` in a coding assistant, or `graphify extract <path>` headless, maps a project into a
knowledge graph: code, docs, PDFs, images, video. Three files come out: `graph.json`, `graph.html`,
`GRAPH_REPORT.md` (god nodes, communities, suggested questions). The graph is queried with
`graphify query`, `path`, `explain`, `affected`. Code goes through tree-sitter only; the rest goes through
a model.

## 0. Pre-registration (committed before any run on the R2 tree)

### 0.1 What was learnt before measuring

**From the README and `BENCHMARKS.md`, the claims this card can test without spending money:**
- **G1, local and free.** "Code is parsed with tree-sitter AST: deterministic, no LLM, nothing leaves your
  machine." "A code-only corpus requires no API key: `graphify extract` runs fully offline."
- **G2, every edge explained.** "Each connection is tagged `EXTRACTED` (explicit in the source) or
  `INFERRED` (resolved by graphify)."
- **G3, the resolver prefers no edge over a wrong one.** `BENCHMARKS.md` audited every `INFERRED`
  cross-file edge between FastAPI's production sources by hand: 12 of 12 correct (2026-10-05).
- **G4, cross-file links.** "`calls` / `imports` / `inherits` / `mixes_in` resolved across ~40 languages."
- **G5, ambiguity is refused.** "A name that matches several nodes is refused with the candidates listed
  rather than guessed." Exit codes: `0` an answer, `3` an ambiguous name, `4` no matching node.
- **G6, the artifact is versioned.** `graph.json` carries `graph.schema_version` and
  `graph.graphify_version`.

The headline numbers (LOCOMO recall@10 0.497; ERPNext key-fact coverage 82.0 % against 70.8 % for grep, n=6)
are about memory and a model-driven agent. Testing either costs money. They are out of this card unless
a separate, pre-registered and approved run is made (the same rule as R1-C61).

**From reading the source of 0.9.102** (`graphify/extract.py`, `build.py`, `analyze.py`, `export.py`):
- **Imports.** `import a.b` gives an `imports` edge from the file node to the module's file.
  `from m import f` gives two edges: `imports_from` file → file of `m`, and `imports` file → the symbol
  node `f`, which lives in the file that *defines* `f`. A relative import resolves from the importing
  file's own directory (`current_path.parent` for one dot), so the grafema `__init__` defect is not
  expected here. Imports under `if TYPE_CHECKING:` keep their edge, stamped `type_only`.
- **The graph is undirected by default.** `build_from_json(..., directed=False)` builds an `nx.Graph`
  "for backward compatibility". Direction is carried in `_src`/`_tgt` attributes and restored when
  `graph.json` is written. `graphify extract` has no `--directed` flag. `query`, `path` and `explain`
  accept `--directed` and default to directed for `explain`.
- **Consequence, predicted and not yet seen:** an `nx.Graph` holds one edge per node pair. Two files that
  import each other give two edges, `a → b` and `b → a`, on the same pair, and only one can survive. So
  **every import 2-cycle should lose one direction**. Any longer cycle that runs through the lost
  direction goes with it.
- **Import cycles in the report** (`analyze.find_import_cycles`): a file-level graph built from
  `imports_from` edges only (`type_only` skipped), then cycles of at most **5** files, the **20** shortest.
- **A model in a code-only run.** README: `GRAPHIFY_BACKEND=none` "disable[s] all LLM backends (semantic
  extraction and the `claude -p` labeling fallback)". So without it, something may call the `claude` CLI
  on the user's subscription, even when the corpus is code.

**One toy run before this was written**, to learn the `graph.json` shape: two files, `tp/m2.py` doing
`from tp.m1 import f` and calling it. It wrote 5 nodes and 5 links, `"directed": false`,
`"multigraph": false`, `graph: {schema_version: 1, graphify_version: "0.9.102"}`. Links carry
`relation`, `confidence` (`EXTRACTED`), `confidence_score`, `source_file`, `source_location`. The
cross-file call `g → f` was tagged `EXTRACTED`. The toy shares no case with the fixture below.

### 0.2 Procedure

- Tree: the R2 staging tree, copied fresh for every run. `graphify extract <tree> --code-only` with
  `GRAPHIFY_BACKEND=none`, an empty `HOME`, no `*_API_KEY` in the environment. Only `bquant/**.py` is
  scored.
- **Module edges** from `graph.json`: each link's endpoints are mapped to modules through their node's
  `source_file` (`bquant/x/y.py` → `bquant.x.y`, `…/__init__.py` → the package). Self-edges are dropped.
  - **Primary set:** `imports_from`, `re_exports`, and `imports` that end on a file node. These are module
    dependencies.
  - `imports` that end on a symbol node are reported separately. They land in the file that defines the
    symbol, which is not the module the import names.
  - Also reported: the `imports_from`-only set, which is what Graphify's own cycle finder reads.
- Truth: codemap 0.0.24 on the same tree, module→module `imports` edges, split by the `scope` extra;
  cycles by `nx.simple_cycles`. The same definition as the grafema, CodeGraph and Understand-Anything
  cards.
- **Calls:** `calls`/`indirect_call` links between different `bquant/**` files, as file pairs, against
  codemap's `calls` edges mapped to their owner modules. codemap is not ground truth for calls, so this is
  **agreement**. A sample of 10 disagreements per side is classified by reading the source.
- Harness: [`research/bench/graphify.py`](../bench/graphify.py), committed with this section. Heavy runs on
  the stand, inside the shared core-slot accounting.

### 0.3 Controls (the measurement is void if C1 or C2 fails, or C3's positive cases fail)

- **C1.** The staging tree verifies `== canonical ✓`. Already true when this was written.
- **C2.** The truth reproduces: 266 edges (240 module-level, 25 function, 1 type_checking), 45 cycles.
  Already true when this was written, on codemap 0.0.24. Also counted then:
  - **14 of the 45 cycles have length 2**, one for each pair of modules that import each other.
    Six pairs are `bquant.analysis` with a subpackage, seven are `indicators.base` with an indicator, one is
    `zones.cache` with `zones.pipeline`.
  - **40 of the 45 cycles use at least one edge of such a pair.**
  - If the lexicographically later direction of each pair is dropped, **25** cycles remain.
- **C3.** A fixture package, extracted the same way. Cases C3a–C3i are the grafema card's fixture,
  unchanged, so the two cards compare. Each line is one edge and its expected outcome.
  - **C3a**, positive: `from pkg.b import f` in `pkg/a.py` gives a→b.
  - **C3a_reversed**, positive: there is **no** b→a. Direction survives the write.
  - **C3b**, positive: `from .c import g` gives a→c.
  - **C3c**: a function-local `from .d import h` gives a→d. Predicted.
  - **C3d**: `if TYPE_CHECKING: from .e import T` gives a→e, stamped `type_only`. Predicted.
  - **C3e**: `try: from .f import k` gives a→f. Predicted.
  - **C3f**: `from . import NAME` (`NAME` defined in `pkg/__init__.py`) gives a→pkg. Predicted.
  - **C3g**: `from .m import x` in `pkg/sub/__init__.py` gives sub→sub.m. Predicted: here the grafema
    defect is not expected (§0.1).
  - **C3h**: `from .m2 import y` in the same `__init__` gives sub→sub.m2 and **not** sub→pkg.m2. Predicted.
  - **C3i**: `from pkg.sub import x` (re-exported by `sub/__init__.py`) gives user→sub. Predicted.
  - **C3j**: `import pkg.b` gives plain→b. Predicted.
  - **C3k**: `pkg/x.py` imports `pkg.y` at module level, and `pkg/y.py` imports `pkg.x` inside a function.
    **Predicted: exactly one of x→y and y→x is present.** This is the undirected-graph consequence.

  If C3a, C3a_reversed or C3b fails, the harness or the setup is wrong and nothing below is read.

### 0.4 Predictions for the R2 tree

- **P1, coverage.** All 89 `bquant/**.py` modules have a file node.
- **P2, scopes.** At least 20 of the 25 function-scope truth edges and the 1 type_checking edge are found.
- **P3, `__init__`.** At least 70 of the 87 truth edges that start in a package `__init__.py` are found.
- **P4, mutual pairs.** Of the 14 mutual pairs, **0** have both directions in `graph.json`.
- **P5, cycles.** The primary set hits **between 20 and 31** of the 45 truth cycles. 31 is 45 − 14: the
  2-cycles cannot be there. The lower bound allows for the longer cycles that run through a lost
  direction (25 remain under the lexicographic choice, C2).
- **P6, report cycles.** The `## Import Cycles` section of `GRAPH_REPORT.md` lists at most 20 cycles, none
  longer than 5 files, and none of length 2.
- **P7, precision.** At least 90 % of the primary set's edges are truth edges.
- **P8, determinism.** Three runs on fresh copies give the same primary set. Whether `graph.json` is
  byte-identical is recorded, not predicted.
- **P9, calls.** At least 80 % of Graphify's call file pairs are also codemap's (agreement). Coverage of
  codemap's 204 pairs is recorded, not predicted.
- **P10, the `INFERRED` claim (G3).** Of the cross-file `bquant → bquant` call edges tagged `INFERRED`, at
  least 90 % are file pairs codemap also has. A sample of 10 of those that are not is read against the
  source.
- **P11, offline (G1).** The fixture extraction succeeds with an empty `HOME`, no API key and
  `GRAPHIFY_BACKEND=none`. Separately, a fresh `HOME`, **no** `GRAPHIFY_BACKEND`, and a fake `claude` on
  `PATH` that only logs its arguments and exits 1: a code-only `extract`, then `cluster-only`. Recorded:
  whether the fake was called, and by which step. No prediction. If it is called, the card says so plainly:
  it would be a model call on the user's subscription during a run the README calls "fully offline".
- **P12, ambiguity (G5).** `graphify explain analyze_zones` exits **3** and lists candidates including the
  top-level function in `analysis/zones/pipeline.py` and the method `UniversalZoneAnalyzer.analyze_zones`.
  `explain MACDZoneAnalyzer` exits 0 and names `bquant/indicators/macd.py`.

At least one of P4, P5, P6 and C3k fails if the undirected-graph consequence is not real.

### 0.5 Decision rules

- **R1.** If C3k and P4 hold, the lost direction is a defect with a minimal reproduction. Filing it
  upstream is the owner's decision (issues in a third-party tracker stay with the owner). Before any
  filing, it is re-checked on a minimal tree with a control and an empty `HOME`, as for grafema.
- **R2.** If P5's hit count is below 45, the card names, by class, what the missed cycles lack: a lost
  direction of a mutual pair, a missing scope, other.
- **R3.** If the fake `claude` is called in P11, that is reported as a finding whatever else holds.
- **R4.** The verdict is set after the run. The licence allows any verdict, `integrate` included.

### 0.6 What this card will not establish

- The memory benchmarks, the ERPNext agent benchmark and the "80 %" Cloud claim: model-driven, they cost
  money (§0.1).
- The non-code layer (docs, PDFs, images, video) and `graph.html`.
- Languages other than Python.
- The MCP server, unless a later addendum pre-registers it.
- Graphify Cloud.
