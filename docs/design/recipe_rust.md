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
