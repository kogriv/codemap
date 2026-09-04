# Design — A name defined twice in one scope is a finding, not a duplicate edge

**Status:** 🟡 **proposed** (2026-09-04, no schema change — one new open `extras` key).
**Motivates:** issue [#16 §5](https://github.com/kogriv/codemap/issues/16) — a consumer found one
`contains` record twice in their graph and, behind it, a method their class defined twice; gap
[deep_tier_union_by_repeat_2026-09-04 §5](../../gaps/deep_tier_union_by_repeat_2026-09-04.md).
**Backlog:** R1-C46.
**Related:** [attribute_edges.md](attribute_edges.md) (R1-C13 — an edge must point at a real node; this is
the mirror: an edge must come from a body that can run).

The consumer offered two options: deduplicate `contains` by full key, or — "more useful" — report a
repeated definition in one scope as a finding. Measured on a toy package, the choice is not between the
two: the duplicate edge is the *least* of what a shadowed definition does to the graph.

**Guiding invariants (unchanged):** source-only, deterministic, resolved-or-honestly-flagged, closed edge
vocabulary, `extras` open-ended.

---

## What a shadowed definition does today

```python
def one(): return 1
def two(): return 2

class Thing:
    def get(self): return one()   # line 8  — can never run
    def get(self): return two()   # line 11 — the live one
```

| layer | behaviour | consequence |
|---|---|---|
| griffe (core package) | `members` is a dict by name; the **last** definition wins (`lineno 11`) | the first body vanishes — no node, no diagnostic, nothing to grep for in the artifact |
| consumer-root walk (`_materialize_defs`) | one node per `def`, same id twice, the second overwrites the first; **one `contains` edge per `def`** | the duplicate record the consumer saw |
| behavioural passes (`_named_functions`, `_named_functions_scoped`) | walk **both** bodies and attribute both to the one surviving node | `Thing.get` carries `calls → one` **and** `calls → two`; its `calls` counter (`out: 1, resolved: 1`) describes the second body only |

The third row is a **phantom edge**: the graph says `get` calls `one`, which no executed code does.
`impact(one)` answers "one caller"; `dead-code` will not list `one`. That is R1-C13's class — an edge
that does not correspond to code — from the other side: not an edge to nothing, an edge from nothing.

## D1 — Process the live body only; record what it shadowed on the surviving node

**Recommended: yes.** The walkers (`_named_functions`, `_named_functions_scoped` in `behavior.py`; `_defs` in
`roots.py`) already produce the full list of definitions per module. One shared step dedupes it: for each
definition id, the **last unconditional** definition is the live one; earlier unconditional definitions of
the same id are dropped from the walk and their line numbers recorded as `extras.shadows: [lineno, …]` on
the surviving node (sorted, ascending). Classes are handled the same way at the class node: a class defined
twice keeps its later body; the earlier body's methods are not walked at all.

- **Core package:** griffe already picked the last body; the node exists; the walk now agrees with griffe
  and stops emitting the earlier body's edges. `extras.shadows` is set by the behavioural pass, which is
  where the AST is in hand.
- **Consumer roots (`--mode full`):** `_materialize_defs` emits one node and **one** `contains` edge per id
  and sets `shadows` the same way. Byte-identical for every tree without a duplicate.
- **No schema bump.** `shadows` is an open `extras` key on function and class nodes, absent when nothing is
  shadowed — the same convention as `seen` (D7) and every extras key since 0.11.

"Unconditional" means a direct statement of the module body or the class body. A definition under `if`,
`try`, `with`, `match`, `for` or `while` — `if TYPE_CHECKING:` / `try … except ImportError` fallbacks — is
conditional on both sides: it neither shadows nor is shadowed, and both bodies keep being walked as today,
which for a genuinely conditional pair is the honest over-approximation.

## D2 — Three idioms are re-binding, not shadowing, and are exempt by rule

**Recommended: exempt exactly these, by decorator, nothing heuristic.**

| idiom | who is exempt | why |
|---|---|---|
| `@overload` / `@typing.overload` on the **earlier** definition | the earlier one is a declaration for the type checker; the implementation that follows is the only body | the one repeated definition in codemap's own tree is this fixture (`hardpkg/modern.py`) |
| `@name.setter` / `.getter` / `.deleter` on the **later** definition | property accessors rebind the same name on purpose | every `property` with a setter would otherwise be a finding |
| `@f.register` on the later definition, or a definition named `_` | `singledispatch` registration conventionally reuses `_` | same |

Exempt pairs are walked as today (both bodies), and no `shadows` is written. The list is closed and short
on purpose: a rule that needs tuning against real trees is a heuristic, and this finding must be a
certainty or it is worth less than the duplicate edge it replaces.

## D3 — Surface it as a certain finding in `report dead-code`

**Recommended: a separate section and a separate list, not a graded candidate.**

`dead_code()` grades **private functions with no inbound resolved call** into `high`/`medium`/`low` and
the report is captioned "candidates, not proof". A shadowed body is not a candidate: it cannot run, and no
inbound edge changes that. Mixing it into the graded list would either mislabel it (`high` still reads as
"probably") or force a fourth confidence level whose only member is this. So:

- `Query.shadowed_definitions()` → `[{id, root, file, lineno, shadows: [lineno, …]}]`, sorted by id.
- `build_dead_code` adds `"shadowed": [...]`; `render_dead_code` renders a section **"Shadowed
  definitions — certain"** ahead of the graded candidates, one line per symbol: *`pkg.Thing.get` — defined
  at line 11 shadows the definition at line 8; the earlier body can never run.* The section is omitted when
  the list is empty, like the consumer-entrypoint block.
- The symbol's dossier already exposes `extras`, so `query` shows `shadows` with no further plumbing; the
  MCP `report` tool serves the same markdown.

- **Alternative rejected: a graph-level diagnostic.** Diagnostics say what the *graph* cannot support; this
  is a fact about one symbol, and it belongs beside the other per-symbol findings.
- **Alternative rejected: only deduplicate `contains`.** That fixes the consumer's symptom and leaves the
  phantom `calls` edge and the vanished body in place — the two things that actually mislead a reader.

**Acceptance (R1-C46):** on the toy package above, `Thing.get` has exactly one `calls` edge (to `two`),
`extras.shadows == [8]`, and `calls.out == 1`; as a consumer root in `--mode full` it has exactly one
`contains` edge; `report dead-code` lists it under the certain section; an `@overload` pair, a property
setter, a `_` singledispatch pair and an `if TYPE_CHECKING` pair each produce **no** `shadows` and keep both
bodies' edges; a mutation that restores the undeduplicated walk reddens the phantom-edge test, and that
test feeds an **actual** duplicate, not a fixture without one (R1-C37); bquant and codemap graphs are
byte-identical before and after on the fast tier (neither tree has a shadowed definition today — the
consumer's was fixed at their `db63b73`).
