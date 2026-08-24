# Design — References the source shows and the graph misses

**Status:** ✅ **shipped** (2026-08-24, **no schema change**).
**User docs:** [docs/dead-code.md](../dead-code.md#what-counts-as-a-reference).

**Decisions resolved (§below):** D1 = **yes** (`references`, `resolution="name"`), D2 = **yes**
(module-sourced `calls`), D3 = **yes** (measured first — the feared cost did not materialise),
D4 = **no grader change**, D5 = additions-only, met.
**Motivates:** gap [dead_code_high_band_2026-08-24](../../gaps/dead_code_high_band_2026-08-24.md), issue
[#7](https://github.com/kogriv/codemap/issues/7). **Backlog:** R1-C22.

Three reference forms are plainly visible in source and produce **no edge**: a function used *as a value*, a
call at **module level**, and a call inside a **nested def**. Measured across codemap and bquant, they make
**20 of 51** `high` dead-code candidates false (39%) — and ② and ③ are missing `calls` edges, so they also
thin out `impact`, `callers`, `flows` and the architecture views.

The grader is not at fault and does not change: `_grade_dead` demotes to `low` on any inbound edge, so each
fix below flows through on its own.

**Guiding invariants (unchanged):** source-only, deterministic, two tiers, resolved-or-honestly-flagged,
closed edge vocabulary (R1-C7), extras open-ended.

## D1 — function-as-value → a `references` edge

**Recommended: yes.**

A `Name` load that resolves to a package function/class and is **not** the callee of a call and **not** a
decorator is a *use of the symbol as a value*: a dict entry, a list element, a `default=` argument, an
assignment RHS. Emit `references` from the enclosing graph node (function, or the module for module-level
code) to that symbol.

- **No new edge type, no schema bump.** `references` is already defined as *"consumer/doc/**dispatch site**
  → the core symbol it names"* (R1-C7) — a dispatch table is precisely that. It is already in
  `_IMPACT_EDGES`, so field-level blast radius improves for free.
- **Label** `extras.resolution = "name"` to distinguish an intra-core name-load from the consumer/doc
  references that carry `"imported"` / `"doc"`.
- **Size:** ~69 edges on codemap, ~149 on bquant — small, because most name uses are calls already.
- **Alternative rejected:** demote to `low` when the name appears anywhere in the defining module (the
  issue's narrower option). It fixes the report and leaves the graph blind — `impact` on `_panel_a` would
  still answer "nothing references this". R1-C20 faced the same fork and chose to model the relationship;
  this follows that precedent.

## D2 — module-level calls → `calls` edges sourced from the module

**Recommended: yes.**

`add_behavior` iterates `_named_functions(tree)`, so statements at module level are never visited. Visit
them, and emit the call edge from the **module** node (the only definition that contains that code).

- Closes a blind class, not just these candidates: import-time registration, availability probes and
  singleton construction are currently invisible to every call-graph consumer.
- **Size:** 27 call sites on codemap, 137 on bquant — small and safe.
- Module → function `calls` edges are already legal in the model (nothing constrains the source kind), and
  `flows`/`impact` read them without change.

## D3 — calls inside nested defs → attribute to the nearest enclosing node

**Recommended: yes in principle, but measure the delta before committing — this is the expensive one.**

```python
if node_id not in graph.nodes:
    continue  # nested closure — not a definition node   ← drops the body wholesale
```

The whole nested function is skipped, so its calls vanish. Attributing them to the nearest **enclosing graph
node** is the same rule `roots.py::_source_for` already uses for consumer roots, so the codebase has a
precedent and a consistent semantic ("the definition that contains this code").

- **Size: 619 call sites on codemap, 5202 on bquant** — one to two orders of magnitude above D1/D2. Most
  will resolve to externals and produce nothing, but the survivors change `calls` counts, `callsites`
  extras, hub degrees and complexity-adjacent views on **every existing graph**.
- Therefore: implement behind the same pass, but **measure the real edge delta first** (added / removed /
  changed-extras on codemap and bquant) and report it before merging. If the delta is disproportionate, ship
  D1+D2 and take D3 as its own change with its own acceptance.
- Honest note either way: attributing a closure's call to its enclosing function is an *approximation of
  location*, not of existence — the call is real; only its source node is approximate. Worth an
  `extras.via = "nested"` marker so the approximation is visible (R1-C13 discipline).

## D4 — the grader stays as it is

**Recommended: no change to `_grade_dead`.** It already reads `references_to` and demotes to `low` with a
reason naming who references the symbol. The three fixes above make it correct by giving it the edges it was
always asking for. Resisting a special case here is the point: the report was never the bug.

## D5 — acceptance is *not* byte-identity

R1-C21 could demand byte-identical graphs because it fixed a layout nothing else touched. These fixes
deliberately **add true edges**, so the criterion changes:

- **Additions only** — no edge removed, no target retargeted, on either package.
- **Every addition traceable** to a source-visible reference (spot-checked by fixture, pinned by tests).
- **The measured false positives go to zero**: codemap's 13 as-value + 4 nested and bquant's 2 module-level
  + 1 nested leave the `high` band; the 31 genuinely unreferenced candidates stay in it.
- **No new schema version** (no new edge type; `extras` keys only).
- Report the edge-count delta for each package in the merge notes — a graph that grows should say by how
  much and why.

## Decisions — resolved

| # | Question | Decision (as shipped) |
|---|---|---|
| **D1** | Model function-as-value | **yes** — `references`, `extras.resolution="name"`, deduped with a `sites` count |
| **D2** | Module-level calls | **yes** — `calls` sourced from the module node |
| **D3** | Nested-def calls | **yes** — attributed to the innermost enclosing definition, `extras.via="nested"` |
| **D4** | Change the grader | **no** — untouched; the edges fixed the report by themselves |
| **D5** | Acceptance | additions-only, measured FPs to zero — met (below) |

## What shipped, and three things the design did not foresee

- `extract/behavior.py` — `_own_name_loads` / `_resolve_name` / `_emit_name_references` (D1),
  `_module_level_nodes` / `_process_module_level` (D2), `_named_functions_scoped` /
  `_nearest_owner` / `_collect_nested_calls` / `_emit_nested_calls` (D3).
- `codemap/incremental.py` — the R1-C9 splice had to learn the new edges, or an incremental
  rebuild silently dropped them (caught by its own byte-identity test, not by inspection).

**① Most name-loads are annotations, not dispatch.** The first run emitted 278 `references`
on bquant against a ~149 estimate; the surplus was `def analyze(...) -> AnalysisResult`. Both
are real references, but they mean different things — a dispatch table implies the symbol
*runs*, an annotation implies a *contract* — so they are labelled apart
(`resolution="annotation"`, 213 vs 80 on bquant) instead of blurred under one name.

**② D3's cost was a phantom.** The design costed it at 5202 nested call sites on bquant and
reserved the right to split it out. Measured properly: of those 5202, **279** resolve to an
internal target and only **21** are pairs the owner does not already call directly (codemap:
624 → 32 → **4**). The expensive-looking number was call *sites*, not new *edges*; measuring
the actual delta turned a deferred decision into a five-line one.

**③ The accuracy benchmark's ground truth was stale.** `c10_closure` listed
`expected: []` with `outer→helper` recorded as a *limitation* — while the case's own
docstring already said "the resolvable edge is from the enclosing function `outer` to
`helper`". D3 emits exactly that, so the harness scored the fix as a false positive. The
label was recording the old behaviour as if it were the correct answer; it is now
`decidable` with `outer→helper` expected, and `outer→inner` / `inner→helper` still
limitations (`inner` is not a definition node). Deep recall-overall: 58% → **62.5%**,
precision still 100%, zero phantom targets.

## Acceptance — met

| criterion | result |
|---|---|
| all three forms modelled | fixture `refpkg` covers value / annotation / module-level / nested (14 tests) |
| **additions only** | bquant (untouched code): **+364 edge pairs, 0 removed**. codemap: +164, 1 removed — the one being `add_behavior → _named_functions`, a call this very change replaced |
| measured FPs → zero | `high` band: codemap **46 → 29**, bquant **5 → 2** — exactly the 31 the audit called genuinely unreferenced |
| every addition traceable | all 278 name-references on bquant have their target's name literally present in the source file (checked) |
| no duplicate call pairs | nested attribution yields to an existing direct call; asserted |
| grader untouched | `_grade_dead` unchanged |
| graph size | codemap +7.7%, bquant +5.0% |
| no schema bump | no new edge type; `extras` keys only |
