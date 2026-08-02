# Design — Scope model (input identity, manifest, profile)

**Status:** 🟡 design, pending review (2026-08-02). Not yet implemented. **git binding approved (O6).**
**Backlog:** M19 (product feature A) + R2.0.1 (research harness B) — see [../../BACKLOG.md](../../BACKLOG.md).
**Motivation:** codemap is deterministic on its **output** (canonical `graph.json`) but says nothing precise
about its **input**. Today the only record of scope is the M18 sidecar's build *command* (`argv/cwd/target`);
the concrete file set is merely *recoverable* (and only approximately) from node paths, with **no content
hashes and no profile**. That is insufficient for two needs:

1. **Reproducibility & change-tracking** for codemap itself (and the substrate for incremental rebuild).
2. **Valid cross-tool comparison** (R2): we must *prove* two tools saw byte-identical input, not assume it.
   The graphlens pilot exposed exactly this — a stray `venv_bquant/` silently changed the scope.

This design introduces a **scope model** shared by both: *spec → resolved manifest → `scope_id` + profile.*

---

## 1. The scope model (shared core)

### 1.1 Scope spec (declarative input definition)
Decouples "what is in scope" from any one tool's flags. A small JSON object:

```json
{
  "root": ".",
  "roots": [
    {"path": "bquant",   "role": "core"},
    {"path": "tests",    "role": "tests"},
    {"path": "examples", "role": "examples"},
    {"path": "research", "role": "research"},
    {"path": "scripts",  "role": "scripts"},
    {"path": "docs",     "role": "docs"}
  ],
  "include": ["**/*.py", "**/*.md"],
  "exclude": ["**/__pycache__/**", "**/*.pyc", "**/.git/**",
              "**/build/**", "**/dist/**", "**/*.egg-info/**",
              ".venv", "venv", "venv_*", "node_modules"]
}
```

- `role` mirrors codemap's provenance vocabulary (core / tests / docs / examples / research / scripts) so a
  spec maps 1:1 onto a `codemap build … --consumer … --docs …` invocation.
- `exclude` carries **sane defaults** (all venv shapes incl. `venv_*`, caches, build artifacts) — the class
  of mistake that bit graphlens. Excludes are glob-based and honor a repo's `.gitignore` when asked.

### 1.2 Resolution → sorted file list
Apply the spec → a **sorted list of concrete files** (paths **relative to `root`**, POSIX separators).
Sorting + relativity make the result path- and machine-independent. Two enumeration modes:

- **git mode (preferred when the root is inside a git repo):** enumerate via `git ls-files [-- pathspec]`,
  then apply the spec's `include`/`exclude` as an **overlay**. This yields the *gitignore-correct* set for
  free — `venv_*`, `build/`, caches, `node_modules` are already excluded by the repo's `.gitignore`, so the
  class of mistake that bit graphlens (a stray `venv_bquant/`) is impossible **by construction**. On bquant
  the 6 scope dirs resolve to 285 tracked files (207 `.py` + 73 `.md`) with **zero** venv files.
- **filesystem mode (fallback):** for a non-git tree, or when the spec explicitly opts in untracked files,
  walk the tree and apply `include`/`exclude` (with sane default excludes).

The spec's `include`/`exclude` always act as an overlay on top of the chosen mode, so you can add an
untracked/generated file or drop a tracked one deliberately. See §1.5 for the git binding.

### 1.3 Manifest (identity + detail)
For each file: `{path, sha256, bytes}` (relative path; full sha-256 hex of content; size). Plus a **profile**:

```json
{
  "scope_id": "sha256:…",           // see 1.4 — canonical, mode-independent
  "file_count": 285,
  "total_bytes": 1234567,
  "by_role":  {"core": 89, "tests": 76, "docs": 61, "...": 0},
  "by_ext":   {".py": 206, ".md": 73},
  "py_loc": 41234,                    // cheap line count over .py
  "git": {                           // present only in a git repo (§1.5)
    "commit": "cb89a24…", "ref": "HEAD", "dirty": true,
    "dirty_files": ["uv.lock"], "mode": "git"
  },
  "files": [{"path": "bquant/__init__.py", "sha256": "…", "bytes": 812,
             "git_blob": "d6f8dec…"}, "…"]   // git_blob only in git mode (free)
}
```

