# Design — a Rust recipe: native tools as the truth, the lab's tools measured against it

**Status:** 🟡 pre-registered (2026-11-21), not started. **Backlog:** R1-C111.
**Gap:** [`gaps/no_recipe_outside_python_2026-11-21.md`](../../gaps/no_recipe_outside_python_2026-11-21.md).

## Problem in one paragraph

Asked what to use on a Rust project, `advise` can list tools but cannot recommend one. Every claim outside Python is
`read`, the Rust ecosystem's own tools are absent, and the agent-facing tools the lab has measured on Python
(GitNexus, CodeGraph, OntoIndex, roam-code, graphlens) have never been run on Rust. Each of them claims Rust
support. How right their Rust answers are is the knowledge an agent needs and nobody has.

## Decisions

### D1 — two layers in a recipe

- **Native layer: the truth, and the tools without rivals.** rust-analyzer resolves names through the compiler's
  front end (types, traits, macros expanded). Its answers are the truth set for the graph needs, in the role
  codemap's hand-checked graph played on bquant. Clippy, cargo-audit, cargo-deny, cargo-machete/cargo-udeps and
  cargo-modules are the ecosystem standards for their needs. They enter as `read` from official docs, and become
  `probed` where the benchmark runs them.
- **Agent layer: what the lab measures.** These tools serve a graph over MCP, which an agent uses more readily than
  an LSP. Each gets scored against the truth on the same tree, as `measured` with `measured_on = ["rust"]`.

### D2 — the benchmark tree

The benchmark is **ripgrep** (`BurntSushi/ripgrep`), pinned to a release tag recorded with its commit hash. It is
public, well known and mid-sized, with a multi-crate workspace, traits with several implementations (`Matcher`,
`Sink`, `Printer`), generics and moderate macro use. The scope file records the crates and excludes `target/`
and vendored code. The tree is extracted from the tag, never a live checkout (the 41-vs-45 lesson: a truth set
names its commit).

### D3 — the questions (Rust's T1–T5)

| # | Question | Truth from |
|---|---|---|
| R1 | where a name is defined, for a method name implemented by several types | rust-analyzer `workspace/symbol` + definitions |
| R2 | callers of a function (and of a trait method, through `dyn`/generic calls) | rust-analyzer call hierarchy, incoming calls |
| R3 | impact: callers to depth 2 | R2 applied twice |
| R4 | module dependency graph (`use` edges between modules) | cargo-modules, cross-checked with a `syn` scan |
| R5 | implementors of a trait | rust-analyzer `textDocument/implementation` |

Each question is asked about 5–8 symbols chosen before any tool runs, with at least one of each kind: a trait
method with several impls, a generic function, a macro-generated item, and a plain function.

### D4 — tools measured, in order

1. **GitNexus** and **CodeGraph**: the most-used agent graphs, both measured on Python already.
2. **roam-code**: claims 28 languages and change gates.
3. **OntoIndex**, **graphlens-mcp**: second wave.
4. **ast-grep**: R1 and R4 only, as structural search, without resolution.

jevgrep is left out: it needs a paid key and uploads source; its Python card stands.

### D5 — what lands in codemap

- A card `research/tools/_rust/` per measured tool, or a section in its existing card, with the scores and
  versions.
- Claims in `matrix.toml` with `measured_on = ["rust"]`. Native tools as new `[[tool]]` entries.
- **A recipe:** a new table `[[recipe]]` with fields `language`, `need`, an ordered `tools` list with a `why` per
  tool, and the evidence. `advise --lang rust` and `--root` on a Rust tree show the recipe first and the
  catalog after it. Recipes are guarded like claims: every tool and need exists, and every `why` that cites a
  number links to its evidence.
- A heavy run (indexing, embeddings) goes to a build stand under the slot rules. Only properties of the machine
  are written down, never its name.

### D6 — not in this design

- Other languages. TypeScript and Go come next, by the same procedure, once this one is reconciled.
- Ranking by stars or popularity.

## Pre-registered expectations

