# Design — namespace subdirectories inside a package, and flat imports that name the module they import

**Status:** ✅ **done** (2026-11-10; D1+D2 3cf4fcb, D3 c3e32a5; `ANSWER_FORMAT` stays 10), reconciled below. Pre-registered in dedb88a, amended in e92a7e5/badef5a after the first acceptance run, before D3's code. **Backlog:** R1-C94. **Gap:**
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

## Amendment 2026-11-10, after the first acceptance run (3cf4fcb) — pre-registered before D3's code

The first run held for D1 and failed E4 for D2: genome 6 of 37, TAOISM **0** of 212, where ≥ 30 and ≥ 150 were
predicted. The shape D2 does not cover: a module **inside a subdirectory** importing a package that sits at the
**root** (`teeslice/sgx_resnet_cifar.py`: `from python.common_net import …`, with `python/` at the root). That is
not a sibling import; it works because the repository root is on `sys.path` (`python -m teeslice.x` from the root,
or `PYTHONPATH=.`). One "regression" the run showed is not one: on `lx-music`, `from common import config`
(a submodule) used to point at `common` and now points at `common.config`. The run's own counter scored the old
edge as exact. The counter is fixed below.

### D3 — on a namespace target, an import may be anchored at the root

When the built directory has no `__init__.py` (the namespace target, the repository-root case), a target whose
head names a module directly under the target resolves to the deepest known module of `<target>.<path>`,
labelled `resolution="flat"`. The sibling rule (D2) is tried first: if both match, the nearer one wins, as
`sys.path[0]` being the script's own directory would make it win at runtime. On a regular package target nothing
changes, since that directory is not on `sys.path` (R1-C72's argument).

### Counter, corrected

A statement's target is, per imported name, `<module>.<name>` if that is a module, else `<module>`. A pair counts
as exact when an `imports` edge goes from the importing module to the deepest known module of that target.

### Expectations for the second run (replace E4's numbers; everything else stands)

| # | Expectation |
|---|---|
| E4′ | With the corrected counter, over the 12 probe repositories: exact pairs rise from 0.0.37 to the fix by at least 3×; TAOISM ≥ 150 of its pairs and genome ≥ 25. lx-music does not fall below 0.0.37 |
| E4″ | A minimal root tree (`python/net.py`, `teeslice/model.py` importing `from python.net import f`): 0.0.37 has no edge from `teeslice.model`; the fix `imports repo.teeslice.model → repo.python.net` (`flat`). A sibling with the same head wins over the root |
| E4‴ | The same rule reaches calls: in that tree a call to `f()` in `teeslice.model` is `calls → repo.python.net.f` (0.0.37: unresolved). The qualified import map (`qualify_target`) applies D3 with D2's order, so calls and `imports` edges agree |
| E6′ | bquant and bquearch: graphs still identical to 0.0.37 apart from the version. bquearch builds `shared`, which has an `__init__.py`? If it is a namespace target, D3 may add edges there; any difference is listed and reported to them before release |

## Reconciliation (2026-11-10)

**First run (3cf4fcb, D1+D2).** E1–E3, E5–E7 held. **E4 failed:** genome 6 of 37, TAOISM 0 of 212. That led to
the amendment above, D3, and a corrected counter.

**Second run (6b5f1bf, D1–D3), 12 probe repositories built from the root:**

| repository | 0.0.37 unread / modules / exact imports | fix |
|---|---|---|
| AA | 0 / 10 / 12 of 12 | 0 / 10 / 12 of 12 |
| Agent4Rec | 6 / 50 / 1 of 14 | 0 / 59 / 13 of 15 |
| FinRock | 0 / 18 / 0 of 36 | 0 / 18 / 36 of 36 |
| G-CASCADE | 0 / 161 / 2 of 85 | 0 / 161 / 85 of 85 |
| SkyScript | 0 / 41 / 5 of 66 | 0 / 41 / 66 of 66 |
| TACO | 0 / 11 / 7 of 8 | 0 / 11 / 8 of 8 |
| TAOISM | 22 / 28 / 0 of 110 | 0 / 52 / 331 of 331 |
| VTimeLLM | 5 / 18 / 0 of 24 | 0 / 24 / 37 of 37 |
| diffusion_reward | 9 / 138 / 0 of 27 | 0 / 152 / **0 of 27** |
| genome | 10 / 32 / 1 of 43 | 0 / 45 / 50 of 51 |
| lx-music-api-server-python | 0 / 36 / 0 of 38 | 0 / 36 / 38 of 38 |
| polygrad-world-models | 7 / 89 / 0 of 15 | 0 / 98 / 18 of 18 |
| **total** | **59 / 632 / 28** | **0 / 707 / 694** |

The denominators differ between columns: a pair counts only when its importing module is in the graph, and
D1 adds modules.

| # | Result |
|---|---|
| E1 | ✅ unit: `pkg.layers` (`file: null`), `pkg.layers.act.act`, the call and the import resolve, no `skipped`; a package below a namespace directory and a relative import inside it resolve too; incremental equals full after an edit there |
| E2 | ✅ unit: `repo.main → repo.engine.dataset` (`flat`); the bare sibling import is unchanged |
| E3 | ✅ unit: `my-dir/x.py` and `a.b.py` stay `unread`; a sourceless `.pyc` in a namespace directory is listed as compiled and not imported |
| E4 | ❌ first run (see above). E4′ ✅: exact pairs 28 → 694 (≥ 3× predicted), TAOISM 331 of 331 (≥ 150), genome 50 of 51 (≥ 25), lx-music 0 → 38 (not below). E4″ ✅, E4‴ ✅ (unit: root-anchored import and call; the sibling wins) |
| E5 | ✅ `unread` 59 → 0, modules 632 → 707, no build fails; TAOISM `python/layers/` 17 `unread` → 0 (the gap's 22 counted all of TAOISM) |
| E6 / E6′ | ✅ bquant `check` and the bquearch gate identical; both graphs identical to 0.0.37: no node and no edge differs. bquearch's `shared` has no dotted flat import that D2 or D3 changes |
| E7 | ✅ suite 1297 passed / 3 skipped (1300 collected). Mutations red: D1 walk off (4), D2 head again (2–3), name filter off (1), D3 anchor off (1), root before sibling (5), anchor on a regular package in the import map (1) and in the edge pass (2); cosmetic control green |

**Surprises.**
- **diffusion_reward stays at 0 of 27.** Its repository directory and its package share a name
  (`diffusion_reward/diffusion_reward/`). Built from the root, `diffusion_reward.models.x` starts with the target's
  own name, so it is read as package-qualified against the root, where it does not exist. Neither D2 nor D3 sees
  it. It is a common layout (`repo/pkg/`), and the usual way to build it is the inner package, so this goes to
  the backlog (R1-C97) rather than into this item.
- An R1-C72 guard patched `behavior.flat_inference_applies` by name. The gate now lives in
  `gsource.flat_known_modules`, and the patch moved with it; the test's meaning is unchanged.
- E4's first counter scored `from common import config` (a submodule) against `common`. It took the fix's more
  precise edge for a regression.
