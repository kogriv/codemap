# Understand-Anything

**Verdict:** learn-only · **Feeds:** R1-C43 / R1-C47 (symbol-loss gate), R1-C61 (the LLM door) ·
**Card status:** hands-on — deterministic layer on the full R2 tree (§0–§2); LLM layer as a one-run
**pilot** on a 9-file slice with Sonnet 5.5 (§3–§4)

**Scope:** `sha256:300e0a010e351d0a91a7e006c3cc18047d7d400c94a525ddbe727f796a5e47d2` (R2 benchmark
`bquant.scope.json` — 280 files, 207 .py / 73 .md, bquant@cb89a24) · run mode: **materialized** from a
fresh `git archive cb89a24` extract (staging verified `== canonical ✓`)

> The most-starred tool in the field so far, at **86 314 ★**. It is a different kind of thing from
> everything else in this folder: an agent skill whose graph is mostly **written by the model**. Its
> deterministic layer does what it says. It is byte-identical across runs, and 215 of its 216 edges are
> real. But it reads only the imports that sit directly at module top level. On bquant that is every
> one of the 45 import cycles gone, and the file-analyzer agent is told not to look again. With a model
> in the loop (Sonnet 5.5, 9-file pilot, $0.71), the model added summaries, layers and a tour, and **not
> one** `calls`, `inherits` or `depends_on` edge.

**How to read this card.** §0 and §3 are the expectations, each committed before its run (304ad69,
cd8f4eb). §1–§2 and §4 are what the runs showed, reconciled against them. The comparison table, the
разбор and the verdict come last.

## Identity

