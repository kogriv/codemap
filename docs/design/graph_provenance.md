# Design — Graph provenance: the artifact says what produced it

**Status:** ✅ **shipped** (2026-08-25, schema **0.11 → 0.12**).
**User docs:** [../provenance.md](../provenance.md).
**Decisions resolved:** D1 = **yes** (top-level block, bump, no clock), D2 = version always + commit when
resolvable, D3 = **warn, never refuse** (routed through `diagnostics.py`, so CLI/`stats`/reports get it at
once), D4 = **yes** (comparability header + envelope field), D5 = enforced — `build_provenance` raises on an
absolute path, D6 = split as tabled, D7 met. **Unforeseen:** `--incremental` shared the same blind spot and
needed the same guard (gap §6).
**Motivates:** gap [graph_provenance_2026-08-25](../../gaps/graph_provenance_2026-08-25.md).
**Backlog:** R1-C25. **Blocks:** R1-C23 D2 and D6 (both need a carrier).
**Related design:** [scope.md](scope.md) (`scope_id` — the input identity this makes portable).

A `graph.json` is a claim: *this is the shape of that source tree, as read by this tool*. It records the
claim and drops both qualifiers. The fix is small and the sequencing matters — two other milestones are
waiting on the carrier.

**Guiding invariants (unchanged):** source-only, **deterministic**, two tiers, resolved-or-honestly-flagged,
canonical timestamp-free serialization (DESIGN §2.2).

The determinism invariant is the sharp constraint here: provenance must be **content identity, never clock
time**. Anything that varies between two builds of the same tree cannot go in the file.

---

## D1 — A `provenance` block inside `graph.json`

**Recommended: yes. Top-level key, schema `0.11` → `0.12`.**

```json
{
  "codemap_schema": "0.12",
  "target": "bquant",
  "provenance": {
    "tool": {"name": "codemap", "version": "0.0.2", "commit": "16fe7de"},
    "tier": "fast",
    "scope_id": "sha256:7877…",
    "source": {"vcs": "git", "commit": "6bbb142", "dirty": false},
    "roots": {"core": "bquant", "consumers": ["tests"], "docs": ["docs"]}
  },
  "nodes": [], "edges": []
}
```

- **Top-level, not per-node.** It is one fact about one build.
- **No `built_at`.** Two builds of a frozen tree must stay byte-identical; a timestamp destroys exactly the
  property this block exists to make checkable. The clock stays in the sidecar.
- **Rejected: a second file next to the graph.** That is the sidecar, and §3 of the gap is the list of
  reasons it does not travel.
- **Rejected: no bump, hide it in an existing key.** The gap's §2 argument runs the other way — the version
  field is *for* shape changes, and a new top-level key is one.

## D2 — `tool.version` is not enough; record a build identity

**Recommended: `version` always, `commit` when resolvable, and never fabricate either.**

The evidence forces this: the two graphs in the gap's §2 differ by 8 edges and 5 dead-code verdicts, and
**both were built by version `0.0.2`** — the package version has not moved across any of R1-C20…R1-C22.
Version alone would have identified them as the same tool.

- `version` — from `importlib.metadata.version("codemap")`, always present.
- `commit` — `git rev-parse --short HEAD` **in the tool's own checkout**, when codemap is running from a
  source tree. From an installed wheel there is no commit; the field is then **absent**, not `"unknown"` and
  not a guess.
- **Rejected: hashing the extractor's source** as a substitute build id. It is deterministic and it *would*
  have separated the two graphs — but it changes on a comment edit, so it cries wolf, and it is opaque to a
  human reading the file. `commit` when we have it, honest absence when we do not.

**Consequence to accept:** a wheel-installed codemap produces graphs whose only tool identity is a version
that moves rarely. That is a real limit and the answer is release discipline, not a fabricated field. State
it in the user docs.

## D3 — Enforce `codemap_schema` on load

**Recommended: load, but never silently.**

Today `Graph.from_dict` and `store.load` ignore the field completely.

| loaded schema vs running | behaviour |
|---|---|
| equal | silent, as now |
| **older minor** | load + **warning** naming both versions and the consequence: *"this graph predates edge/semantic changes; reports may differ from a fresh build"* |
| **newer than the running tool** | load + **warning** — an old tool reading a new file will silently drop nothing today (unknown keys are ignored), but the reader must know the tool is behind |
| unparseable / missing | **warning**, treat as pre-0.12 |

- **Rejected: refuse to load on mismatch.** Every stored graph in existence is 0.11 or older; refusing turns
  an upgrade into an outage, and the honest thing here is a labelled answer, not no answer (R1-C13).
- The warning must reach the same three surfaces the R1-C21 diagnostics reach: CLI stderr, `stats`, and the
  `serve`/MCP envelope — an agent is the consumer most likely to be handed an old file.

## D4 — `diff` compares provenance before it compares symbols

**Recommended: yes — a header, and a warning when the pair is not comparable.**

`codemap diff` exists to compare two snapshots and currently accepts any pair. Two graphs built by different
tool versions, on different tiers, or over different scopes are not a before/after of the *code*.

- Print the pair's provenance as a header (tool, tier, scope_id, source commit).
- When `tool.commit`/`version`, `tier` or `scope_id` differ, emit a **warning**: *"these graphs were built by
  different tools / on different tiers — differences below may be tool changes, not code changes"*.
- **Do not refuse.** Comparing across an upgrade is a legitimate thing to want; being told is what was
  missing. The gap's §2 pair is exactly this case, and `diff`'s "✅ no breaking changes" was true and useless.

## D5 — The artifact stays publishable: no absolute paths, ever

**Recommended: hard rule, enforced by a test.**

The sidecar records `cwd`. Under AGENTS.md an absolute personal path must not appear in anything shared, so
the sidecar is the one file that cannot be published — a bad home for data meant to travel.

The `provenance` block therefore carries **repo-relative roots only**, and a test asserts that a serialized
graph contains no absolute path (no leading `/`, no drive letter) anywhere in `provenance`. Cheap, and it
keeps a whole class of leak out of an artifact people are meant to attach to tickets.

## D6 — The split: identity travels, the recipe stays home

**Recommended: an explicit division, documented once.**

| lives in `graph.json` (`provenance`) | lives in `*.meta.json` (sidecar) |
|---|---|
| tool name / version / commit | `argv` — the exact invocation |
| tier | `built_at` — wall clock |
| `scope_id`, roots (relative) | `cwd` — absolute, machine-local |
| source vcs commit + dirty | per-file hash list (large, and a rebuild input) |

Rule of thumb: **identity** goes in the graph, the **rebuild recipe** stays in the sidecar. `codemap refresh`
keeps working unchanged; `scope --diff` keeps reading the sidecar's file list.

**One duplication is deliberate:** `scope_id` appears in both. In the graph it is identity ("which input was
this"); in the sidecar it is a cache key for `--incremental`. Same value, two jobs.

## D7 — Acceptance

1. **Determinism first.** Two builds of a frozen tree are byte-identical *including* `provenance`. This is
   the invariant most at risk from this change and it gets the first test.
2. The gap's §2 experiment inverts: loading the `4858899` graph with the current tool produces a **visible
   warning**, and `diff` on the pair says the graphs are not comparable.
3. No absolute path anywhere in a serialized graph (D5 test).
4. `provenance.tool.commit` is absent, not fabricated, when codemap runs from an installed wheel.
5. Every existing 0.11 graph still loads, with a warning — no stored artifact is orphaned.
6. R1-C23's D2 (skipped files) and D6 (graph↔scope cross-check) have the carrier they need.
