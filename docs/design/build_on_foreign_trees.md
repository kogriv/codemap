# Design — `build` never imports the target, and degrades instead of crashing on foreign trees

**Status:** ✅ **done** (2026-11-10, fix b4a09ad; `ANSWER_FORMAT` stays 10), acceptance reconciled below. Pre-registered in 45592b2, before code. **Backlog:** R1-C96 (never imports), R1-C95 (degrades).
**Gaps:** [`gaps/build_imports_compiled_modules_2026-11-10.md`](../../gaps/build_imports_compiled_modules_2026-11-10.md),
[`gaps/build_crashes_on_foreign_trees_2026-11-10.md`](../../gaps/build_crashes_on_foreign_trees_2026-11-10.md).

## D1 — griffe never inspects (R1-C96)

Both `griffe.load` calls in `griffe_extractor` pass `allow_inspection=False`. griffe then refuses a module it
cannot read from source (`LoadingError`, which it catches per submodule and skips) instead of importing it. Its
other inspection path, importing a top-level module by name when nothing is found on disk, is closed by the same
flag. A probe before this text (patched in, not committed): the `.pyc` and `.so` marker probes create no marker,
fast tier and `--deep` alike, and the rest of the package still builds.

## D2 — a compiled module is listed, not read and not lost in silence (R1-C96)

- `gsource.module_file` returns `None` for any file that is not `.py`/`.pyi`. No layer reads a binary as text,
  whatever griffe hands it.
- The input report (`provenance.inputs`) gains `compiled`: compiled module files (`.so`, `.pyd`, `.pyc` outside
  `__pycache__`) inside the built package that have **no** `.py` of the same module name beside them. Each one is
  a module the graph does not contain.
- A note diagnostic, `compiled_modules_not_loaded`, states it: "N compiled module(s) without source were not
  loaded — codemap never imports the target: …". It is a note, not a warning, because the graph is right about
  everything it holds.
- A compiled copy **beside** its source (`md.py` + `md.cp38-win32.pyd`) is not listed: the module is built from
  `md.py`. With D1, griffe rejects the `.pyd` in either directory order, so which file it meets first no longer
  matters.

## D3 — a base class behind an unresolvable alias is skipped (R1-C95)

`behavior._class_members` collects the members of internal base classes, so that `self.<inherited>()` resolves.
When the base is a package name that re-exports a third-party class, reading its members makes griffe resolve
the alias, and it raises. Now: `AliasResolutionError` / `CyclicAliasError` there skips that base. Its inherited
members are not known, so `self.<inherited>()` stays unresolved, as it already does for a base imported straight
from the third-party package. The rest of the class resolves as before.

## D4 — the facade refusal names both shapes (R1-C95)

When a re-export points at a top-level package that is not beside the target, the build still refuses (griffe
fails inside its own load, so there is nothing to continue from). The text now names both causes: the facade
layout (R1-C57), **or** a module imported through `sys.path` (script layout, R1-C94). Making that case degrade is
R1-C94's work.

**`ANSWER_FORMAT` stays 10.** A tree without compiled modules and without these alias shapes builds byte for byte
as before. Changed are only trees that crashed (they now build), trees with compiled modules (the new `inputs`
key and note), and the refusal text.

## Pre-registered expectations

E1, E2, E3, E4 and E5 fail on 0.0.36.

