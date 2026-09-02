# Attribute access edges (field-level impact)

codemap models relationships between *symbols* (calls / imports / inherits / …) and
between functions and *string-keyed columns* (`reads` / `writes`, dataflow). R1-C20
adds the missing layer: **attribute access** — which functions read or write a class
field — so `impact` on a field answers truthfully instead of the old affirmative lie.

Before, `impact` on a class attribute returned `refs: []` and `risk: "none"` even when
the field had many real read/write sites: attribute nodes existed, but nothing in the
graph pointed at them (see `gaps/attribute_impact_gap_2026-08-22.md`, issue #1).

## The `accesses` edge

A closed-vocabulary edge (`model.EDGE_TYPES`) from a **function → the `attribute`
node it touches**, carrying:

- `extras.access` — `read` or `write`
- `extras.resolution` — how the target was resolved (below)

Only edges whose target is a real `attribute` node are emitted — never an edge to
nothing (the soundness rule). A method call (`obj.foo()`) is a `calls` edge, not an
access; a `@property` is an *attribute* node in griffe, so reading `obj.prop` is an
`accesses` edge — the only layer that can capture a property-read dependency.

## Resolution tiers

| Form | Example | `resolution` | Tier |
|---|---|---|---|
| `self.field` / `cls.field` | `self.width`, `self.width = 0` | `self` | fast (`ast`) |
| `ClassName.field` | `Config.width` | `class` | fast |
| construction kwarg | `Config(width=5)` → write to `Config.width` | `construct` | fast |
| `obj.field` on a typed local | `c = make(); c.width` | `deep` | deep (`jedi`) |
| `obj.field`, `obj` untyped | `x.field` (x unknown) | — (unresolved counter, no edge) | — |

The fast tier is pure stdlib `ast` (sub-second, byte-stable); the deep tier
(`--deep` / `deep=True`) infers the receiver's type with jedi to resolve `obj.field` — and
is [not byte-stable](provenance.md#the-deep-tier-is-not-byte-stable): the same inference
that resolves a receiver in one build can come back empty in the next.
Per-function `extras.attr_access` records `out` / `resolved` / `unresolved` counts, so
the graph reports its own coverage — attribute access is a **lower bound**, like calls.

## Querying

```bash
codemap query width --build ./pkg      # dossier: "read by …", "written by …"
```

Over serve / MCP:

- `accessors(attribute)` → `{reads: [funcs], writes: [funcs]}` (the attribute analog
  of `column`).
- `impact(attribute)` now spans `accesses`, so a field's blast-radius is real.

`Query.readers(attr)` / `Query.writers(attr)` are the programmatic surface.

## Honesty

`impact` on an attribute with **no modelled accessor** reports `risk: "unknown"` (with
a `risk_reason`), never `none`: attribute access is best-effort, so "no accessor found"
is a lower bound, not proof nothing depends on the field. For a function or class an
empty blast-radius stays the honest `none` — the call/reference layer *does* target
them. Columns' `reads` / `writes` deliberately stay out of impact (a column is a data
key, not a symbol whose change breaks a caller); `accesses` targets attributes only, so
extending impact to it never touches non-attribute blast-radius.