| # | Expectation | Fails if nothing was done? |
|---|---|---|
| E1 | The truth reproduces: two rust-analyzer runs on the pinned tree give identical R1–R5 sets. A hand check of 20 sampled call sites agrees 20/20 or the disagreements are explained | yes |
| E2 | The truth is not trivial: R2 has at least one trait-method target whose callers go through `dyn` or generics, and R1 at least one name with ≥ 3 definitions | yes |
| E3 | GitNexus and CodeGraph are scored on R1, R2 and R4 with precision/recall and versions. Their claims carry `measured_on = ["rust"]` and evidence that resolves | yes |
| E4 | At least one of them misses or misattributes trait-method calls that the truth has. Prediction: tree-sitter graphs without type resolution bind trait calls by name. If both are exact, that is a surprise worth a post | yes (prediction) |
| E5 | `advise --lang rust` shows the recipe first. For `multi-lang-graph` it names rust-analyzer for exact answers and the best-measured agent tool with its recall. Native tools appear for security (cargo-audit/deny), unused dependencies (cargo-machete/udeps) and lint (clippy) | yes |
| E6 | Before this work `advise --lang rust` has **0** claims measured on Rust; after, ≥ 2 tools × ≥ 2 needs | yes |
| E7 | The guards bite: a recipe naming an unknown tool, a `why` with a number but no evidence, and a Rust claim without `measured_on` each fail the suite (mutations) | yes |
| E8 | Nothing about Python answers changes: `advise` without a language filter renders the same rows for every Python need | no (stays) |

## D7 — audit axes (R1-C112, added 2026-11-21 before any audit run)

The R1–R5 numbers answer *navigation*, where rust-analyzer is the truth by construction: no tool can beat it there,
so navigation alone gives no reason to install anything. The owner's question is the right one: **where does a lab
tool give what the native tools do not?** A recipe is a row per audit axis, and a lab tool enters a row only with a
measured gain.

| Axis | Native coverage | Predicted gap |
|---|---|---|
| security, dependencies | cargo-audit, cargo-deny, cargo-vet, cargo-geiger | none |
| API compatibility | cargo-semver-checks | none |
| correctness, lint | rustc, clippy, miri | none |
| unused dependencies | cargo-machete, cargo-udeps | none |
| **dead code** | rustc `dead_code` | a `pub` item of a *library* crate that no workspace crate uses is never reported (in a binary crate it is). In an application workspace of internal library crates this is most of the dead code |
| **architecture** | Cargo forbids crate cycles; cargo-modules draws the module graph | module cycles inside a crate; no layer rule on modules at all (no import-linter analogue) |
| **change impact** | a point call hierarchy in rust-analyzer | no transitive closure, no diff → touched code → tests |
| **duplication** | clippy `match_same_arms`, `if_same_then_else` (local) | no cross-file or near-miss clones |

Complexity × churn hotspots stay out until a measured tool claims them.

**Truth per axis**, all on ripgrep at the pinned commit, with plants made by a script in a copy (never the clean tree):

- *Dead code.* Plants: P1 a private unused fn in a library crate (rustc must flag it: control); P2 a `pub` unused fn
  in a library crate (the gap); traps that are alive: P3 a `pub` fn used only by another workspace crate, P4 an impl
  method reached only through `dyn`, P5 a fn reached only through a generic bound, P6 a fn called only from a
  `macro_rules!` expansion; P7 a fn used only by `#[cfg(test)]` code (reported as its own class). On the natural tree,
  every item a tool reports dead is checked against rust-analyzer `textDocument/references`: an item with a
  reference outside its own declaration is a **false death**.
- *Architecture.* Plants: a two-module cycle inside one crate, and a declared layer rule broken by one `use`.
  Natural: module cycles from the cargo-modules truth (strongly connected components).
- *Change impact.* The transitive caller closure from rust-analyzer for the R2 targets, and for a real ripgrep
  commit the functions its diff touches, closed over callers.
- *Duplication.* Plants of three kinds: an exact copy of a 15+ line fn in another file, a copy with renamed
  identifiers, and a copy with inserted and reordered statements.

**Tools measured** are those that claim the axis in their docs or CLI; the inventory is written into the results
before a run. Expected candidates from the catalog: dead code — CodeGraph, OntoIndex, a GitNexus Cypher query (no
incoming calls); architecture — CodeGraph's cycle finder, GitNexus `check`; impact — GitNexus `impact` and
`detect_changes`, CodeGraph `impact`, graphlens, OntoIndex, roam-code; duplication — jscpd.

