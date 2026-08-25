# Design — Robustness on hard Python (axis B2)

**Status:** ✅ **shipped** (2026-08-25, no schema change of its own — it rides R1-C25's 0.12).
**User docs:** [../hard-python.md](../hard-python.md).
**Decisions resolved:** D1 = **B** (canonical-path visited set), D2 = collect + `build` warning + carried in
`provenance.inputs` (R1-C25 landed first, as sequenced), D3 = **edge only**, name expansion deferred and
recorded, D4 = **yes**, same `annotation` label, measured at +26/+3 edges, D5 = **B** (label, exclude from
dead-code) and `.pyi` left out of the scope manifest as it was, D6 = **yes** — the conservation check is the
milestone's most valuable piece, D7 met.
**Motivates:** gap [hard_python_robustness_2026-08-25](../../gaps/hard_python_robustness_2026-08-25.md).
**Backlog:** R1-C23.
**Related design:** [flat_layout.md](flat_layout.md) (the same "one normalisation boundary" lesson),
[source_visible_references.md](source_visible_references.md) (D4 extends its annotation form),
[graph_provenance.md](graph_provenance.md) (D2 needs a carrier and R1-C25 is building one).

Five measured holes, all silent. The probe in the gap doc shows the parsing itself is fine — metaclasses,
PEP 695 generics, `match`, `singledispatch`, module `__getattr__` and monkeypatching all come through, and
`dead-code high` was empty. So this is not "make the extractor understand dynamic Python". It is four narrow
repairs plus one generic net.

**Guiding invariants (unchanged):** source-only, deterministic, two tiers, resolved-or-honestly-flagged,
closed edge vocabulary (R1-C7), `extras` open-ended.

---

## D1 — Directory symlink cycles: canonicalise and refuse to re-descend

**Recommended: yes, canonical-path visited-set.**

`hardpkg/loop → .` produced **615 modules from 17 files** (600 phantom, depth 40) with no warning.

Three options were considered:

| option | effect | verdict |
|---|---|---|
| **A. do not follow directory symlinks at all** | trivially correct on the cycle | rejected — a symlinked source dir is a legitimate layout (vendored subtree, bind mount); refusing it silently loses real code, which is the same class of defect one level down |
| **B. canonicalise (`Path.resolve()`) and skip an already-visited real directory** | the cycle collapses to its first, real occurrence | **recommended** — keeps legitimate symlinks, kills only the repetition |
| C. depth cap | bounds the damage | rejected — a cap turns a wrong answer into a smaller wrong answer, and picks an arbitrary number |

Enumeration must therefore key on `Path.resolve()`, not on the walked path. **Where:** the same lesson as
R1-C21 — normalise at *one* boundary, not at each consumer. Module enumeration has two entry points today
(the griffe walk and `scope.py`'s own file walk) and `scope.py` is already correct, so the fix belongs in the
extractor's enumeration and must be covered by a test that walks both.

**Note for the implementation:** a symlink to a directory *outside* the target is not a cycle and stays
included; only re-entry into an already-visited real directory is dropped.

## D2 — Unreadable files: the extractor must report what it skipped

**Recommended: yes — collect, print, and hand the list to whoever carries provenance.**

A `SyntaxError` or a `UnicodeDecodeError` currently removes a module from the graph with no trace. Three
questions, in order:

**(a) Collect what?** Per skipped input: repo-relative path, reason class (`syntax` | `encoding` | `io`),
and the parser's message. Never the absolute path (AGENTS.md — the artifact is shareable).

**(b) Surface where?** Three surfaces, all of which already exist:
- `build` prints `[warning] 2 files could not be read: …` — the same channel R1-C21 added for the flat-layout
  diagnostic.
- `stats` and the reports carry it, via `diagnostics.py` (derived, never stored) — *if* the data reaches
  them.
- `serve`/MCP answer with it in the envelope, so an agent is told the graph is partial.

**(c) Carried how?** This is the one real fork, and it is **not ours to settle alone**: a skipped-file list is
provenance about the build, and R1-C25 is deciding where provenance lives.
- If R1-C25 lands a `provenance` block in `graph.json`, the skip list belongs there — the graph stays
  self-describing when handed to an agent.
- Until then, the sidecar `*.meta.json` is the only carrier, and it is `.gitignore`d and optional, so a
  graph consumed alone still lies by omission.

**Decision: implement (a) + the `build` warning of (b) now — they are independent — and take the carrier
from R1-C25 rather than inventing a second one.** Sequencing R1-C25 first is cheaper than migrating a
carrier later.

## D3 — `from X import *` → emit the module-level `imports` edge

**Recommended: yes, edge only; do not expand the names.**

Two separable things:

1. **The dependency.** `from .meta import *` names its target module exactly. Emitting
   `imports: star → meta` is exact, cheap, and restores the edge that `architecture` (layers, cycles),
   `check` and `import_graph` need. **No honesty caveat — this is not an approximation.**
2. **The bindings.** Which names the star actually binds requires `__all__`, or failing that the target
   module's public surface. codemap has both (`export` edges already model `__all__`). Expanding them would
   let a *use* of a star-imported name resolve to its definition.

**Do 1, defer 2.** Reason: 1 is exact and fixes the architectural blindness, which is the damage. 2 is a
*resolution* improvement whose value is unmeasured — the probe has one star-import, and neither codemap nor
bquant uses the form at all. Deferring keeps this milestone from growing an unmeasured feature; the gap doc
records 2 so it is not rediscovered as new.

## D4 — String / `TYPE_CHECKING` annotations → resolve like unquoted ones

**Recommended: yes, same edge, same label.**

R1-C22 emits `references` with `resolution="annotation"` for `def f(r: Reader)`. The quoted form
`def f() -> "Base"` yields nothing, and the quoted form is precisely the idiom used for types that would
otherwise be a circular import — the dependencies most worth seeing.

Mechanics: where an annotation node is a `Constant` holding a `str`, parse it with
`ast.parse(value, mode="eval")` and feed the resulting expression through the same name-resolution path.
On a parse failure, skip silently — an unparseable annotation is a type-checker's problem, not a graph edge.

**Same label, not a new one.** `resolution="annotation"` already means "the symbol appears in a contract, not
in execution"; whether the author quoted it is syntax, not meaning. Adding `"annotation-string"` would split a
category for no consumer's benefit.

**Sizing must be measured before merge** — the same discipline that turned D3 of R1-C22 from "5202 sites, too
expensive" into "21 edges". `TYPE_CHECKING` blocks tend to be small, but `from __future__ import annotations`
makes *every* annotation a string at runtime while leaving it unquoted in source, so this must not
accidentally become "re-resolve every annotation twice".

## D5 — Stub-only modules: label, do not invent

**Recommended: keep the node, label it, exclude it from anything that implies runtime.**

`api.pyi` with no `api.py` currently yields a module with a function `stub_only` that does not exist at
runtime. Two candidate rules:

- **A. skip `.pyi` when no sibling `.py` exists** — simple, loses the declared surface of a stubs-only
  distribution.
- **B. keep, mark `extras.stub = true` on the module and its children** — the surface stays queryable, and
  dead-code/coverage-style answers can exclude it.

**Recommended B**, on the R1-C13 precedent: label an approximation rather than hide it. Cheap to implement
(`extras`, no schema bump). One consequence to handle: a stub node must never be a dead-code candidate — a
stub is *by definition* uncalled.

**Related, noticed while measuring:** `scope.py`'s `DEFAULT_INCLUDE` is `("*.py", "*.md")`, so a `.pyi` the
extractor *does* read is not counted as input. Either the extractor stops reading it (A) or the manifest
starts counting it (B). Under B, add `*.pyi` to the include list — otherwise D6's cross-check has a built-in
off-by-one.

## D6 — The net: cross-check the graph against the scope manifest

**Recommended: yes — this is the highest-value item in the milestone.**

The tool already computes the truth. With the symlink in place, `codemap scope` answers `files: 17` while the
graph holds 615 modules. Nothing compares them.

A derived check in `diagnostics.py` (the R1-C21 pattern — computed on read, never stored):

> *module nodes ≫ input files* → **warning**: "the graph holds 615 modules for 17 input files — the tree was
> probably walked through a symlink"
> *module nodes ≪ input `.py` files* → **warning**: "17 input files produced 15 modules — 2 were not read"

Note what this buys: it catches **B2-1 without knowing about symlinks and B2-2 without knowing about
syntax errors** — it is a conservation law over the build, so it also catches the next cause of the same
shape. It would have fired on #5 too.

**Precondition:** the check needs the file count, which lives in the sidecar today. Same carrier question as
D2 — another reason to sequence R1-C25 first.

**Threshold, deliberately crude:** warn when module count exceeds input file count at all (a module cannot
outnumber the files that define it), and when it falls below by any amount. No ratio, no tuning — both
directions are provably wrong states, not heuristics.

---

## D7 — Acceptance

Byte-identity is **not** the criterion (unlike R1-C21): D3/D4 add true edges, D1 removes fictional ones.

1. The probe fixture reproduces the *truth* column of the gap's §3: 15 modules, 58 nodes, 91 edges — with the
   symlink present.
2. Both unreadable files are **named on stdout** at build time and counted in `stats`.
3. `imports: star → meta` exists; the fixture's layer/cycle answer changes accordingly.
4. `def dump(o) -> "Base"` yields a `references` edge with `resolution="annotation"`; the added-edge count on
   codemap and bquant is measured and reported in the backlog entry before merge.
5. Stub-only symbols are labelled and never appear as dead-code candidates.
6. The D6 diagnostic fires on the symlink build and on a tree with a deliberately broken file, and is silent
   on codemap, bquant and every existing fixture.
7. codemap's and bquant's graphs change by **additions only** apart from what D3/D4 legitimately add — no
   node disappears.
