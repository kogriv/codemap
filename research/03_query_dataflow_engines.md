# R1.3 — Query / dataflow / structural-search engines

The engines that let you *ask questions* of code — via a query DSL, a pattern language, or a library API.
The core decision for codemap here: **query DSL vs fixed AI-facing ops**, and **tree-sitter as a
multi-language extraction backend**.

**Baseline (codemap):** source-only Python graph (griffe + jedi), deterministic, networkx backend, fixed
JSON ops (no query DSL), warm serve + MCP. Has a `columns`/dataflow op (which dict/df string keys a
function reads/writes) and `call_contract` (call-site argument contracts).

---

## CodeQL (GitHub)

- **What / mechanism.** "Code-as-data": extract the codebase into a relational **CodeQL database**, then
  query with **QL** — an object-oriented declarative logic language on **Datalog**. Ships mature **local +
  global dataflow** and **taint-tracking** libraries (sources → sinks across functions/fields, with
  non-value-preserving taint steps). The richest query surface in this category.
- **Static vs build; determinism.** Static, but DB extraction generally **requires observing a build** for
  compiled languages; Python/JS/Ruby extraction is build-free. Deterministic given the same DB.
- **Interface.** CLI (`codeql database create`/`analyze`), VS Code ext, native CI via code-scanning.
- **License / status.** Split: queries+libraries (`github/codeql`) **MIT**; CLI/engine proprietary — free
  only for OSS/public repos + academic; private-repo use needs GitHub Advanced Security. Active.
- **Verdict: LEARN-ONLY.** Too heavy (DB build, GHAS licensing, JVM engine) and philosophically opposite
  (query DSL vs fixed ops) to integrate. But it's the reference for what codemap's `columns`/dataflow could
  aspire to: **source→sink taint-style propagation** (non-value-preserving steps, cross-function flow). Its
  source/sink modeling pattern is worth borrowing conceptually.

## Semgrep

- **What / mechanism.** Pattern-based static analysis. Rules are **YAML** whose patterns look like target
  code with metavariables (`$X`), matched against a per-language AST. Adds a **dataflow engine**
  (`mode: taint`: source/sink/sanitizer/propagator).
- **Static vs build; determinism.** **Source-only, no build**, deterministic. **Intra-procedural** taint is
  free/CE; **inter-procedural/inter-file** taint is **Pro (commercial)**.
- **License / status.** Engine LGPL-2.1; a Dec 2024 relicensing put many rules under a restrictive license
  and moved cross-function taint behind the platform → spawned **OpenGrep** (Jan 2025, LGPL-2.1 community
  fork) restoring cross-function taint across ~12 languages. Both active.
- **Verdict: LEARN-ONLY (watch OpenGrep).** Proves a *pattern* language is friendlier than a logic DSL —
  but it's a lint/find engine, not a persistent graph. codemap's fixed ops serve agents better than teaching
  them to author YAML. Learn: the **source/sink/sanitizer taint vocabulary**, and the free-vs-Pro line —
  inter-procedural is where the real value/cost sits, a signal that codemap's cross-function
  `impact`/`columns` is genuinely valuable territory.

## ast-grep (`sg`)

- **What / mechanism.** Rust CLI for **structural search, lint, rewrite**. Patterns written as ordinary
  code, parsed by **tree-sitter** into a CST; matching + capture + template rewrite; YAML for reusable
  lints/codemods. Strong at *syntactic* search; no dataflow/name resolution.
- **Static vs build; determinism.** **Source-only, no build, deterministic**, purely syntactic.
- **Interface.** CLI, Python/JS bindings (`ast-grep-py`), LSP, and an **MCP server** — positioned as an
  AI-agent tool.
- **License / status.** MIT, ~8k+ stars, very active; multi-language via tree-sitter grammars.
- **Verdict: WRAP / LEARN (esp. multi-language).** The productized proof that tree-sitter gives cheap
  polyglot structural extraction. codemap could **wrap ast-grep (or its tree-sitter grammars) as a
  language-agnostic front-end** to feed non-Python facts, keeping griffe+jedi for deep Python semantics.
  Note the MCP overlap: ast-grep competes for "structural search for agents" — codemap differentiates by
  offering a *resolved semantic graph* (callers/callees/impact) that pure syntactic matching can't.

