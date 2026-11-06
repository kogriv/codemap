# Design — incremental builds for repo-scoped graphs, and for a package that is not at the git root

**Status:** 🟡 pre-registered (expectations below, committed before code). **Backlog:** R1-C86. **Gap:**
[`gaps/incremental_repo_scope_2026-11-06.md`](../../gaps/incremental_repo_scope_2026-11-06.md).

## D0 — scope paths are mapped relative to where the package sits

`_path_to_module` takes the package's path **relative to the scope root** (`research/shared`, `src/pkg`,
or `pkg`) and maps a scope path under it to a module id. `update_graph` computes that prefix from
`new_scope["root"]` and the package path. This fixes single-package incremental builds and `watch` in git trees
where the package is not at the top level.

## D1 — `build --incremental` with consumers or docs

1. The core part is updated by `update_graph`, against the **core subgraph** of the old repo graph: nodes whose
   `root` is `core`, and edges whose source is such a node.
2. The consumer and doc scans then run in full on the updated core, followed by Protocol dispatch, exactly as in
   `extract_repo`. They are deterministic `ast` passes, ~6 s on bquant, so a full rescan costs little and keeps
   the result equal to a full build.
3. Provenance is stamped as a repo build (`roots`) with `incremental` set as before. The R1-C44 note about
   `--incremental` not being applied goes away.

`extract_repo` gains a `core_graph=` parameter so steps 2–3 have one implementation for full and incremental
builds.

## D2 — Protocol dispatch after the splice (deep)

`update_graph` splices the old deep `calls` of unaffected modules **after** `add_behavioral_layer` has computed
the Protocol fan-out (R1-C81 D2), and the spliced region gets no fan-out. `add_protocol_dispatch` therefore runs
again after the splice. It is idempotent. This is not yet observed (D0 hid every deep incremental probe in a
subdirectory tree), so E5 measures it rather than assuming it.

## Pre-registered expectations

E1, E2, E3 and E4 fail on 0.0.33, so the list cannot pass if nothing was done.

| # | Expectation |
|---|---|
| E1 | Fixture, git repo, package in `research/shared`: edit, `build --incremental` → `incremental` mode, the edited module recomputed, graph byte-identical to a full fast build; `src/pkg` the same |
| E2 | Fixture repo-scope (core + tests + docs), fast tier: incremental after (i) a core edit, (ii) a consumer edit, (iii) a doc edit, (iv) a core module added, (v) removed: each byte-identical to a full repo build of the same tree, apart from `provenance.incremental` |
| E3 | bquant: a replay of the 10 most recent commits from `cf039ef` back, one incremental fast repo build per commit: each byte-identical to a full fast repo build at that commit (provenance aside) |
| E4 | Time on bquant, a one-module core edit: incremental **deep** repo build well under the full one (full ~110 s; expected below 30 s); fast incremental reported too |
| E5 | Deep incremental after an edit elsewhere: every `protocol` fan-out edge from an unaffected caller in a full deep build is present in the incremental one (bquearch `shared`, where the fan-out exists) |
| E6 | `watch` with consumers logs `[incremental] incremental: N module(s)` on a core edit |
| E7 | `check` on bquant and the bquearch gate: unchanged apart from the trailer |
| E8 | Full suite passes; guards for D0, D1 and D2 go red when reverted; a cosmetic control stays green |

Surprises are reported in the reconciliation.

## Amendment after the first run (2026-11-06, before the rerun)

The first acceptance run on 508396b failed **E3**. In the bquant replay, the incremental graph equalled the full
one on 1 commit of 10. The first divergence was at `12f09d7` (7 modules recomputed), and every later commit
inherited it, `unchanged` ones included. Edges and nodes were identical. 26 nodes differed in one extras key,
`calls_nested`, which was present in the full build and absent in the incremental one.

**Cause, older than this item:** the splice carries a fixed list of node-extras keys owned by the jedi passes
(`_BEHAVIORAL_EXTRAS`, R1-C9). `calls_nested` (calls inside nested defs, counted on the owner) and
`calls_shadowed` (on the module node) are stamped by the same pass and were never added to it. So every
unaffected module with a nested def lost them. The R1-C9 guards build fixtures with no nested def in an
unaffected module, so the single-package path has carried this since `calls_nested` was introduced. It shows
on any real tree.

**Fix:** both keys added. A property guard was added as well: whatever `add_behavior` / `add_attrflow` stamp on a
fixture that exercises nested defs and shadowed bodies must be in the splice set. The next new key fails it
instead of shipping. A byte-identity test now has a nested def in the unaffected module.

E3 is rerun on the fix commit. E4–E7 held on 508396b and are carried over.
