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
- **Deep tier: cheaper, and weaker in a way the fast tier is not.** The splice itself is
  exact — proven byte-identical on a controlled fixture — and it is ~12× faster. But
  jedi's bounded type inference is not stable across processes, so *two full `--deep`
  builds of an unchanged tree already differ* from each other by a handful of deep-only
  edges, and the splice does something with that noise a full build does not.

  **Corrected 2026-09-02 (R1-C43):** this bullet used to end *"it introduces no divergence
  of its own"*. Measured, and that is wrong twice:

  - **The sample is frozen, not resampled.** An edge jedi missed in the old build is
    copied forward verbatim. Starting from a graph missing one real `accesses` edge, five
    consecutive incremental builds recovered it **0 times**; full builds of the very same
    tree recovered it **5 of 5**. The usual remedy for tier noise — *build again and see
    whether the edge is still gone* — therefore does nothing here.
  - **The miss defends itself.** The rule that would recompute the module reads the *old*
    graph, so a missing edge is a missing reason to recompute. Editing the module that
    owns the target left the writing module unaffected when the edge was absent, and
    affected when it was present: same edit, same tree, same tool.

  - **What a recomputed module gives you is a full build's answer.** Measured 2026-09-03
    over 24 paired samples, each arm reading the same tree state: a module that lands in
    the affected set resolves exactly as well as it does in a full build (best state 5 of
    24 on both sides, sign test `p = 1.000`). So the weakness above is precisely located —
    it is in the modules the build *skips*, not in the ones it redoes. An earlier reading
    of this suggested otherwise and was retracted: that sample had been collected through
    the very rule described in the previous bullet, which only observes runs where the
    edge is still present.

  This is structural rather than an oversight — `unresolved` means *we do not know where
  the edge went*, so that set cannot be indexed by the changed module, which is exactly
  what the rule needs. What the tool does about it today is **say so**: such a graph
  carries `provenance.incremental: true` and a `note` wherever it is presented. The doors
  that would actually close it are BACKLOG R1-C43.
  [Measurement](../gaps/incremental_noise_persistence_2026-09-02.md).

  **So:** if you need a deep graph to reason about *absence* — "nothing calls this", "this
  field has no writers" — build it fully. The fast/structural layers are fully
  deterministic and none of the above touches them.

  **Corrected 2026-09-02 (R1-C42):** this bullet used to attribute the variance to jedi's
  cache warmth. Measured and refuted — a cold `XDG_CACHE_HOME` per build flips just as
  often (5 of 10). The cause is jedi's per-script execution budget: an inference that runs
  out of it returns nothing, and nothing reads as `unresolved`. Five external explanations,
  cache warmth among them, were tested at ten runs each and refuted — see
  [provenance.md](provenance.md#the-deep-tier-is-not-byte-stable) and the
  [measurement](../gaps/deep_tier_nondeterminism_2026-09-02.md).
- **No-op is free.** If no package `.py` file changed, the old graph is returned
  untouched (`mode: unchanged`) — the hot path for a future file watcher (M3.2).
- **…but only when the *builder* is unchanged too** (R1-C25). The source tree is not the
  only input: the same source read by a different extractor is a different graph. Before
  looking at the tree, `update_graph` compares the graph's recorded tool identity and tier
  (see [provenance.md](provenance.md)) against the running one, and falls back to a **full**
  rebuild when they differ (`mode: full`, `reason: builder-changed`). A graph built before
  schema 0.12 records no provenance and counts as a different builder — the conservative
  direction: a needless full rebuild costs a minute, a silently stale graph costs a wrong
  answer.
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
the loop below: rebuild fast, pick up without restarting.

## The automatic loop

Two commands, composed by the shell, each doing one half (M3.2):

```bash
codemap watch ./pkg -o graph.json &            # source   → artifact
codemap serve --graph graph.json --watch       # artifact → memory
```

Measured, save to answerable, at the defaults (1 s poll, 2 s rebuild debounce, 0.5 s reload
debounce):

| tree | save → answerable | of which rebuild |
|---|---|---|
| a real 90-file package, fast tier | **8.1–8.7 s** | 4.3 s (9 modules recomputed; cold build 6.8 s) |
| a 2-file toy | ~4–5 s (1.11 s at `--interval 0.3 --debounce 0.3`) | ~0.05 s |

Since **M3.2-f1** the rebuild debounce is **adaptive**: a change of at most two files — one save, or a
module and its test — settles on `--quick-debounce` (0.3 s) instead of the full `--debounce` (2 s), while a
burst still coalesces on the full window. The size comes from `diff_scopes`, the same comparison the build
uses, so there is no second notion of "how much changed"; when the size cannot be computed the **full**
window applies, because the fast path is taken only when the change is known to be small. Taken from the
peer measured in [research/tools/codegraph.md](../research/tools/codegraph.md), which is why its
save→answerable was 0.33 s rather than the 2 s its headline debounce implies.

_The table above predates that, and is not re-stated here: on this machine whole-build timings vary by
±30% run to run, which is wider than the change. What is verified is the deterministic part — with a
one-file change the loop acts on the tick after it notices, instead of waiting three (`tests/test_m32_watch.py`)._

Two different things dominate, and it is worth knowing which is which. On a toy it is all
**debounce**, and that is deliberate: an editor that saves on every keystroke, a `git
checkout` touching three hundred files, or a formatter sweeping a directory should be **one**
rebuild, and acting mid-flight would rebuild a tree that no longer exists by the time the
build lands. On anything real it is the **rebuild** — so tightening the knobs stops helping
around the 4 s mark, and that floor, not the polling, is what would have to move.

Worth knowing before relying on it:

- **The build's own notion of change.** The watcher polls `resolve_scope` and compares
  `scope_id` — the same manifest a build records in its sidecar. No second include list to
  drift apart, and content hashes rather than mtimes, so `touch` is not a rebuild and a
  revert to identical bytes is not one either.
- **A new file counts before you `git add` it (0.0.8).** Until then git-mode enumeration
  listed only the tracked set, so a module you had just written was read by the extractor
  and absent from the identity: `--incremental` answered `unchanged: 0 module(s)
  recomputed` over a file that had grown a new symbol, and the watcher had nothing to
  react to. A file your `.gitignore` excludes still does not enter the manifest — the graph
  now says so out loud instead (see
  [provenance.md](provenance.md#when-the-manifest-and-the-graph-disagree-about-the-input)).
- **Polling, not inotify** — native file events would mean a dependency. The cost is one
  full scope resolve per interval: **median 50 ms** for a 292-file, 4.7 MB tree (~5% of a
  core at the 1 s default). Raise `--interval` on a much larger tree.
- **Split on purpose.** The rebuild does not run inside the resident server: extraction
  there would compete with the queries the server exists to answer, and a crashing rebuild
  would take the server down with it. Either half also runs alone — `watch` keeps a graph
  current for CI or for cold `codemap query`; `serve --watch` follows *any* external
  rebuild, including one you type by hand.
- **It catches up at startup.** A watcher started over a graph whose recorded `scope_id`
  no longer matches the tree rebuilds immediately instead of waiting for the next edit; an
  unreadable sidecar counts as stale, because "I cannot tell" must not resolve to "it is
  fine". A graph that is already current is left alone.
- **A broken tree gets an honest graph, not a stale one.** Save a syntax error and the
  rebuild proceeds: the module's symbols drop out and the diagnostic says *"1 input file(s)
  produced no module (1 syntax) — anything those files define is missing, not absent"*.
  Withholding it would serve a symbol table for source that no longer exists, unmarked.
  The next save that parses restores it.
- **A failed act is retried, never recorded as done.** If a reload catches a half-written
  file, the watcher does not advance its baseline — a server quietly answering from the old
  graph while believing it is current is exactly the staleness issue #3 removed. Build
  failures are reported once per tree version, so a broken tree does not spam.
