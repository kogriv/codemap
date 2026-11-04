# Graphify

**Verdict:** learn (strong): the highest import recall of any released tool scored on this truth (90 %,
precision 99.6 %), with byte-identical runs. Its cycle report sees **2 of 45** · **Feeds:** R1-C13 (labels on the edge), R1-C75 (new, codemap's
own gap, found here), the `reverse_import` lesson (§Разбор) · **Card status:** hands-on: import graph,
calls, T1/T2, report, offline claim on the full R2 tree (§1–§2); `graphifyy` 0.9.102 from PyPI

> On the code layer, the README's word "deterministic" holds:
> - three runs on fresh copies wrote byte-identical `graph.json`, in 14 s each;
> - of 241 module dependencies, 240 are real (99.6 %); recall is 90 % (codemap's truth on the same tree);
> - the 23 files that call `MACDZoneAnalyzer` are exactly codemap's 23;
> - an ambiguous name is refused with exit 3 and both candidates, as the README promises.
>
> Two things go wrong:
> - **An import inside a function makes no module dependency.** It leaves only an edge to the imported
>   symbol. On this tree 25 of the 266 edges are such imports, and 13 of the 14 mutual-import pairs close
>   through one. So Graphify's own `## Import Cycles` lists **2 of the 45** cycles.
> - **A builtin is resolved to a package class of the same name.** `raise NotImplementedError` became a call
>   to `bquant.core.exceptions.NotImplementedError` in three files that never import it. Two of the five
>   edges are tagged `EXTRACTED`, "explicit in the source".
>
> What I predicted from source and got only half right: the graph is undirected, so two files that import
> each other keep one link. The authors know this (their #4839). They store the other direction as a
> `reverse_import` stamp on the surviving link, and their cycle finder reads it. My scoring did not.
>
> The community-naming step calls the `claude` CLI on the user's subscription when no API key is set.
> It announces that on stderr, and `GRAPHIFY_BACKEND=none` turns it off.

**How to read this card.** §0 is the pre-registration, committed in 9431aa0 before any run on the R2 tree.
§1 is what the runs showed. §2 reconciles §1 with §0, and the diagnostics marked *post hoc* there were
added after the scored run to separate two causes. The comparison, the разбор and the verdict come last.

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

## 1. Hands-on — the R2 tree

Stand, inside the shared core-slot accounting; `graphifyy==0.9.102` in a fresh venv, Python 3.12;
`extract --code-only`, `GRAPHIFY_BACKEND=none`, empty `HOME` per run. Numbers are in
[`bench/graphify_results.json`](../bench/graphify_results.json).

```
run 0/1/2         rc 0, 14.2 / 14.4 / 14.1 s, 5 103 nodes, 11 699 links, 89 bquant modules
graph.json        byte-identical in all three runs; "directed": false, "multigraph": false
                  graph: {schema_version: 1, graphify_version: "0.9.102"}
module deps       241, of them 240 in the truth: precision 99.6 %, recall 240 / 266 = 90.2 %
  by truth scope  module 239 / 240 · function 0 / 25 · type_checking 1 / 1
  from __init__   81 / 87
  imports_from    160 links, 159 true (the set Graphify's own cycle finder reads)
  symbol-only     55 more pairs reached only through an imported symbol's defining file, 19 of them true;
                  with them recall is 97.4 %, precision 87.5 %
cycles (truth 45: 14 of length 2, 5 of 3, 6 of 4, 8 of 5, 8 of 6, 4 of 7)
  links only                  0 of 45
  links + reverse_import      3 of 45, 0 false
  every import link + stamps  28 of 45, 4 false
  GRAPH_REPORT.md             2 cycles: analysis <-> analysis.candlestick, analysis <-> analysis.chart
```

**The one edge outside the truth** is `bquant.cli → bquant.visualization`, the same edge grafema had. The
dependency is real; the truth attributes it to `visualization.charts`.

**All 26 missed truth edges.** 25 are the function-scope imports, each present only as an edge to the
imported symbol, or not at all. The 26th is `zones.pipeline → zones.cache`, a module-level import. It
collapsed into the `TYPE_CHECKING` link `cache → pipeline` and survives only as that link's
`reverse_import` stamp. That is the one place on this tree where the undirected graph itself costs an
edge.

**Diagnostics, post hoc.** The fixture could not tell the two causes apart (§2, C3k), so two minimal trees
were run after the scored run:
- **D1**, two files importing each other at module level. Default `extract`: one `imports_from` link,
  `x → y`, stamped `reverse_import: true`. With `--no-cluster`, which writes the extraction without building
  the networkx graph, both links are there. So the collapse is real, and it is compensated by the stamp.
- **D2**, a single function-local `from pkg.d import h`, with nothing else between the two files: an
  `imports` edge to `h`, and **no** `imports_from`, with or without `--no-cluster`. This one is the
  extractor, not the graph.
- Not explained: two of the six `analysis ↔ subpackage` pairs did get a `reverse_import` stamp for their
  function-local direction, the other four did not.

**Calls**, as file pairs against codemap (agreement, not truth):

```
Graphify cross-file pairs   137; 122 also codemap's: agreement 89.1 %
codemap pairs               204; Graphify has 122: coverage 59.8 %
cross-file call links       EXTRACTED 238 (pair in codemap: 94.5 %) · INFERRED 37 (75.7 %) · indirect 1
calls to a non-callable     167 links, mostly exception classes (IndicatorCalculationError 16, …)
```

The nine `INFERRED` cross-file links whose pair codemap lacks, each read against the source:
- **4 correct:** `config.validate(...)` in four detection modules → `ZoneDetectionConfig.validate` in
  `detection/base.py`. codemap does not have them.
- **1 plausible:** `indicator.calculate(df)` on what `IndicatorFactory.create(...)` returns (`pipeline.py`
  L285). Not decidable statically; `INFERRED` is the honest tag.
- **4 wrong:**
  - three are `raise NotImplementedError(...)` in `analysis/__init__.py` (L185) and `ml/__init__.py` (L10,
    L14). Both files use the **builtin**: neither imports anything from `core.exceptions`. Graphify points the
    call at `class NotImplementedError(BQuantError)` there. Two more calls to the same homonym, from
    `indicators/base.py` (L147, L157), carry the tag `EXTRACTED`; that file imports only
    `IndicatorCalculationError`;
  - one is `from bquant.analysis.timeseries import ZoneRegressionAnalyzer` inside a `try/except ImportError`
    (`analyzer.py` L100). `timeseries` does not export that name, so at runtime the import fails. Graphify
    links the call to the class in `statistical/regression.py` by its name.

The `EXTRACTED` links codemap lacks, sampled: `LibraryManager.create_indicator(...)`,
`.load_all_libraries()`, `.check_library_availability()` and similar. They are calls through the class
name, and they are right. **codemap misses them.** In `CombinedVolatilityStrategy._calculate_bollinger_metrics`,
codemap resolves 0 of 17 calls, and `LibraryManager` there comes in through
`from .....indicators import LibraryManager`, a package re-export. That is codemap's gap, recorded as
R1-C75. It is unverified beyond this one function.

**T1/T2, the CLI.**
- `graphify explain analyze_zones`: **exit 3**, "Ambiguous: 'analyze_zones' matches 2 nodes in different
  files", with `pipeline.py` and `UniversalZoneAnalyzer.analyze_zones` in `analyzer.py`, and how to retry.
- `explain MACDZoneAnalyzer`: exit 0, `bquant/indicators/macd.py L48`, degree 106. Incoming: 57 `calls`
  (`EXTRACTED`), 23 `imports`, 19 `uses` (`INFERRED`, a class whose methods use it).
- The files with a `calls`/`uses` link to it are **exactly codemap's 23 caller files**, on a repo-scoped
  codemap graph of the same tree.

**The offline claim (P11).** A fresh `HOME`, no `GRAPHIFY_BACKEND`, no API key, and a fake `claude` on
`PATH` that logs its arguments and exits 1:
- `extract . --code-only`: the fake was **not** called;
- `cluster-only .`, the step `extract` itself suggests next ("to generate GRAPH_REPORT.md and name
  communities"): the fake was called once, as `claude -p --output-format json --no-session-persistence`.
  stderr said: "no API key found; naming communities via the `claude` CLI (claude -p). … or
  GRAPHIFY_BACKEND=none to disable." The prompt carries the top node labels of each community, which are
  names from the code. With the fake failing, the communities were named "Community N", exit 0.

This is a design decision with its reasoning in the source (#4361): a silent downgrade to placeholders was
judged worse. It is announced and can be turned off. But the README's first line about code reads "Code
maps for free, fully local". On a machine with Claude Code installed and no key, the default run's second
step sends symbol names to a model on the user's subscription.

## 2. Reconciliation with the pre-registration

| | expected | measured | |
|---|---|---|---|
| C1 | staging `== canonical ✓` | ✓ | holds |
| C2 | 266 edges, 45 cycles, 14 of length 2 | ✓ | holds |
| C3a, C3a_reversed, C3b | a→b, no b→a, a→c | all three | holds: the measurement is valid |
| C3c | function-local import gives a→d | only `imports` to the symbol `h`; no `imports_from` | **fails** in the primary set. D2 confirms this is the extractor |
| C3d | a→e, `type_only` | `imports_from:type_only` | holds |
| C3e, C3f, C3i, C3j | a→f, a→pkg, user→sub, plain→b | all four | holds |
| C3g, C3h | sub→sub.m; sub→sub.m2, not pkg.m2 | both, as `re_exports`; no pkg.m2 | holds: no grafema `__init__` defect |
| C3k | exactly one of x→y, y→x | primary set: only x→y. Union: both, y→x through the symbol | holds **as written, for the wrong reason**: y→x is function-local, so D2, not the collapse, removes it. D1 (post hoc) shows the collapse separately |
| P1 | 89 modules | 89 | holds |
| P2 | ≥ 20 / 25 function, 1 / 1 type_checking | **0 / 25**, 1 / 1 | **fails** |
| P3 | ≥ 70 / 87 from `__init__` | 81 | holds |
| P4 | 0 / 14 mutual pairs with both directions | 0 / 14 as links; 3 / 14 with stamps | holds as written. The cause is D2 for 13 pairs, the collapse for 1 |
| P5 | 20–31 / 45 cycles | **0** (links); 3 (with stamps); 28 (every import link) | **fails**: below the range. I bounded it by the collapse and did not foresee D2 |
| P6 | report: ≤ 20 cycles, ≤ 5 files, none of length 2 | 2 cycles, **both of length 2** | **fails**. The stamps put 2-cycles back, and I had not read the stamp code |
| P7 | precision ≥ 90 % | 99.6 % | holds |
| P8 | same primary set in 3 runs | byte-identical `graph.json` | holds, more strongly than predicted |
| P9 | agreement ≥ 80 % | 89.1 % (coverage 59.8 %) | holds |
| P10 | ≥ 90 % of `INFERRED` cross-file links in codemap | 75.7 % (28 / 37) | **fails as written**. Read: of the 9 outside, 4 correct, 1 plausible, 4 wrong; so about 89 % look right |
| P11 | recorded | `extract`: no call. `cluster-only`: one `claude -p` call, announced | finding (R3) |
| P12 | exit 3 with both candidates; MACDZoneAnalyzer exit 0 | as predicted | holds |

At least one of P4, P5, P6 and C3k was to fail if the undirected-graph consequence were not real. P5 and
P6 failed, but not for that reason, so the pre-registration did not discriminate. D1 does. The consequence
is real and compensated, and I could not have seen the compensation without reading `analyze.py` past the
docstring. Its docstring says "from imports_from edges", and its body also reads `reverse_import`.

### Surprises

- **The two causes were not the ones I listed.** I expected the collapse to cost cycles. On this tree it
  costs one edge. The function-local gap costs 25 edges and almost every cycle.
- **codemap has a gap Graphify does not:** calls through a class name imported via a package re-export
  (R1-C75). The comparison ran in the direction I had not planned to read.
- **Graphify's handling of `__init__` relative imports is right where grafema's was not:** 81 of 87, and
  the fixture's C3g/C3h pass. The six missed `__init__` edges are function-local.

### What this card does not establish

- Whether the function-local gap is a decision. I found no note on it in the source or docs. That has to
  be settled before anything is filed, as R1 says.
- The headline benchmarks (memory, ERPNext), the "80 %", the non-code layer, MCP, Graphify Cloud, other
  languages.
- Whether the stamps explain everything the report shows. Two of the six `analysis` pairs got stamps for a
  function-local direction, and four did not; I did not trace why.

## Coverage vs codemap

| task | Graphify 0.9.102 | codemap |
|---|---|---|
| T1 defs | ✅ ambiguity refused, exit 3, both candidates | ✅ (`resolved.ambiguous`) |
| T2 callers | ✅ the same 23 files as codemap for `MACDZoneAnalyzer` | ✅ |
| T3 impact | ◐ `affected` exists; not measured | ✅ |
| T4 sig-change | ✖ no call-contract surface | ✅ |
| T5 arch | ◐ communities and god nodes. Import cycles: 2 of 45, because function-local imports make no dependency | ✅ |
| determinism | ✅ byte-identical `graph.json` | ✅ |

## Разбор

**What to learn.**
- **The stamp is the honest half of a bad trade.** An undirected store loses a direction, and they keep it
  as an attribute their own analysis reads. Any other consumer of `graph.json` that reads links, an
  exporter or someone's script, sees one direction. If codemap ever compresses its graph, the lesson is:
  do not keep a fact only where your own reader looks for it.
- **Tags on the edge, and the cost of getting them wrong.** `EXTRACTED`/`INFERRED` on every link is what
  R1-C13 asks for. The `NotImplementedError` case shows how such a tag fails: "explicit in the source" was
  given to a name the source never imports. It is the same class of defect as codemap's R1-C72 (a stdlib
  name rewritten into a package module), and found the same way, by reading the disagreements.
- **Exit codes for answers.** `0` an answer, `3` ambiguous, `4` no match. codemap says the same in its
  envelope (`resolved.ambiguous`), but a script reading the exit code learns nothing. This is a cheap
  candidate for the CLI.
- **Speed and size of the code layer:** 14 s and about 290 MB for this tree, single process.

**What not to learn.** Sending names from the code to a model by default in the step that follows a
"fully local" one, even when it is announced.

## Verdict & backlog effect

**learn (strong).** On Python imports this is the most complete released graph scored on this truth: recall
90 %, against 61 % for grafema 0.4.1 and 81 % for Understand-Anything's released extractor, at 99.6 %
precision, and byte-identical across runs. It cannot serve as an architecture gate on a codebase
that uses lazy imports to break cycles, which is what bquant does: its cycle report sees 2 of 45. The
licence would allow `integrate`; nothing here needs it.

- **R1-C75 (new, codemap):** a call through a class name imported via a package re-export goes unresolved
  in the fast tier (`LibraryManager.create_indicator(...)` after `from .....indicators import LibraryManager`).
  Seen once; to be verified on a minimal tree before design.
- **R1-C13:** the `EXTRACTED`/`INFERRED` tags, and their failure mode on a builtin homonym.
- **CLI exit codes for ambiguity/no match:** a candidate, not filed.
- **Upstream candidates, the owner's decision after re-verification on a minimal tree with a control:**
  (A) a function-local `from` import makes no `imports_from`, so lazy-import cycles are invisible;
  (B) a builtin resolved to a package class of the same name, tagged `EXTRACTED`. The `claude -p` labeling
  is a documented decision and is not a candidate.

## 3. Re-verification before filing — pre-registration (2026-11-04)

The owner decided to file both candidates after this re-check. Duplicate search first:
- **(A) is partly upstream already.** Open [#2447](https://github.com/Graphify-Labs/graphify/issues/2447),
  cause B: "Import statement inside a function body → no `imports` edge emitted at all", measured on
  0.9.32 against `mod.func()` call resolution. On 0.9.102 an `imports` edge to the symbol *is* emitted
  (D2), so part of it has moved. What is not in #2447 is the consequence for the module graph: no
  `imports_from`, so `## Import Cycles` cannot see a cycle that closes through a lazy import. So (A) goes
  as a **comment on #2447**, not a new issue.
- **(B):** no issue found for "builtin", "shadow", "homonym", "NotImplementedError". A new issue.

Minimal trees, `graphifyy==0.9.102` from PyPI into a fresh venv, an empty `HOME`, `GRAPHIFY_BACKEND=none`,
`extract . --code-only`, then `cluster-only .` for the report:

- **A1:** `pkg/x.py` imports `pkg.y` at module level; `pkg/y.py` imports `pkg.x` inside a function. Python
  sees a cycle (it is the way such cycles are usually broken, and it is still a dependency cycle).
  **Expected:** no `imports_from` link `y → x`, no `reverse_import` stamp for it, and the report says
  "None detected".
- **A1-control:** the same with both imports at module level. **Expected:** the report lists the 2-file
  cycle. If it does not, A1 says nothing and is not filed.
- **B1:** `pkg/errors.py` defines `class NotImplementedError(Exception)`; `pkg/a.py` does
  `raise NotImplementedError("x")` inside a function and imports nothing. **Expected:** a `calls` link
  from that function to `pkg/errors.py`'s class, although Python resolves the builtin there.
- **B1-control:** `pkg/b.py` does `from pkg.errors import NotImplementedError` and the same raise.
  **Expected:** the same link, now correct. If B1 has no link, there is nothing to file.
- **B2:** `pkg/files.py` defines `def open(path)`; `pkg/c.py` calls `open("f")` without importing it.
  Recorded, not predicted: whether the builtin-shadowing applies to functions too.
- Each tag (`EXTRACTED`/`INFERRED`) is recorded as found.