**Practical check.** The finished recipe is applied once on the owner's private Rust workspace (project D), from a
clean copy, read-only. Its results go to the owner privately and never into this repository or the catalog.

### Expectations for D7

| # | Expectation | Fails if nothing was done? |
|---|---|---|
| E9 | The native gap is real: on the planted copy rustc flags P1 and does not flag P2 | yes |
| E10 | Every tool with a dead-code answer is scored for false deaths on the natural tree. Prediction: a dead list built on GitNexus's call edges has ≥ 30 % false deaths (its R2 recall was low); CodeGraph's is lower but not zero | yes (prediction) |
| E11 | At least one tool reports at least one of the alive traps P3–P6 as dead. Prediction: P4 (`dyn`) and P6 (macro) | yes (prediction) |
| E12 | Cycles: the planted cycle is found by the native graph (cargo-modules) — prediction: native covers cycles. The layer rule: no native tool can state it; which lab tool can is recorded, possibly none | yes |
| E13 | Impact recall against the closure, per tool. Prediction: the R2 order holds (CodeGraph above GitNexus) and no tool reaches the closure exactly | yes (prediction) |
| E14 | Duplication: jscpd finds the exact and renamed copies and misses the reordered one. Prediction: no graph tool finds any clone | yes (prediction) |
| E15 | The recipe has one row per axis of the table above. A row recommending a lab tool cites a measured number; a row without one says plainly that no lab tool is needed | yes |

### D7 reconciled (2026-11-21)

Tree: ripgrep 15.2.0 `e89fff89` plus `plant.py`. Truth scripts: `truth_refs.py` (rust-analyzer references and
document symbols; two runs byte-identical), `truth_modules.py`, `truth_ra.py`. Results: `research/tools/_rust/results/audit/`.
Hand checks: 10 of 10 sampled false deaths are real production calls; 12 sampled "unused" functions are public
builder or accessor methods with no caller in the workspace.

| # | Result | Verdict |
|---|---|---|
| E9 | rustc flags P1 and P2b and not P2. On the clean tree it flags nothing: everything below is beyond the compiler | holds |
| E10 | False deaths: CodeGraph library `findDeadCode()` 4.5 % (36 of 806), GitNexus no-callers Cypher 14.9 % (280 of 1 878), roam-code `dead` 54.8 % (108 of 197). Recall on the 95 unreferenced functions: 84, 86, 48. After dropping test entries and trait-impl methods, the share of true candidates: 43 %, 17 %, 24 % | prediction for GitNexus (≥ 30 %) **fails**; CodeGraph lower and non-zero holds. **Surprise:** the only product dead-code command (roam-code) is the worst |
| E11 | Alive traps reported dead: P6 (macro) by all three; P4 (`dyn`) and P5 (generic) by GitNexus; P3 (cross-crate) by roam-code; P7 (test-only) by GitNexus and roam-code | holds |
| E12 | `cargo-modules --acyclic` is item-level: it fails on a type and its own method in 8 of 9 library crates of the clean tree, so it cannot gate module cycles. Truth: 6 file-level components (5 natural, 1 grown by the plant). CodeGraph `cycles`: 3 exact, 2 inside a larger component, 1 missed, plant found. GitNexus `check --cycles`: 2 exact, 1 partial, 3 missed, plant found. roam-code `cycles`: 0 of 6, plus one false cycle from a name mislink. Layer rule: no native tool and neither CodeGraph nor GitNexus can state one; roam-code `fitness` misses the planted break and fires on a control dependency Cargo makes impossible | prediction "native covers cycles" **fails**: the native graph has the edges but no usable check |
| E13 | Impact at depth 2 against the closure, pooled over 5 targets: CodeGraph P 0.90 R 0.78; GitNexus P 0.72 R 0.28; roam-code P 1.00 R 0.13. Two runs identical | holds |
| E14 | jscpd finds the exact copy only, by default after skipping every file over 1 000 lines (83 of 100 files). roam-code `clones` finds exact and renamed, and keeps the renamed one after a rename to an unrelated name. roam-code `duplicates` finds all three only while they share a name prefix; renamed, two drop out | prediction **fails** twice: jscpd misses renamed copies, and a graph tool (roam-code `clones`) does find clones. **Surprise:** `duplicates` clusters by name |
| E15 | Recipe rows below; the catalog table and its guards come with R1-C111's `[[recipe]]` | open |

