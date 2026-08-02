# R1.4 — Python graph / dependency / architecture peers

The most direct reference peers: Python-specific tools that build import graphs, call graphs, or
architecture reports. For most of these the verdict is **already-covered** — the value is in the handful of
**genuine gaps worth adopting**.

**Baseline (codemap):** source-only Python graph (griffe + jedi), deterministic canonical `graph.json`,
networkx backend, CLI/AI-first. Produces import graph, class inheritance, jedi-resolved call graph,
cross-root impact/blast-radius, call-site argument contracts, dataflow columns, and an architecture report
(layers + violations, Ca/Ce/instability, god-objects/hubs). Renders markdown, mermaid, RAG chunks, vault.

---

## Import-graph tools

### pydeps
Module dependency graphs — notably scans **import-opcodes in compiled bytecode** (not AST), so only
import-machinery-resolvable modules appear. Output: Graphviz image (edge thickness ∝ coupling, cycles as
blue boxes) + `--show-deps` JSON. BSD-2, active.
**Verdict: ALREADY-COVERED.** codemap's import graph is AST/griffe-based (no bytecode compile, more
deterministic) and feeds impact. Learn-only nugget: pydeps' edge-thickness-as-coupling / cycle-box visual
idiom is a nice mermaid/report touch.

### grimp
A **library** (not viz) building a queryable directed import graph; Rust-accelerated. API:
`find_descendants`, `find_modules_directly_imported_by`, shortest-path/chain, cycle detection. BSD, active
(v3.x). *Is the engine under import-linter.*
**Verdict: ALREADY-COVERED (import layer) / LEARN-ONLY.** Exactly the import-graph substrate codemap owns
(networkx-backed). Learn: grimp's mature import-chain / shortest-path query API is a good model for
codemap's relational surface.

### snakefood
Older AST-based dependency grapher (`sfood`, `sfood-graph`, `sfood-cluster`, `sfood-checker`). GPL,
**inactive/unmaintained** (2001–2007).
**Verdict: ALREADY-COVERED (legacy).** codemap does all of it more precisely. Its `sfood-cluster`
(package-granularity collapse) maps to codemap's multi-root/package views.

## Call-graph tools

### pyan / pyan3
The classic Python static **call/def-use graph** (self-described "rather superficial" AST analysis).
Output: GraphViz/yEd/GraphML, distinguishing "defines" vs "uses" edges. Recently revived as official
`pyan3` (Py3.10–3.14).
**Verdict: ALREADY-COVERED / LEARN-ONLY.** codemap's closest static-call-graph ancestor, but codemap's
jedi-resolved behavioral call graph is more accurate than pyan's name-heuristics, and adds
impact/contracts/architecture. Learn: pyan's explicit **defines-vs-uses edge typing** is a clean
edge-semantics model.

### code2flow
"Pretty good call graphs for dynamic languages" — heuristic name-matching, multi-language (Python/JS/Ruby/
PHP). Graphviz + JSON. MIT, maintained; a community MCP wrapper exists.
**Verdict: LEARN-ONLY (differentiator).** codemap is deliberately Python-only + jedi-resolved → more
precise where code2flow is broad. Lesson: lean on Python-depth + determinism as the edge over multi-language
heuristics. The code2flow-MCP shows MCP-wrapping demand codemap already serves natively.

