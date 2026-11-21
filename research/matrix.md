# The tool matrix — what codemap covers, what the lab measured, what it has only read

<!-- Generated from codemap/advise/data/ by `codemap advise --matrix`. Do not edit by hand: tests/test_r1c110_advise.py compares this file with the render. -->

Catalog as of 2026-11-21. Agents get the same data through the MCP tool `advise` or `codemap advise`; `codemap advise --refresh` fetches the current catalog without a release.

**Statuses.** `measured` — scored against the lab's truth, numbers in the card. `probed` — run on a real tree, not scored. `read only` — known from its docs or a survey; nobody here has run it. `rejected` — tried and unusable for that need.

21 need(s), 53 tool(s); claims: 23 measured, 18 probed, 62 read, 9 rejected.

| need | codemap | best other tool | tools |
|---|---|---|---|
| `py-symbols` Where a Python symbol is defined, and its dossier | ✅ covered | graphify (measured) | 11 |
| `py-callers` Who calls a Python function, and what it calls | ✅ covered | graphify (measured) | 13 |
| `py-impact` What a change to a Python symbol touches (blast radius) | ✅ covered | jevgrep (measured) | 6 |
| `py-imports` Python import graph and import cycles | ✅ covered | graphify (measured) | 7 |
| `import-gate` An architecture contract on imports, enforced in CI | ✅ covered | import-linter (measured) | 2 |
| `py-tests-for` Which tests exercise a Python symbol | ◐ partial | coverage-py (read only) | 1 |
| `api-diff` Breaking changes in a Python package's public API between two versions | ✅ covered | griffe (read only) | 1 |
| `diff-review` What a diff or pull request touches, and what of it is untested | ✅ covered | gitnexus (probed) | 4 |
| `semantic-search` Find code by concept or natural-language description | ◐ partial | jevgrep (measured) | 7 |
| `context-pack` Token-budgeted repository context for an LLM | ✅ covered | jevgrep (measured) | 5 |
| `repo-overview` Architecture map: subsystems, layers, communities | ✅ covered | graphify (probed) | 7 |
| `dead-code` Unused Python code | ◐ partial | codegraph (probed) | 3 |
| `duplicates` Copy-paste and duplicated code | — not covered | fallow (read only) | 2 |
| `complexity` Complexity metrics (cyclomatic, size) and a threshold in CI | — not covered | radon (read only) | 3 |
| `security-patterns` Security patterns and leaked secrets | — not covered | codeql (read only) | 4 |
| `dataflow-taint` Data flow and taint: where an input value can reach | — not covered | codeql (read only) | 3 |
| `multi-lang-graph` Symbol and call graph for languages other than Python | — not covered | graphify (read only) | 14 |
| `frontend-dead-exports` Unused exports, files and dependencies in a JS/TS project | — not covered | fallow (read only) | 2 |
| `structural-search` Structural (AST) pattern search and rewrite | — not covered | cocoindex-code (probed) | 5 |
| `type-errors` Static type checking | — not covered | mypy (read only) | 2 |
| `db-query-count` How many database queries a code path makes | — not covered | pytest-django (read only) | 1 |

### Where a Python symbol is defined, and its dossier (`py-symbols`)

**codemap:** ✅ covered — MCP `search`, `query`, `resolve`, `source`; CLI `codemap query <symbol>`

**Other tools** (measured first; `read only` means the lab has not run it):
- **Graphify** — measured · v0.9.102 · checked 2026-11-04 · Apache-2.0 · ⚠ measured 0.9.102, latest 0.9.114
  `explain analyze_zones` refuses with exit 3 and both candidates; `explain MACDZoneAnalyzer` exit 0 at indicators/macd.py L48.
  vs codemap: Equal; exit codes for ambiguity are something codemap's CLI lacks.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/graphify.md#1-hands-on--the-r2-tree
- **Understand-Anything** — measured · main@f2d0164 · checked 2026-10-15 · MIT · ⚠ measured main@f2d0164, latest 2.9.8
  T1: the analyze_zones function and same-named method, and MACDZoneAnalyzer class, all found; definition counts match Python's ast exactly.
  vs codemap: Equal.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/understand-anything.md#1-hands-on--the-deterministic-layer-on-the-r2-tree
- **jevgrep (jg)** — measured · v0.8.0 · checked 2026-10-14 · MIT · ⚠ measured 0.8.0, latest 0.8.5
  T1 where analyze_zones is defined: both truth files at ranks 1 and 2 in all runs, 36 files returned (precision 0.06), ambiguity not mentioned.
  vs codemap: codemap returns exactly the two definitions and flags ambiguity.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/jevgrep.md#hands-on-measurements-target-bquant
- **OntoIndex** — measured · v2.2.0 · checked 2026-09-01 · AGPL-3.0-or-later · ⚠ measured 2.2.0, latest 3.2.3
  T1 analyze_zones: both definitions with explicit `status: ambiguous`; startLine is 0-based (121/717 for 122/718).
  vs codemap: Equal (both flag ambiguity); off-by-one lines.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/ontoindex.md#hands-on-measurements-target-bquant--cb89a24-the-r2-scope
- **CodeGraph (colbymchenry)** — measured · v1.6.0 · checked 2026-08-28 · MIT · ⚠ measured 1.6.0, latest 1.6.4
  T1 analyze_zones: both definitions at the same lines as codemap plus fuzzy neighbours and inline signature; 0.33 s. On 1.6.0 ambiguity was a ranked list, never flagged; 1.6.2 adds `ambiguous: true` on callers.
  vs codemap: Equal on correctness; codemap flags ambiguity explicitly; CodeGraph much faster.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/codegraph.md#hands-on-measurements-target-bquant--cb89a24-the-r2-scope
- **GitNexus** — measured · v1.6.9 · checked 2026-08-06 · PolyForm-Noncommercial-1.0.0 · ⚠ measured 1.6.9, latest 1.6.12
  T1 analyze_zones: `context` returned ambiguous with both definitions (pipeline.py and analyzer.py), lines off by one versus codemap.
  vs codemap: Equal: both surface the ambiguity.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/gitnexus.md#hands-on-measurements-target-bquant-r2-scope
- **grafema** — probed · v0.4.1 · checked 2026-11-02 · FSL-1.1-Apache-2.0
  T1: MACDZoneAnalyzer and the method UniversalZoneAnalyzer.analyze_zones found; the top-level analyze_zones missing because defect B dropped its file.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/grafema.md#1-hands-on--the-import-graph-on-the-r2-tree
- **cocoindex-code (ccc)** — probed · v0.2.41 · checked 2026-08-16 · Apache-2.0 · ⚠ measured 0.2.41, latest 0.2.43
  Semantic search for analyze_zones ranked the real definition (pipeline.py:718) only #5; the bundled tree-sitter `ccc grep 'def analyze_zones'` pinpointed both definitions exactly.
  vs codemap: Worse: codemap answers exactly and resolves re-exports.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/cocoindex-code.md#hands-on-measurements-target-bquant-r2-scope
- **graphlens-mcp** — probed · v0.4.0 · checked 2026-08-03 · MIT
  `search` finds the flagship plus content/markdown hits; ranking mediocre (a same-named method outranks the flagship function).
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/graphlens.md#quality-re-measured
- **jedi** — read only · checked 2026-08-02
  Static Python analysis: goto/inference, find-references, completion. codemap already depends on it for deep call resolution.
  vs codemap: codemap's own resolver.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/03_query_dataflow_engines.md#jedi--rope-python
- **universal-ctags** — read only · checked 2026-08-02 · GPL-2.0
  Single-pass, source-only tags file of definitions (name, file, address, kind, scope, roles); no cross-file resolution.
  vs codemap: codemap exports ctags (R1-C2); ctags is the definitions-only floor.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/02_codegraph_index_infra.md#universal-ctags

