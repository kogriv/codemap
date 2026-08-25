# Provenance — what produced this graph

Every `graph.json` carries a `provenance` block describing **which tool built it, on
which tier, from which input**. It exists because a graph is a claim about a source
tree, and a claim without its qualifiers cannot be checked.

```json
{
  "codemap_schema": "0.12",
  "target": "bquant",
  "provenance": {
    "scope_id": "sha256:a14c14e0…",
    "source": {"vcs": "git", "commit": "6bbb142deadb", "ref": "main", "dirty": false},
    "tier": "fast",
    "tool": {"name": "codemap", "version": "0.0.2", "commit": "16fe7de"}
  },
  "nodes": [], "edges": []
}
```

| field | meaning |
|---|---|
| `tool.name` / `version` | the package that wrote the file |
| `tool.commit` | short HEAD of codemap's own checkout — **absent** when codemap was installed from a wheel; never guessed |
| `tier` | `fast` (ast) or `deep` (jedi). Two tiers answer call-graph questions differently, so this is part of the identity |
| `scope_id` | sha-256 over the sorted `path\tsha256` list of every input file — the identity of the tree that was read |
| `source.commit` / `ref` / `dirty` | the target's VCS state, when the target is in a git repo. `dirty` covers **the scanned roots only**, not the whole repo |
| `roots` | present on a repo-scoped build (`--consumer` / `--docs`): core, consumers, docs, mode — names only |

## Two rules the block obeys

**No clock.** The canonical graph is timestamp-free, so two builds of an unchanged tree
are byte-identical. That property is what makes "deterministic" checkable at all, and a
`built_at` field would destroy it. Wall-clock time lives in the sidecar.

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
| `scope_id`, `roots` (names) | `cwd` — absolute, machine-local |
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
