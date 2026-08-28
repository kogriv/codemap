# Gap — a result limit is partiality, and codemap does not say so

**Found:** 2026-08-28, during the R2 разбор of [CodeGraph](../research/tools/codegraph.md).
**Backlog:** R1-C28. **Design:** decided inline below (§4) — small enough not to need its own doc.
**Status:** ✅ closed 2026-08-28 — `codemap/serve/limits.py`, 21 tests in
`tests/test_r1c28_limit_envelope.py`, documented in [`docs/accuracy.md`](../docs/accuracy.md) §(c).
Three things the fix decided that §4 had not: `semantic` reports `total: null` honestly (the adapter
applies the limit upstream, so the pre-limit total is *not observable* — and it is counted on the raw
hits, since dedup is not truncation); the MCP transport's own `shown`/`total` dialect was folded into
the same block; and `tests`/`covers` emit it too, though they already told the truth in their body —
one vocabulary beats a per-op dialect. The upstream half is [#1639](https://github.com/colbymchenry/codegraph/issues/1639), still open.

## 1. How it was found — in someone else's tool first

The first T2 measurement against CodeGraph returned exactly **20** callers of `MACDZoneAnalyzer`,
every one of `kind: "file"` at `startLine: 1`. Read at face value that is a clean finding: *CodeGraph
models callers as file-import fan-in, like GitNexus, not as call sites.* It would have gone in the
card, in the comparison matrix, and eventually in a post.

It is false. `codegraph callers --limit` defaults to `20`, the file-kind rows sort first, and the
default cut the answer **exactly along the line that misrepresents the model**. At `--limit 500` the
same query returns 79 entries — 55 methods, 3 functions, 21 files — a genuinely symbol-level answer
whose symbol half is a strict superset of codemap's.

Nothing in the payload said so. The JSON is `{symbol, callers}`: no total, no `truncated` flag, no
`limit` echo.

Two guards caught it, and both were luck rather than design: the number 20 is suspiciously round, and
this project has been burned before by a default that silently degraded a rival (graphlens's bundled
`ty` off `PATH`, blog post 1).

## 2. Then the same question, asked of codemap

`Session.handle({"op": "search", "args": {"term": "zone"}})` on the R2 benchmark graph:

```
search 'zone'  limit=default(50)  ->   50 hits;  envelope = {'ok': True}
search 'zone'  limit=5000         -> 1259 hits
```

**50 of 1259, and the envelope is `{"ok": true}`.** No total, no marker, no echo of the limit that
produced the cut — the identical defect, in the op documented as *"the discovery entry point (F9) …
for a cold agent that does not yet know exact names."* The one op whose entire job is to tell an agent
what exists is the one that silently answers with 4% of it.

Affected surfaces:

| Surface | Default | Marker today |
|---|---|---|
| `search` (serve op / MCP tool) | `limit=50` | none |
| `semantic` (serve op / MCP tool) | `limit=10` | none |
| `codemap semantic` (CLI `--limit`) | `10` | none |

`pack` also bounds its output (`budget=2000`), but that is a budget the caller sets on purpose and the
result is explicitly a *pack*; it is not in scope here.

## 3. Why this is the same class as `risk: "none"`

codemap's standing commitment is **resolved-or-honestly-flagged**: an approximation may be lossy, but
the answer must say that it is. `_PARTIAL_OPS` already stamps `epistemic: "partial"` on the seven ops
whose *resolution* is a lower bound.

A limit is a second, independent source of lower-boundness, and it is invisible to that machinery.
`callers` is in `_PARTIAL_OPS` and would be flagged; `search` is not in it and takes a limit, so it is
flagged by nothing at all. The consequence is the familiar one, one notch weaker than the confident
empty: a **confident partial** — an answer that is complete-looking, wrong for the question asked, and
carries no way for the caller to detect it.

This is the eighth application of that discipline, and the first found by measuring a competitor and
then turning the same probe on ourselves.

## 4. Decision

**Every op that can truncate says so, in the envelope, always** — not only when truncation happened,
because "the field is absent" is itself ambiguous to a cold agent.

Add to the response envelope of any op that accepts a limit:

```json
{"ok": true,
 "result": [...],
 "limit": {"applied": 50, "returned": 50, "total": 1259, "truncated": true}}
```

- `total` is the pre-limit count. `search` computes the full list before slicing, so this is free; if
  an op ever cannot afford the count, it must say `"total": null` rather than omit the block — an
  unknown total is a fact, not a gap.
- Emitted **whenever the op accepts a limit**, with `truncated: false` when everything fit. A caller
  must never have to distinguish "not truncated" from "this build doesn't report truncation".
- Orthogonal to `epistemic`. An answer can be resolution-partial *and* limit-truncated; the two say
  different things and both belong.
- The CLI prints a one-line footer on truncation (`… 50 of 1259 shown — pass --limit to widen`).
- **No schema change** — this is an op envelope, not `graph.json`.

Rejected: raising the defaults instead. A bigger default moves the cliff, it does not remove it, and
the whole point is that the caller cannot see a cliff it is not told about.

## 5. Acceptance

- `search` with more hits than the limit returns `truncated: true` and the true `total`; with fewer,
  `truncated: false` and `total == returned`.
- `semantic` likewise, and its adapter-absent path still emits the block.
- A test that fails if a new op gains a `limit` argument without the envelope block — the rule outlives
  this fix only if something enforces it.
- The CLI footer appears on truncation and not otherwise.
- Docs: `docs/` and the MCP tool descriptions state that a limited op always reports its limit.

## 6. What this does not cover

- `pack`'s token budget (deliberate, and its result is self-describing).
- `impact --depth` — a depth bound is a *scope* choice, already echoed in the answer as `by_distance` /
  `max_distance`. Worth re-reading once this lands, but not obviously the same defect.
- Whether CodeGraph's author agrees. 400 upstream issues were scanned, no duplicate found (the adjacent
  [#1512](https://github.com/colbymchenry/codegraph/issues/1512) is a different defect in the same
  function), and the report is filed as
  [#1639](https://github.com/colbymchenry/codegraph/issues/1639). **No response yet.**

## 7. What was checked before deciding to report it — and what was dropped

Both halves of this were re-verified before anything went upstream, because the first reading of the
external half was wrong and a second wrong reading would be worse.

**Kept, and filed as [#1639](https://github.com/colbymchenry/codegraph/issues/1639).** Root cause read
in the source (`src/bin/codegraph.ts`, MIT, `6a056ec`): `options.limit || '20'` at :1957,
`allCallers.slice(0, limit)` at :1991 with `allCallers.length` in scope and discarded, the envelope at
:1994, and — decisively — `Callers of "${symbol}" (${limited.length})` at :1998, which prints the
truncated count *as* the total. Reproduced on five symbols of a real package; on two of them the
default returns zero symbol-level callers. Same shape in `callees`; `query` cuts 909 to 10 into a bare
array. And the project's own flagship `explore` already marks elisions with `+N more` — so this fails
on its author's standard, not on an imported one.

**And building the minimal repro for that issue corrected us again.** In a 26-file synthetic project
the survivors of the cut are all `function`, not `file`. So "the file rows sort first" was never a
property of the tool — it is edge-insertion order, and bquant merely happened to order that way. The
mechanism claim gets weaker and the defect gets stronger: what a truncated answer drops is **arbitrary
with respect to kind**, so a consumer cannot tell a complete answer from a slice of one. The filed
issue says that, and explicitly does not ask for any particular ordering. Third time in this track that
writing the repro changed the finding.

**Dropped.** The neighbouring observation — that `query` carries a wall-clock `updatedAt` per node, so
two builds of identical source differ — is factually confirmed (set from `Date.now()` at index time;
never read in any `WHERE`/`ORDER BY`; not file mtime, since the stagings were `copy2`-ed and their
mtimes match). It is **not being filed.** CodeGraph claims byte-for-byte parity only between its Rust
kernel and its reference engine, and that claim holds; run-to-run answer reproducibility is codemap's
commitment, not theirs. Reporting it would be scoring another project against a rubric it never signed.
The distinction is the point: *a finding is reportable when it fails the author's standard, and merely
describable when it fails only ours.*
