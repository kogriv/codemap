# Design — modules of a namespace subpackage carry their source

**Status:** pre-registered (2026-11-21), before code. **Backlog:** R1-C109 (closes R1-C105).
**Gap:** [`gaps/namespace_subpackage_source_lost_2026-11-21.md`](../../gaps/namespace_subpackage_source_lost_2026-11-21.md).

## D1 — `_visit_source` fills `lines_collection` as griffe's loader does

Before `griffe.visit`, `root.lines_collection[path] = code.splitlines(keepends=False)`, the same statement
griffe's loader runs. `module.source` is then the file's text, and the import pass sees function-local,
class-body, `TYPE_CHECKING` and dotted imports in these modules as it does everywhere else.

## D2 — the namespace walk reads the files griffe reads in a regular package

A `.py` file is read whatever its stem, unless the stem contains a dot, mirroring griffe's
`iter_submodules`, which has no identifier filter for files. `0001_initial.py` under a namespace app is read,
as it already is under a regular one. Directory names keep the identifier rule: griffe never loads a directory
without `__init__.py`, so the walk's own rule stays for directories.

**`ANSWER_FORMAT` stays 10.** Graphs of trees without namespace subpackages are byte-identical. Graphs with
them gain edges and modules they were missing.

## Pre-registered expectations

E1–E3 fail on 0.0.38.

| # | Expectation |
|---|---|
| E1 | The 5-file tree: `imports p.nsp.m → p.reg.t` (scope `function`) appears; 0.0.38 has none |
| E2 | `p/nsp/migrations/__init__.py` + `0001_x.py`: the module `p.nsp.migrations.0001_x` is a node and `unread` is empty; 0.0.38 lists it `unread` |
| E3 | Project C clone at the audited commit: `unread` 18 → 0; the `allowed` pairs from the graph equal the independent AST scan exactly (624 = 624, no difference either way) |
| E4 | bquant and bquearch graphs byte-identical to the R1-C108 build (no namespace subpackages there); the 12 RepoBench repositories of R1-C94 rebuild with modules ≥ before and no new `unread` |
| E5 | Full suite passes. Mutations: D1 line removed → E1 test red; D2 filter restored → E2 test red; cosmetic control green |
