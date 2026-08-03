# Design — Scope model (input identity, manifest, profile)

**Status:** 🟢 Feature A implemented (M19.A, 2026-08-02) — `codemap/scope.py` + `codemap scope` + sidecar,
7 tests. 🟢 Feature B implemented (R2.0.1, 2026-08-03) — `research/tools/_scope/{bquant.scope.json,
materialize.py}`, Scope field in the card template + comparison hub, canonical bench `scope_id` pinned
(`sha256:300e0a01…5e47d2`, bquant@cb89a24, 280 files). All decisions O1–O6 settled.
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

### 1.3 Manifest + profile

Two parts. **Manifest** — the exact per-file identity: `{path, sha256, bytes}` (relative path; full sha-256
hex of content; size) + `git_blob` in git mode. **Profile** — cheap aggregate stats *about* the scope, so a
tool's numbers can be read in context (an "impact" cost means nothing without knowing the input size/shape).

```json
{
  "scope_id": "sha256:…",              // §1.4 — canonical, mode-independent
  "profile": {
    "file_count": 285,
    "total_bytes": 1234567,
    "by_role": {                       // provenance bucket → files/bytes/loc
      "core":  {"files": 89, "bytes": 900000, "loc": 30000},
      "tests": {"files": 76, "bytes": 250000, "loc":  9000},
      "docs":  {"files": 61, "bytes":  84000, "loc":  2000}
    },
    "by_ext": {                        // file type → files/bytes/loc
      ".py": {"files": 206, "bytes": 1000000, "loc": 41000},
      ".md": {"files":  73, "bytes":  230000, "loc":  6000}
    },
    "loc_total": 47000,                // text-line count across all in-scope files
    "largest": [                       // top-N by bytes — spot hubs / vendored blobs
      {"path": "bquant/indicators/macd.py", "bytes": 42000}
    ]
  },
  "git": {                             // present only in a git repo (§1.5)
    "commit": "cb89a24…", "ref": "HEAD", "dirty": true,
    "dirty_files": ["uv.lock"], "mode": "git"
  },
  "files": [{"path": "bquant/__init__.py", "sha256": "…", "bytes": 812,
             "git_blob": "d6f8dec…"}, "…"]   // git_blob only in git mode (free)
}
```

**Profile fields — and why each helps a comparison:**
- `file_count` / `total_bytes` / `loc_total` — the raw size of the input; every per-tool number (time, RAM,
  DB size, cost) is only meaningful relative to this.
- `by_role` (core / tests / docs / …) — how much of the scope is package vs tests vs docs; explains, e.g.,
  why an impact query reaches many test files.
- `by_ext` — language/format mix; a Python-only tool vs a multi-language one should be read against this.
- `largest` — surfaces hub files or accidentally-included blobs (an early smell-test that the scope is clean).

All profile fields are **deterministic** (derived from the sorted file set + content) and **timestamp-free**.
They are cheap: counts + `bytes` from `stat`, `loc` from a line count — no parsing, computed during the same
walk that hashes files.

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

### 1.6 Operating mode: in-place (live) vs materialized (benchmark) — O2

The scope model resolves and hashes files **in place, over the real tree** — this is the **default** and the
only mode that supports the live path. Copying to a clean folder is a **benchmark-only escape hatch**, not the
general answer.

- **In-place (default) — the live / interactive / incremental path.** Enumerate + hash the real working tree
  where it lives. The venv/junk problem is solved by **git-mode enumeration** (§1.5), *not* by copying. This
  is the **required** mode for anything that watches the repo and updates the graph on change — a copy would
  freeze the input, break inotify/paths, and defeat the whole point of a live graph. Feature A (codemap's own
  scope), and downstream **R1-C9 (Merkle/watch incremental)** and **M3.2 (hash-freshness)**, all run in-place.
- **Materialized (benchmark only) — Feature B.** Realize a `scope_id` as a clean folder solely to feed
  *third-party* tools that (a) don't accept a file list and (b) have unreliable excludes (graphlens's venv
  trap). It is a **frozen snapshot for a one-shot fair diff**, derived from the *same spec* and carrying the
  *same `scope_id`*, so it stays traceable to the live definition. It deliberately **sacrifices
  interactivity** — never use it for live development.

Rule of thumb: **live/product = in-place; one-shot cross-tool diff of an uncooperative tool = materialize.**
codemap itself never needs materialization even in the benchmark (it takes the real tree in git mode); only
tools that can't be pointed at a clean file set do.

---

## 2. Feature A — codemap input scope manifest (product)

**Where it plugs in.** `extract`/`extract_repo` already enumerate the input tree; add a resolution+hash pass
(`codemap/scope.py`) that produces the manifest **in place, over the real tree** (§1.6 — the live path;
enables watch/incremental in R1-C9/M3.2). It runs on `build` and is written to the **M18 sidecar**, extending it:

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
- **Materialization is a benchmark-only escape hatch (O2, see §1.6):** used *only* for third-party tools that
  can't take a file list and have unreliable excludes (graphlens's venv trap). A helper
  `research/tools/_scope/materialize.py <spec> <out-dir>` realizes the scope as a clean staging tree (~40 MB)
  and emits `manifest.json` (= `codemap scope` output → reuses Feature A), carrying the same `scope_id`.
  It is a frozen snapshot — no interactivity. **codemap itself is NOT materialized** even here: it indexes the
  real tree in git mode. Tools with a live/watch mode of their own should ideally be pointed at the real tree
  too (configuring their excludes); materialize is the fallback when that isn't possible.
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
- **O2 — in-place vs materialize.** ✅ **Resolved (2026-08-02):** **in-place over the real tree is the default**
  and the only mode for the live/interactive/incremental path (A, R1-C9, M3.2) — git-mode enumeration keeps it
  clean without copying. **Materialize is a benchmark-only escape hatch** (§1.6) for uncooperative third-party
  tools; it freezes a snapshot and sacrifices interactivity by design.
- **O3 — hash choice.** Recommend **sha-256 full hex** (stdlib, collision-safe, deterministic). Alt: truncated
  (shorter sidecar) or blake2b (faster).
- **O4 — spec format.** Recommend a **small JSON spec** (§1.1) that maps to build args. Alt: infer scope purely
  from `build` flags (no separate spec) — simpler but not reusable by B/other tools.
- **O5 — non-code files.** Recommend the manifest includes **all in-scope files incl. `.md`** (codemap indexes
  docs; tools differ), with the profile broken down by ext. Alt: code-only manifest.
- **O6 — git binding.** ✅ **Approved (2026-08-02).** git for enumeration (gitignore-correct set) +
  provenance block (`commit/ref/dirty`) + diff shortcut + free `git_blob` hashes, as a preferred-when-available
  layer; **`scope_id` identity stays our sha-256** (mode-independent). Details in §1.5.
