# graphlens-mcp

**Verdict:** learn-only (tentative)  ·  **Feeds:** R1-C13 (benchmark), R1-C14 (positioning)  ·
**Card status:** hands-on — **in progress** (indexing flaw found; T1–T5 pending a fair re-run on package scope)

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

## Coverage vs codemap
_(T1–T5 to be filled after the fair re-run on `bquant/bquant`.)_

| Capability | codemap | graphlens |
|---|---|---|
| symbol lookup (T1) | ✅ | ? |
| callers/callees (T2) | ✅ | ? |
| impact / blast-radius (T3) | ✅ | ? |
| signature-change surface (T4) | ✅ | ? |
| architecture / layers (T5) | ✅ | ? |
| resolves into dependencies | ✖ (by design) | ✅ |
| determinism | ✅ (canonical JSON) | ? (SQLite DB) |
| MCP | ✅ | ✅ |
| languages | Python | Py/TS/Go/Rust/PHP |
| license | MIT | MIT |
| honors .gitignore / excludes venv | takes package dir | ✖ (hardcoded names only) |

## Hands-on measurements (target: bquant)
- **Indexing (repo-root, misconfigured):** > 3h45m, ~9 GB RAM, ~1.1 GB DB, DNF → see finding above.
- **Indexing (package scope):** _pending re-run on `bquant/bquant`._
- **T1–T5:** _pending — require the correctly-scoped graph._
- Reference: codemap builds the `bquant` package graph in ~1 min → ~4.8 MB canonical JSON.

## Разбор
- **What we'd take:** cross-boundary resolution *into* dependencies is a genuinely useful idea codemap
  lacks (careful — it's also what makes graphlens expensive). The LSP-grade `ty` backend buys type
  precision codemap's jedi/griffe approximates.
- **What we'd do differently and why:** codemap stays source-only-of-target + deterministic canonical
  artifact; graphlens's whole-tree, DB-backed, non-deterministic approach is heavier and layout-fragile.
- **What the author knows that we didn't:** using a real type checker (`ty`) as the graph backend, and a
  persisted SQLite store + FS watch for incremental updates (vs codemap's in-memory + rebuild).
- **What we did NOT check (honest boundary):** T1–T5 query accuracy / cost / latency; DB determinism;
  whether `reindex`/watch is truly incremental; behavior once scoped correctly. All pending the fair re-run.

## Verdict & backlog effect
Tentative **learn-only**. Confirms **R1-C14** (codemap's layout-robustness + determinism are real
differentiators — state them) and feeds **R1-C13** (the fair grep-vs-graph / tool-vs-tool benchmark, once
scoped correctly). Full verdict deferred until T1–T5 are measured on `bquant/bquant`.
