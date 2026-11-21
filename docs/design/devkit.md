# Design — the devkit: codemap adopted by a project in one command, kept current by the suite

**Status:** ✅ **done** (2026-11-21, 0.0.39; implementation c0f2988 + acceptance fixes), pre-registered in f35ecfc before code, reconciled below. **Backlog:** R1-C108.
**Gap:** [`gaps/adoption_by_hand_2026-11-21.md`](../../gaps/adoption_by_hand_2026-11-21.md).

## Problem in one paragraph

Three projects use codemap, and each integration was assembled by hand and came out different: how MCP is
launched, how the graph is kept fresh, what the contract says, when an agent should call which tool, how a
defect gets back to codemap. Each project fell into the same known traps. Nothing tells a project its
integration has drifted from the installed codemap. The contract cannot say "no new dependency between
layers" without listing every absent pair. And whether agents use the tool at all is not measured anywhere.

## Decisions

### D1 — the devkit ships inside the package and is driven by `codemap devkit`

Templates live in `codemap/devkit/templates/` (package data) and are rendered by `codemap devkit …`. They are
versioned with `codmap` and tested by codemap's own suite (D7). A separate repository would rot the same way
the hand-written memo for the third project will. The owner chose this placement on 2026-11-21.

Subcommands:

| Command | What it does | Exit |
|---|---|---|
| `devkit init --package PATH [--consumer P]… [--docs P]… [--agents-file F] [--claude-hooks] [--codex] [--ci github\|gitlab] [--no-hook] [--no-build] [--ratchet] [--dry-run]` | first install into a repository | 0 installed; 1 installed with items needing attention; 2 refused |
| `devkit update [--force] [--repin] [--dry-run]` | bring every managed artifact to the installed devkit version | as `init` |
| `devkit status [--format text\|json]` | per artifact: current / outdated / edited by hand / missing; pinned executable's version; graph currency | 0 all current; 1 something needs action |
| `devkit ratchet [--graph G] [--tighten] [--dry-run]` | write the `allowed` region of the contract from the graph (D3), or remove pairs no longer used | 0; 2 on a contract it cannot edit safely |
| `devkit brief` | SessionStart hook: graph currency and the short rule list as plain stdout | always 0 |
| `devkit touched` | PostToolUse hook for Edit/Write: what depends on the edited module, as `additionalContext` | always 0 |
| `devkit index [--graph G]` | per-module digest the hooks read (D5); the post-commit hook calls it after a build | 0; 1 no graph |
| `devkit usage [--days N] [--transcripts DIR]` | codemap tool calls against grep in local Claude Code transcripts (D6) | 0 |

`init` on a repository that already has the devkit behaves as `update` and says so. `update` without a
devkit refuses and names `init`.

### D2 — managed artifacts, and the one rule for touching them

The devkit writes only regions it owns. Each region carries a marker with the devkit version. The hash of
the region as written is recorded in `.codemap-devkit.json`. That file is committed: it says which
devkit version the repository is on, for every machine.

| Artifact | Region | Default |
|---|---|---|
| `AGENTS.md` (or `CLAUDE.md` when only that exists, or `--agents-file`) | between `<!-- codemap-devkit:begin vN -->` and `<!-- codemap-devkit:end -->` | on |
| `.mcp.json` (Claude Code) | the key `mcpServers.codemap` | on |
| `.codex/config.toml` (Codex, trusted projects) | between `# >>> codemap-devkit vN` and `# <<< codemap-devkit` | `--codex` |
| `codemap.toml` `[architecture]` | the whole table when the file has none; otherwise only the `allowed` region, and only with `--ratchet` | on (see D3) |
| git `post-commit` hook (`git rev-parse --git-path hooks`) | the whole file, marker `# codemap-devkit:post-commit vN` | on; `--no-hook` |
| `.claude/settings.json` | `hooks.SessionStart` and `hooks.PostToolUse` entries whose command is `codemap devkit brief`/`touched` | `--claude-hooks` |
| CI | `.github/workflows/codemap.yml` (whole file, marker) or `.codemap/devkit/gitlab-ci.yml` to `include:` | `--ci` |
| `.gitignore` | the line `.codemap/` | on |

