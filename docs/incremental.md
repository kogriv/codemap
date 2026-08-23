# Incremental rebuild

A full **deep** extract of a large package is dominated by the jedi type-inference
tier — on bquant, ~93s of a ~97s build. Almost none of that work is needed after a
small edit. `codemap build --incremental` recomputes only the modules that changed
(and the few that depend on them) and splices the rest from the previous graph.

```bash
codemap build ./pkg -o graph.json --deep              # first build (full)
# … edit a couple of files …
codemap build ./pkg -o graph.json --deep --incremental
# [incremental] incremental: 2 module(s) recomputed
```

On bquant a one-file deep edit rebuilds in **~5s instead of ~60s** (~12×). Requires the
prior `graph.json` and its `graph.json.meta.json` sidecar (written automatically by any
`--out` build — it carries the M19.A input scope manifest); without them, or on a
different target, it falls back to a full build.

## How it works

The build splits cleanly by cost:

- **Cheap, whole, always fresh** — griffe load, definition nodes, structural edges
  (contains / imports / inherits / decorated_by / export), registry dispatch, family
  links, string-key dataflow. ~4s total, so it's simply redone every time and is
  therefore always correct.
- **Expensive, per-module** — the two jedi-sensitive passes (`calls` resolution and
  `accesses` resolution). These run only on the **affected** modules; the rest are
  spliced (their `calls`/`accesses` edges and per-function `calls`/`control`/
  `complexity`/`attr_access` extras) from the old graph.

**Affected modules** = the changed / added / removed modules, plus any module that
freshly imports a changed/added one, plus any module whose old behavioral edge pointed
into a changed/removed one. That covers fast-tier staleness (a renamed symbol an
importer resolves) and deep-tier staleness (jedi reaching a changed target). When the
affected set exceeds half the package a full rebuild is cheaper and certainly correct,
so the build falls back to it (reported as `mode: full`).

## Guarantees

- **Fast tier: byte-identical to a full build.** The incremental result serializes
  byte-for-byte the same as `codemap build`; the test suite pins this across edit / add
  / remove, and it holds on bquant (7437 edges, zero diff).
- **Deep tier: equivalent to a full build, subject to jedi's inference variance.** The
  splice itself is exact — proven byte-identical on a controlled fixture. But jedi's
  bounded type inference is **cache-warmth-dependent**, so *two full `--deep` builds of
  bquant already differ* from each other by a handful of deep-only edges (one resolves
  a chain the other's colder cache didn't). Incremental deep is therefore identical to a
  full deep build *up to that same intrinsic variance* — it introduces no divergence of
  its own, and is ~12× faster. If you need a reproducible deep graph, that's a property
  of the deep tier itself, not of incremental. The fast/structural layers are fully
  deterministic.
- **No-op is free.** If no package `.py` file changed, the old graph is returned
  untouched (`mode: unchanged`) — the hot path for a future file watcher (M3.2).
- **Scope-driven.** Change detection is the content-hash scope manifest (`codemap
  scope`), not mtimes — a touched-but-unchanged file triggers nothing.

## Serving a fresh graph without a restart

A long-lived `codemap serve` (or `serve --mcp`) caches the graph it loaded at start.
After you rebuild the artifact, tell the server to pick it up:

```bash
codemap build ./pkg -o graph.json --deep --incremental   # ~5s
# then, in the running server session:
#   reload            # serve op / MCP tool → swaps in the new graph.json
```

`stats.freshness` describes the graph **actually being served**: if the on-disk artifact
was rebuilt after the server loaded it, freshness is flagged `stale: true` with the
on-disk build time and a "call `reload`" reason — a served snapshot is never labelled
fresh while it's behind the file (issue #3). `reload` returns before/after counts so you
can see what changed. Together, `build --incremental` + `reload` are the manual form of
the deferred file-watcher (M3.2): rebuild fast, pick up without restarting.