### Doxygen (Python support)
Multi-language doc generator; with Graphviz produces call/caller/inheritance graphs. **But Python support is
weak** — documented limitation (#7254): **Python class-method calls are ignored** in call graphs. GPL, very
active.
**Verdict: LEARN-ONLY / ALREADY-COVERED for Python.** codemap's jedi-resolved call graph is the Python-native
answer Doxygen can't give. Learn: Doxygen's per-symbol combined call+caller+inheritance page is a good
"symbol dossier" layout (codemap's `query` dossier already mirrors it).

## Architecture / constraint tools

### import-linter — *most relevant peer to codemap's architecture report*
CLI that **enforces self-imposed architecture** by checking imports (built on grimp) against declared
**contracts** in a config file: **Layers** (ordered, lower may not import higher, transitively),
**Independence** (siblings can't import each other), **Containers**, **Forbidden**, plus **optional**
`(layers)` and **exhaustive** mode. Output: pass/fail with violating chains — a **CI gate** with non-zero
exit. BSD, active (v2.x).
**Verdict: LEARN-AND-ADOPT (biggest gap).** codemap's architecture report *detects* layers and reports
direction/violations descriptively; import-linter's differentiator is
**architecture-constraints-as-declared-contracts that fail CI**. codemap should consider a declarative
contract file + `--check` exit-code mode so its architecture findings become an **enforceable gate**, not
just a report. The single clearest thing to learn here.

## Refactoring / cross-reference

### rope
Mature Python **refactoring library** (safe rename/move/extract) with `rope.contrib.findit.find_occurrences`
(cross-reference). LGPL, active. (See also [R1.3](03_query_dataflow_engines.md).)
**Verdict: LEARN-ONLY / INTEGRATE-IF-EDITS.** Different goal (mutation vs read-only graph), but its
occurrence engine overlaps with codemap's callers/impact; codemap's deterministic graph could be a
*substrate* for refactoring-impact preview. Natural pairing if codemap ever adds safe edits.

## Doc / API-surface extraction

### pydoctor / griffe / Sphinx autodoc
API-surface extractors. **griffe** (codemap's own extractor) — static AST parse (+ optional runtime) →
in-memory API model + JSON + **API-breaking-change diff**. **pydoctor** — static → API HTML (Twisted).
**Sphinx autodoc** — **runtime import** + introspection (the non-deterministic outlier). All active.
**Verdict: ALREADY-USING / ALREADY-COVERED, with one gap.** codemap *uses* griffe, so this class is
foundational, not competitive. What they do that codemap doesn't: (a) render **human docstring-centric API
docs**, and (b) griffe's **API-breaking-change detection between two versions**. Learn-and-adopt: griffe's
API-diff would pair with codemap's deterministic graph for a "what broke between commits" report — codemap
has `review`/diff over the graph but could add signature-level breaking-change detection.

## Dead code & metrics

### vulture — dead-code detection
AST-based defined-vs-used name analysis; reports unused with **confidence 60–100%** + whitelist. **High
false-positive rate** on dynamic code (no cross-module resolution — ~260 FPs on Flask). MIT, active.
**Verdict: ALREADY-SUBSUMED, with an edge.** codemap has **provenance-aware dead-code**: resolving calls
across repo roots (package/tests/docs) with jedi, it distinguishes "unused in package but referenced by
tests/docs" — precisely the context vulture lacks (the root cause of its false positives). Market this as
"vulture without the framework false-positives." Learn: vulture's **confidence score + whitelist file** UX
(graded certainty vs binary) is worth adopting when codemap reports dead code.

### radon / wily — complexity metrics
**radon** — per-block **Cyclomatic Complexity (McCabe)**, **Halstead**, **Maintainability Index**, raw SLOC
(AST). **wily** — tracks radon-style metrics **across git history** (trend over commits). Both MIT-family,
maintained.
**Verdict: LEARN-AND-ADOPT (metrics gap).** codemap's god-object/hotspot detection is
**structural/coupling-based** (Ca/Ce, instability, fan-in/out) — it does **not** compute intra-function
complexity. A "big class" by coupling ≠ a "complex function" by McCabe; hotspot ranking is strongest
combining both. **Adopt/wrap radon** (or reimplement CC/MI over codemap's existing griffe AST — cheap,
deterministic, on-brand) to enrich hotspot scoring. wily's lesson: **metric-over-time trend** — codemap has
diff/`review` but not longitudinal metric trends; a natural future extension.

## Interactive code map

### Sourcetrail — *discontinued*
Interactive visual source explorer (C/C++/Java/Python) over a SQLite symbol DB (SourcetrailDB). GPL,
**discontinued** — development ended Sept 2021, repo archived Dec 2021; community forks exist, no first-party
maintenance.
**Verdict: LEARN-ONLY (cautionary + opportunity).** Proved demand for a navigable code map but died on
**cross-platform GUI maintenance burden** — validating codemap's CLI/JSON/MCP-first, no-GUI stance as the
sustainable form. Opportunity: its abandonment leaves an interactive-code-map gap; codemap's deterministic
`graph.json` could feed a lightweight (web/mermaid) navigator without inheriting the GUI cost. Its
SourcetrailDB "shared index format" idea echoes the SCIP/ctags interop theme ([R1.2](02_codegraph_index_infra.md)).

---

## Themes — what codemap already covers vs the gaps

**Already covered / subsumed.** The whole import-graph + static-call-graph cluster — **pydeps, grimp,
snakefood, pyan3, code2flow, Doxygen-for-Python** — is codemap's core, done with more precision and
determinism: jedi-resolved calls beat pyan's heuristics, code2flow's "pretty good" multi-language matching,
and Doxygen (which drops Python method calls); griffe import parsing avoids pydeps' bytecode-compile
dependency. **vulture** is subsumed *and bettered* — codemap's cross-root, jedi-resolved provenance is the
direct cure for vulture's dominant false-positive source, a marketable differentiator. codemap already
*uses* **griffe**, so doc-extraction is foundational. And **Sourcetrail's** death validates codemap's
no-GUI, CLI/JSON/MCP-first stance.

**Real gaps worth adopting**, in priority order:

1. **Architecture-constraints-as-tests (import-linter).** codemap *describes* layers/violations; adding a
   declarative contract file + `--check` non-zero-exit mode turns the architecture report into an
   **enforceable CI gate** — the highest-value adoption.
2. **Complexity metrics (radon/wily).** codemap's hotspot detection is purely structural; computing
   **cyclomatic/Halstead/Maintainability-Index** over its existing griffe AST (deterministic, source-only,
   on-brand) would sharpen hotspot ranking. wily's metric-over-time is a longitudinal extension of `review`.
3. **API breaking-change detection (griffe).** griffe already ships version-to-version API-diff; codemap has
   graph-level diff/`review` but not signature-level breaking-change reporting — a low-cost, on-brand
   addition since the extractor is already in-house. (Overlaps the deferred two-graph-diff item.)

**Softer gap — visualization.** Peers lean on Graphviz images and (formerly) Sourcetrail's interactive map;
codemap emits mermaid/markdown/RAG/vault, so it isn't absent — but the discontinued-Sourcetrail niche (a
navigable interactive map fed by a deterministic index) is an open opportunity `graph.json` is well-positioned
to fill without inheriting GUI maintenance cost.

---

### Sources

[pydeps](https://github.com/thebjorn/pydeps) · [pyan3](https://github.com/Technologicat/pyan) ·
[code2flow](https://github.com/scottrogowski/code2flow) · [grimp](https://grimp.readthedocs.io/en/stable/) ·
[import-linter](https://import-linter.readthedocs.io/en/latest/contract_types.html) ·
[snakefood](https://github.com/blais/snakefood) · [rope](https://github.com/python-rope/rope) ·
[griffe](https://mkdocstrings.github.io/griffe/) ·
[Doxygen diagrams](https://www.doxygen.nl/manual/diagrams.html) /
[Python call-graph #7254](https://github.com/doxygen/doxygen/issues/7254) ·
[Sourcetrail (archived)](https://github.com/CoatiSoftware/Sourcetrail) ·
[vulture](https://github.com/jendrikseipp/vulture) · [radon](https://radon.readthedocs.io/en/stable/intro.html)
