# Understand-Anything

**Verdict:** _pending — filled after §2_  ·  **Feeds:** R1-C…  ·  **Card status:** hands-on (deterministic layer only; see §0.4)

**Scope:** `sha256:300e0a01…5e47d2` (R2 benchmark `bquant.scope.json` — 280 files, 207 .py / 73 .md,
bquant@cb89a24) · run mode: materialized

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