### 1.4 `scope_id` (the input fingerprint)
`scope_id = "sha256:" + sha256( "\n".join(f"{path}\t{sha256}" for file in sorted(files)) )`.

- Order-independent of FS-walk (inputs are sorted first), content-addressed, timestamp-free.
- **Same `scope_id` ⇒ provably identical input** (same files, same bytes). Different ⇒ `scope --diff` shows
  exactly which files were added / removed / changed.
- Deliberately mirrors `graph.json`'s determinism discipline — now applied to the input side.
- **Algorithm is our sha-256, mode-independent.** The `scope_id` does *not* depend on git — it is identical
  for a git repo, a non-git tree, or a dirty working copy with the same bytes. git is used for convenience
  and set-correctness (§1.5), never for identity — this avoids hash-algorithm ambiguity (git blob-hash ≠
  plain sha256).

### 1.5 Git binding (approved — O6)

When the root is a git repo, bind the scope to git for **enumeration, provenance, and diff** — while keeping
`scope_id` on our sha-256 (§1.4). Rationale grounded on bquant: `git ls-files` over the 6 scope dirs = 285
files, `venv_bquant` = 0 (gitignored); git already holds per-blob hashes; `HEAD = cb89a24`, 1 dirty file.

- **Enumeration:** `git ls-files [-- pathspec]` + spec overlay (§1.2). gitignore-correct set for free.
- **Provenance block** in the manifest: `git: {commit, ref, dirty, dirty_files, mode}`. A **clean** tree
  means the scope is reproducible from the commit alone — "scope = `bquant@cb89a24` over pathspec …", a
  shareable one-liner. A **dirty** tree is still exact: our sha-256 captures the actual working-tree bytes
  (git can't hash uncommitted content), and `dirty`/`dirty_files` flag the divergence from `HEAD`.
- **Free blob hashes:** record `git_blob` per file (from `git ls-tree`) alongside our `sha256` — no extra
  file reads. Informational; identity stays sha256.
- **Diff shortcut:** when both sides are git-anchored & clean, `scope --diff` may delegate to
  `git diff --name-status <a.commit> <b.commit>` (rename-aware) instead of the path/hash comparison.
- **Not a requirement:** git mode is a *preferred-when-available* layer; the sha-256 identity, fs-mode, and
  the spec overlay work with or without git, and git mode only covers tracked files (untracked/generated
  files enter via the spec's `include`).

---

## 2. Feature A — codemap input scope manifest (product)

**Where it plugs in.** `extract`/`extract_repo` already enumerate the input tree; add a resolution+hash pass
(`codemap/scope.py`) that produces the manifest. It runs on `build` and is written to the **M18 sidecar**,
extending it:

```json
// graph.json.meta.json
{ "built_at": 1750000000, "argv": [...], "cwd": "...", "target": "bquant",
  "scope": { "scope_id": "sha256:…", "profile": {...}, "files": [{path, sha256, bytes}, …] } }
```

- **`graph.json` stays purely structural** (no schema change, no scope_id inside it) — the sidecar already
  owns build provenance; scope is provenance. *(Open decision O1: optionally also embed the bare `scope_id`
  in the graph header for self-containment. Recommendation: no — keep the graph structural.)*
- **CLI:**
  - `codemap scope <path> [--consumer P …] [--docs P …] [--spec f.json] [--no-git] [--json]` — resolve +
    print manifest/profile/`scope_id` **without building the graph** (cheap; the R2 harness calls this).
    Defaults to **git-mode enumeration** when the root is a git repo (§1.5); `--no-git` forces fs-mode.
  - `codemap scope --diff <a.meta.json> <b.meta.json>` — added / removed / changed files between two scopes
    (delegates to `git diff` when both are git-anchored & clean).
  - `codemap build …` writes the full `scope` block (incl. the `git` provenance) into the sidecar automatically.
- **Determinism:** sorted inputs, sha-256, no timestamps in the scope block itself (`built_at` stays a
  separate sidecar field). Same inputs → identical `scope_id`.

**Why this is the shared substrate (three deferred items collapse into it):**
- **R1-C9 (Merkle incremental):** the per-file `sha256` list *is* the Merkle input — recompute only files
  whose hash changed vs the manifest.
- **M3.2 (freshness):** hash-based staleness — "does any current file hash differ from the manifest?" is
  precise where mtime (M18) is a proxy.
- **M18:** scope extends the existing recipe sidecar; `refresh` already replays it.

**Tests:** determinism (same tree → same `scope_id`; reordered walk → same); a byte change flips exactly one
file hash + `scope_id`; `--diff` reports the right add/remove/change; excludes actually exclude (venv_* etc.).

## 3. Feature B — R2 benchmark scope harness (research infra)

**Goal.** One source of truth for "the benchmark input," so every tool card is provably comparable.

- **Spec:** `research/tools/_scope/bquant.scope.json` (the spec from §1.1 — the 6 dirs codemap indexes). With
  the git binding (§1.5) the benchmark scope becomes a shareable one-liner — "**`bquant@<commit>` over
  pathspec {bquant,tests,examples,research,scripts,docs}**" — reproducible and gitignore-correct (no venv),
  with `scope_id` pinning the exact bytes.
- **Materialization (Open decision O2):** materialize a **clean staging tree** (rsync per spec excludes) as
  the tool-agnostic input, because tools like graphlens need a clean `--root` and don't reliably follow
  symlinks. Recommendation: **materialize** (staging is ~40 MB, cheap) via a helper
  `research/tools/_scope/materialize.py <spec> <out-dir>` that also emits `manifest.json` (= `codemap scope`
  output → reuses Feature A).
- **Card integration:** the card template gains a **Scope** field = `scope_id` + one-line profile; every
  hands-on row in [comparison.md](../../research/comparison.md) must carry the *same* `scope_id` (asserted in
  the hub). Retro-fill the graphlens card with the scope_id of the staging we already measured.
- **Parity vs behavior:** the `scope_id` guarantees identical **input**; how each tool *treats* it (graphlens:
  markdown as content-match, resolves into deps; codemap: doc-nodes, source-only) stays captured by the card's
  coverage matrix. Scope parity is necessary, not sufficient — both are recorded.

**B rides on A:** once `codemap scope` exists, B is thin — materialize the spec's files, run `codemap scope`
for the manifest/`scope_id`. Hence A and B are built together (A first, B immediately on top).

---

## 4. Plan (phased, this batch)

1. **A-core** — `codemap/scope.py` (spec resolve + manifest + `scope_id` + profile), `codemap scope` CLI
   (+ `--diff`), write `scope` into the M18 sidecar on `build`. Tests.
2. **B-harness** — `research/tools/_scope/bquant.scope.json` + `materialize.py` (reusing A), retro-fill the
   graphlens card's `scope_id`, extend the card template + comparison hub with the Scope field.
3. **Later (separate items, not now):** wire the manifest into R1-C9 (incremental) and M3.2 (hash-freshness).

## 5. Open decisions (for review before coding)

- **O1 — `scope_id` in `graph.json`?** Recommend **no** (sidecar-only; keep the graph structural). Alt: embed
  bare id for self-containment.
- **O2 — materialize vs manifest-over-real-tree for B?** Recommend **materialize** (tool-agnostic, avoids the
  venv trap). Alt: manifest over the real tree + trust each tool's excludes (fragile).
- **O3 — hash choice.** Recommend **sha-256 full hex** (stdlib, collision-safe, deterministic). Alt: truncated
  (shorter sidecar) or blake2b (faster).
- **O4 — spec format.** Recommend a **small JSON spec** (§1.1) that maps to build args. Alt: infer scope purely
  from `build` flags (no separate spec) — simpler but not reusable by B/other tools.
- **O5 — non-code files.** Recommend the manifest includes **all in-scope files incl. `.md`** (codemap indexes
  docs; tools differ), with the profile broken down by ext. Alt: code-only manifest.
- **O6 — git binding.** ✅ **Approved (2026-08-02).** git for enumeration (gitignore-correct set) +
  provenance block (`commit/ref/dirty`) + diff shortcut + free `git_blob` hashes, as a preferred-when-available
  layer; **`scope_id` identity stays our sha-256** (mode-independent). Details in §1.5.