**The rule.** The devkit rewrites a region only when its current content hashes to what the devkit last
wrote. A region edited by hand is reported with a diff and left alone; `--force` overwrites it. A foreign
artifact in the devkit's place is never overwritten without `--force`. Examples: a `post-commit` without the
marker, or a `mcpServers.codemap` the devkit did not write. Instead the devkit says where its own version
went: the hook goes to `.codemap/devkit/post-commit`, to be called from the existing one.

**The pin is the project's.** `.mcp.json`, the hook and CI name one codemap executable or version. `init`
pins the executable it runs from (its absolute path; `codmap==<version>` in CI). `update` keeps the
existing pin and re-pins only with `--repin`. `status` runs the pinned executable's `--version` and reports
"pinned 0.0.35, installed devkit from 0.0.39" as a line, not as a failure.

Machine-specific paths go only into files that are not committed by default (`.mcp.json`, the git hook). The
devkit does not decide whether a project commits `.mcp.json`; it says that it holds an absolute path.

### D3 — `allowed`: the ratchet rule, and its generator

New key in `[architecture]`:

```toml
allowed = [
  { from = "entities", to = "commands" },
  { from = "journals", to = "sales" },   # settle reads the sale; reason written here
]
```

When `allowed` is present, every import between two different layers of the core must be listed. Every
import scope counts — module level, function-local, `TYPE_CHECKING`, stub — because each one is a
dependency of one layer on the other. Any other import fails the rule `allowed`, and the offending edges are
named grouped by pair, as `forbidden` does. An empty list allows no cross-layer import at all.

A listed pair with no import today is **unused**. It is reported in `allowed_unused` (JSON) and as a note
("N allowed pair(s) are no longer used — `codemap devkit ratchet --tighten` removes them"). It is not a
violation: removing a dependency must never turn a gate red.

Validation follows the closed schema (R1-C69): items are `{ from, to }` tables only, `from ≠ to`, no repeated
pair. Applicability (R1-C62): declared = items, applicable = items whose both layers exist.

**Generator.** `devkit ratchet` builds the list from the current graph (all scopes, as the rule judges) and
writes it as a managed region inside `[architecture]`:

```toml
# >>> codemap-devkit allowed v1 — `codemap devkit ratchet` writes this list; add a pair by hand with a reason,
#     `--tighten` only ever removes pairs that are no longer used
allowed = [
  { from = "a", to = "b" },
]
# <<< codemap-devkit allowed
```

The region is edited line by line. A pair line looks like `{ from = "…", to = "…" },` with an optional
`# comment`. `--tighten` removes exactly the unused pair lines and keeps every other line verbatim,
comments included. Hand additions are expected, so this region is exempt from the D2 hash rule. Without
`--tighten`, `ratchet` on an existing region only adds missing pairs, and says that adding them weakens the
gate.

**Starter contract.** When `init` creates `[architecture]`, it writes the `allowed` region plus
`no_cycles = true` and `no_type_only_cycles = true`, each only if the graph holds it today. A gate that is
red on day one is not a ratchet. The flags left out are written as comments with today's counts.

### D4 — the agent rules block

The `AGENTS.md` region is the layer that makes sessions use the tool. The MCP server only makes it available.
It is Codex's too: Codex reads `AGENTS.md` from the repository root. The block is short and concrete:

- *who calls X* → `callers`, not grep: grep cannot tell a call from a mention, nor one class's method from
  another's;
- before changing a public symbol, model or signature → `impact`, and state the reach in the task or the
  review;
- before a merge → `review` on the diff, with its output attached;
- read `currency`, `resolved.ambiguous` and `limit` before trusting an answer; `behind` → rebuild or say so;
- the contract and the ratchet: a new pair in `allowed` is added by hand **with a reason comment**;
  `check` red means fix the import or argue the pair in review;
