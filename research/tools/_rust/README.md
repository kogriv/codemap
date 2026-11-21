# Rust: the lab's tools against the native ones, on ripgrep

**Backlog:** R1-C111 (navigation), R1-C112 (audit axes). **Design and pre-registration:**
[`docs/design/recipe_rust.md`](../../../docs/design/recipe_rust.md) (D1–D7, E1–E15, reconciled there).
**Status:** navigation scored for CodeGraph and GitNexus; audit axes scored for CodeGraph, GitNexus, roam-code
and jscpd (2026-11-21). OntoIndex and graphlens next.

This is the evidence document for everything Rust in the catalog and in the build-story. Numbers here come from
the result files beside it; if a sentence and a result file disagree, the file wins.

## The question

The owner's question, in his words: "where do these tools give what the native ones do not? That is the use and
the expertise. If everything is done by the native tools, why the extra tools?"

On navigation (where is X defined, who calls it, who implements it), rust-analyzer resolves names through the
compiler's front end. It is the truth by construction, so a third-party tool can at most match it. Navigation
alone gives no reason to install anything. The useful comparison is by **audit axis**: dead code, architecture,
change impact, duplication, and the axes the Rust ecosystem already covers.

## The tree and the truth

- **Tree:** ripgrep 15.2.0, commit `e89fff89ac9af12e8d4ce9d5fd07beb408ca730f`, extracted with `git archive`
  (100 `.rs` files, 53 025 lines, 10 workspace crates). For the audit axes, `plant.py` writes a planted copy:
  dead functions, alive traps, a module cycle, a layer break and three clones (§Audit axes).
- **Truth:**
  - rust-analyzer 1.96.0 over LSP (`truth_ra.py`, `truth_refs.py`): workspace symbols, call hierarchy,
    implementations, references, document symbols. Ready in 5 s on this tree.
  - cargo-modules 0.27.0 (`truth_modules.py`): module `uses` edges, `--cfg-test`, workspace crates only.
  - Every truth file reproduces byte for byte over two runs. Hand checks: 20 of 20 sampled call sites; 10 of
    10 sampled "false deaths" are real production calls; 12 sampled "unused" functions have no caller.
- **Tools** (each deterministic over two runs): CodeGraph 1.6.4 (npm), GitNexus 1.6.12 (npm), roam-code
  14.1.0 (PyPI), jscpd 4.3.0 (npm).

## Navigation (R1–R5)

| Question | CodeGraph 1.6.4 | GitNexus 1.6.12 |
|---|---|---|
| R1 definitions (3 names, 25 definitions) | precision 1.0, 23 of 25 | 21 found, one a struct field |
| R2 callers of a plain function (`grep_cli::escape`, 13) | 13 of 13, namesake not conflated | 2 of 13 |
| R2 through `dyn` (`ParallelVisitor::visit`, 3) | 3 of 3 | 0 of 3 |
| R2 through generics (`Sink::matched`, 3) | 1 of 3 (misses `(**self).matched` forwarders) | 0 of 3 |
| R2 trait method, strict (`Matcher::find_at`, 4) | 3 of 4 | 3 of 4 |
| R2 macro call sites (5) | not answered | 0 |
| R4 module graph, crate-root targets excluded | P 0.944 R 0.802 | P 0.989 R 0.563 |
| R5 implementors (16) | 13 (blanket impls missed) | 13 (blanket impls missed) |
| Index time | 3 s | 30 s |

Neither tool binds trait calls by name, the failure predicted in E4. Both fail by **omission**, so on Rust a
short or empty answer does not mean there are no callers. Files: `results/codegraph-1.6.4.*`,
`results/gitnexus-1.6.12.*`.

Scoring decisions, each found while checking a disagreement against the code:
- rust-analyzer lists a call on a concrete type under the trait method *and* the impl, so R2 for a trait method
  also has a strict view without those callers;
- CodeGraph returns file-level `use` lines as callers: filtered and counted in the notes;
- a caller listed once per call site counts once;
- R4 is compared after folding inline modules into their file, with and without crate-root targets.

