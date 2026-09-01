# tools/ — per-tool разбор cards

One card per tool (`<tool-slug>.md`), following the template below. Convention and rules:
[../README.md](../README.md#the-разбор-convention-codemap-native). Rolled up in
[../comparison.md](../comparison.md).

Copy the template, fill every section. Leave a field explicitly **"not checked"** rather than blank —
the honest boundary is part of the finding. Record exact versions / commit hashes / commands so numbers
reproduce.

**Scope parity is mandatory.** Every hands-on card measures on the shared R2 benchmark scope
([`_scope/bquant.scope.json`](_scope/bquant.scope.json)) and records its `scope_id` in the **Scope** field.
Two cards are only comparable when their `scope_id` matches — the [comparison hub](../comparison.md) asserts
this. codemap and file-list-capable tools run **in place**; tools with unreliable excludes (venv trap) get a
byte-identical staging via [`_scope/materialize.py`](_scope/materialize.py) (see
[design §3](../../docs/design/scope.md)).

**The spec's `root` points at the live dogfood checkout, which has moved past the pinned commit.**
Materializing from it now resolves a *different* `scope_id` — the harness prints a warning and continues, so
the failure mode is a card that is quietly not comparable. Since 2026-09-01 the working procedure is to
extract the pinned tree first and materialize from that:

```bash
git -C ../bquant archive cb89a24 | tar -x -C /tmp/bquant_cb89a24     # read-only on the target repo
.venv/bin/python research/tools/_scope/materialize.py \
    research/tools/_scope/bquant.scope.json /tmp/staging --root /tmp/bquant_cb89a24
# expect: canonical scope_id sha256:300e0a01… + "verify: staging scope_id == canonical ✓"
```

`scope_id` is content-derived, so the extracted tree round-trips to the same id as the original git-mode
resolution. Check both lines of that output before recording the id in a card.

---

## Template

```markdown
# <Tool name>

**Verdict:** integrate | wrap | learn-only  ·  **Feeds:** R1-C…  ·  **Card status:** desk | hands-on

**Scope:** `sha256:…` (R2 benchmark `bquant.scope.json` — 280 files, 207 .py / 73 .md, bquant@<commit>) ·
run mode: in-place | materialized

## Identity
- Repo / site:
- License:
- Last commit / release:
- Stack / language:
- Install (exact command):  ·  reproduced? (yes / no + why)

## What it is
Mechanism (AST / tree-sitter / embeddings / graph?), data model, interface (CLI / MCP / lib / SaaS),
source-only vs needs-build, deterministic?

## Coverage vs codemap
Which of codemap's capability axes it has (+ any it has that codemap lacks). One row for comparison.md.

| Capability | codemap | this tool |
|---|---|---|
| symbol lookup (T1) | ✅ | ? |
| callers/callees (T2) | ✅ | ? |
| impact / blast-radius (T3) | ✅ | ? |
| signature-change surface (T4) | ✅ | ? |
| architecture / layers (T5) | ✅ | ? |
| determinism | ✅ | ? |
| MCP | ✅ | ? |
| languages | Python | ? |
| license | MIT | ? |

## Hands-on measurements (target: bquant)
Same five tasks; codemap's answer is the ground-truth reference. Record correct? / cost / latency / deterministic?

| Task | Correct? | Cost (tokens/calls) | Latency | Deterministic? | Notes |
|---|---|---|---|---|---|
| T1 where defined (`analyze_zones`) | | | | | |
| T2 callers (`MACDZoneAnalyzer`) | | | | | |
| T3 impact (`MACDZoneAnalyzer`) | | | | | |
| T4 sig-change (`analyze_zones`) | | | | | |
| T5 architecture | | | | | |

## Quality (on the covered part)
accuracy · determinism · cost · speed · setup friction · language coverage · license · interface · honesty-of-claims.

## Разбор
- **What we'd take** (with where from):
- **What we'd do differently and why** (the "why" is mandatory):
- **What the author knows that we didn't** (the most valuable part):
- **What we did NOT check** (honest boundary):

## Verdict & backlog effect
integrate / wrap / learn-only, one line why. Which R1-C it confirms, reranks, or adds.
```
