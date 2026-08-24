# Design — References the source shows and the graph misses

**Status:** 🟡 **open — decisions D1–D5 pending approval, no code written yet.**
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

## Decisions to resolve

| # | Question | Recommendation |
|---|---|---|
| **D1** | Model function-as-value | **yes** — `references` edge, `extras.resolution="name"`; no schema bump |
| **D2** | Module-level calls | **yes** — `calls` sourced from the module node |
| **D3** | Nested-def calls | **yes in principle** — but measure the delta (5202 sites on bquant) and be ready to split it out |
| **D4** | Change the grader | **no** — the edges fix it; the report was never the bug |
| **D5** | Acceptance | additions-only + measured FP counts to zero, **not** byte-identity |
