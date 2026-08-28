# codemap — gap: a graph does not say who built it, from what, or when it stopped being true

**Date:** 2026-08-25
**Source:** a lived episode during R1-C22-f1 (2026-08-24). `test_determinism_with_semantics` went **red**
— and the cause was not nondeterminism: the target package was being edited by another process between the
two builds. Nothing in the graph, the test, or the tooling could distinguish "the tool is nondeterministic"
from "the input moved". It took a manual rebuild on a frozen copy to tell them apart.
**Type:** provenance / honesty — the artifact is a claim about a source tree at a moment, made by a specific
tool, and it records none of the three.
**Related:** issue [#3](https://github.com/kogriv/codemap/issues/3) (a stale graph labelled fresh — the same
family, patched at one surface), M18 freshness, M19.A scope manifest (`scope_id` — the input identity that is
computed and then thrown away), `hard_python_robustness_2026-08-25.md` (D2/D6 both need a carrier and this is
it).
**Design:** [docs/design/graph_provenance.md](../docs/design/graph_provenance.md).
**Backlog:** R1-C25.
**Unblocks:** blog post **P4** (determinism), held back since 2026-08-02 for want of a real episode — §2 is
that episode. (P6's "provenance" is a different sense — multi-root *role* provenance; it is R1-C24's
neighbourhood, not this one's.)
**Status:** ✅ **closed same day** (2026-08-25, schema **0.11 → 0.12**) — the block ships. The §2 experiment
inverts: the `4858899` graph now renders under *"graph declares schema 0.11, this codemap writes 0.12 — the
artifact predates this tool"*, and `diff` on the pair leads with *"the pair cannot be verified"* before its
"✅ No breaking changes". **bquant's graph is byte-identical apart from the new block** (2833 nodes / 8123
edges, unchanged), and two CLI builds of it are byte-identical **including** `provenance`. Tests 425 → **453**.
One thing the design did not foresee — see §6.

## 1. The gap

`graph.json` has exactly four top-level keys:

```json
{"codemap_schema": "0.11", "target": "bquant", "nodes": [...], "edges": [...]}
```

