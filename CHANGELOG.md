# Changelog

All notable changes to codemap. Format loosely follows [Keep a Changelog](https://keepachangelog.com);
the graph JSON has its own `SCHEMA_VERSION` (`codemap/model.py`), noted per entry.

## [Unreleased]

### Fixed

- **Flat module layouts no longer defeat the build** (R1-C21; issues
  [#4](https://github.com/kogriv/codemap/issues/4), [#5](https://github.com/kogriv/codemap/issues/5)) —
  found within twenty minutes of pointing codemap at a second real target. A directory of sibling modules
  importing each other by bare name used to either **crash** (no `__init__.py`: griffe reports a namespace
  package whose `filepath` is a `list`, fed straight to `Path()` by five separate consumers) or, with an
  `__init__.py`, **succeed with zero `imports` edges** — after which `architecture` reported "no layer
  violations / acyclic" and `dead-code` called every live module an orphan. Sibling imports now resolve,
  labelled `extras.resolution="flat"` because the layout is an inference about `sys.path` rather than
  something the source states; call resolution and attribute access read the same qualified import map.
  A correctly-laid-out package is untouched: `bquant`'s graph is **byte-identical** before and after, and
  the inference is asserted to fire zero times there. No schema change.
  See [docs/flat-layout.md](docs/flat-layout.md).
- **…and across the root boundary** (R1-C21-f1; issue
  [#6](https://github.com/kogriv/codemap/issues/6)) — a consumer root (`--consumer tests`) writing the
  *same* bare-name import produced no edge at all, so `impact` still answered "isolated" for every symbol
  on a flat repo. Consumer-root imports are now qualified the same way, **gated on the core actually being
  flat**: a properly packaged core is never on `sys.path`, so a bare `import config` in a script cannot be
  reaching `pkg/config.py` and no edge is invented (the gate reads evidence — a namespace root, or existing
  `flat` edges — not the presence of `__init__.py`). bquant's full repo-scoped graph is byte-identical.

### Added

- **Graph diagnostics** (`codemap/diagnostics.py`) — a build that produces **0 import edges across ≥2
  modules** now says so at build time (stderr), in `stats` (a `diagnostics` list beside `freshness`), and
  at the top of `report architecture` / `dependencies` / `dead-code`, *before* any conclusion drawn from
  the empty graph. A namespace-package target is named as well. Derived, never stored — `graph.json`
  gains no field. This half stands alone: it stays correct for any layout the extractor fails to parse.
- A second check for the dimension the first one missed: **≥1 consumer/doc root supplied but not one
  reference from them reaches the core**. The case that prompted it had 75 import edges — so the
  "empty graph" check stayed quiet — and none of them crossed a root boundary.
- Each check carries its own **severity** (`warning` invalidates the findings below it; `note` states a
  fact and invalidates nothing) and its own consequence sentence, rendered through one shared presenter.
  Fixes issue [#8](https://github.com/kogriv/codemap/issues/8), where the namespace-package *note* was
  captioned with the empty-graph *warning*'s "derived from that empty import graph — unknown, not clean"
  over a report computed from 404 import edges: the mirror of the bug the banners exist to prevent.

- **The `high` dead-code band is trustworthy again** (R1-C22; issue
  [#7](https://github.com/kogriv/codemap/issues/7)) — it graded a private function "no inbound calls,
  references, or decorators" while its name sat two lines below the definition. Measured across two real
  packages (codemap's own included) that was **20 of 51** candidates, from three forms the graph did not
  model: a function used **as a value** (dispatch table, `default=` callback), a call at **module level**
  (import-time statements were never walked), and a call inside a **nested def** (the closure was dropped
  wholesale). All three are modelled now — `references` with `extras.resolution="name"` / `"annotation"`
  (labelled apart: a dispatch table implies the symbol runs, an annotation implies a contract), `calls`
  sourced from the module node, and closure calls attributed to the innermost enclosing definition with
  `extras.via="nested"`. Two of the three were missing **call** edges, so `impact`, `callers` and `flows`
  were reading a call graph with import-time work and closure bodies cut out. The grader is untouched:
  it always demoted on an inbound edge, and now it has them. `high` went 46 → 29 (codemap) and 5 → 2
  (bquant); additions only (bquant +364 edge pairs, 0 removed). No schema change.
  See [docs/dead-code.md](docs/dead-code.md#what-counts-as-a-reference).
- **…and a local variable no longer counts as a reference to the function it shadows** (R1-C22-f1; issue
  [#9](https://github.com/kogriv/codemap/issues/9)) — the mirror of the above. Python binds per scope, so a
  read of a locally-bound name is the local, not a module function of the same name; six binding forms
  (assignment, parameter, `for`, `with ... as`, `except ... as`, a nested `def`) produced false edges and
  hid a dead function in `low`. `global`/`nonlocal` opt back out, module-level rebinding is unaffected, and
  function-local **imports** deliberately do not suppress — an import binds the name to the symbol it
  imports, which is what the edge records. Measured inert on real code: 0 edges suppressed on either package.


## [0.0.2] - 2026-08-23

First internal (unpublished) cut. Extracted into a standalone repository from its incubation home (the
`bquant` monorepo), preserving the full M0–M16 development history; since extraction it has grown the MCP
adapter (M17), graph freshness (M18), the input scope manifest (M19.A), SCIP + ctags export (R1-C1/C2),
complexity metrics (R1-C4), relevance ranking + context pack (R1-C6), the closed edge vocabulary (R1-C7),
graded dead-code (R1-C8), the external-tool router/adapter layer (R1-C16), **attribute-access edges
(R1-C20)** and **incremental rebuild (R1-C9)**. Graph schema **0.11**; **363 tests** (+ optional
SCIP/ctags CLI checks when those binaries are present); warm serve surface (23 ops), an MCP adapter, and
SCIP/ctags export. Not published to PyPI (the name `codemap` is taken there — see release notes).

### Milestones

- **R1-C20 — attribute-access edges** (schema **0.11**): closes the issue #1 honesty gap — `impact` on a
  class field returned `refs: []` / `risk: "none"` even with real read/write sites, because attribute nodes
  had no inbound edges. A new closed-vocabulary `accesses` edge (function → the attribute it reads/writes,
  `extras.access`/`resolution`) is emitted by `extract/attrflow.py`: `self.field` / `ClassName.field` /
  construction kwargs on the fast `ast` tier, `obj.field` on a typed local via jedi receiver-type inference
  on the deep tier; unresolved sites are honest counters, never edges to nothing. `accesses` joins
  `_IMPACT_EDGES` (attribute-scoped — columns stay out), so a field's blast-radius is real; `Query.readers`/
  `writers`, a serve `accessors` op + MCP tool, an `attributes` block in the dossier, CLI render. Honesty
  fix: a field with no modelled accessor reports `risk: "unknown"` (+reason), never `none`. On bquant: 1619
  fast + 158 deep `accesses` edges; `impact` on `SwingThresholds.zigzag_deviation` → 6 refs (was `[]`).
  +15 tests. Docs: [docs/attribute-edges.md](docs/attribute-edges.md). Closes #1.

- **R1-C9 — incremental rebuild** (no graph schema change): `codemap build --incremental` recomputes only
  changed modules and splices the rest from the previous graph. The cheap, tier-independent passes (griffe +
  structure + dispatch + family + dataflow, ~4s) run whole and fresh every time; the two expensive jedi
  passes run only on the *affected* modules (changed/added/removed + fresh importers + old dependents), which
  is where ~93s of a ~97s deep build lives. Reuses the `.meta.json` scope sidecar (M19.A) for content-hash
  change detection; falls back to a full rebuild past 50% affected. On bquant a one-file deep edit rebuilds
  in ~5s vs ~60s (~12×). Fast tier is byte-identical to a full build; the deep tier matches a full build up
  to jedi's own run-to-run inference variance (two full `--deep` builds already differ by a few deep edges —
  a documented property of the deep tier, not the splice). `model.to_dict` now orders edges by full content
  so a spliced build serializes identically. +12 tests. Docs: [docs/incremental.md](docs/incremental.md).

- **Fixes:** stale dogfood tests repointed after bquant removed `MACDZoneAnalyzer` (deprecation-detection now
  pinned on a dedicated fixture; blast-radius on `ZoneInfo`); gitnexus router disclaimer test made
  environment-independent (mock `which`). Closes #2.

- **R1-C6 — relevance ranking + token-budgeted context pack** (no graph schema change): codemap becomes a
  first-class context provider. `Query.rank(seeds, root)` scores symbols by **personalized PageRank** over
  usage edges (calls/imports/references/inherits/implements) — global importance with no seeds (hubs like
  `logging_config`/`config` rank top on bquant), or relevance to a context with seeds (symbol id / short name
  / file path; aider's repo-map trick). The PageRank is a **pure-Python power iteration** — no numpy/scipy
  dependency (codemap stays lightweight) — and deterministic. `codemap pack --budget N [--seed X]`
  (`serve/pack.py`, serve op + MCP `pack` tool) renders the highest-ranked symbols into a token budget
  (~4 chars/token estimate, no tokenizer): output never exceeds the budget and top hubs land before leaves;
  seeding on `analyze_zones` surfaces the zone subsystem instead of the global hubs. +12 tests. Docs:
  [docs/pack.md](docs/pack.md). Closes the last open Tier-2 R1-C capability.

- **R1-C7 — closed edge-type vocabulary** (no graph schema change): `model.EDGE_TYPES` declares the closed
  set of 10 edge types (`contains`/`imports`/`export`/`inherits`/`decorated_by`/`calls`/`references`/
  `implements`/`reads`/`writes`), each documented; node `kind` stays an open set by design (edges are typed,
  nodes aren't). `tests/test_r1c7_edge_vocab.py` pins the set and fails if a real graph emits an undeclared
  type (a new relationship must be added to the vocabulary, not emitted silently) or if a declared type stops
  appearing (no dead vocabulary). Caught and fixed a drift in passing: both `model.py` and DESIGN §2 wrote
  `exports` while the code emits `export`. +3 tests.

- **R1-C8 — dead-code confidence + whitelist** (no graph schema change): `report dead-code` now **grades**
  each uncalled-private-function candidate instead of listing flat — **high** (no inbound edge or hook),
  **medium** (a decorator / registry may invoke it implicitly), **low** (something *references* it → likely
  alive) — each with a provenance reason naming why. The **low** tier is the false-positive cut a call-only
  tool (vulture) can't make: codemap's cross-root reference edges show a private helper is used by a test, a
  re-export, or a registration. A `[dead_code].whitelist` (exact id / `fnmatch` glob) in `codemap.toml`
  suppresses framework-wired candidates (argparse `set_defaults`, dispatch dicts), and `--min-confidence`
  filters by tier. `Query.dead_code(...)` is the core; `dead_symbols()` stays a back-compat wrapper. Surfaces:
  CLI `report dead-code --min-confidence`, serve/MCP `report` op. +10 tests. Docs: [docs/dead-code.md](docs/dead-code.md).

- **R1-C16 — external-tool router/adapter layer** (no graph schema change): codemap can call a
  **user-installed** external tool for capabilities outside its scope — opt-in, off by default, bundling
  nothing (calling ≠ distributing). Two modes on a license gradient: **router** (forward the answer as-is;
  any license) and **adapter** (translate the output into codemap's own contract; permissive/MIT-Apache
  only, machine-enforced at registration). The router half shipped earlier (GitNexus passthrough,
  `codemap route`); this adds the **adapter** half and the flagship use: **semantic search enriched to
  codemap symbols**. `codemap semantic "<query>"` (also the `semantic_search` MCP tool + serve op) routes a
  concept query to an opt-in **cocoindex** adapter (Apache-2.0, local, no DB/key), then resolves each fuzzy
  hit `(file, line)` to the **exact codemap symbol** at that location via the graph — fuzzy retrieval, exact
  structure, the composition neither tool gives alone. Unresolvable hits are kept honestly as `unresolved`;
  hits de-dup per symbol (best score). Enrichment lives in `serve` (needs the query layer); the adapter
  stays graph-free so `integrations` remains a near-leaf layer (codemap's own architecture contract enforces
  this — dogfood stays green). Generalized: any permissive retrieval tool registers the same way. Core works
  with no tool installed (→ empty result, never an error). +12 tests. Docs: [docs/integrations.md](docs/integrations.md).

- **M19.A — input scope manifest** (no `graph.json` schema change): codemap is deterministic on its output;
  this adds the symmetric thing for its **input**. `codemap/scope.py` resolves a scope (build args) to a
  sorted file list, content-hashes each (sha-256), builds a **profile** (files/bytes/loc by role & ext +
  largest), and computes a **`scope_id`** — same id ⇒ provably identical input. Operates **in place** over
  the real tree (the live path); **git-mode enumeration** (`git ls-files`, preferred when available) yields
  the gitignore-correct set for free — the `venv_bquant` trap from the graphlens pilot is impossible by
  construction — and records git provenance (`commit/ref/dirty` + free `git_blob`), while identity stays
  sha-256 (mode- and dirty-independent). New CLI `codemap scope <path> […] [--no-git] [--json]` and
  `codemap scope --diff A.meta.json B.meta.json`; `build` writes the `scope` block into the M18 sidecar.
  Stdlib-only (hashlib/subprocess). Substrate for R1-C9 (Merkle incremental) and M3.2 (hash-freshness).
  +7 tests. Design: [docs/design/scope.md](docs/design/scope.md).
- **R1-C1 — SCIP export** (no schema change): `codemap export scip -o index.scip` emits a
  [SCIP](https://scip-code.org/) index so Sourcegraph, Glean and any SCIP consumer light up
  go-to-definition, symbol search and type hierarchy over codemap's graph. Highest-value interop move
  from the R1 landscape. **Honest scope:** codemap's graph is symbol-level (no call-site coordinates),
  so the export is *definitions + SymbolInformation* — one Definition occurrence per located node, kind,
  docstring, and `inherits`/`implements` as SCIP `relationships` (`is_implementation`); reference
  occurrences (find-references) are deliberately omitted rather than faked. Symbol strings are built from
  codemap's canonical ids via the SCIP descriptor grammar (namespace `/`, type `#`, method `().`, term `.`).
  `protobuf` is an **optional** extra (`pip install codemap[scip]`); vendored bindings generated from the
  official `scip.proto`, lazy-imported. Deterministic bytes; validated by protobuf round-trip and the real
  `scip print` CLI. Partially satisfies R1-C7 (structured descriptor ids). +8 tests.
- **R1-C2 — ctags export** (no schema change): `codemap export ctags -o tags` emits a universal-ctags
  `tags` file — the lowest common denominator of editor navigation (vim/Emacs/`readtags` binary-search a
  sorted tags file). `codemap/serve/ctags.py` renders one extended-format line per **definition**
  (class/function/method/attribute): a `/^…$/` search-pattern address when the source line is readable
  (robust to line drift; `\`/`/`/`$` escaped), else a bare line-number address (always available from the
  graph). Extension fields are all facts codemap already holds — `kind` (c/f/m/v), `line:`, `scope`
  (`class:Foo`; module scope omitted as universal-ctags does), `signature:(…)` + `typeref:typename:…` for
  functions, `access:` (public/private), `end:`. **Honest scope:** definitions only (no reference tags —
  that is SCIP's job); modules are files not tags (skipped); re-export aliases (a symbol with no own
  location) are skipped so each definition is tagged once at its real site. Deterministic: pseudo-tags
  declare `!_TAG_FILE_SORTED\t1` and real tags sort by name→file→address (binary-searchable). Stdlib-only.
  On bquant: 1585 tags, byte-stable. +9 tests (`readtags`-CLI check when present). Docs:
  [docs/export.md](docs/export.md).
- **R1-C4 — per-function complexity metrics** (schema **0.10**): function nodes carry
  `extras.complexity` = `cc` (McCabe cyclomatic), `volume` (Halstead), `sloc` (physical span) and
  `mi` (Maintainability Index, 0–100). Computed in the behavioural AST pass (same walk as the control
  skeleton) — **source-only, stdlib-only (no radon), deterministic**; cyclomatic counts decision points
  over the function's *own* body (nested defs are separate nodes, not double-counted). codemap's value
  isn't the metrics (radon has those) but **blending them with the graph's structural signals**:
  `Query.hotspots` annotates god-classes with `total_cc`/`max_cc` and adds a `complex_functions` list
  (top by cyclomatic, `min_cc` threshold); `report architecture` and `report behavior` render them; the
  `query` dossier carries per-symbol cc/mi/volume/sloc. This separates "big by connectivity" from "complex
  by McCabe" — e.g. on bquant `NotebookSimulator` (23 methods, ΣCC 50) vs `StatisticalPlots` (23, ΣCC 111).
  +15 tests. Closes the last open Tier-1 R1-C capability.
- **R1 — research track opened** (docs only): survey of adjacent code-analysis / code-graph tools in
  `research/` — a landscape map (comparison matrix + integrate/wrap/learn verdicts) plus four theme reports
  (AI-context/repo-map, code-graph/index infra, query/dataflow engines, Python graph/arch peers). Grounded,
  web-verified. Net finding: the field is converging on codemap's thesis (source-only, deterministic,
  precise graph, no stale index); differentiators are the canonical diffable `graph.json` with provenance
  and native agent/MCP verbs. Concrete capability candidates (SCIP/ctags export, architecture-contracts
  `--check`, complexity metrics, relevance ranking + token-budgeted pack, …) logged as use-driven backlog
  items (R1-C1…C15, fully specified with scope/acceptance/effort, tiered by value÷cost) — including a
  bottom-up field intake (R1.5) of curated Telegram sources that confirms the field has converged on
  codemap's thesis and adds the live competitor roster + a grep-vs-graph benchmark. No code/schema change.
- **F23 — impact accepts a full/canonical id** (no schema change): `impact` (op, markdown, CLI) resolved
  its input by short name only, so passing a full id like `pkg.mod.Class` — exactly what `query`/`search`
  return — matched nothing and gave a falsely-empty blast radius (found on a live task). Added
  `Query.impact_targets` (node-id → itself, short name → all matches, else canonical/where_defined) and
  routed both `_op_impact` and `render_impact` through it. The extraction was fine — class instantiation
  was always captured; the bug was serve-layer input resolution.
- **M18 — graph freshness** (no schema change): the MCP server serves a static graph, so `stats` now
  reports `freshness` (`built_at` / `age_seconds` from the file mtime) — an agent can tell the map may be
  stale. The canonical graph.json stays timestamp-free (determinism preserved); build recipe + time live
  in a sidecar `<graph>.meta.json`, and `codemap refresh <graph.json>` rebuilds from it. First step of the
  deferred freshness work (M3.2), prompted by the now-live MCP consumer.
- **F22 — compact MCP payloads** (no schema change): shaped from the first live agent-over-MCP run.
  The `impact` and `call_contract` MCP tools are compact by default — `impact` omits the duplicate
  markdown and caps the flat ref list at `limit` (by_root counts stay complete); `call_contract` caps
  its list. `full=true` returns everything. On a hub (`MACDZoneAnalyzer`) this cut the `impact` payload
  ~65% and `call_contract` ~49%. Underlying ops / CLI unchanged (markdown still rendered there).
- **M17 — MCP adapter** (no schema change): `codemap serve --mcp` exposes the warm serve surface as
  Model Context Protocol tools (18 tools, one per agent-facing op) so an AI-agent host can drive
  codemap natively. Thin wrapper over `Session.handle` — the ambiguity signal (`resolved.ambiguous`)
  and error envelopes pass through unchanged. `mcp` is an **optional** dependency
  (`pip install codemap[mcp]`); the import is lazy so codemap works without it.
- **M16 — architecture overview** (schema 0.9): `report architecture` — layers + direction/violations
  (order-free), coupling (Ca/Ce/instability), god-objects & call-hubs (pervasive-tagged); `Query.layers/
  coupling/hotspots`, serve op `architecture`.
- **M15 — diff / change-review** (no schema change): `codemap review <diff>` → risk-sorted change-set
  dossier; `Query.symbol_at`/`symbols_in_range` (location→symbol), serve ops `locate`/`review`.
- **M14 — soundness** (schema 0.9): `canonical_info` surfaces ambiguity (`resolved.ambiguous`) instead of
  silently picking one of many defs; dataflow access-form (`subscripted` / `access`) so `columns()`
  returns real column-like keys, not dict-literal payload noise.
- **M13 — serve ergonomics** (no schema change): discovery/orientation ops — `search`, `families`,
  `columns_of`, `source`, `resolve`; re-export canonicalization; `file:line` in query results.
- **M3.1 — warm serve**: resident process, graph in memory, line-delimited JSON over stdio,
  transport-neutral (MCP-mappable).
- **M8–M12** (schema 0.5→0.8): provenance-aware dead-code, registry-family `implements` links,
  class-chunk call aggregation, call-site argument contracts, string-key column dataflow.
- **M6–M7**: repo-scope / impact (multi-root provenance); registry-aware call bridging.
- **M0–M5**: canonical graph (structure, imports, exports, inherits), query API, behavioral call graph,
  deep call resolution (jedi), and the RAG/vault/mermaid render views.

See [BACKLOG.md](BACKLOG.md) for the detailed milestone log and [gaps/](gaps/) for the dogfood runs that
drove each one.
