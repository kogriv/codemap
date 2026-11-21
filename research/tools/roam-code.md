# roam-code

**Verdict:** measured on Rust only (2026-11-21): one strong command (`clones`), the rest of the audit surface
measured here is unreliable on Rust · **Feeds:** R1-C112 · **Card status:** hands-on on ripgrep 15.2.0 (Rust);
not run on Python

## Identity
- **Repo:** `Cranot/roam-code` · Apache-2.0 · PyPI `roam-code` **14.1.0** (installed in a fresh venv with pip).
- **What it says it is:** local codebase intelligence for AI agents: a SQLite code graph over 28 languages, an MCP
  interface, and 287 commands (`roam --help-all`), among them `dead`, `clones`, `duplicates`, `cycles`, `layers`,
  `fitness`, `impact`, `affected-tests`, `hotspots`.
- **Setup:** `roam init` indexed ripgrep in 26 s and wrote `.roam/` (index, `fitness.yaml`, `.roamignore`).

## On Rust — ripgrep, against rust-analyzer (2026-11-21, R1-C112)

Method, plants and every table: [`_rust/README.md`](_rust/README.md). Only the commands that claim an audit axis
were run.

| Axis | Command | Result |
|---|---|---|
| dead code | `dead --all --no-decay` | 199 items, **54.8 % false deaths** (alive in production); 48 of 95 unreferenced functions; calls the cross-crate, macro-only and test-only plants dead; private items are out of scope by design (exports only) |
| module cycles | `cycles` | 0 of 6 file-level components; one false cycle (`write` bound to `PathPrinter::write` instead of `io::Write::write`); planted cycle missed |
| layer rule | `fitness` (dependency rules) | planted break missed; the control "matcher must not depend on searcher" fires on `fmt -> finish`, a dependency Cargo makes impossible |
| change impact | `impact --depth 2` | precision 1.00, **recall 0.13** |
| duplication | `clones` | exact and renamed copies found, and the renamed one kept after a rename to an unrelated name; the reordered copy missed |
| duplication | `duplicates` | all three copies found **only while named alike**; renamed to unrelated names, the renamed and the reordered copies drop out |

Labels to read with care: `dead --json` carries two confidence scales that disagree. The list keyed
`high_confidence` holds 157 items of which 153 are rated `medium` (action REVIEW); the list keyed `low_confidence`
holds all 21 items rated `high` (action SAFE). Not checked further: which scale the authors mean for deletion.

## Verdict
On Rust, recommend `clones` for cross-file duplication (no native tool covers it). Do not act on `dead`,
`cycles`, `fitness` or `impact` output on Rust without a second source. Python not measured.
