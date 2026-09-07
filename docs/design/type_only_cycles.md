# Design — A cycle has three kinds, by the weakest scope that closes it

**Status:** ✅ **shipped** (2026-09-07, no schema change — the graph already carries
`extras.scope`). Acceptance measured: bquant `6b17e35` 0 eager / 9 lazy / **1 type-only**
(`zones.cache ↔ zones.pipeline`; 0 / 10 on 0.0.13), codemap 0 / 0 / 0 with one `TYPE_CHECKING`
import, and the gap's toy green on both old rules, red only under the new one. **Motivates:** gap [type_only_cycles_2026-09-07](../../gaps/type_only_cycles_2026-09-07.md)
— [codemap#18](https://github.com/kogriv/codemap/issues/18), from the one consumer of three with both
cycle rules enabled. **Backlog:** R1-C49. **Revises:** [R1-C29](../../gaps/import_map_module_level_2026-08-28.md)
(two kinds) and [R1-C48](type_checking_imports.md) (which moved the third kind into the second).
**User docs:** [../architecture-contracts.md](../architecture-contracts.md).

**Guiding invariants (unchanged):** resolved-or-honestly-flagged, a report says what it did not judge,
absence means unmeasured (R1-C28), a gate you can walk around is not a gate.

R1-C29 split cycles in two because a lazy import is how a developer *fixes* an import cycle, and
counting the fix as the bug is wrong. R1-C48 then took `if TYPE_CHECKING:` out of the eager graph —
and dropped it into the lazy bucket, where the second rule was waiting. For the consumer with both
rules on, the release changed one red into another; and the reason the two do not belong together is
the reason `no_lazy_cycles` exists at all.

---

## D1 — Three kinds, partitioned by the weakest scope required

**Recommended: partition every cycle by the weakest import scope needed to close it.**

| kind | closes with | what it means | rule |
|---|---|---|---|
| eager | module-level edges alone | breaks at import time | `no_cycles` |
| lazy (runtime) | needs a function-local import | runtime coupling; the lazy import is a way *around* `no_cycles` | `no_lazy_cycles` |
| type-only | needs an import under `if TYPE_CHECKING:` | **no runtime dependency at all** — the modules name each other's types | `no_type_only_cycles` (new, default off) |

The partition is by requirement, not by presence: a cycle that closes through a function-local import
is **lazy** even when a `TYPE_CHECKING` edge also runs between the same modules. Otherwise a tree
could hide real runtime coupling by adding a type import — the walk-around this rule family exists to
refuse.

- **Alternative rejected: a disclosure line only** (the consumer's cheapest option, and the one they
  said they would take). It leaves the verdict wrong: a tree that wants `no_lazy_cycles` still has to
  give up the standard typing idiom. The line is worth having — and falls out of the split for free.
- **Alternative rejected: a mode flag on the existing rule** (`no_lazy_cycles = "function-local" | "all"`).
  A string-valued boolean, and it makes the *default* meaning of an existing rule ambiguous in every
  contract already written.

## D2 — `no_lazy_cycles` narrows; the strictness lost is opt-in again

On 0.0.13 a `no_lazy_cycles = true` tree had its type-only cycles gated. After this change it does
not, and `no_type_only_cycles = true` restores exactly that. This is a behaviour change to a rule
already in use by one consumer, so it is stated in the changelog rather than discovered: their gate
gets *less* strict, and the knob that makes it stricter again is named in the same line.

## D3 — Every consumer prints all three counts, always

`check` (green and red), `report architecture`, `report dependencies`, living docs and the JSON
payloads carry eager / lazy / type-only, zero included (R1-C28). One number covering two phenomena is
what the consumer objected to; three numbers that appear only when non-zero would be the same defect
in a new place.

## D4 — Mechanics

`Query` gains a third graph. `_imports_eager` (module-level) and `_imports` (everything) already
exist; between them goes `_imports_runtime` = module-level + function-local. Then

```
eager     = cycles(_imports_eager)
lazy      = cycles(_imports_runtime) - eager
type_only = cycles(_imports)         - cycles(_imports_runtime)
```

`lazy_import_cycles()` keeps its name and narrows; `type_only_import_cycles()` is new. Cost: one more
`simple_cycles` over a graph the size of the module count.

## Acceptance (R1-C49)

- The gap's toy: both old rules green, `no_type_only_cycles = true` red and naming only the
  `TYPE_CHECKING` pair.
- A cycle closed by a function-local import **and** carrying a `TYPE_CHECKING` edge is lazy, not
  type-only (the walk-around test).
- bquant `6b17e35`: 0 eager, 9 lazy, 1 type-only (`zones.cache ↔ zones.pipeline`) — on 0.0.13 those
  were 0 and 10.
- codemap's own tree: 1 `TYPE_CHECKING` import, 0 type-only cycles, contract unchanged.
- Every consumer prints the three counts including zero.