## tree-sitter

- **What / mechanism.** The **incremental parsing library** itself. Builds a per-file CST, updates it
  efficiently on edit; exposes a **query interface** (S-expression patterns with `#predicate?`). Purely
  syntactic, single-file, no cross-file/semantic resolution.
- **Static vs build; determinism.** Source-only, no build, deterministic parse — a *parsing substrate*, not
  an analysis engine.
- **License / status.** MIT, ~0.26.x (Dec 2025). Extremely widely adopted (GitHub nav, Neovim, ast-grep,
  Semgrep partially, ~1000+ ecosystem repos).
- **Verdict: INTEGRATE (as the multi-language backend).** The strategic option if codemap ever moves beyond
  Python — cheap grammars for dozens of languages, deterministic, offline, no build. The caveat that
  *defines codemap's moat*: tree-sitter gives **syntax only**; codemap's value (name resolution, call graph,
  impact) comes from jedi/griffe semantics on top. Plan: **tree-sitter for breadth + jedi/griffe for Python
  depth.** Its s-expr queries are internal plumbing, not a user-facing DSL — consistent with fixed ops.

## Comby

- **What / mechanism.** Language-agnostic **structural search & replace** via templates with holes
  (`:[name]`); a language-aware parser understands balanced delimiters/strings/comments (tree structure
  implicit, no per-language grammar). No semantic model, no dataflow, no graph.
- **Static vs build; determinism.** Source-only, no build, deterministic, purely textual-structural.
- **License / status.** Apache-2.0, OCaml; quieter than ast-grep.
- **Verdict: LEARN-ONLY.** Its "no grammar, just delimiters" trick is clever, but tree-sitter/ast-grep have
  won this niche with better precision. Nothing to integrate.

## jedi / rope (Python)

- **What / mechanism.** **jedi** — static analysis (completion, goto/inference, find-references, some
  refactoring); **rope** — the leading Python **refactoring** library (rename/extract/inline/move,
  `find_occurrences`) with its own inference.
- **Static vs build; determinism.** **Source-only, no build.** Pure Python; jedi has heuristics/timeouts;
  rope is dependency-free.
- **License / status.** Both OSS, active (jedi ~0.20+, rope ~1.14+). codemap already depends on jedi.
- **Verdict: INTEGRATE MORE (rope).** codemap already uses jedi. The actionable finding is **rope**: safe,
  semantics-aware refactoring (rename/move/extract) that codemap's read-only ops don't offer. If codemap
  ever moves from *analysis* to *safe automated edits* ("rename symbol X across the blast radius you just
  computed"), rope is the natural source-only, deterministic engine to pair with codemap's impact graph.
  Keep it optional to preserve the read-only stance.

## Scalpel / PyCG (Python call-graph frameworks)

- **What / mechanism.** **PyCG** — pragmatic static **call-graph generation** for Python (inter-procedural
  assignment relations → call resolution; handles closures, generators, multiple inheritance).
  **Scalpel** — a broader static-analysis framework (CFG, dataflow, SSA, type inference) whose call-graph
  module wraps PyCG.
- **Static vs build; determinism.** **Source-only, static, no build, deterministic.** PyCG: ~0.38s/1k LoC,
  **~99% precision, ~70% recall** (recall limited by dynamic Python).
- **License / status.** OSS (academic). **PyCG largely dormant**; Scalpel 1.0-beta, lightly maintained — not
  production-hardened.
- **Verdict: LEARN-ONLY (validate against).** codemap's closest technical cousin (static, source-only,
  deterministic Python call graphs). Borrow: (a) PyCG's **assignment-relation resolution** as a precision
  technique to compare codemap's jedi-based callers/callees against; (b) the published **precision/recall
  numbers as a benchmark and honest ceiling** — dynamic dispatch/monkey-patching cap recall ~70% for *any*
  static tool, worth stating in codemap's positioning. Don't depend on them (dormant/beta).

---

## Themes — what this category teaches codemap

