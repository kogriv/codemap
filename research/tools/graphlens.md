# graphlens-mcp

**Verdict:** learn-only  ·  **Feeds:** R1-C13 (benchmark), R1-C14 (positioning)  ·
**Card status:** hands-on — **measured** (fair scope; core impact capability degraded in this env, see below)

_Tested version: **graphlens-mcp 0.4.0**, installed via `uv tool install graphlens-mcp --python 3.13` on 2026-08-02._

## Identity
- Repo / docs: `neko1313/graphlens-mcp` · https://neko1313.github.io/graphlens-mcp/
- License: MIT
- Stack: tree-sitter grammars (Python / TypeScript / Go / Rust / PHP) + **`ty`** (Astral's LSP-grade type
  checker) for Python; graph persisted to **SQLite** (`.graphlens/graph.db`).
- Install: `uv tool install graphlens-mcp` (Python ≥ 3.13).
- Interface: **MCP-only** for querying (stdio `serve`). CLI is operational only: `init` (index+configure
  agent), `reindex`, `remove`, `serve`, `status`. No CLI to query the graph (only `status`).
- Reproduced? yes (install + index attempted on bquant).

## What it is
An LSP-grade semantic code graph for AI agents: `ty` + tree-sitter build a typed graph of symbols, calls,
references and imports (including cross-file and, notably, **cross-boundary into dependencies**), persisted
to a SQLite DB, served to agents as MCP navigation tools. Has a filesystem watch mode (`serve --watch`,
default on) for incremental re-index.

## ⚠️ Finding — indexing pulls in the whole dependency tree (product flaw + workaround)

**What happened (measured).** `graphlens-mcp init --root /data/pro/bquant` (the repo root) on bquant ran
**> 3h45m, ~9 GB RAM, ~1.1 GB `graph.db`, and did not finish** before we killed it. Cause: it indexed
**`venv_bquant/` — 1.5 GB, 16 087 third-party `.py`** (numpy, pandas, plotly, …), type-checking the entire
dependency tree instead of the 89-file `bquant` package.

**Root cause (two parts).**
1. graphlens **does not honor `.gitignore`** — where `venv_*/` is already excluded in this repo.
2. It excludes virtual-envs only by a **hardcoded exact-name list** (`graphlens/contracts/adapter.py`,
   v0.4.0):
   ```python
   _EXCLUDED_DIRS = frozenset({".venv", "venv", "__pycache__", ".git",
                               "dist", "build", ".eggs", "node_modules"})
   ```
   A **non-standard venv name** (`venv_bquant`) doesn't match `.venv`/`venv`, so it slips through and drags
   the whole dependency tree into the graph. There is no `--exclude` flag and no gitignore support in v0.4.0.

**Workarounds.**
- Point `--root` at the **package directory** (`bquant/bquant`), not the repo root — the cleanest fix, and
  what codemap does anyway.
- Or name the virtualenv `.venv`/`venv` (matches the hardcoded list), or keep it **outside** the indexed root.
- No in-tool ignore/exclude exists in v0.4.0, so the safe rule is: **only point graphlens at a clean source
  tree with no venv/deps inside it.**

**codemap contrast.** codemap takes the package dir explicitly and is source-only-**of-the-target**, so it
never wanders into a venv or non-standard dirs — robustness to repo layout is a quiet differentiator
(feeds R1-C14). The flip side is a real *capability* difference, not just a bug: graphlens **can resolve
into dependencies** (cross-boundary — e.g. "what pandas API does bquant call"), which codemap does **not**
do by design.

## MCP surface
Minimalist — **3 tools**: `search` (name/content/meaning → nodes+signatures), `relations` (neighbourhood:
callers/callees/implementors/references — "THE tool for impact"), `info` (symbol source/sig/loc, or file
outline). Contrast: codemap exposes ~18 specialized ops (impact, call_contract, callers, callees,
architecture, columns, …). Different philosophy: 3 general verbs vs many precise ones.

## Coverage vs codemap
Measured on the fair scope (staging = same 6 dirs codemap indexes: bquant/tests/examples/research/scripts/docs).

| Capability | codemap | graphlens |
|---|---|---|
| symbol lookup (T1) | ✅ | ✅ (`search`) |
| callers/callees (T2) | ✅ | ✖ in this env¹ (`relations` → empty) |
| impact / blast-radius (T3) | ✅ | ✖ in this env¹ |
| signature-change surface (T4) | ✅ (`call_contract`) | ✖ no such tool |
| architecture / layers (T5) | ✅ (`architecture`) | ✖ no such tool |
| resolves into dependencies | ✖ (by design) | ✅ (when ty works) |
| determinism | ✅ (canonical JSON) | ✖ (SQLite DB, not diffable) |
| MCP | ✅ (~18 ops) | ✅ (3 tools) |
| indexes markdown/docs as refs | ✅ (doc nodes) | ◐ (content text-match only) |
| languages | Python | Py/TS/Go/Rust/PHP |
| license | MIT | MIT |
| honors .gitignore / excludes venv | takes package dir | ✖ (hardcoded names only) |