- **Repo:** [Egonex-AI/Understand-Anything](https://github.com/Egonex-AI/Understand-Anything)
  (redirected from `Lum1104/Understand-Anything`, created 2026-03-15) — 86 314 ★ / 7 279 forks /
  323 open issues (2026-10-15).
- **License:** MIT.
- **Version measured:** `main` at **f2d0164** (2026-10-12). The plugin installs from the default
  branch; the last tag is v2.9.0 (2026-07-10).
- **Stack:** TypeScript (pnpm workspace). `@understand-anything/core` handles tree-sitter extraction
  through wasm grammars. The skill orchestration lives in Markdown (`skills/*/SKILL.md`,
  `agents/*.md`), and the scripts are Node `.mjs` plus two Python mergers. The dashboard is a separate
  package.
- **Install:** the official route is a plugin or marketplace install into an agent. For this card:
  `git clone` → `pnpm install --frozen-lockfile && pnpm --filter @understand-anything/core build`.
  This is what the skill's own Phase 0 runs on a fresh install. **Reproduced: yes**, first try
  (install 2 m 54 s).

## What it is

`/understand` is a seven-phase script **for an agent to follow**:
- scan → batch → analyze (up to 5 concurrent file-analyzer subagents) → assemble review →
  architecture → tour → review → save.
- The authors moved the rule-lookup parts out of the model and into scripts, and the source says why:
  "runtime LLMs produced inconsistent, regex-only scripts with sparse coverage". These parts are file
  inventory, the import map, structure extraction, batching, fingerprints and the incremental plan.
- What the model still writes: `calls`, `depends_on`, `related`, `tested_by` and every non-code edge,
  plus layers, tours, summaries and the domain graph.
- Output is a `knowledge-graph.json` under `.ua/` plus an interactive dashboard. There is no MCP
  server: the agent reads the JSON through further skills (`/understand-chat`, `-explain`, `-diff`,
  `-onboard`).

## 0. Pre-registration (committed before any run on the R2 tree)

### 0.1 What the tool is, read from source before measuring

Understand-Anything (`Egonex-AI/Understand-Anything`, formerly `Lum1104/…`, MIT, ★86k) is **not a
standalone indexer**. It is a skill/plugin for coding agents (Claude Code, Codex, Cursor, Copilot, Gemini
CLI, …). `/understand` runs a seven-phase pipeline in which **LLM subagents** write the knowledge graph.
Bundled Node scripts handle the parts the authors moved out of the model:

| layer | who produces it | source |
|---|---|---|
| file inventory, language, category | `scan-project.mjs` (deterministic) | `skills/understand/` |
| `imports` edges, file → file | `extract-import-map.mjs` (tree-sitter + per-language resolver) | same |
| functions / classes / methods per file | `extract-structure.mjs` (tree-sitter) | same |
| `calls`, `depends_on`, `related`, `tested_by` edges | **file-analyzer LLM agent** ("infer from imports + function names when confident") | `agents/file-analyzer.md` |
| layers, tour, summaries, domain graph | **LLM agents** | `agents/*.md` |

Two properties read from the source can be checked directly on bquant:

- **Only module-top-level statements are read.** `PythonExtractor.extractStructure` walks
  `rootNode.child(i)` and handles `import_statement` / `import_from_statement` there and nowhere else.
  Imports inside a function, under `if TYPE_CHECKING:`, or inside `try:` are not extracted.
- **`from .. import Name` resolves only to a submodule.** With a leading-dot source and an empty tail,
  `resolvePythonImport` probes `<pkg>/Name.py` and `<pkg>/Name/__init__.py`. It never emits
  `<pkg>/__init__.py`, which is the module that statement actually executes. bquant has 10 such lines,
  all of them `from .. import BaseAnalyzer/AnalysisResult` into `bquant/analysis/__init__.py`.

### 0.2 Version and procedure

- Tool: `main` at **f2d0164** (2026-10-12). The plugin installs from the default branch; the last
  tag is v2.9.0 (2026-07-10). Core built with `pnpm install --frozen-lockfile && pnpm --filter
  @understand-anything/core build` (pnpm 10.6.2, Node 24).
- Tree: a fresh `git archive cb89a24` extract, materialized with `materialize.py --root`.
- Commands, as the skill runs them: `scan-project.mjs <root> <out>` → feed its `files` to
  `extract-import-map.mjs <in> <out>` → feed bquant's `.py` files to `extract-structure.mjs <in> <out>`.
  No LLM is called at any point.
- Mapping: `bquant/x/y.py` → `bquant.x.y`, `…/__init__.py` → the package. Self-edges are dropped.
  Only edges with both ends inside `bquant/` are scored, which matches the truth's universe.
- Truth: codemap on the same staging tree, module→module `imports` edges, split by the `scope` extra
  (absent = module level, `function`, `type_checking`). Every cycle is enumerated with
  `nx.simple_cycles`. This uses the same truth definition as `research/codegraph_remeasure.md`.

### 0.3 Controls

- **C1** — the staging tree verifies as `== canonical ✓`, and the scope_id is `sha256:300e0a01…5e47d2`.
- **C2 — the truth reproduces on this tree:**

  | scope | edges |
  |---|---|
  | module | 240 |
  | function | 25 |
  | type_checking | 1 |
  | **total** | **266** |

  The full graph has 45 cycles. The module-only graph has **0**, and module + type_checking has **1**.
  Already measured on the R2 staging that `codegraph_remeasure` used. C2 asserts that the fresh extract
  gives the same numbers.
- **C3 — fixture, same scripts, three files in one package:**
  - a top-level `from .b import f` gives an edge;
  - a function-local `from .c import g` gives **no** edge;
  - `from . import NAME`, where `NAME` is defined in `__init__.py`, gives **no** edge to `__init__.py`.

  If C3's first case fails, the harness is wrong and nothing below is read.

### 0.4 Predictions

- **P1** — the UA import graph over `bquant/` has **0 cycles**. Its recall on the 45-cycle truth is
  therefore 0. All 45 need a function-local or `TYPE_CHECKING` edge, and the extractor reads neither.
- **P2** — precision: ≥ 95 % of UA's bquant→bquant edges are in codemap's all-scope set.
- **P3** — UA has **0 of the 25** function-scope edges and **0 of the 1** type_checking edge. An edge
  counts as present only if no top-level import also produces it.
- **P4** — recall on the 240 module-level edges is **below 100 %**. The 10 edges from
  `from .. import …` lines into `bquant.analysis` are missing, at least 8 of the 10. A miss can be
  masked only if the same file also imports `bquant.analysis` some other way at top level.
- **P5** — four runs of scan + import map give byte-identical `importMap` output.
- **P6 — T1** — `extract-structure` reports these definitions:

  | symbol | where | kind |
  |---|---|---|
  | `analyze_zones` | `bquant/analysis/zones/pipeline.py` | top-level function |
  | `analyze_zones` | `UniversalZoneAnalyzer` in `analyzer.py` | method |
  | `MACDZoneAnalyzer` | `bquant/indicators/macd.py` | class |

  These are the defs codemap reports.

### 0.5 Decision rules

- **R1** — if P1 holds, the card says the deterministic layer cannot see any of the 45 cycles. T5 is
  then answered only by the LLM layer, which this card does not measure.
- **R2** — if P4 and C3's third case both hold, the `from .. import Name` miss is a confirmed defect
  with a minimal repro. Reporting it upstream is **the owner's call**; it is not filed from here.
- **R3** — if P2 fails, every false edge is classified before any claim uses the precision figure.
- **R4** — the full `/understand` run is **not** part of this card: model in the loop, token cost,
  non-deterministic by construction. It is recorded as a door with its price, for the owner to decide.
  The same reasoning applies as for R1-C61.

### 0.6 What this card will not establish

- Anything the LLM layer produces: `calls` edges, layers, tours, summaries, chat answers. That excludes
  T2–T5 as UA would actually answer them.
- Speed at scale, incremental update, the dashboard, other languages.

## 1. Hands-on — the deterministic layer on the R2 tree

Harness: [`research/bench/understand_anything.py`](../bench/understand_anything.py). Raw results:
[`understand_anything_results.json`](../bench/understand_anything_results.json). Wall time is 28 s for
four full scan + import-map runs plus the truth build and one structure pass. No LLM is called.

| measure | result |
|---|---|
| files scanned | 281 = the 280 of the scope + `manifest.json`, which `materialize.py` writes into the staging root |
| UA import edges, bquant→bquant (module level, self-edges dropped) | **216** |
| … of them in codemap's truth | **215** (99.5 %) |
| truth edges found, by scope | module **215 / 240** · function **0 / 25** · type_checking **0 / 1** |
| cycles in UA's import graph | **0** (truth: 45) |
| determinism, 4 runs | **1 distinct digest** of `importMap` |
| T1 `analyze_zones` | `pipeline.py` function + `UniversalZoneAnalyzer.analyze_zones` method — both ✅ |
| T1 `MACDZoneAnalyzer` | `indicators/macd.py` class ✅ |
| classes / top-level functions / methods | 126 / 206 / 628 |

**The 25 module-level misses, every one classified** by statement position (with `ast`, against
the source):

| cause | edges | example |
|---|---|---|
| `from .. import Name`, where `Name` is defined in the package `__init__` | **10** | `regression.py:16 from .. import BaseAnalyzer` → no edge to `bquant/analysis/__init__.py` |
| import inside a module-level `try:` | **15** | `analysis/zones/__init__.py:522`, inside `try:`: `from .analyzer import UniversalZoneAnalyzer` |

Both causes were read from source before the run (§0.1), and C3 shows both on three files. No third
cause exists on this tree.

**The one edge outside the truth** is `bquant.cli → bquant.visualization`, from
`cli.py:15 from .visualization import charts`. Python does execute `bquant/visualization/__init__.py`
there. UA emits the package and the submodule; codemap's truth records only the deepest module. The
truth's convention is what makes this edge "false". It is not UA's error.

**Definition counts agree with Python's `ast` exactly** (206 + 628). codemap's 863 function nodes
differ by convention only:
- `@property` methods become attributes (5);
- dataclass-synthesized `__init__` methods are added (35);
- a property setter shares its getter's id (1).

834 − 5 + 35 − 1 = 863. Neither side has a defect here.

## 2. Reconciliation with the pre-registration

| | expected | measured | |
|---|---|---|---|
| C1 | `== canonical ✓`, `sha256:300e0a01…5e47d2` | as expected | ✅ |
| C2 | 240 / 25 / 1 = 266 edges; 45 cycles; module-only 0; +tc 1 | identical | ✅ |
| C3 | top-level edge yes; function-local no; `from . import NAME` → no `__init__` | `pkg/a.py → [pkg/b.py]` only | ✅ |
| P1 | 0 cycles | 0 | ✅ |
| P2 | precision ≥ 95 % | 99.5 % (215/216) | ✅ |
| P3 | 0 / 25 function, 0 / 1 type_checking | 0, 0 | ✅ |
| P4 | < 100 % of module edges; ≥ 8 of the 10 named `from ..` edges missing | 215 / 240; **10 of 10** missing | ✅ |
| P5 | 4 runs byte-identical | 1 digest | ✅ |
| P6 | the three T1 definitions | all three | ✅ |

**Decision rules.**
- **R1** applies. The deterministic layer cannot see any of the 45 cycles. T5 as UA answers it, through
  LLM-assigned layers, is not measured here.
- **R2** applies. The `from .. import Name` miss is confirmed with a three-file repro. **Not filed —
  reporting it is the owner's call.** The `try:` miss belongs to the same report, since it comes from
  the same loop over `rootNode.child(i)`.
  *Filed 2026-10-15 on the owner's decision: [#727](https://github.com/Egonex-AI/Understand-Anything/issues/727).*
  The `try:` / function-local / `TYPE_CHECKING` half was already upstream as #692, with a patch in a
  comment. It was not re-filed. Instead it was measured: patched `main` on this tree recovers all 25
  function-local edges, the 15 under `try:` and the one under `TYPE_CHECKING` (256 of 266 edges), and
  sees **13 of 45** cycles, all real. The only edges still missing are the 10 `from .. import Name`
  lines. Adding exactly those 10 to the patched graph gives **45 of 45**. #727 carries that table.
- **R3** does not apply (P2 held). The one false edge was classified anyway, above.
- **R4** stands: the `/understand` run with a model is not part of this card.

### Surprises

- **S1 — the misses are locked in by instruction.** `agents/file-analyzer.md` tells the model: "use
  `batchImportData[filePath]` directly … Do NOT attempt to re-resolve imports from source", and
  requires the count of `imports` edges to equal the map's length. The model therefore cannot repair
  the 25 misses even when it reads the file. It can only add `depends_on` edges ("dynamic requires,
  lazy loads", weight 0.6), and only if it decides to.
  *Narrowed 2026-10-15: "cannot" was too strong.* By instruction, no agent repairs these misses: the
  assemble-reviewer is bound to the same map ("only add edges that are backed by `$IMPORT_MAP`
  data"). But upstream #692 reports a real run where agents went past that, recovered 5 076 Python
  edges with their own AST pass, and injected them. So recovery can happen, against the design rather
  than by it, and it is not something a reader can count on.
- **S2 — the structural layer does what the README promises.** "Same input → same output, every run":
  4 / 4 here. "The same code always yields the same edges": yes, for the edges it extracts.
- **S3 — the first false edge in the R2 series that is the truth's fault.** The package-import
  convention (`from .pkg import sub` also imports `pkg`) is a real Python dependency that codemap's
  module graph leaves implicit. It is recorded here, not changed: every earlier card was scored under
  the same convention, and one edge does not move any figure.

### What this card does not establish

- Anything the LLM layer produces: `calls` edges, layers, tours, summaries, chat answers. That covers
  T2–T5 as UA would actually answer them, and their cost and stability.
- Whether, in a real `/understand` run, the model's `depends_on` edges recover some of the 25 misses
  or the 26 function / TYPE_CHECKING edges.
- Other languages, incremental updates (`prepare-incremental.mjs`, the symbol-loss gate), the
  dashboard, speed at scale.

## 3. Pilot: the LLM layer with a model in the loop — pre-registration

*Committed 2026-10-15 before the run. The owner chose the model, Sonnet 5.5, after reading the cost
estimate. The pilot replaces that estimate with a measurement on a small slice; whether to do the
full tree is decided after it.*

### 3.1 Setup

- **Host and model:**
  - Claude Code 2.1.300 headless:
    `claude -p "/understand --full" --model claude-sonnet-5-5 --output-format stream-json --verbose`.
  - Plugin loaded for this session only with `--plugin-dir`, from the same f2d0164 checkout as §1.
  - `--strict-mcp-config` with no servers.
  - `--no-session-persistence`.
  - `--max-budget-usd 10` as a hard cap. Hitting it ends the pilot, and that is a result too.
- **Auth:** subscription (OAuth). `total_cost_usd` is therefore the API-price equivalent the host
  reports, not money charged. It is the figure extrapolated below.
- **Isolation:** `bwrap`. The whole filesystem is read-only except the pilot directory and the host's
  own state directory, which auth refresh needs. `--dangerously-skip-permissions` is used *inside*
  that sandbox, because the skill's agents run shell commands and write files.
- **Slice:** `bquant/core/` from the R2 tree: 9 files, 142 023 bytes, 4 019 lines, and nothing
  else. It is copied into a fresh git repo with one commit, because the skill reads `git rev-parse
  HEAD`. In the §1 batching of the full tree, these 9 files spread over 2 of the 19 batches. Alone,
  they are expected to form 1 batch.
- **Truth for the slice:**
  - `imports` = `extract-import-map.mjs` on the same slice (the deterministic map of §1);
  - `calls` = codemap on the same slice, module-level pairs of `calls` edges.

### 3.2 Expectations

- **Q1 — completion.** The run ends with `.ua/knowledge-graph.json` written, under the cap. If the
  sandbox blocks a write the skill needs, the error is reported as a surprise; it is not worked around
  mid-run.
- **Q2 — imports 1:1.** File-level `imports` edges in the final graph equal the deterministic map's
  pairs for the slice. The file-analyzer is instructed to emit them 1:1, and the merger recovers any
  it drops. Prediction: identical sets.
- **Q3 — `calls` edges.** At least one cross-file `calls` edge. Precision of the file-level pairs
  against codemap's module-level `calls` pairs is **≥ 80 %**. Recall is measured, not predicted.
- **Q4 — cost of the pilot** (this is the estimate under test):

  | | expected |
  |---|---|
  | input tokens, incl. cache reads | 3–12 M |
  | output tokens | 30–150 k |
  | `total_cost_usd` | 0.5–5 |
  | wall time | 10–40 min |

- **Q5 — attribution.** Usage can be split by agent through the `parent_tool_use_id` of
  `stream-json` events into:
  - the orchestrator;
  - each file-analyzer;
  - the fixed phases (scanner, assemble-reviewer, architecture, tour).

  If it cannot be split, the extrapolation below is not attempted, and only the pilot's total is
  reported.

### 3.3 Extrapolation rule (fixed now)

`full ≈ fixed + 19 × analyzer`, where:
- `fixed` = everything except file-analyzers in the pilot;
- `analyzer` = the mean cost of one file-analyzer in the pilot, scaled by bytes per batch (the mean
  §1 batch is 231 kB; this slice is 142 kB).

**Known bias, named in advance.** The fixed phases read the assembled graph, which is ~31× larger on
the full tree. The rule therefore understates them. The extrapolated figure is reported as a lower
bound for those phases.

### 3.4 What the pilot will not establish

- Quality on the full tree.
- Run-to-run variance (one run).
- How the LLM layer handles the embedded sample-data modules, which are not in the slice.
- Any model other than Sonnet 5.5.

## 4. Pilot — what happened, reconciled

Harness: [`research/bench/understand_anything_pilot.py`](../bench/understand_anything_pilot.py). Results:
[`understand_anything_pilot_results.json`](../bench/understand_anything_pilot_results.json).

**Attempt 1 stopped at a human gate, as designed.**
- Phase 0.5 generates `.understandignore` and **waits for the user's confirmation**. Headless, the run
  ended there: "success", 4 turns, **$0.17**, nothing analyzed.
- The run also listed a stray empty file, `ok`. That was my sandbox write probe left in the slice; it
  was removed before attempt 2.
- Attempt 2 started from a clean `.ua/`. The prompt answered the gate in advance, as a user would:
  "the generated `.understandignore` is reviewed and accepted as is — continue through all phases
  without waiting". That is the **one deviation** from an interactive run. No other gate was hit.

**Attempt 2 completed: 108 s wall, $0.708 API-equivalent, all on `claude-sonnet-5-5`.**

| | tokens |
|---|---|
| cache reads | 1 253 916 |
| cache writes | 123 014 |
| plain input | 60 |
| output | 19 064 (523 of them thinking) |

The graph has:
- **nodes:** 102 — 9 file, 32 class, 61 function;
- **edges:** 198 — imports 12 · contains 93 · exports 93;
- **layers:** 4;
- **tour:** 7 steps.

| | expected | measured | |
|---|---|---|---|
| Q1 completion under the cap | graph written | written, on attempt 2 (attempt 1 stopped at the Phase 0.5 gate) | ✅ with the gate noted |
| Q2 imports 1:1 | identical sets | 12 = 12, identical | ✅ |
| Q3 `calls` | ≥ 1 cross-file edge, precision ≥ 80 % | **0 `calls` edges** (also 0 `inherits`, 0 `depends_on`); codemap has 4 cross-file call pairs on the slice | ❌ |
| Q4 cost | 3–12 M input · 30–150 k output · $0.5–5 · 10–40 min | 1.38 M · 19 k · **$0.71** · **108 s** | input, output and time below the range; cost inside it |
| Q5 attribution | splittable by agent | splittable, with one defect (below) | ◐ |

**Usage by agent.** The cost split uses price-ratio weights; see the harness docstring.

| agent | messages | input incl. cache | cost share |
|---|---|---|---|
| orchestrator | 16 | 934 k | $0.44 |
| file-analyzer, batch 1 (33 kB) | 5 | 159 k | $0.13 |
| file-analyzer, batch 2 (69 kB) | 4 | 126 k | $0.07 |
| file-analyzer, batch 3 (40 kB) | 5 | 158 k | $0.08 |

### Surprises

- **S4 — the orchestrator shortened the pipeline on its own.** Its final report says so: it "built the
  layers and tour directly … instead of dispatching the architecture-analyzer, tour-builder and
  assemble-reviewer agents", and "replaced the review with an inline structural check". It also
  reports that some file and class summaries were "written from names and line ranges, not source"
  (`exceptions.py`, `nb.py`, `numpy_fix.py`, `NotebookSimulator`), and that no analyzer ran its edge
  validation pass. Three of the seven phases' agents were never dispatched. **The skill's design was
  not what ran.** The model decided what the run would be, and its report says so.
- **S5 — no semantic edges at all.** Everything in the graph beyond `imports` is `contains`/`exports`,
  which mirror the deterministic structure. The model contributed summaries, 4 layer names and a 7-step
  tour. It contributed not a single relationship. codemap's 4 cross-file call pairs on the slice:
  - `cache → config`
  - `cache → logging_config`
  - `performance → cache`
  - `performance → logging_config`

  None of them appears.
- **S6 — 3 batches, not 1.** The 9 files went to three file-analyzers, not the single one §3.1
  expected.
- **S7 — the harness under-counts output per message.** The per-message `usage` in `stream-json`
  sums to ~2 k output tokens against the session's 19 064, so the per-agent split carries that
  error. Totals come from the session's `modelUsage`, which is the host's own figure.

### Extrapolation (rule §3.3, applied as fixed)

- **Analyzer cost per kB of source:** $0.27 for 142 kB of slice, about **$0.0019/kB**.
- **Full tree:** 4 388 kB → **$8.4** across the analyzers, plus the orchestrator's $0.44.
- **Result: ≈ $8.8.** Putting all the unattributed output on the analyzers (S7) gives **≈ $11.8**.
- **Read it as a lower bound of ~$9–12 API-equivalent per full run on Sonnet 5.5.** Three reasons:
  - the skipped phases (S4) cost nothing here;
  - the orchestrator's context grows with 19 batches, which the rule cannot see;
  - the 0.74 MB of embedded sample-data modules are priced at the slice's per-kB rate.
- **Wall time:** with 5 analyzers at a time, the pilot's ~1-minute analyzers suggest **tens of
  minutes, not hours**. That is not measured.

**What the pilot changes in the card's verdict:** nothing for T2–T5. On this slice, Sonnet 5.5 added
no `calls`, `inherits` or `depends_on` edge, so the LLM layer answered none of the structural
questions codemap is measured on. Its contribution is prose: summaries, layers, a tour. That prose is
what a newcomer reads first, and it is outside this benchmark's tasks.

**Not established:** behaviour on the full tree (the orchestrator might not skip phases there);
run-to-run variance; any other model; summary quality. Summaries were not scored, beyond the model's
own admission that some were written without reading source.

## Coverage vs codemap

| Capability | codemap | Understand-Anything |
|---|---|---|
| symbol lookup (T1) | ✅ | ✅ (deterministic structure; measured) |
| callers/callees (T2) | ✅ | ◐ by design, ✖ on the pilot slice: **0** `calls` edges written by the model (codemap: 4 cross-file pairs); full tree not measured |
| impact (T3) | ✅ | ◐ `/understand-diff` over the LLM graph — not measured; on the pilot that graph held imports only |
| signature-change surface (T4) | ✅ | ✖ no per-call argument data |
| architecture (T5) | ✅ | ◐ LLM-assigned layers (pilot: 4, written by the orchestrator itself after skipping the architecture agent); **import cycles: 0 of 45 visible** to its import graph |
| determinism | ✅ | ◐ structural layer ✅ (4/4); graph as a whole ✖ by construction (pilot: one run, variance not measured) |
| MCP | ✅ | ✖ (skills read a JSON file) |
| languages | Python | many (tree-sitter wasm) + non-code (config, docs, IaC, SQL, Figma) |
| license | MIT | MIT |

## Разбор

- **What we'd take.**
  - **The symbol-loss gate on incremental updates** (`validate-incremental-symbols.mjs`). Before an
    incremental graph is published, every function, class and method that disappeared is classified
    against base and current source. Only confirmed deletions pass; "still present" and "unknown"
    block publication. Our splice (R1-C43) discloses that it may be carrying an old miss. Theirs
    refuses to publish a loss it cannot explain. Read from source, not measured. The idea fits our
    absent-answer work (R1-C44), and it is worth a look when incremental is next touched.
  - **"Move rule lookup out of the model" stated as a reason.** Their source comments name the failure
    that forced each script ("inconsistent, regex-only scripts with sparse coverage"; "billed at LLM
    rates"). That is a trace of measurement inside the code, the same habit as our `devref/gaps/`.
- **What we'd do differently, and why.**
  - Read imports wherever they occur and label them with a scope (module / function / type_checking),
    rather than reading only the top level. On bquant every cycle lives in the non-top-level part. A
    graph that drops those imports does not merely shrink: it reports "acyclic" about a tree with 45
    cycles.
  - Never forbid the consumer from checking the producer. S1 is a design choice that turns a
    resolver's blind spot into the whole system's blind spot.
- **What the author knows that we didn't.**
  - **Demand.** 86k stars for "graphs that teach": onboarding tours, plain-English summaries,
    business-domain mapping, non-code files (Dockerfiles, Terraform, SQL) in the same graph. None of
    it is a query answer, and all of it is what a newcomer asks first. codemap answers questions; this
    tool explains a codebase. That is a different product, and the stars say which one more people
    want.
  - **Graphs for non-code.** `configures`, `deploys`, `migrates`, `documents` edges put the repo's
    operational files on the same map. codemap stops at Python.
- **What we did NOT check.** See §2 *What this card does not establish*, §3.4 and the end of §4. The
    LLM layer was measured once, on 3 % of the tree: enough to price it and to see that it added no
    structural edge there, not enough to judge it on the full tree or across runs.

## Verdict & backlog effect

**learn-only.** The deterministic layer is honest and reproducible, but too shallow for Python import
structure, and by design it is not corrected downstream (agents may still do it on their own, as #692 shows). The rest is model output and out of this
card's reach. The pilot (§4) is the first look into that part: on 9 files, Sonnet 5.5 added prose
(summaries, layers, a tour) and no relationship, at $0.71; a full run extrapolates to ≥ ~$9–12.
- **Confirms R1-C29.** Cycles need non-top-level imports; this tree is the cleanest demonstration yet,
  with 0 module-level cycles against 45 in total.
- **Adds a read-only pointer for R1-C43** (the symbol-loss gate).
- **Adds a second instance to R1-C61's door, now priced:** the pilot measured what a model in the
  loop costs here (§4). The full run stays the owner's decision.
- **Reported upstream:** [#727](https://github.com/Egonex-AI/Understand-Anything/issues/727) for `from .. import Name`. The `try:` / nested half is their #692.