**Query DSL vs fixed ops.** The category splits: CodeQL (logic/Datalog), Semgrep/ast-grep/Comby (pattern
DSLs), tree-sitter (s-expr), vs library-API tools (jedi, rope, PyCG). A DSL buys open-ended expressiveness
but imposes a *learning tax* — someone must author QL or YAML. codemap's audience is **AI agents**, for whom
a small set of well-named JSON-returning ops (`impact`, `callers`, `call_contract`, `columns`) is *more*
usable than composing a novel query language each call. Evidence favors keeping fixed ops as the primary
surface; a DSL would be a distraction. (The existing `query` dossier op is the right amount of generality.)

**Dataflow depth is the real frontier — and where money lives.** CodeQL and Semgrep-Pro show that
*inter-procedural, taint-style* dataflow is both the hardest part and the commercially gated part. codemap's
`columns`/dataflow op is a lightweight domain-specific slice of this. Lesson: adopt the
**source/sink/propagator/sanitizer vocabulary** and consider *non-value-preserving propagation* (a key
derived from another key), but stay scoped — full taint analysis is a different, heavier product.

**tree-sitter is the multi-language extraction answer.** If codemap goes polyglot, tree-sitter (proven by
ast-grep) is the standard, deterministic, build-free, offline backend. The durable insight: tree-sitter
gives **syntax/breadth**, but codemap's moat is **semantics/depth** (resolved call graph, impact, contracts)
that jedi/griffe provide for Python and pure syntactic tools *cannot*. Target architecture: **tree-sitter
for breadth + jedi/griffe (and possibly rope for safe edits) for Python depth.**

**PyCG sets codemap's call-graph benchmark and honest ceiling.** As the closest static, source-only Python
call-graph cousin, PyCG validates codemap's approach and quantifies its limits: static resolution tops out
near ~99% precision / ~70% recall because dynamic Python is fundamentally unresolvable statically. codemap
should benchmark callers/callees against PyCG-style resolution and *state these bounds openly* as a strength
of its determinism, not hide them.

**Net positioning.** codemap occupies an under-served spot: **semantic (resolved) code-graph, deterministic,
source-only, offline, AI-first (JSON/MCP).** The syntactic tools lack semantics; the semantic heavyweight
(CodeQL) needs a DB build + licensing friction; the Python research tools (PyCG/Scalpel) are dormant/beta;
jedi/rope are libraries, not agent-facing graph services. Highest-value moves: **wrap/learn ast-grep +
tree-sitter for eventual multi-language breadth, integrate rope if codemap adds safe edits, borrow
CodeQL/Semgrep's taint vocabulary for `columns`, benchmark call-graph precision against PyCG** — while
keeping the fixed-ops, no-DSL, source-only stance that is its differentiator.

---

### Sources

- CodeQL: [data-flow docs](https://codeql.github.com/docs/writing-codeql-queries/about-data-flow-analysis/) ·
  [Python data flow](https://codeql.github.com/docs/codeql-language-guides/analyzing-data-flow-in-python/) ·
  [CLI](https://docs.github.com/en/code-security/concepts/code-scanning/codeql/about-the-codeql-cli) ·
  [LICENSE](https://github.com/github/codeql/blob/main/LICENSE)
- Semgrep: [taint mode](https://semgrep.dev/docs/writing-rules/data-flow/taint-mode/overview) ·
  [Opengrep fork](https://socket.dev/blog/opengrep-forks-semgrep) ·
  [Opengrep after a year](https://www.aikido.dev/blog/opengrep-sast-one-year)
- ast-grep: [GitHub](https://github.com/ast-grep/ast-grep) · [site](https://ast-grep.github.io/) ·
  [MCP](https://github.com/ast-grep/ast-grep-mcp)
- tree-sitter: [GitHub](https://github.com/tree-sitter/tree-sitter) ·
  [Wikipedia](https://en.wikipedia.org/wiki/Tree-sitter_(parser_generator))
- Comby: [comby.dev](https://comby.dev/) · [GitHub](https://github.com/comby-tools/comby)
- jedi/rope: [jedi](https://github.com/davidhalter/jedi) · [rope library](https://rope.readthedocs.io/en/latest/library.html)
- PyCG/Scalpel: [PyCG paper](https://arxiv.org/abs/2103.00587) · [Scalpel paper](https://arxiv.org/pdf/2202.11840) ·
  [Scalpel call-graph](https://python-scalpel.readthedocs.io/en/latest/user-guide/core-utilities/Call-Graph.html)
