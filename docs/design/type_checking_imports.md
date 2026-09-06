# Design — An import under `if TYPE_CHECKING:` is a third scope, not an eager edge

**Status:** 🟡 in progress (2026-09-06, no schema change — `extras.scope` is an open field, a new
value). **Motivates:** gap [type_checking_imports_2026-09-06](../../gaps/type_checking_imports_2026-09-06.md)
— [codemap#18](https://github.com/kogriv/codemap/issues/18): `no_cycles` red on a correct tree.
**Backlog:** R1-C48. **User docs:** [../architecture-contracts.md](../architecture-contracts.md),
[../hard-python.md](../hard-python.md).

**Guiding invariants (unchanged):** source-only, resolved-or-honestly-flagged, an import map that says
what each scope contributed (R1-C29), a gate that names what it did not judge (R1-C30-f2), absence
means unmeasured (R1-C28).

R1-C29 split the import graph in two because two questions were being answered with one number:
*is this a dependency* (every import) and *can this break at import time* (only imports that run
then). It knew two scopes, `module` and `function`. `if TYPE_CHECKING:` is a third: the import is
written at module level and never runs — not at import time, not later. griffe files it as
module-level; codemap's own AST pass looked only for what griffe misses; nobody looked at the
condition. So the edge landed in the eager graph and the gate failed on the idiom that exists to
make it pass.

---

## D1 — `scope: "type_checking"`, its own value

**Recommended: a third scope value, not a reuse of `"function"`.**

`function` says *where the import is written* and implies *runs when the function runs*. A
`TYPE_CHECKING` import runs never. Filing it as `function` would make `import_map.function_local`
count imports that no function contains, and a reader of the edge would look for a function that
is not there. Filing it as eager is the defect. The value names the construct.

- **Alternative rejected: drop the edge.** It is a dependency — the module's annotations name the
  other module's types; `dependents`, coupling and orphan detection want it (the R1-C29 argument,
  unchanged).
- **Alternative rejected: a boolean `lazy` beside `scope`.** Two fields for one axis; every
  consumer would have to read both.

## D2 — Precedence: the edge says how the dependency is reached at its *earliest*

One pair of modules may be imported several ways. The edge carries the strongest: `module` beats
`type_checking` beats `function`. R1-C29 already ordered module-level entries first so a pair
imported both eagerly and lazily reads as eager; the new value slots between.

## D3 — What is recognised, narrowly

| written | scope of the `if` body | of the `else` body |
|---|---|---|
| `if TYPE_CHECKING:` | `type_checking` | eager |
| `if typing.TYPE_CHECKING:` / `if t.TYPE_CHECKING:` (any attribute named `TYPE_CHECKING`) | `type_checking` | eager |
| `if not TYPE_CHECKING:` | eager | `type_checking` |
| `if TYPE_CHECKING or X:`, `if TYPE_CHECKING and X:`, anything else | eager | eager |
| any of the above **inside a function** | `function` | `function` |

Unrecognised conditions stay eager on purpose: a condition the tool cannot read is judged
strictly, never leniently — a gate that guesses "probably never runs" is not a gate.

## D4 — The eager graph excludes it; the lazy cycles include it

`Query._imports_eager` drops `type_checking` edges as it drops `function` ones. A cycle closed
only through such an import is still mutual coupling — the modules reference each other's
types — and reports where lazy cycles report: `lazy_cycles`, `no_lazy_cycles`. The five
consumers that say "closed only by a function-local import" now say "closed only by a non-eager
import (function-local, or under `if TYPE_CHECKING:`)".

## D5 — `import_map` gains `type_checking`, always

`{"module_level": n, "function_local": m, "type_checking": k}` — emitted by every consumer of the
import map, zero included (R1-C28): a reader must be able to tell "no such import here" from
"this build did not look". The `check` scope line reports the count of non-judged cycles as before
and adds how many `TYPE_CHECKING` imports were read.

## D6 — Mechanics

`_source_import_targets` (one AST pass per module with an indented import, already there) learns
to enter a module-level `if` whose test is a recognised `TYPE_CHECKING` form and to collect the
imports in the right branch with scope `type_checking`; it also returns the targets imported at
plain module level, so `_collect` can demote griffe's entry for a target that is imported **only**
under `TYPE_CHECKING`. The hint regex already matches an indented `from`/`import`, so the file is
parsed. Cost: the pass exists; the extra work is one set per module.

## Acceptance (R1-C48)

Measured, on the same tree the issue was filed from (bquant `6b17e35`, fast tier):

- `no_cycles = true` is green; the scope line names 1 `TYPE_CHECKING` import; `lazy_cycles` is 10
  (the `cache ↔ pipeline` pair moved from eager to lazy).
- Byte-diff against the graph built before the change: exactly one edge differs —
  `cache → pipeline` gains `extras.scope = "type_checking"`; nodes and every other edge identical.
- codemap's own tree: 1 such import (`serve/mcp_server.py`), its contract stays green, its lazy
  cycle count unchanged.
- Toy package covering every row of D3, with the mutation "the condition is not recognised"
  turning the tests red.
