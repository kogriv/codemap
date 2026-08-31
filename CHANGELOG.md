# Changelog

All notable changes to codemap. Format loosely follows [Keep a Changelog](https://keepachangelog.com);
the graph JSON has its own `SCHEMA_VERSION` (`codemap/model.py`), noted per entry.

## [Unreleased]

### Added

- **A warm server says when it is running code the installed distribution has moved past (R1-C38).**
  `reload` refreshes the graph; nothing refreshes the code. Found while closing an unrelated debt: a server
  started before R1-C33 served a freshly rebuilt graph — `reload` reported 4656 → 4743 nodes and the
  schema-mismatch diagnostic cleared — and returned dossiers without the `signature` the artifact contained,
  with nothing in the answer to say why. `stats` and `reload` now carry a `tool_restart_needed` diagnostic
  when the version loaded at import differs from the one the installed metadata reports at call time. It is
  R1-C25 one level up: there the graph's schema and the tool's shared a field, here the process's code and
  the installed code.

### Changed

- **Every contract rule is now mutation-tested on a real tree (R1-C37).** The method is the lab's: they
  did not believe a green `no_lazy_cycles` gate, put one lazy import back, and watched it go red. Each of
  the six rules already had a violation test — on a hand-built three-node graph, which proves the rule's
  arithmetic and nothing about the path that runs in production. The dogfood test runs the real tree and
  asserts green, which is the shape of evidence that method rejects. Now: one copy of codemap's own
  package, and per rule, green → one changed line → red naming the added edge → restore → byte-identical,
  each under a contract holding only the rule under test. Two things fell out: `Violation.modules` on a
  cycle carries rendered paths (`a → b → a`), not module ids, and a baseline for `exhaustive` has to name
  all sixteen real components, not the ten `codemap.toml` declares for a reader.

- **The R1-C36 target guard is tested on a namespace package assembled from several directories
  (R1-C36-f1).** The requested directory being *one of* the parts is a legitimate resolution; a build
  passes one `search_paths` entry, so no end-to-end test could have caught a guard that rejected it. The
  decision now lives in `_assert_is_the_target()` and is tested directly, including that an empty answer is
  not a mismatch — "griffe said nothing about the file" is not "griffe named the wrong file".

## [0.0.5] - 2026-08-31

**A correctness release: three of its four items were found by looking, one was reported.** No schema
change — graphs stay 0.13 and a 0.0.4 graph is still readable — but rebuild, because two of these fixes
change what a graph *says*.

The thread running through all four: **the tool answered, the answer was well-formed, and nobody could tell
it was wrong.** A signature that could not be called. A gate that found no contract and did not say where it
looked. A build that analysed a package other than the one it was given. In each, the failing output is
shaped exactly like the succeeding one — which is what stops a reader from checking it. Three of the four
were found while doing something else, and the one deliberate hunt (verifying a new rule on a real pair of
releases) is what surfaced the worst of them.

### Added

- **The declared signature travels with the `query` dossier (R1-C33).** The question after "where is it"
  is "how is it called", and `Node.signature` was already in the graph — getting it meant a second op.
  A function match now carries `signature`; a class carries `constructor` (its own `__init__`, under its
  own name, never dressed up as a signature the class does not have); a symbol marked deprecated carries
  `deprecated`. An inherited constructor is not resolved, and a field with nothing to say is absent rather
  than `null` — "we did not look" must not be spelled the same way as "there is nothing there".
  `signature` is how a symbol is *declared*; `call_contract` remains the answer to how it is *called in
  fact*, per call site.

  It came from auditing the "what we'd take" list of the CodeGraph разбор, where this item had been
  recorded three days earlier and never carded — a list without status reads as done. Taking it is what
  surfaced R1-C34 below.

### Fixed

- **A build could silently analyse a different package with the same name (R1-C36).** `griffe.load` defaults
  to `try_relative_path=True`, which reinterprets the module *name* as a path relative to the current
  directory and wins over the `search_paths` codemap passes. Run from a repo whose root holds `pkg/`,
  `codemap build /elsewhere/pkg` analysed the local `pkg` — exit 0, no warning, a complete graph of the
  wrong code. It hides wherever the two coincide (your package, your repo root) and appears exactly where
  the difference matters: a tag archive, a worktree, a copy — that is, in any two-snapshot workflow, which
  is what `codemap diff` exists for. A release gate comparing two such graphs reports "no API changes"
  every time. Found while verifying the new `apidiff` rule on a real pair of release tags, whose two graphs
  came out with identical node ids and an identical edge count across nine changed files.

  The name now resolves through `search_paths` only, and a resolved path outside the requested directory
  raises instead of being used. The absolute paths that appeared in `file` were a symptom of the same
  thing (D5: the artifact carries no absolute paths).

- **`check` names the file it looked in, and says that a miss exits 0 (R1-C35).** Reported by the lab as a
  lost minute: they reached for `check --config codemap.toml`, which is not a flag, and the reply — "No
  `[architecture]` contract found in codemap.toml" — reads the same whether the project has no contract or
  the command ran one directory away from it. Both exit 0. The default is right (a project without a
  contract must not fail), so what changed is the output: the absolute path it searched, the fact that this
  is a success exit, and the names of `--require-contract` and `--root`. `contract_path` joins the JSON
  surface. Docs now carry the discovery rule beside the first example instead of forty lines below it.

- **The stored signature keeps parameter kind (R1-C34).** `*args` was rendered as a parameter named
  `args` with a default of `()`, `**kw` as `kw = {}`, and the `/` and bare `*` markers were dropped, so
  `def h(*args, **kw)` and `def h(args=(), kw={})` produced the same string and a keyword-only parameter
  read as positional — write the call the signature describes and Python raises `TypeError`. Measured on
  two trees: **62 of 435** functions on codemap (14.3%), **152 of 931** on bquant (16.3%), including
  codemap's own public `resolve_scope`, whose six keyword-only parameters were documented as positional.
  Five consumers read that string (`report api-surface`, `export ctags`, `export vault`, living-docs and
  the `query` dossier), and `apidiff` re-parses it — where the loss had silently disabled three of its own
  rules, so `def f(a, b)` → `def f(a, *, b)`, breaking for every positional caller, was classified as no
  change at all. `apidiff` now reports `param-made-keyword-only` (breaking) and the widening
  `param-made-positional` (info).

  No schema bump: the shape of the graph did not change, and neither did the meaning of the field — it was
  simply rendered wrong. **Rebuild old graphs anyway**, and do not diff a pre-R1-C34 snapshot against a
  newer one: the churn it reports is the renderer changing, not the code (`docs/api-diff.md`).

## [0.0.4] - 2026-08-29

**Two days of a second real user, and a schema bump.** Everything below is `Fixed`, and all but one item
came from someone else's tree: a lab running codemap on a **flat, 47-module** layout filed four issues in
two days, each of which turned out to be wider than reported. Schema **0.12 → 0.13**: a repo-scoped graph
now has one origin for its paths, so rebuild those (a single-package graph is byte-identical and needs
nothing).

The theme, stated once because it repeated: **three of the six defects were in presentation, not in
computation** — a gate that judged a subset and printed an unqualified ✅, a `pytest` line naming a path
that does not exist, and `--format json` answering with the whole graph. The graph was right all three
times. An answer shaped exactly like the right one is what stops a reader from checking it, which is the
same discipline as `unknown ≠ none`, applied to form instead of content.

### Fixed

- **`codemap.__version__` was a second copy of the version, and it had drifted** — it read `0.0.2` while
  `codmap` 0.0.3 was on PyPI, so every SCIP index and ctags file stamped a version the package had not been
  for a release. Graphs were unaffected: `provenance` asks `importlib.metadata` rather than reading the
  literal, which is exactly why the literal was free to rot. It now reads the same source, and two tests
  hold it there — one that the two agree, one that the installed metadata matches `pyproject.toml`.

- **`report --format json` printed the graph instead of the report** (R1-C32,
  [#14](https://github.com/kogriv/codemap/issues/14)). The format branch sat above the dispatch on the
  report kind, so the kind was never read on that path and every kind returned the whole graph —
  byte-identical for `api-surface`, `dead-code` and `architecture` alike. Found by a consumer measuring
  documentation coverage, who parsed the result without error and first assumed they had called it wrong:
  no refusal, a substitution, and it passes the "did I get an answer?" check. Every report kind the CLI
  accepts now has a structured form carrying what its markdown carries, one level deeper: `api-surface`
  yields symbols with signature, first docstring line and file; `dependencies` keeps eager and lazy cycles
  **apart** (R1-C29's distinction survives into the data, not only the prose); `dead-code` carries the
  graded candidates and the whitelist error; `behavior` the call-site aggregate; `impact` and `flows`
  return **every** definition the name matched rather than picking one. `report` over `serve`/MCP still
  answers markdown, which is its documented contract.

- **A graph had no single origin for its paths** (R1-C31,
  [#12](https://github.com/kogriv/codemap/issues/12), schema **0.12 → 0.13**). `codemap tests` ends in a
  ready-to-paste `pytest …` line; built with roots below the repo root it named a path that does not exist,
  while looking exactly like one that does. The printed path was the symptom. Each root was its **own**
  origin — core files relative to the core package's parent, consumer files relative to their own root's
  parent — so `codemap build src/pkg --consumer tests` produced `pkg/mod.py` (relative to `src/`) beside
  `tests/test_mod.py` (relative to the repo root): two coordinate systems in one graph, and nothing
  anywhere saying so. Both read as repo-relative and at most one was. The packaged dogfood could not show
  it, because there the roots sit at the repo root and the two coincide. Now every `file` is relative to
  the nearest common ancestor of the roots' parents, and `provenance.roots` records each root relative to
  that origin instead of by basename — a basename was *less* than design D5 allows ("repo-relative roots")
  and dropped exactly the segment at issue. **Where that origin is** stays out of the graph, because it is
  a machine location and the graph is the half that travels; it goes in the `*.meta.json` sidecar as
  `roots_base`, and the **local** CLI resolves the pytest line against it — printing a rewritten path only
  when the file is actually there, and otherwise naming the directory the untouched path belongs to rather
  than letting the reader discover it from pytest. Served/MCP payloads keep the graph-relative id. Also
  fixed in the same pass: a function or class under a consumer root carried `lineno` and **no `file`** (the
  reporter counted 1093 such nodes against 61 with one), so `search` answered a consumer symbol with a line
  number and no file. A single-package build is byte-identical to before.

- **A passing `check` did not say it had judged only the eager import graph** (R1-C30-f2, from the
  second target's run of the gate). `codemap check` printed `✅ Contract satisfied. Rules enforced:
  no_cycles` on a tree where `report architecture`, from the same graph, listed **48 dependency cycles
  closed only by a function-local import**. The gate's scope was deliberate (R1-C29: a lazy import is how
  an import cycle is broken, so failing a build for it would report the remedy as the bug) — the silence
  was not. It is the same property-claim-over-a-partial-view that R1-C29 had removed from the report one
  day earlier, reappearing in the gate, where it is not a sentence but an unqualified ✅ the reader
  completes into "acyclic". The reporter's summary: *it did not fail on an unexpected violation; it failed
  to fail where violations exist.* Now: the gate still judges the eager graph, a passing run **always**
  states what it did not judge and how much of it there is (including zero — the R1-C28 rule that a field
  present only when there is something to say cannot be distinguished from a build that never says it),
  the structured payload carries the same under `scope`, and **`no_lazy_cycles = true`** lets a contract
  owner take the opposite position — *a gate you walk around by making the import lazy is not a gate* —
  instead of having one chosen for them. This closes the question §7 of the R1-C29 gap doc deliberately
  left open; what §7 got wrong was assuming the reachable defect was the gating, when it was the silence.

- **A call to a re-exported name resolved to nothing on the fast tier** (R1-C30-f1,
  [#13](https://github.com/kogriv/codemap/issues/13)). Reported against R1-C30 the day it shipped, as the
  one case that survived it on the reporting tree: `import registry as _r` inside a function, six calls
  through the alias, five resolved and the sixth — the re-exported one — did not. Same alias, same
  statement. Reproducing it made the case wider than reported: the fast tier dropped **every** call to a
  re-exported name, in all four import forms, including `from pkg.api import run` where `api/__init__.py`
  re-exports `run` — the most ordinary shape in Python. The mechanism is arithmetic, not inference: the
  resolver computes `pkg.api.run`, no such definition exists (it lives in `pkg.impl`), and the soundness
  guard correctly refuses to emit an edge pointing at a non-node. The guard was right; the **lookup was
  missing** — and the answer was already in the graph, since the structural pass emits an `export` edge for
  every re-export. It is now followed, transitively and with a cycle guard, and only ever along an edge
  that exists: a name the re-exporting module does not carry stays unresolved rather than being routed to
  a plausible neighbour. **Underneath it, a second defect** that would have kept the fix from reaching the
  reporter at all: on a **flat** layout there were no `export` edges to follow — R1-C21 taught the
  `imports` pass to recognise a bare sibling and the alias pass was never given the same rule, so every
  re-export in such a tree was filed as external and vanished. Now emitted, labelled
  `resolution: "flat"` like its `imports` counterpart. Measured against a deep build from before either
  change: `calls` 986 → 992 on bquant and 502 → 521 on codemap, none lost; `references` +24 and +8;
  `export` counts unchanged on both, which is the flat rule declaring itself narrow on correctly packaged
  trees. Micro-suite gains `c12_reexport`; recall over all true edges: fast 64.7% → **66.7%**, deep 66.7% →
  **68.4%**, precision unchanged at 100%.

- **The other half of the same blind spot: a call *through* a function-local import** (R1-C30,
  remainder of [#11](https://github.com/kogriv/codemap/issues/11)). R1-C29 taught the import map to see
  `def go(): from leaf import helper; return helper(x)`; call resolution still could not, so `--deep`
  produced the `calls` edge and the **default** fast tier — the one `codemap watch` runs in a loop — did
  not. That made the reporter's asymmetry ("the call resolves, the import does not") true of deep and
  backwards on fast, where both halves were blind. The fast resolver now reads a **per-function** import
  map: a name imported inside a function is bound in that function and inherited only where Python
  inherits it (a closure sees the enclosing function's import; a class body's import is *not* visible in
  its methods). Merging these into the module map would have been shorter and would have resolved
  `helper(x)` in a sibling function that never imported it — the false-edge shape this project holds
  against tools that walk name-matched call edges, so the guard is a test, not a comment. Measured
  against a **deep build from the previous commit** as an independent reference: `calls` 962 → 986 on
  bquant and 442 → 502 on codemap itself, **84 new edges, 84 confirmed by jedi, none lost**; the
  deep∖fast gap narrowed 600 → 576 and 225 → 165. `references` grew too (the same map feeds the
  used-as-a-value layer): +9 on bquant, +1 on codemap. The banded dead-code report did not move on either
  tree — but **three symbols went from zero inbound edges to one**, and one of them is codemap's own
  `DebouncedPoller`: `codemap query DebouncedPoller` on codemap's own graph returned no `used_by` block at
  all, because the only thing that constructs it imports it inside `_cmd_watch`. The watcher this project
  shipped last week looked, in this project's own graph, used by nothing. The accuracy micro-suite gained `c11_local_import`, whose second function calls
  the same bare name without importing it, so the cheap way to win this recall registers as a precision
  loss rather than a better score; suite recall over all true edges: fast 57.1% → **64.7%**, deep 60.0% →
  **66.7%**, precision unchanged at 100%. **Cost:** no extra parse (the behavioral pass already holds the
  AST) and the same indented-import gate as R1-C29, now shared between the two passes instead of written
  twice — **3.3% of the behavioral pass** on bquant, 4.1% on codemap. Still not resolved on fast:
  `import pkg.leaf` followed by `pkg.leaf.other()` (an attribute chain, not a name — a pre-existing limit
  of the fast resolver at module level too) and a function-local `import *`.

- **A function-local import was invisible, and the report called that "acyclic"** (R1-C29,
  [#11](https://github.com/kogriv/codemap/issues/11)). The import map was built from module-level
  imports only — a limitation recorded about the *extractor* and never traced to the *consumers*, who
  turned it into `_none — import graph is acyclic._`, a property claim over a partial map. The blind
  spot was anti-correlated with the question: a function-local import is precisely what a developer
  writes to break a cycle, so the edges the map could not see were the ones most likely to close one.
  On the benchmark target the report said **1 cycle where there were 41**. Function-local imports are
  now collected by codemap's own AST pass (griffe records neither them nor class-body imports) and
  carried on the edge as `extras.scope`. **A cycle now has two kinds**: `import_cycles` stays the eager
  graph, because "import cycle" means "breaks at import time" and calling a lazy import a cycle would
  report the remedy as the bug; the ones that close only through a lazy import are reported separately
  as coupling you cannot extract your way out of. Class-body imports count as **eager** — they run at
  class-definition time. Everything except cycles — coupling, layers, dependents, orphans — now uses the
  complete map. **Behaviour change worth knowing:** layer violations therefore see lazy imports too, and
  on the dogfood target that immediately surfaced one the report had never shown, reached only through
  an import written inside a function. A gate you can walk around by making the import lazy is not a
  gate. `_none — import graph is acyclic._` is gone from all three renderers that had inherited the
  sentence, enforced by a test that parses codemap's own source rather than asserting on three outputs.
  The tool's 41 cycles are set-identical to an independently computed AST truth set — the acceptance
  criterion, because a matching count is not a matching answer. **Cost:** griffe discards its own AST, so
  this means a second parse per module; the first implementation parsed nearly every file and walked each
  function's subtree separately, which cost ~30% of the fast build before it was caught. With one
  pre-order descent and a gate on *indented* imports (a module-level import is never indented), the
  measured price is **+0.33 s on the structural pass** — 2.02 → 2.35 s median of 7 runs on a 90-module
  package.

- **A result limit was partiality nobody declared** (R1-C28). `search "zone"` returned **50 matches of
  1 259** under an envelope that read, in full, `{"ok": true}` — in the one op whose whole job is to tell
  an agent what exists. Found by measuring a competitor and then asking the same question of ourselves:
  its `callers` defaults to `--limit 20` and says nothing either, which made a 79-entry answer read as a
  20-entry one of a different shape and nearly published a false finding
  ([#1639](https://github.com/colbymchenry/codegraph/issues/1639) upstream; the near-miss is written up in
  [`gaps/limit_truncation_2026-08-28.md`](gaps/limit_truncation_2026-08-28.md)). Every op that accepts a
  limit now carries `limit {applied, returned, total, truncated}` in its envelope — **always**, including
  `truncated: false`, because an only-on-truncation field forces a machine consumer to distinguish
  "nothing was cut" from "this build does not report cuts", and it cannot. `search` counts the full match
  set before slicing, so `total` is the real total rather than the page size. `total: null` is a legitimate
  answer and never an omission: `semantic`'s limit is applied inside the external adapter, so a full page
  comes back with the pre-limit total honestly unobserved. Orthogonal to `epistemic` — an answer can be
  resolution-partial *and* limit-truncated, and collapsing the two would lose which one bit. Ops bounded by
  something that is not a slice of a computed list (`pack`'s token budget, `impact`/`flows` depth) are
  exempt **in writing**, with reasons, and a guard test reads the ops' own source so a new op cannot learn
  a limit without declaring it. The MCP transport's separate `shown`/`total` dialect is folded into the
  same block. Surfaces: `search`, `semantic`, `tests`, `covers`, MCP `impact`/`call_contract`, plus a CLI
  footer on truncation. No schema change. See [`docs/accuracy.md`](docs/accuracy.md) §(c).

### Added

- **The rebuild debounce adapts to how big the change is** (M3.2-f1). A flat 2 s window taxed the common
  case — one file saved — for the burst that rarely happens. A change of at most two files (one save, or a
  module and its test) now settles on 0.3 s; a `git checkout` still coalesces on the full window. The size
  comes from `diff_scopes`, the build's own comparison, so there is no second notion of "how much changed",
  and an unknown size gets the **full** window: the fast path is taken only when the change is *known* to be
  small. Taken from the peer measured in `research/tools/codegraph.md`, which is why its save→answerable was
  0.33 s rather than the 2 s its headline debounce implies. No end-to-end number is claimed here — on the
  machine available, whole-build timings vary by ±30% run to run, wider than the effect; what is pinned is
  the deterministic behaviour, in `tests/test_m32_watch.py`.
- **The graph keeps itself current while you work** (M3.2 — the fourth and last brick). `codemap watch
  ./pkg -o graph.json` rebuilds incrementally once the tree settles; `codemap serve --graph graph.json
  --watch` reloads the warm session when the artifact moves. Measured save-to-answerable at the defaults:
  **8.1–8.7 s** on a real 90-file package, of which **4.3 s** is the rebuild itself — on anything real the
  rebuild dominates, not the polling; on a toy tree it is ~4–5 s, almost all debounce (1.11 s at
  `--interval 0.3 --debounce 0.3`). For scale, the peer that prompted this ships the same loop at
  **0.33 s** save→answerable, measured the same way. Deliberately two commands rather than one: extraction
  inside the resident server would compete with the queries it exists to answer, and a crashing rebuild
  would take the server down with it — so either half also runs alone, and `serve --watch` follows any
  external rebuild, including one typed by hand. What counts as a change is `scope_id`, the same
  content-hash manifest a build records in its sidecar, so the watcher and the build cannot drift apart and
  `touch` is not a rebuild. Polling, not inotify — native events would mean a dependency; the price is named
  and measured rather than hidden (median **50 ms** per poll for a 292-file, 4.7 MB tree, ~5% of a core at
  the 1 s default). A watcher started over a graph that already lags the tree catches up immediately, and an
  unreadable sidecar counts as stale, because "I cannot tell" must not resolve to "it is fine". A syntax
  error rebuilds like anything else — the module's symbols drop out and the diagnostic says *missing, not
  absent*; withholding the rebuild would serve a symbol table for source that no longer exists. A reload
  that catches a half-written file is retried rather than recorded as done, so the server never quietly
  answers from the old graph while believing it is current. See
  [`docs/incremental.md`](docs/incremental.md).

## [0.0.3] - 2026-08-27

**The first published release.** `pip install codmap` — the distribution name, because `codemap` was
taken on PyPI; the command, the import and this repository stay `codemap`. Everything below had
accumulated unreleased since 0.0.2, and the milestone that made publishing possible (M20) was mostly
about discovering that the things this repository claimed about itself were not checked by anything —
starting with the supported Python range, which turned out to be wrong.

### Fixed

- **CI stopped being green on a tenth less than it appeared to cover** (M20). Its second run reported
  474 passed / 55 skipped against 528 / 2 locally: fifty-three of those skips were the dogfood tests,
  which analyse a real external package expected beside the checkout that a fresh runner does not have.
  A green run made of skips — in the milestone that had just written exactly that sentence about another
  job. The target is now checked out and **pinned to a commit**, since its API is what those assertions
  encode and following its HEAD would be a moving input; the job fails if the tests skip regardless.
  Alongside it, `test_resolve_adapter_mode_skips_router` contradicted its own module's docstring ("no
  external tool is needed") by requiring the `ccc` binary on `PATH` — it passed on a machine that
  happened to have it and failed the first time it ran anywhere else. Availability is stubbed; the rule
  under test is dispatch, not installation.
- **The suite runs under plain `pytest`, not only `python -m pytest`** (M20). Four test modules do
  `from tests.frozen import frozen`, which needs the repo root on `sys.path` — `python -m pytest` puts
  it there, the `pytest` console script does not. So the suite passed the way CONTRIBUTING documents it
  and failed the way most people type it, with four collection errors. `pythonpath = ["."]` in
  `[tool.pytest.ini_options]` makes both work. Found by CI on its first run, which is roughly the whole
  argument for having it: an unchecked claim diverges from reality exactly where nobody tried it.
- **A typo in `codemap.toml` no longer paints the CI gate green** (R1-C27). Three loaders — the
  architecture contract, the integration gate, the dead-code whitelist — collapsed `OSError`,
  `ValueError` and `ModuleNotFoundError` into one silent empty result, which every caller then
  rendered as *the user configured nothing*. `tomllib.TOMLDecodeError` subclasses `ValueError`, so
  **deleting a single `]`** from a contract that reported 14 layer violations turned `codemap check`
  into "_No `[architecture]` contract found — nothing to enforce_", **exit 0**. As a CI gate, that is
  a green build on a gate that never ran. The tolerance is unchanged — nothing raises, a bad file
  still breaks no build — but the three conditions are now distinct (`codemap/tomlio.py`), the reason
  reaches every surface that renders a conclusion, and `check` **exits 2** on a contract it could not
  read. Exit 2 rather than a new code on purpose: the status answers *may the pipeline proceed?*, and
  a third code would sort an unreadable contract into the success branch of every `if rc == 2` that
  already exists. The JSON surface carried the same lie (`"ok": true` with zero violations) and is
  fixed in the same place. Found not by dogfooding but by measuring release-readiness; seventh
  application of "`unknown` is never rendered as `none`", and the first aimed at codemap's own
  configuration rather than at a target's source. No schema change.
- **Flat module layouts no longer defeat the build** (R1-C21; issues
  [#4](https://github.com/kogriv/codemap/issues/4), [#5](https://github.com/kogriv/codemap/issues/5)) —
  found within twenty minutes of pointing codemap at a second real target. A directory of sibling modules
  importing each other by bare name used to either **crash** (no `__init__.py`: griffe reports a namespace
  package whose `filepath` is a `list`, fed straight to `Path()` by five separate consumers) or, with an
  `__init__.py`, **succeed with zero `imports` edges** — after which `architecture` reported "no layer
  violations / acyclic" and `dead-code` called every live module an orphan. Sibling imports now resolve,
  labelled `extras.resolution="flat"` because the layout is an inference about `sys.path` rather than
  something the source states; call resolution and attribute access read the same qualified import map.
  A correctly-laid-out package is untouched: `bquant`'s graph is **byte-identical** before and after, and
  the inference is asserted to fire zero times there. No schema change.
  See [docs/flat-layout.md](docs/flat-layout.md).
- **…and across the root boundary** (R1-C21-f1; issue
  [#6](https://github.com/kogriv/codemap/issues/6)) — a consumer root (`--consumer tests`) writing the
  *same* bare-name import produced no edge at all, so `impact` still answered "isolated" for every symbol
  on a flat repo. Consumer-root imports are now qualified the same way, **gated on the core actually being
  flat**: a properly packaged core is never on `sys.path`, so a bare `import config` in a script cannot be
  reaching `pkg/config.py` and no edge is invented (the gate reads evidence — a namespace root, or existing
  `flat` edges — not the presence of `__init__.py`). bquant's full repo-scoped graph is byte-identical.

### Changed

- **`requires-python` is now `>=3.11`, and it is measured** (M20). It said `>=3.10` and had never been
  checked, because there had never been a second interpreter. Running the suite across the full declared
  range found 3.10 failing **13** tests and 3.11 failing **4**, against 512 passing on 3.12/3.13/3.14. Nine
  of 3.10's thirteen were the `tomllib` defect above; the other four (and all of 3.11's) were a fixture
  written in 3.12 syntax — where two of them were failing *because* the tool was right, naming the
  unparseable file with a reason. 3.10 is not bought back with a `tomli` dependency: codemap has exactly
  three runtime dependencies, and spending one on an interpreter whose upstream support ends in October 2026
  is rent on a version nobody is on. Also documented: **codemap parses a target with the `ast` of the
  interpreter it runs on**, so syntax newer than that interpreter is an unreadable input — always named,
  never dropped ([docs/hard-python.md](docs/hard-python.md)).
- **The distribution is now `codmap`; the command, the import and the repository stay `codemap`** (M20/D7).
  `codemap` is taken on PyPI. Only the packaging name moves, so nothing you type changes: `pip install
  codmap`, then `codemap build ./yourpkg` and `import codemap` exactly as before — stated in README's first
  install line rather than left to be discovered. The rename had one non-obvious consequence, and it was a
  provenance one: `provenance.py` looked up its own version with `version(TOOL_NAME)`, which after a rename
  raises `PackageNotFoundError` — turned into `None` by the existing handler, so **the version would have
  vanished from every graph in silence**, making two graphs built by different releases indistinguishable
  again. That is the gap R1-C25 exists to close, reopened by a packaging change. `TOOL_NAME` (the identity
  written into every graph, which does not move) and `DIST_NAME` (what `importlib.metadata` is asked about)
  are now separate, with tests holding both the resolution and the match to `pyproject.toml`.
- **Package metadata is no longer nearly empty** (M20). The wheel now carries a `License-Expression: MIT`
  (machine-readably it declared *no licence at all*, despite shipping an MIT `LICENSE`), project URLs,
  classifiers, keywords and an author. README's **Install** section showed only `pip install -e .` — an
  instruction to clone — and now tells a reader who has not cloned anything how to install, including the
  plain fact that codemap is not on PyPI yet.

### Added

- **CI** (M20) — [`.github/workflows/ci.yml`](.github/workflows/ci.yml), under one rule: *a claim in the
  repository is either checked here or removed*. Four jobs, each defending a sentence a user can read:
  `tests` (matrix 3.11–3.14) holds the test count and the supported range; `determinism` holds README's
  headline property by building the same tree twice and comparing bytes; `wheel` holds that the shipped
  artifact installs and runs, from a directory containing no codemap source — a path never once executed
  before, including the no-checkout branch of `provenance.tool` (R1-C25), which turned out to be correct;
  `interop` installs `readtags` and the `scip` CLI and **fails if they are absent**, because those two tests
  had skipped in every run this project has ever made and a green run made of skips is not a pass.
  Deliberately scoped: `determinism` runs the **fast tier only** — R1-C9 measured that the deep tier is not
  byte-stable, and asserting otherwise would be exactly the unchecked claim this work exists to end — and
  compares two builds within one job rather than across runs, since the determinism failure that taught this
  project the most was a *moving input*. What CI does not catch is written down too: see
  [docs/ci.md](docs/ci.md).
- **`codemap tests <symbol>` — which tests exercise a symbol** (R1-C24, axis A10), as runnable pytest node
  ids, ending in a `pytest …` line you can paste. Plus `--covers` for the inverse, serve ops `tests`/`covers`
  (29 → 31 ops, 26 → 28 MCP tools), and `Query.tests_for` / `Query.covers`. Needs a repo-scoped graph
  (`--consumer tests --mode full`); anything less says so instead of returning an empty list.
  The direct answer that existed before — `callers` — is empty for **82%** of core symbols, because a test
  calls `extract()` and `extract()` calls two hundred things. This walks backwards and returns the *nearest
  band* of tests, ranked by graph distance and nothing else (name similarity would be a guess about intent).
  **Validated against `coverage.py`, not asserted.** Running the suite with per-test contexts gave a
  precision cliff — median precision 1.00 at 1–3 hops returning 2–8 tests, then **0.67 at four hops
  returning 78** — so the default depth is 3, taken from that table. At the cutoff: **57%** of exercised
  symbols get an answer (deep tier, 43% fast), median precision **1.00**, and **93%** of answers contain at
  least one test coverage.py confirms executes the symbol.
  The other **16% come back `unknown`, never "untested"** — the fifth time this project has had to replace a
  confident nothing with an honest unknown. Its dominant cause is named rather than left mysterious: a method
  called on an object the test constructed resolves to no edge.
  The pytest **fixture seam was measured and deliberately not built**: on a suite that has a conftest (894
  tests, 48% taking a fixture parameter, 68 fixtures), exactly **1 symbol of 1043** is reachable only through
  a fixture. See [docs/test-mapping.md](docs/test-mapping.md).

### Fixed

- **`--deep` was a *downgrade* on a flat layout** (R1-C26; issue
  [#10](https://github.com/kogriv/codemap/issues/10)) — reported after the flat-layout fixes were verified on
  a real target: the import graph came alive (0 → 407 edges) but *"0 of 338 in-core call edges cross a module
  boundary"*. The tiers were **exclusive**: with `--deep` every call went to jedi and the name-based resolver
  was never consulted. Measured on that target: **487 calls / 158 cross-module on fast, 336 / 0 on deep** —
  paying for the better tier and receiving less, which is the one direction of failure a user cannot
  anticipate. The mechanism was not "jedi failed": jedi resolves `from leaf import helper` **correctly**, to
  `leaf.helper`, and the internal test `startswith(pkg + ".")` reads a name without the package prefix as
  external. The same defect R1-C21 fixed for griffe's import map, one layer down, at a boundary nobody had
  taught. It also cost 5 true edges on codemap and 5 on bquant, where nothing is flat.
  Now the jedi boundary applies the same sibling inference, and the two tiers are a **union**: when jedi has
  no usable answer — no answer at all, or an internal name that is not a graph node — the name resolver is
  consulted instead of the call being dropped. When jedi resolves a name *outside* the package that answer
  stands: it is a judgement, not a failure. **`calls(deep) ⊇ calls(fast)`** now holds — fast-only edges
  158 → 0 on the reporter's target (cross-module 0 → **234**), 5 → 0 on codemap, 5 → 1 on bquant, where the
  single remaining difference is deep being *more precise*. Accuracy-bench precision unchanged at 100%.
  See [docs/flat-layout.md](docs/flat-layout.md#the-deep-tier).
- **The conservation check no longer misfires on a repo-scoped graph** (R1-C23-f1) — caught in the first
  hour of using it: `--consumer tests --mode full` reported "137 modules built from 48 input file(s)",
  because `inputs.python_files` counts the extractor's walk of the *core* while the module count included
  consumer roots. It now counts core modules only. A point in the check's own favour: it fired on the first
  live discrepancy it met, which happened to be its own.
- **Robustness on hard Python** (R1-C23, axis B2) — a deliberate probe, one module per awkward construct,
  built cleanly and printed **nothing**. Most of it came through honestly (metaclasses, a `type()`-built
  class recorded as an *attribute* rather than an invented class, PEP 562/695, `match`, `async`,
  `singledispatch`, monkeypatching — and `dead-code high` was empty). Five things did not, all silently:
  - **a directory symlink into its own ancestry** produced **615 modules for 15 real ones**, 2378 nodes for
    58, nested 40 deep — while `codemap scope` on the same tree answered `files: 17`. Symlinks are still
    followed (a symlinked source tree is a legitimate layout), but a directory whose real path was already
    walked is not re-entered, and the skipped duplicate is recorded in `provenance.inputs.aliased_modules`.
  - **a file the extractor could not read simply disappeared** — a syntax error or a non-UTF-8 byte removed
    a module with no message, after which every report answered over a tree codemap had not fully seen. The
    build now names them, and the list travels in `provenance.inputs.skipped` with a reason each.
  - **`from X import *` produced no `imports` edge at all**, so the least explicit dependency in the language
    was invisible to layers, cycles and `check`. It now resolves through the same path as any other import.
  - **quoted and `TYPE_CHECKING` annotations were invisible** — R1-C22 taught the graph that an annotation is
    a reference and it only learned the unquoted form, while the quoted one is the idiom for a type that
    would otherwise be a circular import. Same edge, same `resolution="annotation"` label.
  - **a stub-only `.pyi` module was presented as real code.** Its symbols now carry `extras.stub` and are
    never dead-code candidates: "nothing calls it" says nothing about a symbol with no body.
- **A conservation check over every build** — modules cannot outnumber the files that define them, nor fall
  short of them beyond the files already accounted for as unreadable. Both directions are provably wrong
  states, so there is no threshold to tune; the point is the cause not met yet — it flags the symlink
  explosion without knowing what a symlink is, and would have fired on issue #5.
  Measured across the two tool versions on **frozen** copies (the dogfood target was being edited
  concurrently): bquant **+26 edges, 0 removed**, all of them quoted annotations; codemap **+3, 0 removed**;
  node counts unchanged. See [docs/hard-python.md](docs/hard-python.md).

### Added

- **Build provenance in the graph** (R1-C25; **schema 0.11 → 0.12**) — `graph.json` gains a top-level
  `provenance` block: tool name/version/**commit**, `tier` (`fast`/`deep`), the input `scope_id` (M19.A)
  and the target's VCS commit + dirty flag. The artifact used to have four keys and no answer to *"which
  tool, from what tree?"*. Measured: one frozen source tree built by codemap four commits apart gave **30
  edges vs 38** and **12 vs 7** `high` dead-code verdicts — with **both files declaring
  `codemap_schema: "0.11"`**, correctly, because only open `extras` had changed. Provenance is not schema.
  **Timestamp-free and path-free by construction**: two builds of an unchanged tree stay byte-identical
  *including* the block, and no absolute path can enter it (`build_provenance` raises; a test enforces it),
  so the graph remains safe to attach to a ticket. `tool.commit` is **absent, never guessed**, when codemap
  runs from an installed wheel. `tool.dirty` mirrors what `source` records about the target, and for the same
  reason — two builds from one commit with different working trees are two different tools (learned the hard
  way while measuring R1-C23: a clean worktree and a dirty checkout of the same HEAD reported the identical
  commit). Wall clock, `argv` and `cwd` stay in the `*.meta.json` sidecar — identity travels with the graph,
  the rebuild recipe stays home. See [docs/provenance.md](docs/provenance.md).
- **`codemap_schema` is finally read.** It was written and never checked, so a graph predating an
  extraction change was consumed in silence and answered with the new tool's confidence over the old tool's
  blindness. A mismatch now raises a diagnostic through the shared channel — CLI stderr, `stats`, and the
  three report headers at once. A **warning, never a refusal**: every stored graph predates 0.12, and
  turning an upgrade into an outage is not the honest option. `stats` also stops conflating two facts:
  `schema` is what the **graph** declares, `tool_schema` what the running tool writes.
- **`codemap diff` compares provenance before symbols.** Two graphs built by different tools, tiers or
  scope roots are a before/after of the *tool*, not of the code; the pair is now labelled as not
  comparable, above the verdict. On the evidence pair, `diff`'s "✅ No breaking changes" was true at the API
  level while the two graphs disagreed about which functions were dead — which is exactly how a clean
  verdict gets read as proof.
- **`build --incremental` checks the builder, not only the tree** (found by R1-C25, not designed for it) —
  it used to decide from the source alone: no `.py` changed, return the old graph. After a codemap upgrade
  that returns yesterday's graph built by yesterday's extractor, reporting `mode: unchanged` while doing it.
  It now compares the stored tool identity and tier against the running one and falls back to a **full**
  rebuild (`reason: "builder-changed"`); a graph with no provenance counts as a different builder.
- **The determinism tests now freeze their input** (`tests/frozen.py`). Four of them built the live bquant
  checkout twice and compared bytes — which measures whether anyone edited bquant between the two calls, not
  whether codemap is deterministic. One went red during this milestone for exactly that reason. Same
  discipline as the block above, one level down: freeze the input, or you are measuring the wrong thing.

- **Graph diagnostics** (`codemap/diagnostics.py`) — a build that produces **0 import edges across ≥2
  modules** now says so at build time (stderr), in `stats` (a `diagnostics` list beside `freshness`), and
  at the top of `report architecture` / `dependencies` / `dead-code`, *before* any conclusion drawn from
  the empty graph. A namespace-package target is named as well. Derived, never stored — `graph.json`
  gains no field. This half stands alone: it stays correct for any layout the extractor fails to parse.
- A second check for the dimension the first one missed: **≥1 consumer/doc root supplied but not one
  reference from them reaches the core**. The case that prompted it had 75 import edges — so the
  "empty graph" check stayed quiet — and none of them crossed a root boundary.
- Each check carries its own **severity** (`warning` invalidates the findings below it; `note` states a
  fact and invalidates nothing) and its own consequence sentence, rendered through one shared presenter.
  Fixes issue [#8](https://github.com/kogriv/codemap/issues/8), where the namespace-package *note* was
  captioned with the empty-graph *warning*'s "derived from that empty import graph — unknown, not clean"
  over a report computed from 404 import edges: the mirror of the bug the banners exist to prevent.

- **The `high` dead-code band is trustworthy again** (R1-C22; issue
  [#7](https://github.com/kogriv/codemap/issues/7)) — it graded a private function "no inbound calls,
  references, or decorators" while its name sat two lines below the definition. Measured across two real
  packages (codemap's own included) that was **20 of 51** candidates, from three forms the graph did not
  model: a function used **as a value** (dispatch table, `default=` callback), a call at **module level**
  (import-time statements were never walked), and a call inside a **nested def** (the closure was dropped
  wholesale). All three are modelled now — `references` with `extras.resolution="name"` / `"annotation"`
  (labelled apart: a dispatch table implies the symbol runs, an annotation implies a contract), `calls`
  sourced from the module node, and closure calls attributed to the innermost enclosing definition with
  `extras.via="nested"`. Two of the three were missing **call** edges, so `impact`, `callers` and `flows`
  were reading a call graph with import-time work and closure bodies cut out. The grader is untouched:
  it always demoted on an inbound edge, and now it has them. `high` went 46 → 29 (codemap) and 5 → 2
  (bquant); additions only (bquant +364 edge pairs, 0 removed). No schema change.
  See [docs/dead-code.md](docs/dead-code.md#what-counts-as-a-reference).
- **…and a local variable no longer counts as a reference to the function it shadows** (R1-C22-f1; issue
  [#9](https://github.com/kogriv/codemap/issues/9)) — the mirror of the above. Python binds per scope, so a
  read of a locally-bound name is the local, not a module function of the same name; six binding forms
  (assignment, parameter, `for`, `with ... as`, `except ... as`, a nested `def`) produced false edges and
  hid a dead function in `low`. `global`/`nonlocal` opt back out, module-level rebinding is unaffected, and
  function-local **imports** deliberately do not suppress — an import binds the name to the symbol it
  imports, which is what the edge records. Measured inert on real code: 0 edges suppressed on either package.


## [0.0.2] - 2026-08-23

First internal (unpublished) cut. Extracted into a standalone repository from its incubation home (the
`bquant` monorepo), preserving the full M0–M16 development history; since extraction it has grown the MCP
adapter (M17), graph freshness (M18), the input scope manifest (M19.A), SCIP + ctags export (R1-C1/C2),
complexity metrics (R1-C4), relevance ranking + context pack (R1-C6), the closed edge vocabulary (R1-C7),
graded dead-code (R1-C8), the external-tool router/adapter layer (R1-C16), **attribute-access edges
(R1-C20)** and **incremental rebuild (R1-C9)**. Graph schema **0.11**; **363 tests** (+ optional
SCIP/ctags CLI checks when those binaries are present); warm serve surface (23 ops), an MCP adapter, and
SCIP/ctags export. Not published to PyPI (the name `codemap` is taken there — see release notes).

### Milestones

- **R1-C20 — attribute-access edges** (schema **0.11**): closes the issue #1 honesty gap — `impact` on a
  class field returned `refs: []` / `risk: "none"` even with real read/write sites, because attribute nodes
  had no inbound edges. A new closed-vocabulary `accesses` edge (function → the attribute it reads/writes,
  `extras.access`/`resolution`) is emitted by `extract/attrflow.py`: `self.field` / `ClassName.field` /
  construction kwargs on the fast `ast` tier, `obj.field` on a typed local via jedi receiver-type inference
  on the deep tier; unresolved sites are honest counters, never edges to nothing. `accesses` joins
  `_IMPACT_EDGES` (attribute-scoped — columns stay out), so a field's blast-radius is real; `Query.readers`/
  `writers`, a serve `accessors` op + MCP tool, an `attributes` block in the dossier, CLI render. Honesty
  fix: a field with no modelled accessor reports `risk: "unknown"` (+reason), never `none`. On bquant: 1619
  fast + 158 deep `accesses` edges; `impact` on `SwingThresholds.zigzag_deviation` → 6 refs (was `[]`).
  +15 tests. Docs: [docs/attribute-edges.md](docs/attribute-edges.md). Closes #1.

- **R1-C9 — incremental rebuild** (no graph schema change): `codemap build --incremental` recomputes only
  changed modules and splices the rest from the previous graph. The cheap, tier-independent passes (griffe +
  structure + dispatch + family + dataflow, ~4s) run whole and fresh every time; the two expensive jedi
  passes run only on the *affected* modules (changed/added/removed + fresh importers + old dependents), which
  is where ~93s of a ~97s deep build lives. Reuses the `.meta.json` scope sidecar (M19.A) for content-hash
  change detection; falls back to a full rebuild past 50% affected. On bquant a one-file deep edit rebuilds
  in ~5s vs ~60s (~12×). Fast tier is byte-identical to a full build; the deep tier matches a full build up
  to jedi's own run-to-run inference variance (two full `--deep` builds already differ by a few deep edges —
  a documented property of the deep tier, not the splice). `model.to_dict` now orders edges by full content
  so a spliced build serializes identically. +12 tests. Docs: [docs/incremental.md](docs/incremental.md).

- **Fixes:** stale dogfood tests repointed after bquant removed `MACDZoneAnalyzer` (deprecation-detection now
  pinned on a dedicated fixture; blast-radius on `ZoneInfo`); gitnexus router disclaimer test made
  environment-independent (mock `which`). Closes #2.

- **R1-C6 — relevance ranking + token-budgeted context pack** (no graph schema change): codemap becomes a
  first-class context provider. `Query.rank(seeds, root)` scores symbols by **personalized PageRank** over
  usage edges (calls/imports/references/inherits/implements) — global importance with no seeds (hubs like
  `logging_config`/`config` rank top on bquant), or relevance to a context with seeds (symbol id / short name
  / file path; aider's repo-map trick). The PageRank is a **pure-Python power iteration** — no numpy/scipy
  dependency (codemap stays lightweight) — and deterministic. `codemap pack --budget N [--seed X]`
  (`serve/pack.py`, serve op + MCP `pack` tool) renders the highest-ranked symbols into a token budget
  (~4 chars/token estimate, no tokenizer): output never exceeds the budget and top hubs land before leaves;
  seeding on `analyze_zones` surfaces the zone subsystem instead of the global hubs. +12 tests. Docs:
  [docs/pack.md](docs/pack.md). Closes the last open Tier-2 R1-C capability.

- **R1-C7 — closed edge-type vocabulary** (no graph schema change): `model.EDGE_TYPES` declares the closed
  set of 10 edge types (`contains`/`imports`/`export`/`inherits`/`decorated_by`/`calls`/`references`/
  `implements`/`reads`/`writes`), each documented; node `kind` stays an open set by design (edges are typed,
  nodes aren't). `tests/test_r1c7_edge_vocab.py` pins the set and fails if a real graph emits an undeclared
  type (a new relationship must be added to the vocabulary, not emitted silently) or if a declared type stops
  appearing (no dead vocabulary). Caught and fixed a drift in passing: both `model.py` and DESIGN §2 wrote
  `exports` while the code emits `export`. +3 tests.

- **R1-C8 — dead-code confidence + whitelist** (no graph schema change): `report dead-code` now **grades**
  each uncalled-private-function candidate instead of listing flat — **high** (no inbound edge or hook),
  **medium** (a decorator / registry may invoke it implicitly), **low** (something *references* it → likely
  alive) — each with a provenance reason naming why. The **low** tier is the false-positive cut a call-only
  tool (vulture) can't make: codemap's cross-root reference edges show a private helper is used by a test, a
  re-export, or a registration. A `[dead_code].whitelist` (exact id / `fnmatch` glob) in `codemap.toml`
  suppresses framework-wired candidates (argparse `set_defaults`, dispatch dicts), and `--min-confidence`
  filters by tier. `Query.dead_code(...)` is the core; `dead_symbols()` stays a back-compat wrapper. Surfaces:
  CLI `report dead-code --min-confidence`, serve/MCP `report` op. +10 tests. Docs: [docs/dead-code.md](docs/dead-code.md).

- **R1-C16 — external-tool router/adapter layer** (no graph schema change): codemap can call a
  **user-installed** external tool for capabilities outside its scope — opt-in, off by default, bundling
  nothing (calling ≠ distributing). Two modes on a license gradient: **router** (forward the answer as-is;
  any license) and **adapter** (translate the output into codemap's own contract; permissive/MIT-Apache
  only, machine-enforced at registration). The router half shipped earlier (GitNexus passthrough,
  `codemap route`); this adds the **adapter** half and the flagship use: **semantic search enriched to
  codemap symbols**. `codemap semantic "<query>"` (also the `semantic_search` MCP tool + serve op) routes a
  concept query to an opt-in **cocoindex** adapter (Apache-2.0, local, no DB/key), then resolves each fuzzy
  hit `(file, line)` to the **exact codemap symbol** at that location via the graph — fuzzy retrieval, exact
  structure, the composition neither tool gives alone. Unresolvable hits are kept honestly as `unresolved`;
  hits de-dup per symbol (best score). Enrichment lives in `serve` (needs the query layer); the adapter
  stays graph-free so `integrations` remains a near-leaf layer (codemap's own architecture contract enforces
  this — dogfood stays green). Generalized: any permissive retrieval tool registers the same way. Core works
  with no tool installed (→ empty result, never an error). +12 tests. Docs: [docs/integrations.md](docs/integrations.md).

- **M19.A — input scope manifest** (no `graph.json` schema change): codemap is deterministic on its output;
  this adds the symmetric thing for its **input**. `codemap/scope.py` resolves a scope (build args) to a
  sorted file list, content-hashes each (sha-256), builds a **profile** (files/bytes/loc by role & ext +
  largest), and computes a **`scope_id`** — same id ⇒ provably identical input. Operates **in place** over
  the real tree (the live path); **git-mode enumeration** (`git ls-files`, preferred when available) yields
  the gitignore-correct set for free — the `venv_bquant` trap from the graphlens pilot is impossible by
  construction — and records git provenance (`commit/ref/dirty` + free `git_blob`), while identity stays
  sha-256 (mode- and dirty-independent). New CLI `codemap scope <path> […] [--no-git] [--json]` and
  `codemap scope --diff A.meta.json B.meta.json`; `build` writes the `scope` block into the M18 sidecar.
  Stdlib-only (hashlib/subprocess). Substrate for R1-C9 (Merkle incremental) and M3.2 (hash-freshness).
  +7 tests. Design: [docs/design/scope.md](docs/design/scope.md).
- **R1-C1 — SCIP export** (no schema change): `codemap export scip -o index.scip` emits a
  [SCIP](https://scip-code.org/) index so Sourcegraph, Glean and any SCIP consumer light up
  go-to-definition, symbol search and type hierarchy over codemap's graph. Highest-value interop move
  from the R1 landscape. **Honest scope:** codemap's graph is symbol-level (no call-site coordinates),
  so the export is *definitions + SymbolInformation* — one Definition occurrence per located node, kind,
  docstring, and `inherits`/`implements` as SCIP `relationships` (`is_implementation`); reference
  occurrences (find-references) are deliberately omitted rather than faked. Symbol strings are built from
  codemap's canonical ids via the SCIP descriptor grammar (namespace `/`, type `#`, method `().`, term `.`).
  `protobuf` is an **optional** extra (`pip install codemap[scip]`); vendored bindings generated from the
  official `scip.proto`, lazy-imported. Deterministic bytes; validated by protobuf round-trip and the real
  `scip print` CLI. Partially satisfies R1-C7 (structured descriptor ids). +8 tests.
- **R1-C2 — ctags export** (no schema change): `codemap export ctags -o tags` emits a universal-ctags
  `tags` file — the lowest common denominator of editor navigation (vim/Emacs/`readtags` binary-search a
  sorted tags file). `codemap/serve/ctags.py` renders one extended-format line per **definition**
  (class/function/method/attribute): a `/^…$/` search-pattern address when the source line is readable
  (robust to line drift; `\`/`/`/`$` escaped), else a bare line-number address (always available from the
  graph). Extension fields are all facts codemap already holds — `kind` (c/f/m/v), `line:`, `scope`
  (`class:Foo`; module scope omitted as universal-ctags does), `signature:(…)` + `typeref:typename:…` for
  functions, `access:` (public/private), `end:`. **Honest scope:** definitions only (no reference tags —
  that is SCIP's job); modules are files not tags (skipped); re-export aliases (a symbol with no own
  location) are skipped so each definition is tagged once at its real site. Deterministic: pseudo-tags
  declare `!_TAG_FILE_SORTED\t1` and real tags sort by name→file→address (binary-searchable). Stdlib-only.
  On bquant: 1585 tags, byte-stable. +9 tests (`readtags`-CLI check when present). Docs:
  [docs/export.md](docs/export.md).
- **R1-C4 — per-function complexity metrics** (schema **0.10**): function nodes carry
  `extras.complexity` = `cc` (McCabe cyclomatic), `volume` (Halstead), `sloc` (physical span) and
  `mi` (Maintainability Index, 0–100). Computed in the behavioural AST pass (same walk as the control
  skeleton) — **source-only, stdlib-only (no radon), deterministic**; cyclomatic counts decision points
  over the function's *own* body (nested defs are separate nodes, not double-counted). codemap's value
  isn't the metrics (radon has those) but **blending them with the graph's structural signals**:
  `Query.hotspots` annotates god-classes with `total_cc`/`max_cc` and adds a `complex_functions` list
  (top by cyclomatic, `min_cc` threshold); `report architecture` and `report behavior` render them; the
  `query` dossier carries per-symbol cc/mi/volume/sloc. This separates "big by connectivity" from "complex
  by McCabe" — e.g. on bquant `NotebookSimulator` (23 methods, ΣCC 50) vs `StatisticalPlots` (23, ΣCC 111).
  +15 tests. Closes the last open Tier-1 R1-C capability.
- **R1 — research track opened** (docs only): survey of adjacent code-analysis / code-graph tools in
  `research/` — a landscape map (comparison matrix + integrate/wrap/learn verdicts) plus four theme reports
  (AI-context/repo-map, code-graph/index infra, query/dataflow engines, Python graph/arch peers). Grounded,
  web-verified. Net finding: the field is converging on codemap's thesis (source-only, deterministic,
  precise graph, no stale index); differentiators are the canonical diffable `graph.json` with provenance
  and native agent/MCP verbs. Concrete capability candidates (SCIP/ctags export, architecture-contracts
  `--check`, complexity metrics, relevance ranking + token-budgeted pack, …) logged as use-driven backlog
  items (R1-C1…C15, fully specified with scope/acceptance/effort, tiered by value÷cost) — including a
  bottom-up field intake (R1.5) of curated Telegram sources that confirms the field has converged on
  codemap's thesis and adds the live competitor roster + a grep-vs-graph benchmark. No code/schema change.
- **F23 — impact accepts a full/canonical id** (no schema change): `impact` (op, markdown, CLI) resolved
  its input by short name only, so passing a full id like `pkg.mod.Class` — exactly what `query`/`search`
  return — matched nothing and gave a falsely-empty blast radius (found on a live task). Added
  `Query.impact_targets` (node-id → itself, short name → all matches, else canonical/where_defined) and
  routed both `_op_impact` and `render_impact` through it. The extraction was fine — class instantiation
  was always captured; the bug was serve-layer input resolution.
- **M18 — graph freshness** (no schema change): the MCP server serves a static graph, so `stats` now
  reports `freshness` (`built_at` / `age_seconds` from the file mtime) — an agent can tell the map may be
  stale. The canonical graph.json stays timestamp-free (determinism preserved); build recipe + time live
  in a sidecar `<graph>.meta.json`, and `codemap refresh <graph.json>` rebuilds from it. First step of the
  deferred freshness work (M3.2), prompted by the now-live MCP consumer.
- **F22 — compact MCP payloads** (no schema change): shaped from the first live agent-over-MCP run.
  The `impact` and `call_contract` MCP tools are compact by default — `impact` omits the duplicate
  markdown and caps the flat ref list at `limit` (by_root counts stay complete); `call_contract` caps
  its list. `full=true` returns everything. On a hub (`MACDZoneAnalyzer`) this cut the `impact` payload
  ~65% and `call_contract` ~49%. Underlying ops / CLI unchanged (markdown still rendered there).
- **M17 — MCP adapter** (no schema change): `codemap serve --mcp` exposes the warm serve surface as
  Model Context Protocol tools (18 tools, one per agent-facing op) so an AI-agent host can drive
  codemap natively. Thin wrapper over `Session.handle` — the ambiguity signal (`resolved.ambiguous`)
  and error envelopes pass through unchanged. `mcp` is an **optional** dependency
  (`pip install codemap[mcp]`); the import is lazy so codemap works without it.
- **M16 — architecture overview** (schema 0.9): `report architecture` — layers + direction/violations
  (order-free), coupling (Ca/Ce/instability), god-objects & call-hubs (pervasive-tagged); `Query.layers/
  coupling/hotspots`, serve op `architecture`.
- **M15 — diff / change-review** (no schema change): `codemap review <diff>` → risk-sorted change-set
  dossier; `Query.symbol_at`/`symbols_in_range` (location→symbol), serve ops `locate`/`review`.
- **M14 — soundness** (schema 0.9): `canonical_info` surfaces ambiguity (`resolved.ambiguous`) instead of
  silently picking one of many defs; dataflow access-form (`subscripted` / `access`) so `columns()`
  returns real column-like keys, not dict-literal payload noise.
- **M13 — serve ergonomics** (no schema change): discovery/orientation ops — `search`, `families`,
  `columns_of`, `source`, `resolve`; re-export canonicalization; `file:line` in query results.
- **M3.1 — warm serve**: resident process, graph in memory, line-delimited JSON over stdio,
  transport-neutral (MCP-mappable).
- **M8–M12** (schema 0.5→0.8): provenance-aware dead-code, registry-family `implements` links,
  class-chunk call aggregation, call-site argument contracts, string-key column dataflow.
- **M6–M7**: repo-scope / impact (multi-root provenance); registry-aware call bridging.
- **M0–M5**: canonical graph (structure, imports, exports, inherits), query API, behavioral call graph,
  deep call resolution (jedi), and the RAG/vault/mermaid render views.

See [BACKLOG.md](BACKLOG.md) for the detailed milestone log and [gaps/](gaps/) for the dogfood runs that
drove each one.