### Who calls a Python function, and what it calls (`py-callers`)

**codemap:** ✅ covered — MCP `callers`, `callees`; CLI `codemap query <symbol>` (both lists in the dossier)
  Calls through a string (a registry keyed by name, `run("name")`) are not resolved (R1-C107); dynamic dispatch is reported as partial, never as complete.

**Other tools** (measured first; `read only` means the lab has not run it):
- **Graphify** — measured · v0.9.102 · checked 2026-11-04 · Apache-2.0 · ⚠ measured 0.9.102, latest 0.9.114
  Files with calls/uses links to MACDZoneAnalyzer are exactly codemap's 23 caller files. Cross-file call pairs: 89.1 % agree with codemap, covering 59.8 % of codemap's pairs; builtin NotImplementedError bound to a same-named package class (fixed upstream in 0.9.103).
  vs codemap: Found calls through a re-exported class name that codemap's fast tier misses (R1-C75).
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/graphify.md#1-hands-on--the-r2-tree
- **jevgrep (jg)** — measured · v0.8.0 · checked 2026-10-14 · MIT · ⚠ measured 0.8.0, latest 0.8.5
  T2 'Which files call MACDZoneAnalyzer?': 26-27 files returned, recall 21/22 in all six runs, precision 0.78-0.81 (file level; no call edges).
  vs codemap: File-level only; codemap gives symbol-level edges.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/jevgrep.md#hands-on-measurements-target-bquant