| # | Expectation |
|---|---|
| E1 | Marker probes: `pkg/evil.pyc` (sourceless, writes a marker on import) and `pkg/fast<EXT_SUFFIX>` (C extension, `PyInit` writes a marker). 0.0.36 under Python 3.12 creates the marker and exits 1. The fix creates **no** marker, fast tier and `--deep`, exits 0, and the graph holds `pkg.user` and its function |
| E2 | Same trees: `provenance.inputs.compiled` lists the compiled file, and `compiled_modules_not_loaded` appears in `diagnostics()` and on `build`'s stderr. 0.0.36: no graph at all |
| E3 | Source beside a compiled copy: the vendored `charset_normalizer` copy on the machine where griffe picked `md.cp38-win32.pyd`. 0.0.36 exits 1 (`UnicodeDecodeError`). The fix exits 0, `charset_normalizer.md` holds its functions from `md.py`, and `compiled` is empty. Unit test: the same with the directory order reversed both ways |
| E4 | Alias base (gap (a), 7-line tree): 0.0.36 exits 1 with `Could not resolve alias`. The fix exits 0, `pkg.user.Mine.go` is a node, and `self.other()` is not resolved to anything |
| E5 | The five R1-C93 repositories whose build failed, at their recorded commits, built the way the harness built them: detectron2 (UniRef), mmdet3d (SPGroup3D), pip (vendored in `venv/`), charset_normalizer: exit 0 with the fix. AccoMontage-3 (`piano_arranger`): still exit 1, and the text names the script layout |
| E6 | bquant `check` and the bquearch gate are identical to 0.0.36 apart from the version; bquant's graph is byte-identical apart from the version |
| E7 | Full suite passes. Mutations go red: D1 flag removed (marker test), `module_file` guard removed, D3 guard removed, D2 `compiled` listing removed. A cosmetic control stays green |

Surprises go into the reconciliation.

## Reconciliation (2026-11-10, b4a09ad)

| # | Result |
|---|---|
| E1 | ✅ 0.0.36 under the interpreter that compiled the probe: marker **created** by the `.pyc` and by the `.so`, fast tier and `--deep`, then exit 1 (`'utf-8' codec can't decode …`). Fix: no marker in all four, exit 0, `pkg.user.use` present |
| E2 | ✅ fix: `inputs.compiled` lists `pkg/evil.pyc` / `pkg/evil.cpython-312-x86_64-linux-gnu.so`, and the note is on stderr. 0.0.36: no graph |
| E3 | ✅ with one wrong prediction. On the machine where griffe's default picks `md.cp38-win32.pyd`: 0.0.36 exit 1 (`UnicodeDecodeError`); fix exit 0, `charset_normalizer.md` holds its classes from `md.py`. `compiled` is **not** empty as predicted: it lists `md__mypyc.cp38-win32.pyd`, a second module of that tree that has no source at all. Listing it is correct; the prediction missed the file |
| E4 | ✅ 0.0.36 exit 1, `Could not resolve alias pkg.utils.file_io.PathHandler …`; fix exit 0, `pkg.user.Mine.go` a node, no call edge from it |
| E5 | ✅ detectron2 (UniRef), mmdet3d (SPGroup3D), vendored pip, charset_normalizer: 0.0.36 exit 1, fix exit 0 (charset_normalizer with the note). AccoMontage-3: still exit 1, and the text names `sys.path` |
| E6 | ✅ bquant `check` and the bquearch gate identical apart from the version. bquant's graph is identical except `provenance.tool`: the dev build carries `commit`/`dirty`, and its `version` read 0.0.35 from stale editable metadata (the stand script's reinstall step did not find `uv`). Nodes, edges and every other field are equal |
| E7 | ✅ suite 1284 passed / 3 skipped (1287 collected). Mutations red: D1 flag off on the target load (2 tests), D1 off on both loads together with the `module_file` guard (5), D3 guard off (1), `compiled` listing off (3), refusal text reverted (1); cosmetic control green |

**Surprises.**
- **Two guards cannot be killed by a mutation, and that is stated, not hidden.** The `module_file` guard alone
  stays green: with D1, griffe never hands a compiled file to any layer, so the guard is a second line that
  nothing reaches today. It stays as defence in depth. The E3 unit test also stays green when D1 is off: a
  win32 `.pyd` is not importable on Linux, so inspection fails and griffe falls back to `md.py` anyway. The
  crash only appears on a filesystem whose order puts the `.pyd` last, and the real-tree E3 run above is the
  check that saw it.
- **The defect is older than 0.0.10.** Every release probed (0.0.10, 0.0.20, 0.0.36) imports a sourceless
  module under the matching interpreter. Under Python 3.14 the same probe showed no marker only because the
  `.pyc` had been compiled for 3.12.
