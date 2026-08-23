# Design — Attribute access edges (impact/refs for class fields)

**Status:** design, pre-code. **Motivates:** gap [attribute_impact_gap_2026-08-22](../../gaps/attribute_impact_gap_2026-08-22.md),
issue [#1](https://github.com/kogriv/codemap/issues/1). **Backlog:** R1-C20.

codemap models relationships between *symbols* (calls/imports/inherits/decorated_by/references) and between
functions and *string-keyed columns* (reads/writes, M12) — but **not between code and Python attributes**.
So `impact`/`references_to` on a class field return empty and `risk:"none"`, an affirmative "nothing depends
on this" that is wrong (see gap-doc). This design adds attribute access as first-class edges so field-level
`impact` answers truthfully, mirroring what M12 did for columns and M4–M7 did for calls.

**Guiding invariants (unchanged):** source-only, deterministic, two tiers (fast `ast` / deep `jedi`),
**resolved-or-honestly-flagged**, closed edge vocabulary (R1-C7).

## 1. What we model

An **attribute access edge**: `source function → target attribute node`, where the attribute node already
exists (kind `attribute`, canonical id `pkg.mod.Class.field` or `pkg.mod.module_var`). Two access forms,
distinguished on the edge (as columns already carry `extras.access`):

- **write** — the field is assigned (`self.field = …`, `obj.field = …`, `Cls(field=…)` construction kwarg).
- **read** — the field's value is used (`self.field`, `obj.field`, `Cls.field` in a Load context).

Each edge carries `extras.resolution` (how the target was resolved) and `extras.access` (`read`/`write`),
consistent with the `calls` and `reads`/`writes` conventions.

### 1.1 Edge-type decision (open — §9 D1)

Three options, recommendation **B**:

- **A. Reuse `reads`/`writes`.** Attribute nodes become a second valid target of the existing column edges.
  Pro: no new vocabulary; `access` field already exists. Con: conflates DataFrame-column lineage with
  Python-attribute access under one name — queries that mean "columns" must now filter by target kind, and
  the M12 semantics ("data threads through string keys") blur.
- **B. New edge type `accesses`** (recommended). A dedicated closed-vocabulary entry
  (`model.EDGE_TYPES`, R1-C7) for function→attribute access, `extras.access ∈ {read, write}`. Pro: clean
  separation, self-documenting, columns stay columns; existing `reads`/`writes` queries are untouched.
  Con: one new type (a deliberate, documented R1-C7 addition — exactly what its guard test is for).
- **C. Reuse `references`.** Pro: `references` already means "X names this symbol" and is already in
  `_IMPACT_EDGES`. Con: `references` today is the cross-root consumer/doc layer; overloading it with
  intra-core attribute access loses the read/write distinction and muddies provenance.

**B** keeps every existing edge's meaning intact and makes the new relationship legible; the R1-C7 vocabulary
was built to absorb exactly this (add the type + doc + let the guard test enforce it).

## 2. Extraction (bounded AST pass)

A new pass `extract/attrflow.py`, structured like `extract/dataflow.py` (`_own_*` walk that stops at nested
def/class boundaries, per-function). Runs in the same behavioral phase; **fast tier is pure `ast`**, deep
tier adds `jedi` for typed locals. Detected sites → resolved target attribute id → `accesses` edge from the
enclosing function.

Access forms and how each resolves:

| Form | Example | Resolution | Tier |
|---|---|---|---|
| `self.field` / `cls.field` | `self.distance`, `self.distance = x` | enclosing class's attribute (reuse the R1-C13-f1 `members`/owner map — `self.<inherited>` → base owner) | fast |
| `ClassName.field` | `SwingThresholds.peak_prominence` | the named class's attribute, if `ClassName` resolves to a package class (imports/module members) | fast |
| construction kwarg | `SwingThresholds(peak_prominence=…)` | the constructed class's attribute (write); class resolved like a call target | fast |
| `obj.field` on a typed local | `t = make(); t.peak_prominence` | jedi types `obj` → class → attribute | deep |
| `obj.field`, `obj` untyped | `x.field` (x unknown) | **unresolved** — counted, no edge (honest) | — |

Only edges whose **target is a real attribute node** are emitted; anything else is a counter, never an edge
to nothing (the R1-C13-f2 soundness rule). Dunder/`property` nuances: a `property` is a `function` node, not
an attribute — `self.x` where `x` is a property resolves to the function (a `calls`-like access); out of
scope here (attributes only), flagged not modelled.

## 3. Query / impact integration

- **`impact` / `references_to`** must span `accesses` edges **when the target is an attribute**. Today
  `_IMPACT_EDGES = (calls, references, inherits, imports, decorated_by)` — add `accesses` so a field's
  blast-radius is real. (Columns' `reads`/`writes` deliberately stay out of impact; `accesses` is
  attribute-scoped, so this doesn't re-open the column question.)
- **New surfaces** (thin, over the same edges): `Query.readers(attr)` / `Query.writers(attr)`, and the field
  appears in the owning class's dossier ("fields: … — read by N, written by M"). `report`/MCP ride along.
- **Risk / epistemic:** an attribute answer carries `epistemic: "partial"` (attribute resolution is
  best-effort, like calls). Crucially, an attribute with **no modelled `accesses` edge** reports
  `risk: "unknown"` + reason "attribute access is a lower bound", **never `none`** — this is the honesty fix.

## 4. Phase 0 — the honesty fix ships first (cheap, independent)

Independent of extraction: make `impact`/risk on an **attribute** target return `unknown`/`unmodelled` with a
reason instead of `none`, whenever there are zero modelled inbound edges. This removes the *lie* immediately
(closes the sharp edge of issue #1) and is safe to merge before the extraction lands. Phases 1–3 then replace
"unmodelled" with real edges where we can resolve them, downgrading to "unknown" only for the genuine tail.

## 5. Determinism & honesty

- Deterministic by construction: sorted per-file/per-function walk, edges sorted in `to_dict` (existing
  invariant); jedi tier deterministic as in M5.
- Every edge labelled `resolution` (`self` | `class` | `deep` | `construct`); unresolved accesses are
  counters surfaced in `report behavior` (coverage %), matching the calls layer. No edge to a non-node.

## 6. Schema

New closed-vocabulary edge type `accesses` in `model.EDGE_TYPES` (R1-C7) with a one-line doc; graph
`SCHEMA_VERSION` bump (additive). The R1-C7 guard test (`test_r1c7_edge_vocab`) will require the vocabulary
update + confirm the type actually appears on the dogfood target — the intended workflow.

## 7. Boundaries (explicitly not in v1)

- **Value-level dataflow** (which value flows into the field) — no; this is *access* modelling, not taint.
- **`property`/descriptor** access modelled as attribute — no (they're functions; separate concern).
- **Dynamic attribute access** (`getattr(obj, name)`, `setattr`) — counted as unresolved, never guessed.
- **Cross-object aliasing** beyond jedi's local type inference — the known static ceiling (M5), unchanged.

## 8. Plan (phased)

- **P0 — honesty fix:** attribute `impact`/risk → `unknown`/`unmodelled` instead of `none`. +tests. (ships first)
- **P1 — extraction, fast tier:** `extract/attrflow.py` for `self.field`, `ClassName.field`, construction
  kwargs → `accesses` edges (`read`/`write`, `resolution`). `EDGE_TYPES` + schema bump. Wire into `impact`/
  `references_to`. `Query.readers`/`writers`. Dogfood on bquant: `peak_prominence` → its 6 core sites.
- **P2 — deep tier:** jedi-typed `obj.field`. Coverage % in `report behavior`.
- **P3 — surfaces:** field read/write counts in the class dossier; MCP/report polish; docs.

## 9. Open decisions (for review before coding)

- **D1 — edge type:** `accesses` (new, recommended B) vs reuse `reads`/`writes` (A) vs `references` (C). §1.1.
- **D2 — impact inclusion:** confirm `accesses` joins `_IMPACT_EDGES` (attribute blast-radius) while columns'
  `reads`/`writes` stay out. §3.
- **D3 — construction kwargs as writes:** treat `Cls(field=…)` as a `write` to `Cls.field`? (Recommended yes —
  it's how dataclass fields are most often set; it's what made the G16 rename 9 sites, not 6.)
- **D4 — P0 scope:** is the honesty fix (unknown vs none) worth shipping standalone ahead of extraction?
  (Recommended yes — closes the misleading half of #1 immediately.)