¹ `relations` returned empty because graphlens's **`ty` LSP resolver failed to initialize** here (see below);
its own response flagged `resolver_status: "degraded"`. Structural `search` still worked.

## Hands-on measurements (target: bquant, fair scope — 212 .py / 73 .md)
Reference: codemap builds the same input in ~1 min → 4.8 MB canonical JSON, 4225 nodes / 9970 edges.

**Indexing:** **12.1 s**, **246 MB** peak RAM, **17.5 MB** SQLite DB, **16 796 nodes / 20 889 edges**.
(The earlier 3h45m/9 GB/1.1 GB run was the *misconfigured* repo-root scope pulling `venv_bquant` — see finding.)

| Task | Correct? | Cost / latency | Notes |
|---|---|---|---|
| T1 where defined (`analyze_zones`) | ✅ | ~260 ms | `search` finds the flagship `…pipeline.analyze_zones` (3rd of 25); ranking surfaces a same-named method + `_analyze_zones` above it. Returns signatures + content matches (incl. markdown). |
| T2 callers (`MACDZoneAnalyzer`) | ✖ | ~130 ms | `relations` → 0 callers/callees/impl/refs (`degraded`). |
| T3 impact (`MACDZoneAnalyzer`) | ✖ | ~130 ms | 0 refs vs **codemap's 68** (core 2 / docs 7 / examples 1 / scripts 2 / tests 56). Degraded resolver. |
| T4 sig-change (`analyze_zones`) | ✖ | — | No call-contract/argument-shape tool exists. |
| T5 architecture | ✖ | — | No architecture/layers/coupling tool exists. |

**Why T2/T3 empty (diagnosed, fairly):** graphlens's impact resolution needs the **`ty` LSP server**
(Astral ty 0.0.63, bundled). `ty check` runs fine on the staging (997 diagnostics), but graphlens's
`ty server` LSP handshake **fails to initialize deterministically** in this env → it silently falls back
to tree-sitter-only, where `relations` yields nothing. codemap resolves the same callers/impact
**source-only via jedi** with no such dependency, on the identical input. A fully-provisioned env (project
venv + working ty) might populate `relations` — untested (see "did NOT check"). Also: semantic `search`
mode was disabled (embedding model unreachable — no egress), so only name/content search ran.

## Разбор
- **What we'd take:** cross-boundary resolution *into* dependencies is a genuinely useful idea codemap
  lacks (careful — it's also what makes graphlens expensive). The LSP-grade `ty` backend buys type
  precision codemap's jedi/griffe approximates.
- **What we'd do differently and why:** codemap stays source-only-of-target + deterministic canonical
  artifact; graphlens's whole-tree, DB-backed, non-deterministic approach is heavier and layout-fragile.
- **What the author knows that we didn't:** using a real type checker (`ty`) as the graph backend, and a
  persisted SQLite store + FS watch for incremental updates (vs codemap's in-memory + rebuild).
- **What we did NOT check (honest boundary):** `relations`/impact with a **fully-provisioned env** (project
  venv installed + a working `ty` server) — it may populate there; we measured the out-of-box source-only
  result (same setup codemap handles). Also unchecked: DB determinism across re-index; whether `--watch`
  incremental is correct; semantic search quality (embedding model was unreachable — no egress).

## Quality (on the covered part)
- **accuracy:** `search` good (finds the symbol + content matches incl. markdown); ranking mediocre (a
  same-named method outranks the flagship function). `relations` unusable here (degraded → empty).
- **determinism:** ✖ — SQLite DB, not a canonical/diffable artifact; determinism across runs untested.
- **cost/speed:** indexing 12 s / 246 MB (fair scope); queries fast (~130–260 ms) once served.
- **setup friction:** high — needs Python ≥3.13; **fragile scoping** (no gitignore/exclude → the venv trap);
  core impact depends on an experimental `ty` LSP that didn't initialize here.
- **languages:** broad (Py/TS/Go/Rust/PHP) — codemap is Python-only.
- **license:** MIT (same as codemap). **interface:** MCP-only querying (3 tools) + operational CLI.
- **honesty-of-claims:** good — it self-reports `resolver_status: "degraded"` rather than faking results.

## Verdict & backlog effect
**learn-only.** graphlens's ambitions overlap codemap's (graph-for-agents, impact, MCP) and it has real
reach (5 languages, resolves into deps *when ty works*), but out-of-box on a source-only tree it degraded
to structural search with **empty impact** — the exact query where a graph should beat grep — while codemap
answered T1–T5 on the identical input. Findings folded to the roadmap:
- **R1-C14 (positioning):** codemap's **determinism** (diffable JSON vs opaque SQLite), **layout robustness**
  (package-dir, no venv trap), and **source-only resolution that actually works without deps** are concrete,
  now-measured differentiators. State them.
- **R1-C13 (benchmark):** the fair grep-vs-graph bench must ensure the *competitor's resolver is actually
  functioning* — here the honest result is "graph tool degraded to search"; codemap's 68-ref impact is the
  baseline to beat.
- **learn:** the 3-verb MCP surface (search/relations/info) is an interesting minimalism vs codemap's ~18
  ops; and cross-boundary dep resolution remains a genuine capability codemap lacks by design.