## Audit axes

| Axis | Native coverage | Gap |
|---|---|---|
| security, dependencies | cargo-audit, cargo-deny, cargo-vet, cargo-geiger | none |
| API compatibility | cargo-semver-checks | none |
| correctness, lint | rustc, clippy, miri | none |
| unused dependencies | cargo-machete, cargo-udeps | none |
| dead code | rustc `dead_code` | a `pub` item of a library crate unused by the workspace |
| architecture | Cargo forbids crate cycles; cargo-modules draws the graph | module cycles and layer rules inside a crate |
| change impact | rust-analyzer call hierarchy, one level per request | no transitive closure in one step |
| duplication | clippy `match_same_arms`, `if_same_then_else` (local) | cross-file and near-miss clones |

### Plants (`plant.py`)

| Plant | What | Truth |
|---|---|---|
| P1 | private unused fn in a library crate | dead; rustc must flag it |
| P2 | `pub` unused fn, exported from a library crate | dead; rustc cannot see it |
| P2b | `pub` unused fn in a private module of the binary crate | dead; rustc must flag it |
| P3 | `pub` fn used only from another workspace crate | alive |
| P4 | impl method reached only through `&dyn Trait` | alive |
| P5 | impl method reached only through a generic bound | alive |
| P6 | fn called only from a `macro_rules!` expansion | alive |
| P7 | fn used only by `#[cfg(test)]` code | test-only |
| cycle | `lines` ↔ `audit_plants` in grep-searcher | a cycle |
| layer | `lines` uses `sink` (rule: it must not) | a violation |
| C1–C3 | copies of `lines::preceding_by_pos` (28 lines): exact, identifiers renamed, statements reordered | clones |

### Dead code (`results/audit/dead_code.json`)

rustc flags P1, P2b and P7, and not P2. On the clean tree it flags nothing, so everything a tool adds is beyond
the compiler. Each reported item is classed against rust-analyzer references (`score_dead.py`): test entry or
`main`, trait-impl method (cannot be deleted while the impl stands), alive (a production reference outside `use`
lines: a **false death**), test-only, re-exported only, `#[cfg]` twin, unused.

| Tool, route | Items | False deaths | Recall on the 95 unused functions | True candidates after dropping entries and trait impls | Alive traps called dead |
|---|---|---|---|---|---|
| CodeGraph, library `findDeadCode()` (not in CLI or MCP) | 808 | 36 (4.5 %) | 84 | 43 % | P6 |
| GitNexus, Cypher "no incoming CALLS" (no dead-code command) | 1 898 | 280 (14.9 %) | 86 | 17 % | P4, P5, P6, P7 |
| roam-code, `dead --all` (product command) | 199 | 108 (54.8 %) | 48 | 24 % | P3, P6, P7 |

What the false deaths are: calls through a facade crate's path (`grep::cli::hostname()`), method calls on a value
(`.build()`, `.close()`), and, for roam-code, plain calls in the same file. In ripgrep the crates are published,
so an unused `pub` item there is API. In an application workspace of internal crates (`publish = false`) the same
item is dead code, and rustc still cannot see it.

### Architecture (`results/audit/cycles.json`, `results/audit/layers.json`)

`cargo-modules dependencies --acyclic` checks items, not modules. It fails on a type and its own method
(`Hasher` ↔ `Hasher::default`) in 8 of the 9 library crates of the clean tree, so it cannot gate module cycles.
The truth is its `uses` edges folded to files: 6 strongly connected components (5 natural, 1 grown by the plant).

| Tool | Components found | Planted cycle |
|---|---|---|
| CodeGraph `cycles` (exits 1: a CI gate) | 3 exact, 2 inside a larger component, 1 missed | found |
| GitNexus `check --cycles` | 2 exact, 1 partial, 3 missed | found |
| roam-code `cycles` | 0 of 6, plus a false cycle (`write` bound to the wrong method) | missed |

Layer rules: no native tool states one, and neither CodeGraph nor GitNexus can. roam-code `fitness` misses the
planted break and fires on a control rule, "matcher must not depend on searcher", through a call edge
`fmt -> finish` that Cargo makes impossible.

