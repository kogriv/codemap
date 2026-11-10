# Design — `build` never imports the target, and degrades instead of crashing on foreign trees

**Status:** pre-registered 2026-11-10, before code. **Backlog:** R1-C96 (never imports), R1-C95 (degrades).
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
