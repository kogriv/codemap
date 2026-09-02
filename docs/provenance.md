# Provenance — what produced this graph

Every `graph.json` carries a `provenance` block describing **which tool built it, on
which tier, from which input**. It exists because a graph is a claim about a source
tree, and a claim without its qualifiers cannot be checked.

```json
{
  "codemap_schema": "0.13",
  "target": "bquant",
  "provenance": {
    "scope_id": "sha256:a14c14e0…",
    "source": {"vcs": "git", "commit": "6bbb142deadb", "ref": "main", "dirty": false},
    "tier": "fast",
    "tool": {"name": "codemap", "version": "0.0.2", "commit": "16fe7de", "dirty": false},
    "inputs": {"python_files": 89}
  },
  "nodes": [], "edges": []
}
```

| field | meaning |
|---|---|
| `tool.name` / `version` | the package that wrote the file |
| `tool.commit` | short HEAD of codemap's own checkout — **absent** when codemap was installed from a wheel; never guessed |
| `tool.dirty` | whether codemap's own checkout had uncommitted changes. Two builds from one commit with different working trees are two different tools |
| `tier` | `fast` (ast) or `deep` (jedi). Two tiers answer call-graph questions differently, so this is part of the identity |
| `incremental` | whether parts of this graph were **carried over rather than recomputed in this build**. Always present, `false` included; absent means the graph predates the field, which is *unknown*, not *full*. On the deep tier it carries a consequence — [see below](#an-incremental-deep-graph-is-a-frozen-sample) |
| `scope_id` | sha-256 over the sorted `path\tsha256` list of every input file — the identity of the tree that was read |
| `source.commit` / `ref` / `dirty` | the target's VCS state, when the target is in a git repo. `dirty` covers **the scanned roots only**, not the whole repo |
| `inputs.python_files` | how many `.py` files the walk found — the input half of the conservation check below |
| `inputs.skipped` | files that produced **no module**, each with a reason (`syntax` / `encoding` / `io` / `unread`). Absent when there are none |
| `inputs.aliased_modules` | modules skipped because their real file was already read under another name (a directory symlink). Absent when there are none |
| `inputs.unlisted` | `{count, sample, outside_root}` — files this graph was built from that the input manifest does not list. Present whenever a manifest resolved, **including `count: 0`**; absent means the build could not compare, which is *unknown*, not clean |
| `roots` | present on a repo-scoped build (`--consumer` / `--docs`): core, consumers, docs, mode — each **relative to the graph's path origin**, never absolute (see below) |

## One origin for every path (schema 0.13)

Every `file` in a graph is relative to a single directory: the nearest common ancestor of
the roots' parents. Before 0.13 each root was its own origin — core files relative to the
core package's parent, consumer files relative to their own root's parent — which coincide
when the roots sit side by side and diverge silently when they do not
([#12](https://github.com/kogriv/codemap/issues/12)):

```
codemap build src/pkg --mode full --consumer tests
   0.12:  pkg/mod.py          ← relative to src/
          tests/test_mod.py   ← relative to the repo root
   0.13:  src/pkg/mod.py      ← both relative to the repo root
          tests/test_mod.py
```

Both read as repo-relative; at most one of them was, and the artifact said nothing. A
single-package build is unchanged, which is why the packaged dogfood never showed it.

**Where that directory *is* stays out of the graph**, because it is a machine location and
the graph is the half that travels. It goes in the sidecar as `roots_base`, so a *local*
command can turn a graph path into one that runs from where you are standing — which is
what makes the `pytest …` line `codemap tests` prints paste-able. See
[test-mapping.md](test-mapping.md).

## Two rules the block obeys

**No clock.** The canonical graph is timestamp-free, so two **fast-tier** builds of an
unchanged tree are byte-identical. That property is what makes "deterministic" checkable
at all, and a `built_at` field would destroy it. Wall-clock time lives in the sidecar.
The deep tier does not reach the same bar — [see below](#the-deep-tier-is-not-byte-stable),
and that is why CI compares bytes on the fast tier only.

**No absolute paths.** The graph is the half that travels — attached to a ticket,
committed to a sibling repo, handed to an agent. Paths here are repo-relative or a bare
name. A test enforces it.

## What is in the graph vs the sidecar

`codemap build -o graph.json` also writes `graph.json.meta.json`. The split is
deliberate: **identity travels with the graph, the rebuild recipe stays home.**

| `graph.json` → `provenance` | `graph.json.meta.json` (sidecar) |
|---|---|
| tool name / version / commit | `argv` — the exact invocation |
| `tier` | `built_at` — wall clock |
| `scope_id`, `roots` (relative) | `cwd`, `roots_base` — absolute, machine-local |
| `source` commit + dirty | the per-file hash list (a rebuild input) |

`scope_id` is in both on purpose: in the graph it is *identity*, in the sidecar it is
the cache key `build --incremental` compares against.

The sidecar records an absolute `cwd`, so it is the half that must **not** be published.
The graph is safe to share.

## `codemap_schema` is now read, not just written

Loading a graph whose schema differs from the running tool's raises a warning wherever
graphs are presented — the CLI, `stats`, and the report headers:

```
[warning] graph declares schema 0.11, this codemap writes 0.12 — the artifact predates
this tool. Extraction semantics change without a schema bump (open `extras`), so the two
are not interchangeable. Built by: codemap 0.0.2 @4858899, tier=fast.
```

It is a warning, never a refusal: every graph stored before 0.12 predates the block, and
turning an upgrade into an outage is not the honest option.

**What the check can and cannot do.** It catches a *declared* mismatch. It cannot prove
two graphs are semantically equivalent — the whole reason this exists is that extraction
semantics change *without* a schema bump, because `extras` is deliberately open. That is
what `tool.commit` is for.

## Comparing two graphs

`codemap diff old.json new.json` compares provenance before it compares symbols, and
says when the pair is not a before/after of the *code*:

```
[warning] different tool: codemap 0.0.2 @4858899 → codemap 0.0.2 @16fe7de
[warning] differences below may be tool changes, not code changes
```

Without it, a clean `✅ No breaking changes` reads as proof. On the pair that motivated
this work — one frozen tree, two codemap versions four commits apart — that verdict was
true at the API level while the two graphs disagreed about which functions were dead.

## `build --incremental` checks the builder too

An incremental rebuild used to decide from the source tree alone: no `.py` changed, so
return the old graph. That is wrong after a codemap upgrade — the same source read by a
different extractor is a different graph. `update_graph` now compares the stored tool
identity and tier against the running one, and falls back to a **full** rebuild when
they differ (`mode: full`, `reason: builder-changed`). A graph with no provenance
(pre-0.12) counts as a different builder — the conservative direction.

## Reading it

```bash
python - <<'PY'
import json; print(json.load(open("graph.json"))["provenance"])
PY
```

Or over `serve`/MCP: `stats` returns `provenance`, plus `schema` (what the **graph**
declares) and `tool_schema` (what the running tool writes) — two facts that used to
share one field.

**Design:** [design/graph_provenance.md](design/graph_provenance.md).
**Gap:** [../gaps/graph_provenance_2026-08-25.md](../gaps/graph_provenance_2026-08-25.md).

## What the graph says about what it could not read

`inputs` is here rather than in the sidecar for one reason: a consumer holding only
`graph.json` is exactly the one who must be told the tree was read incompletely. A file
with a syntax error or a non-UTF-8 byte used to vanish without a word, and every report
then answered over a tree codemap had not fully seen.

```
[warning] 2 input file(s) produced no module (1 encoding, 1 syntax):
pkg/broken.py, pkg/latin1.py  Anything those files define or depend on is missing,
not absent — dead-code, layers and impact are all short by that much.
```

Three derived checks read `inputs` (they are recomputed on read, never stored):

- **unread inputs** — the warning above, wherever the graph is presented.
- **module conservation** — modules cannot outnumber the files that define them, nor
  fall short of them unexplained. Both directions are *provably* wrong states, so there
  is no threshold to tune. It flags a symlink-cycle explosion without knowing what a
  symlink is, and an unexplained shortfall without knowing what a syntax error is.
- **scope membership** — every file in the graph must be one the input manifest lists.

See [hard-python.md](hard-python.md) for what produces these conditions.

## The deep tier is not byte-stable

`tier` is in the provenance block because the two tiers answer call-graph questions
differently. It is also there for a second reason, which until 0.0.9 was written down
nowhere a reader would find it: **`deep` graphs are not reproducible byte-for-byte.**

Measured on three trees. Ten deep builds of an unchanged tree here produced **two**
distinct artifacts (7 and 3): two per-symbol `calls` counters out of 2133 nodes moved one
call between `external` and `unresolved`, and no edges changed. On the pinned research
benchmark, three builds gave two artifacts differing by exactly one **`accesses`** edge of
12190 — so the flap is not confined to `calls`; the attribute layer uses jedi too. On a
larger external tree one build in seven lost a **real** call edge of 9524 — a call through
`getattr` whose receiver type jedi resolved in six runs and not in the seventh.

The cause is jedi's per-script execution budget (`total_function_execution_limit` and its
per-function siblings). An inference that runs out of budget returns no values, and no
values is indistinguishable, at our boundary, from "nothing to find" — so the call is
recorded `unresolved`. What varies between processes is how much budget earlier queries in
the same file consumed. Five external explanations were tested and refuted at ten runs
each: hash-seed randomization, jedi's and parso's on-disk caches, jedi's compiled
subprocess, the garbage collector, and address-space randomization.

What follows for you:

- **A deep graph is one sample, not a function, of its input.** Every deep build states this
  in its own diagnostics as a `note` — nothing in it is invalid, and a small call-graph
  delta between two of them is not evidence of a change in the code.
- **`codemap diff` says so too** when both sides are deep: the pair stays comparable, with
  the noise floor named above the verdict.
- **Anything that must be reproducible byte-for-byte belongs on the fast tier** — a CI gate,
  a two-release comparison, a provenance argument. The fast tier is `ast`-only and stable.
- The fast tier is a *subset* of the deep tier by construction (R1-C26), so nothing is lost
  by gating on it; the deep tier's extra edges are the part that carries the noise.
- **A published number off a deep build deserves a second build.** Ours did: the caller sets
  behind the research track's cross-tool comparison came back identical in three runs while
  the graph around them did not — which is the difference between a checked claim and a
  lucky one.

**Measurement:** [../gaps/deep_tier_nondeterminism_2026-09-02.md](../gaps/deep_tier_nondeterminism_2026-09-02.md).

## An incremental deep graph is a frozen sample

The advice above — *a deep graph is one sample, so build it again* — has one exception,
and it is the case where the advice is most likely to be taken: `build --incremental`.
That path recomputes only the modules an edit touched and splices the rest from the
previous graph, so on the deep tier **the parts it did not recompute keep the previous
build's sample, misses included**. Building again incrementally returns them unchanged.

Measured on an 88-module package: from a graph missing one real `accesses` edge, five
consecutive incremental builds recovered it **0 times**, while full builds of the same
tree recovered it **5 of 5**. And the miss is self-defending — the invalidation rule that
would recompute the writing module reads the old graph, where the edge is precisely what
is absent, so editing the module that owns the target did **not** mark the writer for
recompute. With the edge present, the same edit did.

Every such graph now says so:

```
[note] parts of this deep graph were spliced from an earlier build rather than
recomputed: on this tier that carries the earlier build's jedi sample forward, including
anything it missed. Do not read a missing call or attribute edge here as evidence that
nothing depends on a symbol, and do not test that by rebuilding incrementally — only a
full rebuild resamples.
```

The fast tier is excluded: there the splice is byte-identical to a full build and the
suite pins it, so there is no sample to freeze.

**Measurement:** [../gaps/incremental_noise_persistence_2026-09-02.md](../gaps/incremental_noise_persistence_2026-09-02.md).

## When the manifest and the graph disagree about the input

The sidecar's manifest is the artifact you read to answer *"what exactly was analyzed"*,
and until 0.0.8 it could answer wrong in silence. In git mode it enumerated the **tracked**
set while the extractor walked the **filesystem**, so a module that exists and has not been
`git add`ed — or one your `.gitignore` excludes — was in the graph, absent from
`scope.files`, and did not move `scope_id`. Reported by a second target whose sidecar listed
47 files with a hash on each beside a graph built from 48
([#15](https://github.com/kogriv/codemap/issues/15)).

That is not a reporting nicety: `scope_id` is the cache key for `build --incremental` and
the `watch` probe, so an edit that does not move it is an edit the rebuild does not see.

Two things changed:

- **Untracked source is part of the input.** git-mode enumeration now adds
  `git ls-files --others --exclude-standard` — exactly what `git add .` would stage. Those
  records carry `tracked: false` and no `git_blob`; every git-mode record states `tracked`
  either way, because a missing key is not a statement. A clean tree resolves to the
  identical `scope_id` it did before.
- **Gitignored files are named, not adopted.** If `.gitignore` says a file is not part of
  the tree, the manifest does not overrule it — the graph says so instead:

```
[warning] 1 file(s) in this graph are not listed in the input manifest:
pkg/generated_version.py  The manifest and `scope_id` describe a different input than this
graph was built from, so read the input identity as unknown — and with it `--incremental`
and `watch`, which key off that value.
```

The check runs forward only — a manifest file that produced no node is legitimately common
(a `.md` that yields no doc node, a deliberately unreadable fixture) and its Python half is
already *unread inputs*.

**Design:** [design/scope.md §1.7](design/scope.md).
**Gap:** [../gaps/scope_membership_2026-09-02.md](../gaps/scope_membership_2026-09-02.md).