**The recipe for Rust, by axis** (what each row would tell an agent):

| Axis | Use | A lab tool adds | Watch out |
|---|---|---|---|
| security, deps, API, lint, unused deps | cargo-audit / cargo-deny, cargo-semver-checks, clippy, cargo-machete | nothing | — |
| dead code | rustc for private items; for `pub` items across crates, rust-analyzer references (scriptable, exact) | CodeGraph's dead list is the closest (5 % false deaths) but is library-only, not in its CLI or MCP | never act on a GitNexus or roam-code dead list: 15 % and 55 % of it is live code; macro-called functions are reported dead by all; in a published library crate an unused `pub` item is API |
| module cycles | no usable native check | CodeGraph `cycles` (exits 1, a CI gate): 5 of 6 components found or covered | GitNexus finds half; roam-code none |
| module layers | nothing native | nothing measured works | a script over cargo-modules edges is the honest option |
| change impact | rust-analyzer call hierarchy, one level at a time | CodeGraph `impact` in one call: 78 % of the depth-2 closure at 90 % precision | GitNexus 28 %, roam-code 13 %: a short impact list on Rust does not mean a small blast radius |
| duplication | nothing native | roam-code `clones` (exact and renamed copies) | not `duplicates` (name-driven); jscpd only exact copies and skips files over 1 000 lines unless told |

## D8 — the recipe in the catalog (added 2026-11-21 before the code)

D5 said "a table `[[recipe]]`". The audit axes (D7) decide its shape:

- **Needs per language, not reworded Python ones.** `dead-code`, `py-impact`, `py-imports` and `import-gate`
  describe Python and carry codemap's Python coverage; rewording them would change every Python answer (E8).
  New needs, `languages = ["rust"]`, codemap `none`: `rs-dead-code`, `rs-module-cycles`, `rs-layers`, `rs-impact`,
  and the native axes `rs-security-deps`, `rs-api-semver`, `rs-lint`, `rs-unused-deps`. Navigation stays
  `multi-lang-graph`, duplication stays `duplicates` (both already language-neutral).
- **Native tools enter as tools.** rustc, clippy, rust-analyzer, cargo-modules: `probed` where the benchmark ran
  them (with what was seen, including cargo-modules `--acyclic` as `rejected` for a cycle gate); cargo-audit,
  cargo-deny, cargo-semver-checks, cargo-machete, cargo-udeps: `read`.
- **Lab tools get their Rust numbers as claims** with `measured_on = ["rust"]` on the `rs-*` needs, and CodeGraph
  and GitNexus on `multi-lang-graph` (their present `read` claims there become `measured` on Rust).
- **A recipe row** = `language`, `need`, `summary`, `evidence`, `use` (ordered `{tool, why}`), `avoid`
  (`{tool, why}`). A row with no lab tool in `use` says so in its summary.
- **Display.** With a language filter (`--lang`, or `--root` detecting it), the overview starts with that
  language's recipe table, and a need answer starts with its recipe row. Without a filter nothing changes.
  The answer gains an additive key `recipe`; `ANSWER_FORMAT` stays 11.
- **Guards.** A recipe naming an unknown tool, need or language, a `why` or summary with a digit and no evidence,
  and a claim whose evidence lies under `research/tools/_rust/` without `"rust"` in `measured_on` are schema
  problems. Recipe evidence must resolve (repo check).

### Expectations for D8

| # | Expectation | Fails if nothing was done? |
|---|---|---|
| E16 | `advise --lang rust` (and `--root` on a Rust tree) prints the recipe table before the need table; for `rs-module-cycles` it names CodeGraph `cycles`, for `rs-security-deps` cargo-audit and cargo-deny, for `rs-dead-code` it names no lab tool in `use` and lists GitNexus, OntoIndex and roam-code under `avoid` | yes |
| E17 | Rust-measured claims: before, 3 claims on 1 need; after, ≥ 5 lab tools on ≥ 4 needs | yes |
| E18 | Each guard of D8 goes red under a mutation that removes it, with a green control | yes |
| E19 | Every Python-filtered need answer and the unfiltered overview rows for Python needs are identical to those of the same catalog with every Rust addition removed | no (stays) |
| E20 | The packaged catalog passes `schema_problems` and `repo_problems`; the suite is green | no (stays) |