- a codemap defect → message the codemap session and file an issue upstream with a minimal example on
  invented names (the tracker is public; none of the project's code);
- the pin is the project's decision; `codemap devkit status` says what is behind.

Commands and tool names in the block are the ones D7 checks.

### D5 — hooks that bring codemap to the moment, cheaply

Claude Code only, opt-in (`--claude-hooks`). Codex has no equivalent: D4 is its layer.

- **SessionStart → `codemap devkit brief`.** Plain stdout is added to context. It prints graph currency
  (current / behind / absent, devkit version, pinned version) and the rule list in five lines. It does not
  load the graph: the currency comes from the meta sidecar and the scope hash, so it runs in well under a
  second on a large repository.
- **PostToolUse (Edit|Write) → `codemap devkit touched`.** Reads the hook JSON on stdin and takes
  `tool_input.file_path`. If the file is a module of the package, it prints
  `hookSpecificOutput.additionalContext`: how many modules import it, its functions with outside callers and
  their counts (top 5), and "run `impact <symbol>` before changing a public signature". Otherwise it prints
  nothing. It reads the small per-module digest `.codemap/devkit/index.json` that `devkit index` writes after
  every hook build. Loading a 40 MB graph on each edit would cost seconds. A missing or stale digest gives one
  line saying so, never an error. Exit 0 always: a hook must not block an edit.

### D6 — measuring whether the tool is used

`devkit usage` reads local Claude Code transcripts of the project
(`~/.claude/projects/<path with / → ->/*.jsonl`, or `--transcripts`). For the last N days it counts tool uses
named `mcp__codemap__*`, against the `Grep` tool and Bash commands that start with `grep`/`rg`. It prints both
counts, the ratio and the per-tool split. It reads names and counts only, never message text. Codex
transcripts are not read, and the output says so.

### D7 — what keeps the devkit current: the suite, not memory

`tests/test_r1c108_devkit.py`:

1. **Every command in every template parses.** Each `codemap …` line is placeholder-substituted and handed
   to `build_parser().parse_args`. A renamed subcommand or flag fails the suite in the same commit.
2. **Every MCP tool the templates name exists** in `MCP_TOOLS`.
3. **Templates cannot change silently.** `codemap/devkit/__init__.py` holds `DEVKIT_VERSION` and
   `TEMPLATES_SHA256`. The test recomputes the hash; a mismatch fails with "bump `DEVKIT_VERSION` and update
   `TEMPLATES_SHA256`". The bump is what `status` reports as "outdated" in every adopting project.
4. **The release step:** CONTRIBUTING gains a line. When `DEVKIT_VERSION` moved since the last release, the
   release note says "run `codemap devkit update`", and the neighbours' notification repeats it.

### D8 — what is not in this design

- No cron entry: the hook does a full build when the last one is older than a day, as project A's does.
- No edits to user-level config (`~/.codex`, `~/.claude`): repository files only.
- The devkit does not decide the pin, the commit status of `.mcp.json`, or the contract's rules beyond the
  starter. Those are the project's.
- No migration of the three existing integrations. Each project runs `init` itself if it chooses to; E7
  shows what that does to project A.

**`ANSWER_FORMAT` stays 10.**
- `allowed` is a new key. A contract without it is judged exactly as before.
- The `check` markdown for such a contract is byte-identical.
- JSON gains one additive key, `applicability.allowed`, which is always present (R1-C28).
- `allowed_unused` appears only when `allowed` is declared.
- A contract with `allowed` needs codmap ≥ 0.0.39: older versions refuse the unknown key (R1-C69), which is
  the right failure.

## Pre-registered expectations

E1, E2, E4–E11 and E13 fail on 0.0.38: there is no `allowed` key and no `devkit` command.

| # | Expectation |
|---|---|
| E1 | Fixture `pkg/{a,b,c}`: `a → b` module-level, `b → c` function-local. `allowed = [a→b]`: `check` exit 2, rule `allowed`, names `pkg.b… → pkg.c…`, the function-local edge. `allowed = [a→b, b→c, c→a]`: exit 0, `allowed_unused = [c→a]`, and the note names `--tighten`. 0.0.38 on the same contract: exit 2 `unknown key \`allowed\`` |
| E2 | `allowed` with a repeated pair, `from = to`, and an extra item key: one contract error naming all three; no rule enforced |
| E3 | Project A's `check` markdown is byte-identical to 0.0.38's apart from the version line. Its JSON differs only by `applicability.allowed = {declared: 0, applicable: 0}`. Project B's gate output is identical apart from the version |
| E4 | Clean clone of project C at the audited commit: `devkit ratchet` writes the region; the pair count equals the count from an independent AST scan of the same tree (all scopes, top-level component), with any difference reconciled by name. `check` is green. One added import from a foundation module into a domain one (a pair absent today), fast rebuild: `check` exit 2, exactly that edge named |
| E5 | Remove the only import behind one pair: `ratchet --tighten` removes exactly that line. A hand comment on another line and a hand-added pair line with a reason are kept byte for byte |
| E6 | Empty repo (`git init`, two-module package): `devkit init --package pkg` creates the AGENTS.md region, `.mcp.json`, the post-commit hook, `codemap.toml` with `[architecture]` (`no_cycles = true`, the `allowed` region), `.codemap-devkit.json` and the `.gitignore` line. `status` exit 0. The exact `.mcp.json` command, spawned with an MCP client, answers `initialize` and lists all `MCP_TOOLS`. A commit runs the hook, and the graph and `index.json` appear |
| E7 | Clone of project A (its `.mcp.json` codemap server on another venv, its own contract, a foreign `post-commit`, a long `AGENTS.md`): `init` leaves the text outside the AGENTS region byte-identical; `codemap.toml` byte-identical (no `--ratchet`); `.mcp.json` `codemap` entry untouched and reported as foreign; the foreign hook untouched, the devkit's copy written to `.codemap/devkit/post-commit` and reported. Exit 1 (needs attention), not 0 and not 2 |
| E8 | Update path: with `DEVKIT_VERSION` raised in the test, `status` says outdated (exit 1); `update` rewrites the regions and `status` says current (exit 0). A region edited by hand is skipped with a diff (exit 1); `--force` rewrites it. `update` keeps the pin; `--repin` moves it |
| E9 | D7 guards: a template flag misspelt (`--deeep`) → red; a tool name misspelt → red; a template changed without bumping → red; each restored → green |
| E10 | `devkit brief` against project C's graph sidecar: under 1 s wall (median of 5), prints currency. `devkit touched` with a recorded Edit payload for a module of the package prints valid JSON with `hookSpecificOutput.additionalContext` naming the importer count; for a file outside the package it prints nothing and exits 0; with no digest, one line. A real Claude Code session (`claude -p` in the E6 repo, hooks installed) quotes the SessionStart line back |
| E11 | `devkit usage` over project A's local transcripts for 7 days: the codemap and grep counts equal an independent `jq` count over the same files |
| E12 | Full suite passes. Mutations go red: the `allowed` rule check off; the unused-pair note off; the D2 hash guard off (a hand edit gets overwritten); the foreign-artifact guard off; the template parse test made to skip a file. A cosmetic control stays green |
| E13 | Project C clone: `devkit init --package <its package> --consumer tests` then `status` exit 0 and `check` green, with no hand step between them |

Surprises go into the reconciliation.

## Reconciliation (2026-11-21)

| # | Result |
|---|---|
| E1 | ✅ fixture `a → b` (module), `b → c` (function-local): `allowed = [a→b]` → rule `allowed`, exactly `pkg.b.n → pkg.c.o`; three pairs → green, `allowed_unused = [c→a]`, the note names `--tighten`; an empty list fails both edges. 0.0.38 refuses the key (`unknown key \`allowed\``) |
| E2 | ✅ one contract error naming the repeat, `from = to` and the extra key; nothing enforced |
| E3 | ✅ with one surprise. bquant and bquearch `check` markdown byte-identical to 0.0.38; bquant JSON differs only by `applicability.allowed = {declared: 0, applicable: 0}`. Surprise: the answer-format pin moved — the refusal of an *invalid* contract lists the known keys, and `allowed` is one. Wording only; re-pinned without a format bump |
| E4 | ✅ after R1-C109. First run: 608 pairs against 624 from the independent scan; reconciled by name: every missing pair started in one of three apps without `__init__.py`. That was a codemap defect, not the devkit's: namespace-subpackage modules had no source (R1-C109). After it: 624 = 624, no difference either way. Mutation (`i18n/phone.py` imports `structure.models`, a pair absent): `check` exit 2, exactly that edge named |
| E5 | ✅ `--tighten` removed exactly the unused line; a reason comment, a free comment line and a hand-added pair kept byte for byte; an edit that would leave a repeated pair wrote nothing |
| E6 | ✅ empty repo: every artifact, `status` 0. The `.mcp.json` command spawned with an MCP client: `initialize`, all 28 `MCP_TOOLS`, `callers` answers. A commit ran the hook: `rebuild.log` "full ok", graph and `index.json` present |
| E7 | ✅ bquant clone: `AGENTS.md` outside the block identical, the block appended; `codemap.toml`, `.mcp.json` and the foreign hook byte-identical; the devkit's hook in `.codemap/devkit/post-commit`; exit 1 |
| E8 | ✅ outdated → `update` → current; a hand edit kept with its diff, `--force` rewrote it; the pin kept, `--repin` moved it. Also seen live: raising `DEVKIT_VERSION` to 2 (below) made `status` say "v1 in this repository, v2 available" and `update` rewrote the regions |
| E9 | ✅ misspelt flag, misspelt tool, template changed without a bump: each red, each green when restored |
| E10 | ✅ `brief` on project C (196k lines + 148k of tests): 0.38 s median of 5; `touched` 0.23 s, valid JSON, importer count and top callers; outside the package nothing; no digest → one line. A real `claude -p` session in the E6 repo quoted the SessionStart line back verbatim |
| E11 | ✅ after two counter defects were fixed (surprises). On a frozen copy of 13 transcripts: codemap 0 / 0, Grep 0 / 0, grep in Bash 512 / 512 against an independent `jq` + split count |
| E12 | ✅ red: `allowed` check off (2), unused note off (1), hash guard off (1), foreign guard off (1), the scan skipping `.yml` (1), usage de-duplication off (1), misspelt tool (4), misspelt flag (3); cosmetic control green. Full suite 1322 passed, 2 skipped |
| E13 | ✅ project C clone: `init --package <pkg> --consumer tests` 1 min 13 s (fast graph included), `status` 0, `check` green (608, then 624 after R1-C109) |

**Surprises.**
- **A codemap defect found by the acceptance, not the unit tests**: modules of a namespace subpackage carried
  no source, so their function-local imports were lost (R1-C109, fixed in the same release). It also explained
  R1-C105, whose hypothesis was wrong.
- **The D7 guard caught the templates on its first run**: prose like "managed by \`codemap devkit\`" and
  "\`codemap devkit init\` wrote it" reads as a command without its required arguments. Rewritten as prose.
  Two strengthenings followed: per-template command counts are pinned, so the scan cannot silently stop
  reading a file. And a git-history check makes sure `TEMPLATES_SHA256` never moves without `DEVKIT_VERSION`:
  updating the hash alone would have silenced the guard.
- **The GitLab snippet's path was wrong in D2**: `.codemap/devkit/gitlab-ci.yml` is under a gitignored
  directory, so it could never be included. It is now `.gitlab/codemap-ci.yml`.
- **The usage counter was wrong twice**. Transcripts store request blobs that repeat earlier tool calls without
  a timestamp (1 301 of 16 536 on the run); only `assistant` records count now, once per tool-use id.
  And a newline separates commands in bash, which the first regex missed. Subagent transcripts are counted too.
- **`cwd = ".."` for Codex was an unverified assumption**. Codex reads `.codex/config.toml` only in a trusted
  project, which was checked with a temporary `CODEX_HOME`, and resolves a relative `cwd` against `.codex/`.
  The entry now names the absolute root. The template changed, so `DEVKIT_VERSION` is 2 at release.
- The pin path kept a `..` (`e13/../dkv/bin/codemap`); now `abspath`.
- Measured, not designed: on the same tree the per-machine `.mcp.json` and the git hook hold absolute paths,
  and `.codex/config.toml` now does too. The devkit says so and leaves committing them to the project.
