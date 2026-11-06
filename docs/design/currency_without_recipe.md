# Design — a graph built elsewhere is checked from its own roots; what cannot be checked is said

**Status:** 🟡 pre-registered (expectations below, committed before code). **Backlog:** R1-C90. **Gap:**
[`gaps/currency_without_recipe_2026-11-06.md`](../../gaps/currency_without_recipe_2026-11-06.md).

## D1 — fall back to the graph's recorded roots

When the recipe cannot be used (no sidecar, or its `cwd` is gone), `graph_currency` tries the graph's own
`provenance.roots` (core, consumers, docs, relative to the graph's path base) and its `target`. The base is
`source_root` when given (`serve --source-root`, CLI `--source-root`), else the current directory. If the core
root exists there, the scope is resolved from those roots and compared with `provenance.scope_id`. The result
says how it was checked: `"via": "recipe"` or `"via": "provenance roots under <base>"`. A single-package graph has
no `roots` and falls back to `<base>/<target>`.

Scope ids are computed from file content and relative paths, so a tree checked out elsewhere with the same files
gives the same `scope_id`. That is what makes the comparison valid across machines. E2 verifies it rather than
assuming it.

## D2 — `unknown` in a cold CLI read is one note

When `currency` is still `unknown`, a cold CLI read prints one `[note] could not check <graph> against the source
tree: <reason>` line on stderr. `behind` keeps its `[warning]`. `current` prints nothing.

No answer-shape change beyond R1-C85's field (it gains `via`); ships with R1-C86 under **`ANSWER_FORMAT` 10**:
`currency` gains a field, and `unknown` becomes rarer in meaning.

## Pre-registered expectations

E1, E3 and E4 fail on 0.0.33.

| # | Expectation |
|---|---|
| E1 | Fixture: graph built with a sidecar, the sidecar's `cwd` then rewritten to a missing directory; run from the repo root → `currency` is `current` with `via` naming the provenance roots; after an edit → `behind` |
| E2 | A copy of the same tree at another path: the graph built in one copy is `current` against the other (the `scope_id` does not depend on the location) |
| E3 | bquant: a graph built at `d9a2a4f` in one clone, with its sidecar's `cwd` made invalid, checked from a clone at `cf039ef` → `behind` via provenance roots, not `unknown` |
| E4 | No sidecar and no matching roots under the base: a cold CLI read prints one `[note] could not check …` line with the reason; stdout unchanged |
| E5 | Full suite passes; guards go red when D1 or D2 is reverted; a cosmetic control stays green |
