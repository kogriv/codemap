# Exports

codemap builds one canonical graph (`graph.json`) and renders it into several output views.
All exporters read an existing graph (`--graph graph.json`) or build one on the fly (`--build ./pkg`).

| View | Command | Output | Extra needed |
|---|---|---|---|
| RAG chunks | `codemap export rag -o chunks.jsonl` | JSONL, one chunk per symbol | — |
| Mermaid | `codemap export mermaid --mkind class` | mermaid diagram (stdout or `-o`) | — |
| Obsidian vault | `codemap export vault -o vault/` | linked markdown tree | — |
| **SCIP index** | `codemap export scip -o index.scip` | binary SCIP protobuf | `[scip]` |
| **ctags** | `codemap export ctags -o tags` | universal-ctags `tags` file | — |

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
pip install 'codmap[scip]'        # adds protobuf (optional extra); from a clone: -e '.[scip]'

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

## ctags (editor interop)

A [universal-ctags](https://ctags.io/) `tags` file is the lowest common denominator of
code navigation — vim, Emacs, `readtags` and countless editors do go-to-definition by
binary-searching it. codemap already holds every definition's name, file, line and scope,
so this export is near-free and needs no extra.

```bash
codemap export ctags --graph graph.json --project-root /path/to/repo -o tags
```

`--project-root` is the filesystem root the graph's file paths are relative to (default:
cwd). codemap reads source lines from it to build robust `/^…$/` search-pattern addresses;
if a line is unreadable it falls back to a bare line-number address (always available from
the graph).

### What's in it (and what isn't)

One line per **definition** — classes, functions, methods, attributes — in extended
(exuberant) format with extension fields codemap already knows:

- `kind` — `c` class · `f` function · `m` method · `v` variable/attribute
- `line:` · `scope` (e.g. `class:Foo`) · `access:` (public/private)
- functions also carry `signature:(…)` and `typeref:typename:…`, and `end:` when known

It does **not** emit reference tags (find-uses): codemap tracks no token positions, so this
is a *tags* file, not a references index (that is SCIP's job). Modules are files, not tags,
so they are skipped — as universal-ctags itself does. Re-export aliases (a symbol with no
own definition location) are skipped too, so each definition is tagged once at its real site.

### Verifying

The output is deterministic (byte-stable) and sorted by name (pseudo-tags declare
`!_TAG_FILE_SORTED\t1`) so `readtags` can binary-search it:

```bash
readtags -t tags analyze_zones   # look up a symbol
```