- **rag_for_git (rag-reviewer)** — measured · v0.7.0 · checked 2026-09-12 · MIT
  Graph-level callers of MACDZoneAnalyzer: SCIP backend 60 (strict superset of codemap's 58, +2 intra-class calls); default tree-sitter backend 58 by count but 57 shared. On the whole scope the default backend has 9 779 CALLS vs 4 914 for SCIP; only 27.3 % of default edges are confirmed by SCIP, and the backend chosen (scip-python on PATH or not) never reaches the answer.
  vs codemap: Equal with SCIP; the silent tree-sitter fallback inflates edges on ambiguous names (.get, .info).
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/rag_for_git.md#hands-on-measurements-target-bquant
- **scip-python** — measured · v0.6.6 · checked 2026-09-12 · MIT · ⚠ measured 0.6.6, latest 0.6.8
  Measured indirectly: rag_for_git's SCIP backend (scip-python 0.6.6) gave 60 callers of MACDZoneAnalyzer, a strict superset of codemap's 58 (+2 intra-class calls); 4 914 CALLS edges on 207 files, 52 s build.
  vs codemap: Equal up to a definitional difference.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/rag_for_git.md#hands-on-measurements-target-bquant
- **OntoIndex** — measured · v2.2.0 · checked 2026-09-01 · AGPL-3.0-or-later · ⚠ measured 2.2.0, latest 3.2.3
  `context` silently caps incoming calls at 30 (30 of 57 for MACDZoneAnalyzer, 30 of 78 for get_sample_data) with `truncated: false`, and two builds of identical input return different 30-element subsets; exact under the cap (NotebookSimulator 28 = 28).
  vs codemap: Worse via context (silent cap); via impact the full set is returned (see py-impact).
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/ontoindex.md#t2-in-detail-a-completeness-field-that-says-false-while-dropping-27-of-57
- **CodeGraph (colbymchenry)** — measured · v1.6.0 · checked 2026-08-28 · MIT · ⚠ measured 1.6.0, latest 1.6.4
  T2 MACDZoneAnalyzer: 58 symbol-level callers vs codemap 57; codemap's set is a complete subset, the extra is an isinstance reference. On 1.6.0 the default --limit 20 silently truncated (all 58 symbol callers hidden behind 20 file rows); reported #1639, fixed in 1.6.1 (1.6.2 returns total and truncated).
  vs codemap: Equal on a unique name; on polymorphic names it binds by name (dict.get to MemoryCache.get, 6 of 6 sampled false on 1.6.0).
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/codegraph.md#hands-on-measurements-target-bquant--cb89a24-the-r2-scope
- **graphlens-mcp** — measured · v0.4.0 · checked 2026-08-03 · MIT
  With the bundled `ty` on PATH (resolver_status ok), `relations` gave 9 callers + 2 references for MACDZoneAnalyzer with tests auto-excluded; codemap's non-test count is 12, so the resolved graph roughly matches. Without `ty` on PATH it silently degrades to tree-sitter and returns nothing.
  vs codemap: Close on non-test callers; codemap returns tests+docs+code in one provenance-tagged answer, graphlens hides tests by default.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/graphlens.md#hands-on--impact-head-to-head-on-macdzoneanalyzer-identical-staging
- **Understand-Anything** — probed · main@f2d0164 · checked 2026-10-15 · MIT · ⚠ measured main@f2d0164, latest 2.9.8
  LLM layer pilot only (Sonnet 5.5, 9-file slice, $0.71, 108 s): the model wrote 0 calls, inherits or depends_on edges; codemap has 4 cross-file call pairs on the slice. Full tree not run.
  vs codemap: Worse: no call edges at all on the pilot.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/understand-anything.md#4-pilot--what-happened-reconciled
- **GitNexus** — probed · v1.6.9 · checked 2026-08-06 · PolyForm-Noncommercial-1.0.0 · ⚠ measured 1.6.9, latest 1.6.12
  T2 MACDZoneAnalyzer: `context` reports file-level import fan-in (22) plus 3 methods, not call sites; codemap's deep build gave 65 references by role (tests 53).
  vs codemap: Worse: file-import model, not symbol-level call sites.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/gitnexus.md#hands-on-measurements-target-bquant-r2-scope
- **code2flow** — read only · checked 2026-08-02 · MIT
  Heuristic name-matching call graphs for dynamic languages; Graphviz + JSON; community MCP wrapper exists.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/04_python_graph_arch_peers.md#code2flow
- **Doxygen** — read only · checked 2026-08-02 · GPL-2.0
  Call/caller/inheritance graphs via Graphviz; Python class-method calls are ignored in call graphs (issue #7254).
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/04_python_graph_arch_peers.md#doxygen-python-support
- **pyan3** — read only · checked 2026-08-02 · GPL-2.0
  Classic AST call/def-use graph (self-described superficial name heuristics) with defines vs uses edges; revived for Python 3.10-3.14.
  vs codemap: codemap's jedi-resolved calls are described as more accurate; not measured head to head.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/04_python_graph_arch_peers.md#pyan--pyan3
- **rope** — read only · checked 2026-08-02 · LGPL
  Python refactoring library (rename/move/extract) with find_occurrences cross-referencing.
  vs codemap: Candidate edit layer over codemap's impact; codemap is read-only.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/03_query_dataflow_engines.md#jedi--rope-python

**Tried and rejected:**
- **cocoindex-code (ccc)** — rejected · v0.2.41 · checked 2026-08-16 · Apache-2.0
  T2 not answerable: a query 'who calls MACDZoneAnalyzer' returns semantically similar docs/tests, not a caller list.
  vs codemap: codemap answers; ccc has no call graph.
  why not: vector index only, no call graph
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/cocoindex-code.md#hands-on-measurements-target-bquant-r2-scope
- **grafema** — rejected · v0.4.1 · checked 2026-11-02 · FSL-1.1-Apache-2.0
  With pipeline.py dropped, `who analyze_zones` attributes 109 callers marked [resolved] to the same-named method; no call to a class is ever resolved (60 MACDZoneAnalyzer calls all unresolved). Call file pairs agree with codemap 95.8 % but cover 35.9 % of codemap's pairs (second pass).
  vs codemap: Worse: confident wrong answer where codemap flags ambiguity.
  why not: namesake substitution without a flag; class calls never resolved
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/grafema.md#1-hands-on--the-import-graph-on-the-r2-tree
- **PyCG** — rejected · v0.0.8 · checked 2026-08-14 · Apache-2.0
  Does not run on Python 3.12: case-mismatched package, missing pkg_resources, and a fatal import-hook collision with the 3.12 stdlib even on a 3-line file. Its published ~99 % precision / ~70 % recall ceiling is cited, not reproduced.
  why not: structural incompatibility with the Python 3.12 import machinery; project dormant
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/pycg.md#what-happened--three-layered-breakages-on-python-312

### What a change to a Python symbol touches (blast radius) (`py-impact`)

**codemap:** ✅ covered — MCP `impact`; CLI `codemap report impact --symbol <symbol> [--depth N]`

**Other tools** (measured first; `read only` means the lab has not run it):
- **jevgrep (jg)** — measured · v0.8.0 · checked 2026-10-14 · MIT · ⚠ measured 0.8.0, latest 0.8.5
  T3 blast radius: 48 files, recall 25/29 (tests 19/19, scripts 2/2, examples 1/1, docs 3/7), precision 0.52.
  vs codemap: Misses documents; no distance or role structure.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/jevgrep.md#hands-on-measurements-target-bquant
- **OntoIndex** — measured · v2.2.0 · checked 2026-09-01 · AGPL-3.0-or-later · ⚠ measured 2.2.0, latest 3.2.3
  `impact --include-tests` depth-1 CALLS set is set-identical to codemap callers: 57 = 57 (MACDZoneAnalyzer) and 78 = 78 (get_sample_data); re-verified on three codemap deep builds 2026-09-02. Defaults exclude tests (55 vs 149 impacted) and order is unstable across runs.
  vs codemap: Equal on the set; tests excluded by default and non-diffable order.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/ontoindex.md#t3-in-detail-two-independent-graphs-the-same-57
- **graphlens-mcp** — measured · v0.4.0 · checked 2026-08-03 · MIT
  Impact split across two tools: `relations` (resolved code edges) and `search exhaustive` (44 files incl. 5 generated docs/_build copies); codemap impact 31 refs (core 2, docs 7, examples 1, scripts 2, tests 19) on the same staging.
  vs codemap: codemap: one call, provenance-tagged. graphlens: resolves into dependencies (codemap does not), but 12x index time and SQLite artifact.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/graphlens.md#hands-on--impact-head-to-head-on-macdzoneanalyzer-identical-staging
- **CodeGraph (colbymchenry)** — probed · v1.6.0 · checked 2026-08-28 · MIT · ⚠ measured 1.6.0, latest 1.6.4
  T3 MACDZoneAnalyzer: 89 affected / 146 edges at depth 2, flat and untagged; codemap 69 references tagged by type, root and distance. Byte-identical across two builds; not scored against a truth set.
  vs codemap: More reach, less structure (no calls/references or tests/docs split).
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/codegraph.md#hands-on-measurements-target-bquant--cb89a24-the-r2-scope
- **GitNexus** — probed · v1.6.9 · checked 2026-08-06 · PolyForm-Noncommercial-1.0.0 · ⚠ measured 1.6.9, latest 1.6.12
  T3 MACDZoneAnalyzer: transitive upstream import closure, 48 impacted (direct 5, by depth 5/15/28), risk MEDIUM, byte-identical across two clean stagings; judged correct in its own model, not scored against a truth set.
  vs codemap: Better: transitive depth and risk band. Worse: file-level and provenance-blind (no tests/docs split).
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/gitnexus.md#hands-on-measurements-target-bquant-r2-scope
- **Graphify** — read only · v0.9.102 · checked 2026-11-04 · Apache-2.0
  `affected` exists; not measured.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/graphify.md#coverage-vs-codemap

**Tried and rejected:**
- **cocoindex-code (ccc)** — rejected · v0.2.41 · checked 2026-08-16 · Apache-2.0
  T3 not answerable: no graph, so no blast radius.
  vs codemap: codemap answers.
  why not: no symbol or call graph
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/cocoindex-code.md#hands-on-measurements-target-bquant-r2-scope
- **grafema** — rejected · v0.4.1 · checked 2026-11-02 · FSL-1.1-Apache-2.0
  `impact analyze_zones` reports 93 direct callers, 0 transitive, all against the namesake method; direct-only on both probe symbols.
  why not: misattributed and direct-only
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/grafema.md#1-hands-on--the-import-graph-on-the-r2-tree
- **rag_for_git (rag-reviewer)** — rejected · v0.7.0 · checked 2026-09-12 · MIT
  Product impact is `get_impact(repo, pr)`, diff-scoped; a symbol-scoped blast radius exists only in the library (`expand(hops)`) and is not exposed.
  vs codemap: codemap answers symbol-scoped, role-tagged impact (69 refs on the same tree).
  why not: no symbol-scoped impact in the product
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/rag_for_git.md#hands-on-measurements-target-bquant

### Python import graph and import cycles (`py-imports`)

**codemap:** ✅ covered — CLI `codemap report dependencies`; MCP `report kind=dependencies`, `architecture`

**Other tools** (measured first; `read only` means the lab has not run it):
- **Graphify** — measured · v0.9.102 · checked 2026-11-04 · Apache-2.0 · ⚠ measured 0.9.102, latest 0.9.114
  241 module dependencies, 240 true (precision 99.6 %), recall 240/266 = 90.2 % (function-scope 0/25); its own GRAPH_REPORT lists 2 of 45 cycles because function-local imports make no module dependency; graph.json byte-identical over 3 runs, 14 s each.
  vs codemap: Close on module-level edges; cannot serve as a cycle gate where lazy imports break cycles (codemap: 45/45).
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/graphify.md#1-hands-on--the-r2-tree
- **grimp** — measured · v3.18 · checked 2026-11-04 · BSD-2-Clause · ⚠ measured 3.18, latest 3.20
  Import graph of bquant on the R2 tree: 89/89 modules, 266/266 edges (precision 100 %, recall 100 %; module 240, function 25, type_checking 1), 45/45 cycles, 0 false; three builds identical, 0.11-0.14 s. Measured as the engine under import-linter 2.15.
  vs codemap: Equal on this tree (set-identical to codemap's import edges), much faster; library only, no symbol graph.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/import-linter.md#1-hands-on
- **CodeGraph (colbymchenry)** — measured · v1.6.2 · checked 2026-10-15 · MIT · ⚠ measured 1.6.2, latest 1.6.4
  Library-only findCircularDependencies(): 1.6.0 reported 136 cycles, 13 of the 45 real (precision 9.6 %, recall 28.9 %); 1.6.2 reports 25, 16 real (64 % / 35.6 %). Derived from name-resolved call edges, not import statements; not exposed on CLI/MCP.
  vs codemap: Worse: codemap reports all 45 (eager vs lazy split) and exposes it on CLI/MCP.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/codegraph.md#re-measured-on-162-2026-10-15
- **Understand-Anything** — measured · main@f2d0164 · checked 2026-10-15 · MIT · ⚠ measured main@f2d0164, latest 2.9.8
  Deterministic import map: 216 edges, 215 true (precision 99.5 %), recall 215/266 (module 215/240, function 0/25, type_checking 0/1), 0 of 45 cycles; byte-identical over 4 runs. A patched main (upstream #692) recovers 256/266 and 13/45 cycles; the `from .. import Name` miss (#727) was fixed upstream 2026-10-22, not re-measured.
  vs codemap: Worse: reads only top-level imports, so reports an acyclic graph where codemap finds 45 cycles.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/understand-anything.md#1-hands-on--the-deterministic-layer-on-the-r2-tree
- **OntoIndex** — probed · v2.2.0 · checked 2026-09-01 · AGPL-3.0-or-later · ⚠ measured 2.2.0, latest 3.2.3
  `audit` (needs git) reports 'Import Cycles (6)' mixing markdown-link rings, call cycles and basename-only paths; not scored against the 45-cycle truth.
  vs codemap: Worse: codemap separates hard and lazily-closed import cycles with full module ids.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/ontoindex.md#t5-in-detail-the-right-sections-and-what-is-inside-them
- **GitNexus** — probed · v1.6.9 · checked 2026-08-06 · PolyForm-Noncommercial-1.0.0 · ⚠ measured 1.6.9, latest 1.6.12
  `check --cycles` reported 3 file-level import cycles; not scored against the later 45-cycle truth set.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/gitnexus.md#hands-on-measurements-target-bquant-r2-scope
- **pydeps** — read only · checked 2026-08-02 · BSD-2-Clause
  Module dependency graphs from import opcodes in compiled bytecode; Graphviz output with cycle boxes plus --show-deps JSON.
  vs codemap: codemap's AST import graph needs no bytecode compile.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/04_python_graph_arch_peers.md#pydeps

**Tried and rejected:**
- **grafema** — rejected · v0.4.1 · checked 2026-11-02 · FSL-1.1-Apache-2.0
  164 module edges, 163 true (precision 99.4 %), recall 163/266 = 61 %, 8 of 45 cycles; deterministic over 3 runs. Defect A (relative imports in __init__.py resolve one package too high, 85 edges), defect B (any f-string with !r/!s/!a drops the file, exit 0), and the quickstart analyzes 0 Python modules at exit 0. Filed upstream #480-#482.
  vs codemap: Worse: codemap reads all 266 edges and 45 cycles.
  why not: Python product not usable as measured on 0.4.1: integration defects hide 37 of 45 cycles without failing the run
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/grafema.md#1-hands-on--the-import-graph-on-the-r2-tree

### An architecture contract on imports, enforced in CI (`import-gate`)

**codemap:** ✅ covered — `[architecture]` in codemap.toml; CLI `codemap check --require-contract`; MCP `check`

**Other tools** (measured first; `read only` means the lab has not run it):
- **import-linter** — measured · v2.15 · checked 2026-11-04 · BSD-2-Clause · ⚠ measured 2.15, latest 2.17
  The graph under the gate (grimp) equals the lab's truth: 266/266 import edges, 45/45 cycles, 0.11 s. 19 gate probes on a 3-layer fixture: lazy, TYPE_CHECKING, `import a.b.c` and `__init__` violations all caught; on bquant's translated contract it agrees with `codemap check` on all four trees (as-is pass; module-level, function-local and TYPE_CHECKING violations fail). On 2.15 three silent passes: unknown option ignored, misspelled forbidden module dropped (fixed on main), zero contracts pass; the first and third were fixed in 2.16 (verified 2026-11-09).
  vs codemap: Better: indirect (chain) semantics, `protected` contract, mature. Worse: cycles only via acyclic_siblings; codemap names the single offending edge and has separate eager/lazy/type-only cycle rules.
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/import-linter.md#1-hands-on
- **ArchUnitPython** — read only · checked 2026-08-02
  Architecture rules as pytest: have_no_cycles(), layer direction, naming, file size.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/05_curated_sources.md#4-architecture-as-tests-reinforces-r1-c3

**Tried and rejected:**
- **grafema** — rejected · v0.4.1 · checked 2026-11-03 · FSL-1.1-Apache-2.0
  Datalog guarantees work as a mechanism (recursive rule found exactly the 11 modules on cycles; ordinary-module violation caught), but the first `check` on a fresh graph evaluates nothing at exit 0, a predicate typo passes, an edited rule keeps its old body, an __init__ violation is invisible, and importing costs about 300 s per rule. Filed #483-#484.
  vs codemap: Worse: codemap check catches the __init__ case.
  why not: silent vacuous passes on 0.4.1
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/grafema.md#66-second-pass-reconciled-2026-11-0203

### Which tests exercise a Python symbol (`py-tests-for`)

**codemap:** ◐ partial — MCP `tests`, `covers`; CLI `codemap tests <symbol>` — on a repo-scoped graph (`build --consumer tests --mode full`)
  Static reach, not runtime coverage; tests that reach code through dispatch by name are missed (R1-C107). For line coverage use coverage.py.

**Other tools** (measured first; `read only` means the lab has not run it):
- **coverage.py** — read only · Apache-2.0
  Line and branch coverage measured while the tests run; with dynamic contexts (`--context=test`) it records which test executed each line. Runtime truth, where codemap gives static reach.
  vs codemap: Complements codemap: needs a test run; sees dispatch by name that a static graph cannot.
  check it first: not scored by the lab: check it on a question whose answer you know first
  https://github.com/nedbat/coveragepy

### Breaking changes in a Python package's public API between two versions (`api-diff`)

**codemap:** ✅ covered — CLI `codemap diff old.json new.json`; MCP `diff`

**Other tools** (measured first; `read only` means the lab has not run it):
- **griffe** — read only · checked 2026-08-02 · ISC
  Static API model with version-to-version API-breaking-change detection; codemap's own extractor.
  vs codemap: codemap ships its own `diff` (R1-C5) on top of griffe.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/04_python_graph_arch_peers.md#pydoctor--griffe--sphinx-autodoc

### What a diff or pull request touches, and what of it is untested (`diff-review`)

**codemap:** ✅ covered — CLI `codemap review < diff`; MCP `review`

**Other tools** (measured first; `read only` means the lab has not run it):
- **GitNexus** — probed · v1.6.9 · checked 2026-08-06 · PolyForm-Noncommercial-1.0.0 · ⚠ measured 1.6.9, latest 1.6.12
  `detect-changes` (git diff to symbols and flows, the analog of codemap review) requires git and errored on the git-less staging; not evaluated.
  vs codemap: codemap review works on any directory; GitNexus needs .git.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/gitnexus.md#hands-on-measurements-target-bquant-r2-scope
- **Understand-Anything** — read only · main@f2d0164 · checked 2026-10-15 · MIT
  `/understand-diff` over the LLM graph exists; not measured.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/understand-anything.md#coverage-vs-codemap
- **rag_for_git (rag-reviewer)** — read only · v0.7.0 · checked 2026-09-12 · MIT
  An AI pull-request reviewer: every graph op is keyed by (repo, pr); get_impact names callers outside the diff of changed signatures. Stages B/C (Neo4j, ParadeDB, paid Voyage key) not run, so the review product is unmeasured.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/rag_for_git.md#what-it-is
- **OntoIndex** — read only · v2.2.0 · checked 2026-09-01 · AGPL-3.0-or-later
  Ships `review diff` (requires a git repository); read, not exercised.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/ontoindex.md#what-it-is

### Find code by concept or natural-language description (`semantic-search`)

**codemap:** ◐ partial — MCP `semantic_search` through an opt-in adapter (cocoindex-code), resolved back to exact symbols
  Needs the adapter installed and indexed; without it the answer is empty and says so.

**Other tools** (measured first; `read only` means the lab has not run it):
- **jevgrep (jg)** — measured · v0.8.0 · checked 2026-10-14 · MIT · ⚠ measured 0.8.0, latest 0.8.5
  Natural-language questions answered by a typed classifier walk (no embeddings, no index); scored on the same T1-T4 file sets as above (T4 recall 26/49, precision 0.50).
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/jevgrep.md#hands-on-measurements-target-bquant
- **cocoindex-code (ccc)** — probed · v0.2.41 · checked 2026-08-16 · Apache-2.0 · ⚠ measured 0.2.41, latest 0.2.43
  Concept query 'detect swing high/low pivot points within a zone' returned strategies/swing/pivot_points.py as top hit (score 0.72) with no name knowledge; only a handful of queries spot-checked, no labelled query set. Index: 280 files to 6403 chunks, cold CPU build 559 s on 4 cores, incremental re-index of unchanged content about 1 s; GPU follow-up 48 s vs 216 s CPU on the same box.
  vs codemap: Card: does concept search codemap (as measured then) could not; but its artifact is a binary LMDB/SQLite store, not a diffable graph.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/cocoindex-code.md#hands-on-measurements-target-bquant-r2-scope
- **GitNexus** — probed · v1.6.9 · checked 2026-08-16 · PolyForm-Noncommercial-1.0.0 · ⚠ measured 1.6.9, latest 1.6.12
  On the full bquant repo (13 054 nodes, 4 516 embedding chunks) a concept query returned relevant MACD-zone flows by inspection; not measured against a labelled set. Full CPU embedding pass about 18 min on 4 cores; ANN index needs a one-time network install.
  vs codemap: Card (2026-08): codemap had no fuzzy layer; GitNexus fuses BM25 + embeddings (RRF) with the graph.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/gitnexus.md#follow-up-run-as-an-end-user-dev-tool-on-full-bquant-2026-08-16
- **rag_for_git (rag-reviewer)** — read only · v0.7.0 · checked 2026-09-12 · MIT
  Hybrid retrieval (ParadeDB BM25 + pgvector, RRF) with Voyage embeddings (hard dependency, paid key); entirely unmeasured.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/rag_for_git.md#what-it-is
- **OntoIndex** — read only · v2.2.0 · checked 2026-09-01 · AGPL-3.0-or-later
  BM25 plus optional local embeddings with RRF; embeddings are off by default and were not built, so retrieval quality is untested.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/ontoindex.md#what-it-is
- **graphlens-mcp** — read only · v0.4.0 · checked 2026-08-03 · MIT
  `search` advertises meaning-based ranking, but the embedding model was unreachable (no egress), so only name/content search ran.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/graphlens.md#mcp-surface--3-general-verbs-richer-than-the-first-pass-implied
- **Continue (@codebase)** — read only · checked 2026-08-02 · Apache-2.0
  Hybrid local embeddings + keyword FTS + tree-sitter with optional LLM re-rank; @codebase deprecated for agentic retrieval.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/01_ai_context_repomap.md#continuedev--codebase-indexing--codebase

### Token-budgeted repository context for an LLM (`context-pack`)

**codemap:** ✅ covered — MCP `pack` (budget, seeds); CLI `codemap pack`

**Other tools** (measured first; `read only` means the lab has not run it):
- **jevgrep (jg)** — measured · v0.8.0 · checked 2026-10-14 · MIT · ⚠ measured 0.8.0, latest 0.8.5
  With real Jev (OpenRouter typesafe/jev-1.13), file-level recall against codemap truth: code that uses a symbol found almost completely, documents poorly (docs 3/7 on T3, 2/24 on T4); $0.026-0.15 per cold search, 18-75 s; the 17-search campaign cost $1.14. Not byte-stable even serialised; never states which eligible files were not sent.
  vs codemap: Closest competitor to codemap pack: no index or build, 7.3 MB install, but needs a paid key and uploads source; no structure (T3-T5 absent).
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/jevgrep.md#hands-on-measurements-target-bquant
- **CodeGraph (colbymchenry)** — read only · v1.6.0 · checked 2026-08-28 · MIT
  Default MCP surface is one tool, codegraph_explore (verbatim source, call paths, blast radius in one call); README reports 80 % more resident context but fewer tool calls/tokens. Headline benchmark not reproduced; MCP path not exercised.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/codegraph.md#what-it-is
- **aider repo-map** — read only · checked 2026-08-02 · Apache-2.0
  tree-sitter def/ref graph ranked by personalized PageRank, rendered as a token-budgeted text map (binary search into --map-tokens, ~1k default); graph is transient, internal to the aider chat loop.
  vs codemap: Source of codemap's pack idea (R1-C6); codemap persists a diffable graph and exposes query verbs.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/01_ai_context_repomap.md#aider--repo-map-the-closest-peer
- **gpt-repository-loader** — read only · checked 2026-08-02 · MIT
  Flattens a git repo into one prompt blob; dormant; the naive floor.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/01_ai_context_repomap.md#repomix--gpt-repository-loader--llamaindex-code-loaders
- **Repomix** — read only · checked 2026-08-02 · MIT
  Concatenates a repo into one AI-friendly pack with token counting, gitignore/glob and --compress (tree-sitter signature stripping); deterministic formatter with an MCP server.
  vs codemap: No structural intelligence; complementary output form.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/01_ai_context_repomap.md#repomix--gpt-repository-loader--llamaindex-code-loaders

### Architecture map: subsystems, layers, communities (`repo-overview`)

**codemap:** ✅ covered — CLI `codemap report architecture`; MCP `architecture`, `communities`, `flows`

**Other tools** (measured first; `read only` means the lab has not run it):
- **Graphify** — probed · v0.9.102 · checked 2026-11-04 · Apache-2.0 · ⚠ measured 0.9.102, latest 0.9.114
  Writes GRAPH_REPORT.md with god nodes and communities; community naming calls the `claude` CLI on the user's subscription when no API key is set (announced, disabled with GRAPHIFY_BACKEND=none). Quality not scored.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/graphify.md#1-hands-on--the-r2-tree
- **Understand-Anything** — probed · main@f2d0164 · checked 2026-10-15 · MIT · ⚠ measured main@f2d0164, latest 2.9.8
  Pilot produced summaries, 4 layers and a 7-step tour; the orchestrator skipped three phases' agents and wrote some summaries from names only. Full run extrapolated to at least about $9-12 on Sonnet 5.5; summary quality not scored.
  vs codemap: Different product: explains a codebase (tours, summaries) rather than answering structural queries.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/understand-anything.md#4-pilot--what-happened-reconciled
- **OntoIndex** — probed · v2.2.0 · checked 2026-09-01 · AGPL-3.0-or-later · ⚠ measured 2.2.0, latest 3.2.3
  Index yields 254 Leiden clusters and 300 flows, but `report hubs` and `report surprising-connections` print 'no hubs found' at exit 0 on a 10 745-node graph because the vendored Cypher parser rejects label negation.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/ontoindex.md#the-bug-worth-reporting-upstream
- **GitNexus** — probed · v1.6.9 · checked 2026-08-06 · PolyForm-Noncommercial-1.0.0 · ⚠ measured 1.6.9, latest 1.6.12
  Index on the R2 scope produced 276 Leiden clusters and 294 process flows; cluster count stable across A/B, membership not verified; `wiki` (needs an LLM key) not run.
  vs codemap: Has communities/flows codemap lacked at the time; lacks codemap's layer/coupling metrics.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/gitnexus.md#hands-on-measurements-target-bquant-r2-scope
- **CodeWiki (Google)** — read only · checked 2026-08-02 · proprietary
  Living wiki auto-updated per commit with Gemini chat and class/sequence diagrams.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/05_curated_sources.md#2-living-docs-from-code-new-capability-signal
- **Tutorial-Codebase-Knowledge** — read only · checked 2026-08-02
  Walks a repo and generates a tutorial with diagrams via the PocketFlow engine.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/05_curated_sources.md#2-living-docs-from-code-new-capability-signal
- **roam-code** — read only · Apache-2.0
  Per its package description: local codebase intelligence for AI coding agents, with a structural repo map, change-safety gates and an MCP interface; says local analysis needs no API keys and sends no source code.
  check it first: not scored by the lab: check it on a question whose answer you know first
  https://github.com/Cranot/roam-code

### Unused Python code (`dead-code`)

**codemap:** ◐ partial — CLI `codemap report dead-code`; MCP `report kind=dead-code`
  Candidates, not verdicts: functions registered by a decorator and called by name look dead (R1-C106).

**Other tools** (measured first; `read only` means the lab has not run it):
- **CodeGraph (colbymchenry)** — probed · v1.6.0 · checked 2026-08-28 · MIT · ⚠ measured 1.6.0, latest 1.6.4
  Library-only findDeadCode() returned 1 207 unreferenced symbols as one flat list; precision not measured.
  vs codemap: codemap bands candidates by confidence with whitelist and blind-spot notice.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/codegraph.md#the-same-question-asked-of-both--function-local-imports
- **OntoIndex** — read only · v2.2.0 · checked 2026-09-01 · AGPL-3.0-or-later
  `audit` includes a Dead Code section; its contents were not evaluated.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/ontoindex.md#what-it-is
- **vulture** — read only · checked 2026-08-02 · MIT
  AST defined-vs-used names with confidence 60-100 % and whitelist; high false-positive rate on dynamic code (~260 on Flask, as reported).
  vs codemap: codemap's provenance-aware dead-code adds cross-root context; not measured head to head.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/04_python_graph_arch_peers.md#vulture--dead-code-detection

### Copy-paste and duplicated code (`duplicates`)

**codemap:** — not covered

**Other tools** (measured first; `read only` means the lab has not run it):
- **fallow** — read only · MIT
  Per its README: duplication detection for TypeScript and JavaScript, also CSS and Vue, Svelte and Astro components.
  check it first: not scored by the lab: check it on a question whose answer you know first
  https://github.com/fallow-rs/fallow
- **jscpd** — read only · MIT
  Copy/paste (clone) detector over token streams for many languages.
  check it first: not scored by the lab: check it on a question whose answer you know first
  https://github.com/kucherenko/jscpd

### Complexity metrics (cyclomatic, size) and a threshold in CI (`complexity`)

**codemap:** — not covered

**Other tools** (measured first; `read only` means the lab has not run it):
- **radon** — read only · checked 2026-08-02 · MIT
  Per-block cyclomatic complexity, Halstead, Maintainability Index and raw SLOC from the AST.
  vs codemap: codemap added complexity to hotspots (R1-C4).
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/04_python_graph_arch_peers.md#radon--wily--complexity-metrics
- **wily** — read only · checked 2026-08-02 · Apache-2.0
  Tracks radon-style metrics across git history.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/04_python_graph_arch_peers.md#radon--wily--complexity-metrics
- **lizard** — read only · MIT
  Cyclomatic complexity and function-length analyzer across many languages.
  check it first: not scored by the lab: check it on a question whose answer you know first
  https://github.com/terryyin/lizard

### Security patterns and leaked secrets (`security-patterns`)

**codemap:** — not covered

**Other tools** (measured first; `read only` means the lab has not run it):
- **CodeQL** — read only · checked 2026-08-02 · MIT (queries/libraries); CLI/engine proprietary
  Native CI via GitHub code scanning (described only).
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/03_query_dataflow_engines.md#codeql-github
- **Repomix** — read only · checked 2026-08-02 · MIT
  Includes a security scan of the packed content (described only).
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/01_ai_context_repomap.md#repomix--gpt-repository-loader--llamaindex-code-loaders
- **Semgrep** — read only · checked 2026-08-02 · LGPL-2.1 (engine)
  YAML rules with code-like patterns and metavariables over a per-language AST; source-only, deterministic. A Dec 2024 relicensing put many rules under a restrictive license.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/03_query_dataflow_engines.md#semgrep
- **Bandit** — read only · Apache-2.0
  AST-based security linter for common Python issues (e.g. eval, hardcoded passwords, unsafe subprocess).
  check it first: not scored by the lab: check it on a question whose answer you know first
  https://github.com/PyCQA/bandit

### Data flow and taint: where an input value can reach (`dataflow-taint`)

**codemap:** — not covered

**Other tools** (measured first; `read only` means the lab has not run it):
- **CodeQL** — read only · checked 2026-08-02 · MIT (queries/libraries); CLI/engine proprietary
  Relational CodeQL database queried in QL (Datalog); mature local + global data flow and taint tracking; build observation needed for compiled languages, Python/JS build-free; private-repo use needs GHAS.
  vs codemap: codemap has only a columns data-flow slice; CodeQL is the reference for taint.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/03_query_dataflow_engines.md#codeql-github
- **OpenGrep** — read only · checked 2026-08-02 · LGPL-2.1
  Community fork of Semgrep (Jan 2025) restoring cross-function taint across about 12 languages.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/03_query_dataflow_engines.md#semgrep
- **Semgrep** — read only · checked 2026-08-02 · LGPL-2.1 (engine)
  `mode: taint` (source/sink/sanitizer/propagator); intra-procedural free, inter-procedural/inter-file is Pro.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/03_query_dataflow_engines.md#semgrep

**Tried and rejected:**
- **grafema** — rejected · v0.4.1 · checked 2026-11-03 · FSL-1.1-Apache-2.0
  `wtf` answers 'no reachable nodes' for 3 of 3 Python questions and a Python toy; the same toy in JS returns 4- and 7-node chains (a control, not a JS measurement). Filed #486.
  vs codemap: codemap offers no data flow beyond columns.
  why not: Python backward data flow returns nothing on 0.4.1
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/grafema.md#66-second-pass-reconciled-2026-11-0203

### Symbol and call graph for languages other than Python (`multi-lang-graph`)

**codemap:** — not covered

**Other tools** (measured first; `read only` means the lab has not run it):
- **Graphify** — read only · v0.9.102 · checked 2026-11-04 · Apache-2.0
  30 tree-sitter grammars as hard dependencies (about 40 languages with extras); only Python measured.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/graphify.md#identity
- **grafema** — read only · v0.4.1 · checked 2026-11-02 · FSL-1.1-Apache-2.0
  JS/TS is the primary language (Python listed as Beta); JS/TS not measured beyond a data-flow toy.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/grafema.md#what-it-is
- **jevgrep (jg)** — read only · v0.8.0 · checked 2026-10-14 · MIT
  Local declaration parsing for Python, Go, Rust (wasm grammars) and TS/JS (tsc); no graph. Only Python measured.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/jevgrep.md#what-it-is
- **OntoIndex** — read only · v2.2.0 · checked 2026-09-01 · AGPL-3.0-or-later
  14 languages via tree-sitter; Python only was run.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/ontoindex.md#identity
- **CodeGraph (colbymchenry)** — read only · v1.6.0 · checked 2026-08-28 · MIT
  Rust kernel with 20 tree-sitter grammars; only Python measured, byte-identical-to-reference claim for other languages not checked.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/codegraph.md#identity
- **GitNexus** — read only · v1.6.9 · checked 2026-08-06 · PolyForm-Noncommercial-1.0.0
  14 languages via tree-sitter; only Python was measured.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/gitnexus.md#what-it-is
- **graphlens-mcp** — read only · v0.4.0 · checked 2026-08-03 · MIT
  Tree-sitter plus per-language LSP resolvers for Python, TypeScript, Go, Rust, PHP; only Python tested.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/graphlens.md#identity
- **code2flow** — read only · checked 2026-08-02 · MIT
  Same heuristic call graph for JS, Ruby, PHP.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/04_python_graph_arch_peers.md#code2flow
- **Glean (Meta)** — read only · checked 2026-08-02 · BSD-style
  Fact database of defs/refs/types/calls/imports queried with Angle (Datalog-style); ingests SCIP/LSIF; open-sourced Dec 2024.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/02_codegraph_index_infra.md#glean-meta
- **Kythe** — read only · checked 2026-08-02 · Apache-2.0
  Language-agnostic node/fact/edge graph with VName identity, produced by compiler-integrated extractors; perpetually pre-1.0.
  vs codemap: Schema teacher; too build-coupled for source-only use.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/02_codegraph_index_infra.md#kythe-google
- **SCIP (format)** — read only · checked 2026-08-02 · Apache-2.0
  Language-agnostic Protobuf interchange format with structured symbol strings; produced by per-language, mostly type-checker-integrated indexers (scip-python builds on Pyright); open governance since March 2026.
  vs codemap: codemap exports SCIP (R1-C1); compiler-backed indexers are more precise but build-coupled.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/02_codegraph_index_infra.md#scip--sourcegraph-code-intelligence-protocol
- **Sourcegraph (incl. Cody)** — read only · checked 2026-08-02 · proprietary (open components)
  Code search and navigation in two tiers: search-based (tree-sitter heuristics) and precise (uploaded SCIP indexes). Cody is Enterprise-only since July 2025.
  vs codemap: Consumer of a codemap SCIP export.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/02_codegraph_index_infra.md#sourcegraph-the-product
- **Stack Graphs** — read only · checked 2026-08-02 · MIT/Apache-2.0
  Source-only name-resolution graph from tree-sitter plus per-language .tsg rules; repository archived 2025-09-09.
  vs codemap: Cautionary: per-language binding DSLs did not scale.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/02_codegraph_index_infra.md#stack-graphs-github
- **roam-code** — read only · Apache-2.0
  Per its README: a local SQLite code graph over 28 languages (Python, JavaScript, TypeScript, Go, Rust, Java, C#, PHP, Ruby and more); extraction depth varies by language. Not run by the lab.
  check it first: not scored by the lab: check it on a question whose answer you know first
  https://github.com/Cranot/roam-code

### Unused exports, files and dependencies in a JS/TS project (`frontend-dead-exports`)

**codemap:** — not covered

**Other tools** (measured first; `read only` means the lab has not run it):
- **fallow** — read only · MIT
  Per its README: Rust analyzer for TypeScript and JavaScript that builds one repository graph and reports unused code, circular dependencies and architecture-boundary violations, with an `audit` command that fails only on findings a change introduces.
  check it first: not scored by the lab: check it on a question whose answer you know first
  https://github.com/fallow-rs/fallow
- **Knip** — read only · ISC
  Finds unused files, exports and dependencies in JS/TS projects.
  check it first: not scored by the lab: check it on a question whose answer you know first
  https://github.com/webpro-nl/knip

### Structural (AST) pattern search and rewrite (`structural-search`)

**codemap:** — not covered

**Other tools** (measured first; `read only` means the lab has not run it):
- **cocoindex-code (ccc)** — probed · v0.2.41 · checked 2026-08-16 · Apache-2.0 · ⚠ measured 0.2.41, latest 0.2.43
  `ccc grep` is index-free tree-sitter structural search by example; on T1 it found pipeline.py:718 and analyzer.py:122 exactly. Only this one lookup was exercised.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/tools/cocoindex-code.md#hands-on-measurements-target-bquant-r2-scope
- **ast-grep (sg)** — read only · checked 2026-08-02 · MIT
  Rust CLI for structural search, lint and rewrite with patterns written as code over tree-sitter CSTs; Python/JS bindings, LSP and MCP server; no data flow or name resolution.
  vs codemap: Syntactic only; codemap gives a resolved semantic graph but no pattern search.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/03_query_dataflow_engines.md#ast-grep-sg
- **Comby** — read only · checked 2026-08-02 · Apache-2.0
  Language-agnostic structural search and replace with hole templates; no semantic model.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/03_query_dataflow_engines.md#comby
- **Semgrep** — read only · checked 2026-08-02 · LGPL-2.1 (engine)
  Pattern language that looks like target code.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/03_query_dataflow_engines.md#semgrep
- **tree-sitter** — read only · checked 2026-08-02 · MIT
  Incremental parsing library with an S-expression query interface; syntax only, single-file, no cross-file resolution. Substrate under most tools in this matrix.
  vs codemap: Candidate multi-language backend for codemap; gives breadth, not semantics.
  check it first: not scored by the lab: check it on a question whose answer you know first
  evidence: https://github.com/kogriv/codemap/blob/main/research/03_query_dataflow_engines.md#tree-sitter

### Static type checking (`type-errors`)

**codemap:** — not covered

**Other tools** (measured first; `read only` means the lab has not run it):
- **mypy** — read only · MIT
  Static type checker for annotated Python.
  check it first: not scored by the lab: check it on a question whose answer you know first
  https://github.com/python/mypy
- **Pyright** — read only · MIT
  Static type checker and language server for Python; scip-python is built on it (research/02, passing mention).
  check it first: not scored by the lab: check it on a question whose answer you know first
  https://github.com/microsoft/pyright

### How many database queries a code path makes (`db-query-count`)

**codemap:** — not covered

No static tool sees this: the number of queries depends on the data and the ORM at run time. Use query-counting tests on the paths that matter (Django's `assertNumQueries`, pytest-django's `django_assert_num_queries`, or a counter on the connection).

**Other tools** (measured first; `read only` means the lab has not run it):
- **pytest-django** — read only · BSD-3-Clause
  The `django_assert_num_queries` and `django_assert_max_num_queries` fixtures fail a test when a code path makes more queries than allowed; Django's own `assertNumQueries` does the same in TestCase.
  check it first: not scored by the lab: check it on a question whose answer you know first
  https://github.com/pytest-dev/pytest-django

## Tools

| tool | license | languages | claims | card |
|---|---|---|---|---|
| [aider repo-map](https://github.com/Aider-AI/aider) | Apache-2.0 | multi (tree-sitter) | context-pack (read only) | — |
| [ArchUnitPython](https://github.com/LukasNiessen/ArchUnitPython) | ? | python | import-gate (read only) | — |
| [ast-grep (sg)](https://github.com/ast-grep/ast-grep) | MIT | multi (tree-sitter) | structural-search (read only) | — |
| [Bandit](https://github.com/PyCQA/bandit) | Apache-2.0 | python | security-patterns (read only) | — |
| [cocoindex-code (ccc)](https://github.com/cocoindex-io/cocoindex-code) | Apache-2.0 | multi (tree-sitter) | py-symbols (probed), semantic-search (probed), structural-search (probed), py-callers (rejected), py-impact (rejected) | [card](../research/tools/cocoindex-code.md) |
| [code2flow](https://github.com/scottrogowski/code2flow) | MIT | python, javascript, ruby, php | multi-lang-graph (read only), py-callers (read only) | — |
| [CodeGraph (colbymchenry)](https://github.com/colbymchenry/codegraph) | MIT | python, typescript, javascript, go, rust, java, ... (20 via Rust kernel) | py-callers (measured), py-imports (measured), py-symbols (measured), dead-code (probed), py-impact (probed), context-pack (read only), multi-lang-graph (read only) | [card](../research/tools/codegraph.md) |
| [CodeQL](https://github.com/github/codeql) | MIT (queries/libraries); CLI/engine proprietary | python, javascript, typescript, go, rust, java, csharp, php, ruby | dataflow-taint (read only), security-patterns (read only) | — |
| [CodeWiki (Google)](https://codewiki.google) | proprietary | multi | repo-overview (read only) | — |
| [Comby](https://github.com/comby-tools/comby) | Apache-2.0 | any (delimiter-aware) | structural-search (read only) | — |
| [Continue (@codebase)](https://github.com/continuedev/continue) | Apache-2.0 | multi | semantic-search (read only) | — |
| [coverage.py](https://github.com/nedbat/coveragepy) | Apache-2.0 | python | py-tests-for (read only) | — |
| [Doxygen](https://www.doxygen.nl) | GPL-2.0 | multi | py-callers (read only) | — |
| [fallow](https://github.com/fallow-rs/fallow) | MIT | typescript, javascript | duplicates (read only), frontend-dead-exports (read only) | — |
| [GitNexus](https://github.com/abhigyanpatwari/GitNexus) | PolyForm-Noncommercial-1.0.0 | python, typescript, javascript, java, kotlin, csharp, go, rust, php, ruby, swift, c, cpp, dart | py-symbols (measured), diff-review (probed), py-callers (probed), py-impact (probed), py-imports (probed), repo-overview (probed), semantic-search (probed), multi-lang-graph (read only) | [card](../research/tools/gitnexus.md) |
| [Glean (Meta)](https://glean.software) | BSD-style | multi | multi-lang-graph (read only) | — |
| [gpt-repository-loader](https://github.com/mpoon/gpt-repository-loader) | MIT | any (text) | context-pack (read only) | — |
| [grafema](https://github.com/Disentinel/grafema) | FSL-1.1-Apache-2.0 | javascript, typescript, python (beta) | py-symbols (probed), multi-lang-graph (read only), dataflow-taint (rejected), import-gate (rejected), py-callers (rejected), py-impact (rejected), py-imports (rejected) | [card](../research/tools/grafema.md) |
| [Graphify](https://github.com/Graphify-Labs/graphify) | Apache-2.0 | python, ~40 via tree-sitter, non-code via LLM | py-callers (measured), py-imports (measured), py-symbols (measured), repo-overview (probed), multi-lang-graph (read only), py-impact (read only) | [card](../research/tools/graphify.md) |
| [graphlens-mcp](https://github.com/neko1313/graphlens-mcp) | MIT | python, typescript, go, rust, php | py-callers (measured), py-impact (measured), py-symbols (probed), multi-lang-graph (read only), semantic-search (read only) | [card](../research/tools/graphlens.md) |
| [griffe](https://mkdocstrings.github.io/griffe/) | ISC | python | api-diff (read only) | — |
| [grimp](https://github.com/python-grimp/grimp) | BSD-2-Clause | python | py-imports (measured) | [card](../research/tools/import-linter.md) |
| [import-linter](https://github.com/seddonym/import-linter) | BSD-2-Clause | python | import-gate (measured) | [card](../research/tools/import-linter.md) |
| [jedi](https://github.com/davidhalter/jedi) | ? | python | py-symbols (read only) | — |
| [jevgrep (jg)](https://github.com/dzhng/jevgrep) | MIT | python, go, rust, typescript, javascript, text fallback | context-pack (measured), py-callers (measured), py-impact (measured), py-symbols (measured), semantic-search (measured), multi-lang-graph (read only) | [card](../research/tools/jevgrep.md) |
| [jscpd](https://github.com/kucherenko/jscpd) | MIT | multi (150+ formats) | duplicates (read only) | — |
| [Knip](https://github.com/webpro-nl/knip) | ISC | javascript, typescript | frontend-dead-exports (read only) | — |
| [Kythe](https://kythe.io) | Apache-2.0 | multi | multi-lang-graph (read only) | — |
| [lizard](https://github.com/terryyin/lizard) | MIT | multi (C/C++, Java, JS, Python, Go, ...) | complexity (read only) | — |
| [mypy](https://github.com/python/mypy) | MIT | python | type-errors (read only) | — |
| [OntoIndex](https://github.com/ontograph/ontoindex) | AGPL-3.0-or-later | typescript, javascript, python, java, kotlin, csharp, go, rust, php, ruby, swift, c, cpp, dart | py-callers (measured), py-impact (measured), py-symbols (measured), py-imports (probed), repo-overview (probed), dead-code (read only), diff-review (read only), multi-lang-graph (read only), semantic-search (read only) | [card](../research/tools/ontoindex.md) |
| [OpenGrep](https://github.com/opengrep/opengrep) | LGPL-2.1 | multi (~12 for cross-function taint) | dataflow-taint (read only) | — |
| [pyan3](https://github.com/Technologicat/pyan) | GPL-2.0 | python | py-callers (read only) | — |
| [PyCG](https://github.com/vitsalis/PyCG) | Apache-2.0 | python | py-callers (rejected) | [card](../research/tools/pycg.md) |
| [pydeps](https://github.com/thebjorn/pydeps) | BSD-2-Clause | python | py-imports (read only) | — |
| [Pyright](https://github.com/microsoft/pyright) | MIT | python | type-errors (read only) | — |
| [pytest-django](https://github.com/pytest-dev/pytest-django) | BSD-3-Clause | python | db-query-count (read only) | — |
| [radon](https://github.com/rubik/radon) | MIT | python | complexity (read only) | — |
| [rag_for_git (rag-reviewer)](https://github.com/mimfort/rag_for_git) | MIT | python | py-callers (measured), diff-review (read only), semantic-search (read only), py-impact (rejected) | [card](../research/tools/rag_for_git.md) |
| [Repomix](https://github.com/yamadashy/repomix) | MIT | multi | context-pack (read only), security-patterns (read only) | — |
| [roam-code](https://github.com/Cranot/roam-code) | Apache-2.0 | multi | multi-lang-graph (read only), repo-overview (read only) | — |
| [rope](https://github.com/python-rope/rope) | LGPL | python | py-callers (read only) | — |
| [SCIP (format)](https://github.com/sourcegraph/scip) | Apache-2.0 | python, typescript, go, java, ... (per indexer) | multi-lang-graph (read only) | — |
| [scip-python](https://github.com/sourcegraph/scip-python) | MIT | python | py-callers (measured) | [card](../research/tools/rag_for_git.md) |
| [Semgrep](https://github.com/semgrep/semgrep) | LGPL-2.1 (engine) | multi | dataflow-taint (read only), security-patterns (read only), structural-search (read only) | — |
| [Sourcegraph (incl. Cody)](https://sourcegraph.com) | proprietary (open components) | multi | multi-lang-graph (read only) | — |
| [Stack Graphs](https://github.com/github/stack-graphs) | MIT/Apache-2.0 | multi (tree-sitter + .tsg) | multi-lang-graph (read only) | — |
| [tree-sitter](https://github.com/tree-sitter/tree-sitter) | MIT | multi (grammars) | structural-search (read only) | — |
| [Tutorial-Codebase-Knowledge](https://github.com/The-Pocket/Tutorial-Codebase-Knowledge) | ? | multi | repo-overview (read only) | — |
| [Understand-Anything](https://github.com/Egonex-AI/Understand-Anything) | MIT | multi (tree-sitter wasm), non-code (config, docs, IaC, SQL) | py-imports (measured), py-symbols (measured), py-callers (probed), repo-overview (probed), diff-review (read only) | [card](../research/tools/understand-anything.md) |
| [universal-ctags](https://github.com/universal-ctags/ctags) | GPL-2.0 | multi | py-symbols (read only) | — |
| [vulture](https://github.com/jendrikseipp/vulture) | MIT | python | dead-code (read only) | — |
| [wily](https://github.com/tonybaloney/wily) | Apache-2.0 | python | complexity (read only) | — |

## Latest news

- 2026-11-21 · new-tool · `roam-code` New to the catalog: roam-code 14.1.0 (Apache-2.0, 28 languages per its README), local codebase intelligence for AI coding agents with change-safety gates and an MCP interface. — https://pypi.org/project/roam-code/
- 2026-11-21 · new-tool · `fallow` New to the catalog: fallow, an MIT-licensed Rust analyzer for TypeScript and JavaScript offering CLI, MCP and LSP interfaces, per its README. — https://github.com/fallow-rs/fallow
- 2026-11-21 · card · The codemap lab's tool catalog is served to agents: MCP `advise`, `codemap advise`, generated inventory research/matrix.md. — https://github.com/kogriv/codemap/blob/main/research/matrix.md
- 2026-11-06 · finding · `import-linter` import-linter 2.16 closes two silent passes the lab filed: an unknown contract option and zero contracts now fail (verified by the lab on 2.16). — https://github.com/seddonym/import-linter/issues/393
- 2026-11-05 · finding · `graphify` Graphify 0.9.103 fixes the builtin homonym the lab filed (a builtin exception bound to a same-named package class); verified by the lab 2026-11-06. — https://github.com/Graphify-Labs/graphify/issues/4989
- 2026-10-15 · finding · `codegraph` CodeGraph 1.6.1 fixes the silent truncation of callers the lab filed; 1.6.2 returns total and truncated. Figures re-measured on 1.6.2. — https://github.com/colbymchenry/codegraph/issues/1639
