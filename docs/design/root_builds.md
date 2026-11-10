# Design — namespace subdirectories inside a package, and flat imports that name the module they import

**Status:** pre-registered 2026-11-10, before code. **Backlog:** R1-C94. **Gap:**
[`gaps/root_builds_lose_modules_and_targets_2026-11-10.md`](../../gaps/root_builds_lose_modules_and_targets_2026-11-10.md).

## D1 — a directory without `__init__.py` inside the package is a namespace subpackage

After griffe's load, codemap walks the built directory. A directory that griffe did not load, has a valid
identifier name and holds `.py` files becomes a namespace module (`file: null`, as the namespace target already
is). Each `.py` file in it with a valid identifier stem is read with `griffe.visit` into that module. A
subdirectory that does have `__init__.py` below such a directory is a regular package and is read from its
`__init__.py`. Walk order is sorted, `__pycache__` and hidden directories are skipped, symlink cycles are cut as
`_enumerate_sources` cuts them. This only uses griffe's public `Module` and `visit`, and imports nothing.

A directory or file whose name Python cannot import (`my-dir/`, `detailed diaram/`, `a.b.py`) stays out and
keeps its `unread` entry: Python cannot import it either.

## D2 — the flat inference returns the deepest module it can see

`_flat_sibling` keeps its gate: the target's head must name a module beside the importer. It now returns the
longest known module that prefixes `<parent>.<target>`, not the head. `from engine.dataset import get` is
`imports repo.main → repo.engine.dataset`, labelled `resolution="flat"` as before. Re-exports and the qualified
import map (`qualify_target`) already carry the whole path, so they do not change.

**`ANSWER_FORMAT` stays 10:** no layout or field meaning changes. What changes: graphs with `unread` files in such
directories (they gain modules) and graphs with dotted flat imports (those edges point deeper).

## Pre-registered expectations

E1, E2, E4 and E5 fail on 0.0.37.

| # | Expectation |
|---|---|
| E1 | Minimal tree (`pkg/__init__.py`, `pkg/layers/act.py`, `pkg/net.py` calling `act()`): 0.0.37 has no `pkg.layers*` nodes and an `unread` entry; the fix has `pkg.layers` (`file: null`), `pkg.layers.act.act`, `calls pkg.net.run → pkg.layers.act.act`, `imports pkg.net → pkg.layers.act`, and no `skipped` |
| E2 | Minimal root tree (`main.py`, `engine/dataset.py`): 0.0.37 `imports repo.main → repo.engine`; the fix `→ repo.engine.dataset` with `resolution="flat"`. A bare sibling import (`from helper import X`) is unchanged |
| E3 | Names Python cannot import (`my-dir/x.py`, `pkg/a.b.py` where applicable) stay `unread`; nothing is imported (the R1-C96 marker probe stays clean) |
| E4 | TAOISM at its R1-C93 commit, built from the root: 0.0.37 has 22 `unread` files under `python/layers/`; the fix reads them (0 `unread` there). Dotted in-repo absolute imports that reach an `imports` edge to the exact module: genome 1 → ≥ 30 of 37, TAOISM 0 → ≥ 150 of 212 |
| E5 | The 12 probe repositories built from the root: total `unread` files drop, total module nodes rise, and none of the 12 fails to build |
| E6 | bquant: `check` identical, graph byte-identical apart from the version (no `unread`, no flat edges). bquearch: the gate verdict is unchanged; graph differences are listed and are only flat `imports` edges pointing deeper. If the gate verdict changes, that is a finding to report to them before release, not a release |
| E7 | Full suite passes. Mutations go red: D1 walk off, D2 returning the head again; a cosmetic control stays green |

Surprises go into the reconciliation.
