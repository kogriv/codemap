# Exports

codemap builds one canonical graph (`graph.json`) and renders it into several output views.
All exporters read an existing graph (`--graph graph.json`) or build one on the fly (`--build ./pkg`).

| View | Command | Output | Extra needed |
|---|---|---|---|
| RAG chunks | `codemap export rag -o chunks.jsonl` | JSONL, one chunk per symbol | — |
| Mermaid | `codemap export mermaid --mkind class` | mermaid diagram (stdout or `-o`) | — |
| Obsidian vault | `codemap export vault -o vault/` | linked markdown tree | — |
| **SCIP index** | `codemap export scip -o index.scip` | binary SCIP protobuf | `[scip]` |

## RAG chunks

```bash
codemap export rag --graph graph.json -o chunks.jsonl
```

One JSON object per line, each a self-contained, retrieval-friendly chunk describing a symbol
(signature, docstring, relations). Feed it to any vector store or agent context pipeline.

## Mermaid diagrams

```bash
codemap export mermaid --graph graph.json --mkind class            # class/inheritance
codemap export mermaid --graph graph.json --mkind deps  --scope pkg.sub
codemap export mermaid --graph graph.json --mkind calls --root myfunc --depth 2
```

- `--mkind class|deps|calls` — diagram kind (default `class`).
- `--scope <id-prefix>` — restrict class/deps to a subtree.
- `--root <symbol> --depth N` — for `calls`, the BFS root and depth.

## Obsidian vault

```bash
codemap export vault --graph graph.json -o vault/
```

Writes a tree of cross-linked markdown notes (one per symbol) you can open as an Obsidian vault.

## SCIP index (interop)

[SCIP](https://scip-code.org/) (Sourcegraph Code Intelligence Protocol) is the open interchange format
for precise code intelligence. Exporting a SCIP index lets **Sourcegraph, Glean and any SCIP consumer**
drive go-to-definition, symbol search and type hierarchy over codemap's graph.

```bash
pip install -e '.[scip]'          # adds protobuf (optional extra)

codemap export scip --graph graph.json -o index.scip \
    --project-root /abs/path/to/repo \
    --package mypkg --package-version 1.2.3
```

Options:

- `--project-root DIR` — filesystem root the document paths are relative to (default: cwd). Written as
  the SCIP `project_root` URI; documents must live under it.
- `--package NAME` — package name used in symbol strings (default: the graph target).
- `--package-version V` — version used in symbol strings (default: `.`, i.e. unversioned).

### What's in the index (and what isn't)

codemap's graph is **symbol-level** — its edges relate symbol→symbol but carry no call-site
coordinates. SCIP occurrences are location-based, so the export includes exactly what codemap knows
precisely:

- **Definition occurrences** — one per node that has a file location (module / class / function /
  attribute) → go-to-definition and symbol search.
- **SymbolInformation** — kind, docstring, and `inherits` / `implements` as SCIP `relationships`
  (`is_implementation`) → type hierarchy.

It **deliberately does not** emit reference occurrences (find-references): that needs token positions
codemap doesn't track, and emitting approximate positions would be worse than omitting them. This is
consistent with codemap's honesty principle — approximations are labeled or left out, never faked.

Symbol strings follow the SCIP descriptor grammar, derived from codemap's canonical ids:
namespace `/`, type `#`, method `().`, term `.` — e.g. `codemap python mypkg 1.2.3 mypkg/mod/MyClass#method().`

### Verifying

The output is deterministic (byte-stable across runs). Validate it with the official
[`scip`](https://github.com/sourcegraph/scip) CLI:

```bash
scip print index.scip          # human-readable dump
scip print --json index.scip   # JSON dump
```
