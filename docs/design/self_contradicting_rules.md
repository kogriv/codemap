# Design — a contract rule that names one layer twice is refused

**Status:** 🟡 pre-registered (2026-11-05), no code. **Backlog:** R1-C79. **Found by:** the gate probe battery
(R1-C77, [`gate_probe_battery.md`](gate_probe_battery.md), probes C11, C13, C14). **Reference:** import-linter
rejects repeated layers (their #391, merged 2026-11).

## The defect

Measured on `main` (73a757e), fixture `gp` with `high/h.py` importing `mid.m` (down) and `mid/m.py` importing
`high.h` (up):

```
layers = ["high", "mid", "high", "low"]

❌ 1 rule(s) broken.
## `layered` — 1 import(s) point up the layer stack (high → mid → high → low)
- `gp.high.h` → `gp.mid.m`          ← the legal edge, named as the violation
                                      the real upward edge gp.mid.m → gp.high.h is not named
```

`check_contract` builds `rank = {name: i}`; the second `high` overwrites the first, so `high` ranks below `mid`
and the stack is inverted between them. In a tree where `high` does not import `mid`, the upward edge passes
green. My prediction (a silent pass) was right about the mechanism and wrong about this fixture: the gate was
red, for the wrong edge, and the battery test passed because it asserted only the exit code.

Two neighbours of the same kind:
- **C13** `forbidden = [{from = "low", to = "low"}]`: can never fire (rules read cross-layer edges), yet is
  counted applicable, `forbidden (1)`.
- **C14** `independent = [["low", "low"]]`: `applicability` counts members present *with repeats*, so one layer
  named twice passes "at least two members" and is counted applicable, `independent (1)`, for a rule that can
  never fire.

## D1 — refused by the schema (R1-C69 path)

`contract_problems` adds three problems:
- `layers` names a layer more than once → "`layers` repeats `high`";
- `independent[i]` names a layer more than once → "`independent[0]` repeats `low`";
- `forbidden[i]` has `from` equal to `to` → "`forbidden[0]`: `from` and `to` are both `low`".

Exit 2, "Contract not read — nothing was enforced", MCP `ok: false`. A contract that contradicts itself is not
a contract written ahead of the code (R1-C62's reason to keep inert rules); it has no reading under which it
means what it says.

## D2 — no other change

`applicability` keeps counting as it does. After D1 a repeated member can no longer reach it. No answer-format
change: the refusal is the existing error path, pinned under format 4.

## Pre-registered acceptance

- **A1** C11 fixture → exit 2, "`layers` repeats `high`", nothing enforced.
- **A2** C13 → exit 2, "`from` and `to` are both `low`"; C14 → exit 2, "`independent[0]` repeats `low`".
- **A3** battery probes C11, C13, C14 (marked `xfail(strict=True)` with this number before the fix) pass with
  the mark removed; every other probe as before.
- **A4** a valid contract is byte-identical: `RENDERED_SHA` unchanged; bquant (`aca0718`) and bquearch (HEAD)
  `check` output byte-identical before and after (neither repeats a name, read from their `codemap.toml`).
- **A5** mutation: removing each of the three checks turns its own test red; a cosmetic change leaves all green.

At least A1–A2 fail if nothing is done.