### Change impact (`results/audit/impact.json`)

Depth 2, five targets, against rust-analyzer's callers and their callers, as (file, function):

| Tool, command | Precision | Recall | Per target recall |
|---|---|---|---|
| CodeGraph `impact -d 2` | 0.90 | 0.78 | 1.0, 0.5, 1.0, 0.86, 0.75 |
| GitNexus `impact --depth 2 --include-tests` | 0.72 | 0.28 | 0.31, 0.44, 0.33, 0, 0 |
| roam-code `impact --depth 2` | 1.00 | 0.13 | 0.13, 0.13, 0, 0, 0.5 |

### Duplication (`results/audit/clones.json`)

| Tool | Exact | Renamed | Reordered | Note |
|---|---|---|---|---|
| jscpd 4.3.0 | yes | no | no | by default skips files over 1 000 lines: 83 of 100 files, 20 231 of 53 212 lines |
| roam-code `clones` | yes | yes | no | keeps the renamed copy after a rename to an unrelated name |
| roam-code `duplicates` | yes | yes* | yes* | *only while the copies share a name prefix; renamed, both drop out |
| CodeGraph, GitNexus | — | — | — | no clone feature |

Precision on the natural tree is not scored: natural clones have no objective truth.

## The recipe, by axis

| Axis | Use | A lab tool adds | Watch out |
|---|---|---|---|
| security, deps, API, lint, unused deps | cargo-audit / cargo-deny, cargo-semver-checks, clippy, cargo-machete | nothing | — |
| dead code | rustc for private items; rust-analyzer references for `pub` items across crates | CodeGraph's list is the closest, but library-only | GitNexus and roam-code lists are 15 % and 55 % live code; macro-called functions are called dead by all three |
| module cycles | no usable native check | CodeGraph `cycles`, a CI gate | GitNexus finds half, roam-code none |
| module layers | nothing | nothing that works | a script over cargo-modules edges |
| change impact | rust-analyzer, one level per request | CodeGraph `impact`: 78 % of the closure in one call | GitNexus 28 %, roam-code 13 %: a short list is not a small blast radius |
| duplication | nothing | roam-code `clones` | not `duplicates`; jscpd only exact copies, and only files under 1 000 lines unless told |

## Surprises, in the order they happened

1. **E4 failed:** neither tool confuses trait calls by name. They miss calls instead.
2. **cargo-modules `--acyclic` is unusable as a cycle gate** (item level), so the "native covers cycles"
   prediction failed and a lab tool earned the row.
3. **The only product dead-code command measured is the worst** (roam-code, 55 % false deaths).
4. **roam-code `duplicates` clusters by name:** the planted copies were found because they were named alike.
5. **jscpd silently skips large files** by default.
6. **My own adapter cut GitNexus answers over 64 KB** (the process exits before the pipe drains). The R1–R5
   answers re-ran identical after the fix.
7. **My truth twice needed a fix before it could judge anyone:** an indentation scan for trait impls was fooled by
   raw strings at column 0 (now document symbols), and `#[cfg(windows)]` twins look unused to rust-analyzer on
   Linux (now their own class).

## Reproduce

```
python research/tools/_rust/truth_ra.py <ripgrep at the commit> > truth_ra.json
python research/tools/_rust/truth_modules.py <ripgrep> > truth_modules.json
python research/tools/_rust/plant.py <ripgrep> <planted copy>
python research/tools/_rust/truth_refs.py <planted copy> <items.json> > refs.json
python research/tools/_rust/score_dead.py <planted copy> refs.json <planted copy>.plants.json name=dead.json ...
python research/tools/_rust/score_cycles.py <planted copy> <modules.json> <plants.json> name=components.json ...
python research/tools/_rust/adapter_impact.py <tools.json> > impact.json
```

Adapters: `adapter_codegraph.py`, `adapter_gitnexus.py` (R1–R5), `adapter_impact.py` (impact, all three tools);
`score.py` scores R1–R5.
