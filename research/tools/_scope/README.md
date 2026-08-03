# _scope/ — R2 benchmark scope harness

The single source of truth for **"the input every tool card is measured on,"** so any two hands-on cards are
provably comparable. Realizes [`docs/design/scope.md`](../../../docs/design/scope.md) §3 (Feature B), built on
Feature A (`codemap scope` / `codemap.scope.resolve_scope`).

## Files
- **`bquant.scope.json`** — the spec: `root` (a sibling bquant checkout, relative to this file), 6 `roots`
  with provenance roles (core/tests/examples/research/scripts/docs), `include` globs, and an `expected`
  block pinning the canonical `scope_id` + counts at a known commit.
- **`materialize.py`** — realize the spec as a clean staging tree for third-party tools.

## Canonical benchmark scope (pinned)
```
scope_id : sha256:300e0a010e351d0a91a7e006c3cc18047d7d400c94a525ddbe727f796a5e47d2
git      : bquant@cb89a24 (main), clean
files    : 280  (207 .py / 73 .md),  4.33 MB,  112 457 loc
by_role  : core 90 · tests 81 · docs 56 · research 30 · examples 12 · scripts 11
```
Git enumeration makes this **venv-free by construction** (the `venv_bquant` trap that bit graphlens is
impossible here) and gitignore-correct (generated `docs/_build/*.py` are excluded).

## Usage
**codemap and any file-list-capable tool run in place** — no materialization:
```bash
codemap scope /path/to/bquant/bquant --consumer …/tests --docs …/docs --json
```

**venv-trap tools** (can't take a file list, unreliable excludes) get a **byte-identical staging**:
```bash
python research/tools/_scope/materialize.py research/tools/_scope/bquant.scope.json /tmp/stage
#   → copies EXACTLY the 280 manifest files, writes /tmp/stage/manifest.json,
#     and self-verifies the staging scope_id == canonical.
# then point the tool at /tmp/stage
```
`--root PATH` overrides the spec's root; `--no-verify` skips the round-trip check.

## Rule
Every hands-on card records this `scope_id` in its **Scope** field. If a card measured a *different* input
(e.g. graphlens's pre-harness ad-hoc staging), it must say so explicitly — parity is asserted in
[`../../comparison.md`](../../comparison.md), and an unstated deviation is a bug in the comparison.

## Note
Materialize **outputs** (staging trees, `manifest.json` under a staging dir) are throwaway — write them to a
scratch/tmp dir, never commit them. Only the spec + helper live here.
