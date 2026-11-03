# Design — a contract the gate cannot fully read is refused, not partly enforced

**Status:** ✅ **shipped** (2026-11-03, no schema change), with acceptance reconciled below. Pre-registered in 4734368 before any code. **Motivates:** gap
[contract_silent_passes_2026-11-03](../../gaps/contract_silent_passes_2026-11-03.md), rows P1–P2d.
**Backlog:** R1-C69. **Precedent:** [R1-C27](../../gaps/unverified_claims_2026-08-27.md): one missing
`]` turned a failing gate green. The file is now read, but its *meaning* still is not checked.

## The defect, measured in the probe

`parse_contract` reads the keys it knows with `section.get(...)` and coerces their values:

| `[architecture]` | answer today |
|---|---|
| `forbiden = [...]` alone | "No `[architecture]` contract found … nothing to enforce", exit 0. The section exists |
| `forbiden = [...]` + `no_cycles = true` | "Rules enforced: no_cycles", exit 0. The typo is never named |
| `forbidden = [{from="core", too="analysis"}]` | "No contract found", exit 0 |
| `independent = [["core"]]` | "No contract found", exit 0 |
| `no_cycles = "false"` | the rule is **on**, because `bool("false")` is True |
| `layers = "core"` | four layers `c`, `o`, `r`, `e`, shown as absent names, exit 0 |

grafema's version of the same thing is a predicate typo that passes (filed upstream as #484). Ours
is worse in one respect: nothing promised a warning, so nothing gave one.

## D1 — validate the whole section against a closed schema

Known keys: `layers`, `independent`, `forbidden`, `no_cycles`, `no_lazy_cycles`,
`no_type_only_cycles`, `exhaustive`, `no_phantom_rules`.

| key | must be |
|---|---|
| `layers` | a list of strings |
| `independent` | a list of lists, each with ≥ 2 strings |
| `forbidden` | a list of tables, each with exactly the string keys `from` and `to` |
| the five flags | TOML booleans: `true` or `false`, not strings or numbers |
| `[architecture]` itself | a table |

An unknown key is an error, and the message suggests the closest known key (`difflib`, cutoff 0.6).
An empty list stays valid; it is an empty rule, as today.

## D2 — any problem refuses the whole contract (exit 2), and every problem is named

**Recommended:** a contract with any invalid part is not enforced at all. It is reported through the
existing `ArchitectureContract.error` path, the one R1-C27 built for an unreadable file:
- the CLI exits 2;
- MCP returns `ok: false` with `contract_error`;
- the renderer says "Contract not read — nothing was enforced".

The message lists **all** problems, each with its key (and item index), not just the first.

- **Rejected: enforce the valid rules and warn about the rest.** That is exactly the P1b case: a
  green tick over a contract whose author wrote a rule the gate never ran. Partial enforcement is a
  partial pass, and the class of defect this fixes.
- **Rejected: a warning with exit 0.** The status of a gate answers "may the pipeline proceed?". A
  contract the gate did not understand is not a yes.
- **Rejected: a new exit code.** For the R1-C27 reason: existing `if rc == 2` pipelines would sort
  it into success.
- **Cost, accepted: forward compatibility.** A contract that uses a key from a newer codemap is
  refused by an older one. For a gate that is the correct answer: it cannot enforce a rule it does
  not know. The message names the key, so the cause is one line away.

## D3 — names that do not exist stay as they are

A layer or module name that is absent from the graph is a *meaning* question, not a schema one.
R1-C62 already reports it as "declared vs applicable", and refuses only with `no_phantom_rules`. Not
changed.

## Pre-registered acceptance (committed before the code)

- **V1–V6, the probe's rows plus one.** Each with exit 2 and the message as stated:

  | | `[architecture]` | the message names |
  |---|---|---|
  | V1 | `forbiden = [...]` | `forbiden`, "did you mean `forbidden`" |
  | V1b | `forbiden = [...]` + `no_cycles = true` | `forbiden`. Exit 2 although `no_cycles` alone is valid |
  | V2 | `forbidden = [{from="core", too="analysis"}]` | `forbidden[0]`, the unknown `too` and the missing `to` |
  | V2b | `independent = [["core"]]` | `independent[0]`, "at least 2" |
  | V2c | `no_cycles = "false"` | `no_cycles`, "true or false" |
  | V2d | `layers = "core"` | `layers`, "list of strings" |
  | V3 | `architecture = 1` at the top level, not a table | `[architecture]`, "a table"; no traceback |
  | V4 | V1 and V2c together | both problems, in one message |

- **V5, MCP.** The `check` op on V1 returns `ok: false`, with `contract_error` naming `forbiden`.
- **V6, controls, no change on valid contracts.**
  - `codemap check --build` output on bquant (`8efa112`, its own `codemap.toml`) is byte-identical
    before and after.
  - The same for codemap's own tree and contract.
  - bquearch's `[architecture]`, read from its checkout, parses to the same contract before and after.
  - P3 (an absent name) and P4 (no contract) answer exactly as before.
- **V7, mutation.** With the unknown-key check removed, V1 exits 0 again. With the type check
  removed, V2c enables the rule again. Each is a test that goes red.

At least one expectation fails if nothing is done: V1–V4 all exit 0 today (measured in the probe).

## Acceptance reconciled (2026-11-03)

| | expected | measured | |
|---|---|---|---|
| V1–V4 (8 rows) | exit 2, the named key or index in the message | all 8: exit 2, "Contract not read — nothing was enforced", each needle present. V4 names both problems in one line | holds |
| V5 | MCP `ok: false`, `contract_error` names `forbiden` | so | holds |
| V6 bquant | `check` output byte-identical | identical, exit 0 both | holds |
| V6 codemap | byte-identical | identical, exit 0 both | holds |
| V6 bquearch | parses to the same contract | same, no error (read from its checkout, parse only) | holds |
| V6 P3, P4 | as before | absent name: "1 declared, 0 applicable", exit 0; no contract: exit 0 with the path | holds |
| V7 | each mutation red | both in-test mutations red. With `arch.py` reverted, 11 of 13 new tests fail; the 2 that pass are the "as before" tests | holds |

Suite: 1079 passed, 3 skipped (1065 + 14).

**Changed besides the code:**
- `test_parse_contract_shapes` (R1-C3) pinned the old behaviour: "<2 members dropped", "malformed
  dropped". It is split. The valid shape is parsed as before, and the old malformed input now
  refuses the contract and names both items.
- `docs/architecture-contracts.md` still said that a malformed `codemap.toml` "yields an empty
  contract (a no-op success)". That was untrue since R1-C27 (exit 2) and is corrected here. It is
  doc drift from August, found while writing this.

**Surprises:** the stale sentence above. No surprise in the measurements.