No tool version. No source revision. No tier. No scope id. And `codemap_schema` — the one field that looks
like provenance — is **written and never read**: it appears in `model.py` (written) and in
`serve/session.py` (reporting the *running* tool's version). `Graph.from_dict` and `store.load` ignore it
entirely.

## 2. Evidence — the same source, two tools, two answers, one label

A frozen copy of `tests/fixtures/refpkg` (byte-identical input, nothing moving) built twice: once by codemap
at `4858899`, once at `16fe7de` — four commits apart, both on schema `"0.11"`.

| | edges | `report dead-code` **high** |
|---|---|---|
| built at `4858899` | 30 | **12** |
| built at `16fe7de` | 38 | **7** |

Five functions that one graph calls dead, the other calls live. **Both graphs declare
`codemap_schema: "0.11"`, and the current tool loads either without a word.** A reader handed the older file
gets today's confident report over yesterday's blindness.

And note what is *not* wrong here: no schema bump was warranted. R1-C22 added no node kind and no edge type —
it used existing `references`/`calls` with new `extras`, which DESIGN §2 explicitly leaves open. **The
semantics changed correctly and the version field correctly did not move.** That is the whole argument:
provenance is not schema. A schema version describes the *shape* of the file; nothing describes the *process*
that produced it.

`codemap diff old.json new.json` on that pair reports:

```
✅ **No breaking changes.** 0 added, 0 removed, 0 changed.
```

Which is *correct* — nothing changed on the public API surface — and precisely why `diff` cannot be the
safety net. Two graphs that disagree about which functions are dead are, to `diff`, the same program.

## 3. The sidecar is not the answer

`graph.json.meta.json` (M18/M19.A) does carry real provenance: `argv`, `built_at`, `cwd`, `target`, and a
`scope` block with `scope_id`, git state, per-file hashes and a role profile. Four reasons it does not close
this gap:

1. **It is a separate file.** Every way a graph actually travels — attached to a ticket, committed to a
   sibling repo, handed to an agent, copied into a container — moves `graph.json` and leaves the sidecar
   behind.
2. **It is `.gitignore`d** (`*.meta.json`), so it is precisely the half that cannot be shared.
3. **It is best-effort and optional.** The bquant sidecar sitting in this working tree right now has **no
   `scope` key at all** — `{argv, built_at, cwd, target}` and nothing else. Provenance that is sometimes
   absent cannot be relied on by a consumer.
4. **It records `cwd`** — an absolute personal path. Under AGENTS.md that makes the sidecar the one file that
   must *not* be published, which is an awkward home for the data that is supposed to travel with the
   artifact.

## 4. Why it matters

- **Determinism is the project's headline property, and it is currently unfalsifiable.** "Same input, same
  output" is a claim about a pair of builds; without an input identity in the artifact, a reader cannot check
  the pair. The R1-C22-f1 episode is what that costs: a red test, an hour, and a conclusion reachable only by
  hand.
- **An agent is the primary consumer, and it cannot tell a stale answer from a current one.** #3 fixed this
  for the *served* graph at one surface. The file itself still cannot answer "am I about this commit?".
- **Two of R1-C23's decisions are blocked on it.** The skipped-file list (D2) and the graph↔scope
  cross-check (D6) both need a carrier that travels with the graph.
- **`diff` invites the error.** Its whole purpose is comparing two snapshots, and it accepts a pair built by
  different tools, on different tiers, over different scopes, without remark.

## 5. Scope of a full solution

1. A `provenance` block **inside** `graph.json`: tool version and build identity, tier, `scope_id`, git
   commit + dirty flag when resolvable. **Timestamp-free** — a clock in the artifact breaks the determinism
   this is meant to defend.
2. **Enforce `codemap_schema` on load**: a mismatch is a loud, structured warning, never a silent accept.
3. **`diff` compares provenance first** and says so when the two graphs are not comparable.
4. **Path-free by construction** — the artifact must stay publishable; `cwd` and absolute paths stay in the
   machine-local sidecar with the rebuild recipe.

This is the first change since 0.11 that genuinely earns a **schema bump** (a new top-level key), which is
itself the point: the field exists to mark shape changes, and shape is finally changing.

Design decisions and sizing: [docs/design/graph_provenance.md](../docs/design/graph_provenance.md).

---

## 6. What the work turned up that the design missed

**`build --incremental` had the same blind spot one level down.** It decided from the source tree alone: no
`.py` changed → return the old graph untouched. That is wrong the moment *codemap itself* changes — the same
source read by a different extractor is a different graph, which is the entire thesis of §2. An upgrade
followed by `--incremental` would have returned yesterday's graph, built by yesterday's tool, and reported
`mode: unchanged` while doing it.

Found only because the provenance block made the question askable. `update_graph` now compares the stored
tool identity and tier against the running one and falls back to a **full** rebuild (`reason:
"builder-changed"`); a graph with no provenance counts as a different builder, which is the conservative
direction — a needless full rebuild costs a minute, a silently stale graph costs a wrong answer.

**And a small live demonstration.** Between the first and last build of this milestone, the dogfood target's
recorded `source.commit` moved from `6bbb142` to `f8765cc` — the neighbouring agent committed to bquant
mid-session. That is exactly the condition that made `test_determinism_with_semantics` red on 2026-08-24, and
it is now a field in the artifact rather than an hour of manual bisection.

**And the lesson was applied to the tests that started it.** Four `test_determinism_*` tests built the live
bquant checkout twice and compared bytes. Pointed at a tree someone else is editing, that does not measure
codemap's determinism — it measures whether anybody committed in the last fifteen seconds, and it went red
again during this very milestone (the neighbouring agent landed `f8765cc` mid-run). They now build a
**frozen snapshot** (`tests/frozen.py`), which is the same discipline this gap argues for at the artifact
level: freeze the input, or you are measuring the wrong thing. Verified separately on a frozen bquant copy —
two extracts byte-identical, 3.9 MB.
