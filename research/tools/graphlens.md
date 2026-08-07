# graphlens-mcp

**Verdict:** learn (competent peer; overlaps our thesis)  ·  **Feeds:** R1-C13 (benchmark), R1-C14 (positioning)  ·
**Card status:** hands-on — **re-measured on a fully-provisioned env** (ty LSP now working; see correction below)

_Tested version: **graphlens-mcp 0.4.0** (core `graphlens 0.8.2`, bundled `ty 0.0.63`), installed via
`uv tool install graphlens-mcp --python 3.13`. First pass 2026-08-02 (degraded); re-measured 2026-08-03 (ty fixed)._

**Scope:** canonical R2 benchmark = `sha256:300e0a010e351d0a91a7e006c3cc18047d7d400c94a525ddbe727f796a5e47d2`
([`_scope/bquant.scope.json`](../_scope/bquant.scope.json) — 280 files, 207 .py / 73 .md, bquant@`cb89a24`) ·
run mode: **materialized**. ⚠️ *Retro-fill honesty:* the measured graphlens run used an **ad-hoc rsync
staging** of the same 6 dirs (285 files = +5 generated `docs/_build/*.py` that git ignores) built before the
harness existed, so its input was near-identical but **not** this exact `scope_id`. The 5 extra generated
copies only inflate the grep-style `exhaustive` file list (they show up as `docs/_build/...` there); they
don't touch the `relations` impact numbers. A canonical re-run is `materialize.py bquant.scope.json <dir>`
then point graphlens at `<dir>`.

## ⚠️ Correction to the first pass — the "empty impact" was OUR environment, not the tool

The 2026-08-02 pass reported `relations`/impact returning **empty** and marked graphlens's core
capability as broken here. **That conclusion was wrong** — traced to a packaging/PATH issue on our side,
not a tool weakness. Re-measured with it fixed, **impact works and roughly matches codemap** on the
resolved non-test call graph. The corrected picture is below; the old numbers are struck through where they
appear.

### Root cause (packaging, fixable in one line)
graphlens's Python resolver spawns Astral's `ty` LSP server via
`ty_bin = shutil.which("ty") or "ty"` (`graphlens_python/_resolver.py:34`). The tool **bundles** `ty` at
`~/.local/share/uv/tools/graphlens-mcp/bin/ty`, but `uv tool install` does **not** put that dir on `PATH`
(only the declared `graphlens-mcp` entry point is symlinked). So `shutil.which("ty")` returns `None`,
`Popen(["ty","server"])` raises `FileNotFoundError`, and `TyResolver.prepare()` swallows it
(`except Exception:` → `_client=None`) → silent fall-back to tree-sitter-only → `relations` returns nothing
and self-reports `resolver_status: "degraded"`. The `ty` binary itself is fine (`ty --version` → 0.0.63,
`ty server` starts).

**Workaround (what we did):** put the bundled bin on `PATH` before launching graphlens —
`PATH="$HOME/.local/share/uv/tools/graphlens-mcp/bin:$PATH"`. Then `ty server` starts, indexing switches
from structural to type-resolved, and `resolver_status` flips to **`ok`**. (Arguably a graphlens bug: a
tool that bundles `ty` should resolve it relative to its own install, not rely on the caller's `PATH`.)

## Identity
- Repo / docs: `neko1313/graphlens-mcp` · https://neko1313.github.io/graphlens-mcp/
- License: MIT
- Stack: tree-sitter grammars (Python / TypeScript / Go / Rust / PHP) + a **per-language LSP resolver**
  (`ty` for Python, `gopls` for Go, `intelephense` for PHP, …) for type-grade resolution; graph persisted
  to **SQLite** (`.graphlens/graph.db`, WAL).
- Install: `uv tool install graphlens-mcp` (Python ≥ 3.13). **Gotcha:** ensure the bundled `ty` is on `PATH`
  (see correction above) or Python impact silently degrades.
- Interface: **MCP-only** for querying (stdio `serve`, watch-mode default on). CLI is operational only:
  `init` (index + auto-configure an agent's MCP config), `reindex`, `remove`, `serve`, `status`.
- Reproduced? yes — installed, indexed, and queried over MCP on bquant (both degraded and fixed).

## What it is
An LSP-grade semantic code graph for AI agents: tree-sitter + a real type checker (`ty`) build a typed graph
of symbols, calls, references and imports — including cross-file and, notably, **cross-boundary into
dependencies** — persisted to SQLite and served to agents as MCP navigation tools. Filesystem watch mode
(`serve --watch`) for incremental re-index.

## Setup side-effects worth knowing
- `init` **auto-writes an agent MCP config** (here it picked Codex → `~/.codex/config.toml`; override with
  `--agent`). It edits files outside the indexed repo — expect it.
- `init` did a **network fetch** ("Fetching 7 files", ~18 s) — vendored `ty`/typeshed stubs. Needs egress on
  first index.
- Under our tool sandbox, the `ty server` subprocess got killed (signal 16) → had to run graphlens with the
  sandbox disabled. Not graphlens's fault; noted so the runbook is reproducible.

## Indexing cost — structural vs type-resolved (same fair scope, 212 .py / 73 .md)
Reference: codemap builds the same input in ~1 min (fast mode) → 3.6 MB canonical JSON on this staging.

| Mode | Time | Peak RAM | DB size | Nodes | Edges | resolver_status |
|---|---|---|---|---|---|---|
| tree-sitter only (ty missing) | **12 s** | 246 MB | 17.5 MB | 16 796 | 20 889 | `degraded` |
| **ty-resolved (fixed)** | **2 m 20 s** | 424 MB | 31 MB | **32 399** | **55 691** | **`ok`** |

Type resolution costs ~12× the wall-clock and ~2.7× the edges — those extra edges are the resolved
calls/references that were missing in the degraded run. (The earlier 3h45m/9 GB/1.1 GB catastrophe was a
*different* bug — the venv trap below — not this.)

## MCP surface — 3 general verbs (richer than the first pass implied)
- **`search(query, limit=25, path_glob, exhaustive)`** — the one way in. Name / content / **meaning** →
  nodes **with signatures** (`via` shows which ranked it); `text_matches` = non-symbol hits (incl. markdown);
  content matched **literally**. `path_glob` scopes (`tests/*`, `!tests/*`). **Test files auto-excluded**
  unless you scope them or the query says "test". `exhaustive=true` → *every* matching file path, uncapped
  (grep-flavoured, no signatures).
- **`relations(symbol, depth=2, limit=25, file)`** — neighbourhood in one call: callers, callees,
  implementors/subclasses, non-call references, each with signature. THE impact tool. **Also auto-drops
  test call-sites** by default (`lean.py:53`, a deliberate context-budget heuristic traced from real agent
  runs) unless the symbol mentions "test".
- **`info(target, limit=200, file, mode)`** — symbol → source/sig/loc; file → symbol outline, or
  `mode='source'` → line-numbered content **+ which files import it**.

codemap exposes ~18 specialized ops; graphlens bets on 3 general verbs. Different philosophy, not strictly
worse — the auto-test-exclusion is a genuinely thoughtful agent-ergonomics call.

## Coverage vs codemap — re-measured (same staging)
| Capability | codemap | graphlens (ty working) |
|---|---|---|
| symbol lookup (T1) | ✅ | ✅ `search` (finds flagship + content/markdown hits; ranking mediocre) |
| callers/callees (T2) | ✅ | ✅ `relations` — **works** (~~✖~~), tests auto-excluded |
| impact / blast-radius (T3) | ✅ | ✅ `relations` (code) + `search exhaustive` (files) — **works** (~~✖~~) |
| signature-change surface (T4) | ✅ `call_contract` | ✖ no such tool |
| architecture / layers (T5) | ✅ `architecture` | ✖ no such tool |
| resolves into dependencies | ✖ (by design) | ✅ (real capability codemap lacks) |
| determinism | ✅ canonical diffable JSON | ✖ SQLite DB, not diffable |
| single-call provenance impact | ✅ (core/docs/examples/scripts/tests in one number) | ◐ (2 tools; tests hidden by default) |
| works source-only, no LSP dep | ✅ (jedi/griffe) | ◐ (needs `ty` on PATH or silently degrades) |
| indexes markdown/docs as refs | ✅ doc nodes | ◐ content text-match; counts generated `_build/` copies |
| languages | Python | Py / TS / Go / Rust / PHP |
| license | MIT | MIT |
| honors .gitignore / excludes venv | takes package dir (immune) | ✖ hardcoded exact-name list only |

## Hands-on — impact head-to-head on `MACDZoneAnalyzer` (identical staging)
| Tool / metric | Result |
|---|---|
| **codemap** `impact` (1 call) | **31 refs** — core 2 / docs 7 / examples 1 / scripts 2 / **tests 19**, each provenance-tagged |
| **graphlens** `relations` (resolved graph, tests auto-dropped) | 9 callers + 1 callee (`deprecated`) + 2 refs, `resolver_status: ok` |
| **graphlens** `search exhaustive` (grep-like, all files) | 44 files — bquant 2 / docs 14 / examples 2 / research 3 / scripts 2 / **tests 21** |

**Reading it fairly.** On the **non-test resolved call graph** the two are close — codemap 12
(core 2 + docs 7 + examples 1 + scripts 2), graphlens ~9–11 — so graphlens's engine is **sound**, not empty.
The differences are shape, not capability:
- graphlens **splits** the answer across two tools (`relations` = resolved code edges, `search exhaustive`
  = textual file list) and **hides tests by default**; codemap returns tests + docs + code in **one
  provenance-tagged number**.
- graphlens's exhaustive list counts **generated `docs/_build/html/_downloads/*.py`** copies (no gitignore
  → staging hygiene leaks in); codemap's doc references are the 7 real `.md` mentions.

## Разбор
- **What we'd take:** cross-boundary resolution *into* dependencies (a real capability codemap lacks by
  design); the **auto-test-exclusion** heuristic for agent context budgets (smart default — impact answers
  shouldn't drown in test call-sites); watch-mode incremental re-index; the 3-verb minimal surface as a
  design foil.
- **What we'd do differently and why:** codemap stays source-only-of-target + **deterministic canonical
  artifact** (diffable JSON vs opaque SQLite) + **no LSP dependency** (jedi/griffe resolve impact with
  nothing to provision — graphlens's core silently dies if `ty` isn't on PATH) + **layout robustness**
  (package-dir, immune to venv/`_build` traps). And codemap answers T4/T5 (call-contracts, architecture)
  that graphlens has no tool for.
- **What the author knows that we didn't:** using a real type checker (`ty`) as the graph backend for
  cross-boundary precision; a persisted SQLite store + FS watch for incremental updates; and the
  context-budget rationale for de-emphasising tests in agent-facing results.
- **What we did NOT check (honest boundary):** cross-boundary *into deps* actually resolving (would need the
  project venv installed under the indexed root); DB determinism across re-index; whether `--watch`
  incremental stays correct; semantic `search` quality (embedding model was unreachable — no egress, so only
  name/content search ran); other languages (Go/TS/Rust/PHP have their own LSP resolvers, untested here).

## The venv trap (still valid — separate from the ty issue)
`init --root <repo-root>` on a repo with a **non-standard venv name** (`venv_bquant`) drags the whole
dependency tree in: graphlens ignores `.gitignore` and excludes virtualenvs only by a hardcoded exact-name
list (`.venv`/`venv`/…), so `venv_bquant` slips through → our first attempt ran **> 3h45m / ~9 GB / 1.1 GB
DB** type-checking numpy/pandas/… before we killed it. **Workaround:** point `--root` at a clean source tree
(the package dir), or name the venv `.venv`/`venv`, or keep it outside the root. No `--exclude` in v0.4.0.
codemap takes the package dir explicitly and is immune.

## Quality (re-measured)
- **accuracy:** `search` good (flagship + content/markdown hits); ranking mediocre (a same-named method
  outranks the flagship function). `relations` **now accurate** (`resolver_status: ok`), matches codemap on
  the non-test call graph.
- **determinism:** ✖ — SQLite DB, not a canonical/diffable artifact; determinism across runs untested.
- **cost/speed:** type-resolved indexing 2m20s / 424 MB / 31 MB DB (fair scope); queries fast (~130–260 ms).
- **setup friction:** high — Python ≥3.13; **`ty`-on-PATH gotcha** (silent degrade); no gitignore/exclude
  (venv trap); first index needs egress; `init` edits an external agent config.
- **languages:** broad (Py/TS/Go/Rust/PHP). **license:** MIT. **interface:** MCP-only querying (3 tools).
- **honesty-of-claims:** good — self-reports `resolver_status: "degraded"` rather than faking results
  (which is exactly how we caught our own PATH bug).

## Verdict & backlog effect
**learn — a competent peer, not "nothing to take."** Corrected finding: graphlens's impact engine **works**
and ≈ codemap on the resolved non-test call graph; the earlier "empty impact" was our PATH bug. We still
wouldn't integrate/wrap it — it overlaps codemap's thesis and is heavier (12× index time), non-deterministic
(SQLite), layout-fragile (venv/`_build` traps), LSP-dependent, and lacks T4/T5 tools — but the ideas are
real. Roadmap effects:
- **R1-C14 (positioning):** codemap's durable differentiators, now measured against a *working* competitor:
  **determinism** (diffable JSON), **single-call provenance-complete impact** (tests + docs + code, one
  number), **no-LSP-dependency robustness** (impact works with nothing to provision), **layout robustness**,
  and **T4/T5 coverage**. State these — not "graphlens is broken."
- **R1-C13 (benchmark):** the grep-vs-graph bench must **verify the competitor's resolver is actually up**
  (`resolver_status == ok`) before comparing — our own run shows how easily a graph tool degrades to grep.
  Fair same-scope baseline: codemap 31-ref provenance impact vs graphlens 9-caller resolved graph + 44-file
  exhaustive.
- **learn candidates:** cross-boundary dep resolution (capability gap); context-budget test-de-emphasis
  (ergonomics idea); watch-mode incremental (feeds M3.2 freshness).

## Integration spike (2026-08-07) — adapter feasibility for R1-C17 → **negative, deferred**
Hands-on test of the one adapter candidate (resolve-into-deps → codemap `calls_external` sidecar). Synthetic
target: `mypkg.core.dump` calls `json.dumps`; control `caller`→`helper`. Findings from graphlens's own
`graph.db` (`init --no-agent`, `ty` on PATH):
- **Cross-boundary edges DO exist** (more than codemap has): `calls: mypkg.core.dump → external_symbol`,
  `resolves_to: import json → external_symbol {"origin":"stdlib"}`, `has_type` edges to external types;
  the intra-project `caller → helper` control edge is correct too. Node kind `external_symbol` (6), edge
  kinds `calls/references/resolves_to/has_type/contains/declares/imports`.
- **Blocker 1 — external member not named:** the call target is a **span placeholder** `call@6:17`, not
  `json.dumps`. graphlens records "this call crosses into stdlib at line 6" but not *which* symbol → the
  headline value ("what pandas API does the code call") is not delivered at symbol granularity.
- **Blocker 2 — real third-party breaks the resolver:** with `pandas` installed, `ty server` timed out
  repeatedly (1s/30s), **0 nodes after 10+ min**; only the stdlib-only project completed. Embeddings also
  failed (no egress). Confirms the card's "setup friction: high".
- **Verdict:** absorbing non-deterministic, low-resolution, fragile data into a sidecar for marginal gain
  over codemap's existing external-leaf nodes isn't worth it now. **Adapter deferred (R1-C17).** Revisit if
  graphlens names the external member (not a span) and `ty` stabilizes on heavy deps. The spike-first gate
  worked — it prevented building the adapter. Net: **neither worked-through tool yields a built adapter** —
  unique capabilities are built natively (R1-C18/19), foreign ones are routed (GitNexus, R1-C16).
