# The devkit — adopting codemap in a repository (`codemap devkit`)

MCP makes codemap *available* to an agent. It does not make the agent *use* it: an agent used to grep greps.
The devkit installs the whole discipline in one command, keeps it current with codemap, and says when it has
drifted. Design and acceptance: [`design/devkit.md`](design/devkit.md) (R1-C108).

```bash
codemap devkit init --package src/mypkg --consumer tests   # first install
codemap devkit status                                       # what is current, outdated, edited, missing
codemap devkit update                                       # bring it to the installed codemap
```

## What `init` writes

| Artifact | What it is for | Default |
|---|---|---|
| a block in `AGENTS.md` (or `CLAUDE.md` if only it exists) | **the layer that makes sessions use the tool**: when to call `callers`, `impact`, `review`; what `currency`, `ambiguous`, `limit` mean; the contract and the ratchet; how to report a codemap defect. Claude Code and Codex both read it | on |
| `.mcp.json` → `mcpServers.codemap` | `serve --mcp --watch` on the repository's graph, for Claude Code | on |
| `.codex/config.toml` | the same server for Codex (trusted projects only) | `--codex` |
| `codemap.toml` `[architecture]` | a starter contract **written from the graph**: `no_cycles` and `no_type_only_cycles` where they hold today, and the `allowed` ratchet. The gate starts green and turns red on a new problem, never an old one | on, when the file has no `[architecture]` |
| git `post-commit` | rebuilds the graph after each commit in the background (incremental, a full `--deep` build daily, one at a time, its own process group), then the hooks' digest | on; `--no-hook` |
| `.claude/settings.json` hooks | SessionStart: one paragraph with the graph's currency and the rule. PostToolUse on Edit/Write: what imports the edited module and which of its functions have callers elsewhere | `--claude-hooks` |
| CI | `.github/workflows/codemap.yml`, or `.gitlab/codemap-ci.yml` to `include:` — build and `check --require-contract` | `--ci github\|gitlab` |
| `.codemap-devkit.json` | the devkit version and the hash of everything it wrote — **commit it** | always |
| `.gitignore` | `.codemap/` (graphs and the digest are local) | on |

`init` writes its files first and builds a fast graph after them, so a rules file inside a `--docs` root is already
in the graph. An existing graph is kept when **this** codemap built it and it is not behind its source tree, and
rebuilt otherwise. With `--no-build` nothing is built: the contract is written only from such a fit graph, and
otherwise the note says why (another version, or how many files changed); rebuild with the pinned codemap and run
`codemap devkit ratchet`, which applies the same check and exits 2 on an unfit graph.

`init` and `update` say when the pinned interpreter cannot import `mcp` (install `codmap[mcp]`), and when
`.codex/config.toml` was written from a linked git worktree, whose path is usually temporary.

The pin (the codemap executable in `.mcp.json` and in the post-commit hook) is the project's: `update` keeps it,
`update --repin`, run by the new codemap, moves both.

## The one rule for touching files

The devkit rewrites a region only when it is exactly what the devkit last wrote (its hash is in
`.codemap-devkit.json`). A region you edited is **kept** and reported with a diff; `--force` rewrites it. Something
in the devkit's place that it did not write — your own `post-commit`, a `codemap` entry in `.mcp.json` — is
**never** touched without `--force`. The devkit's hook then goes to `.codemap/devkit/post-commit`, for your hook
to call. Exit codes: 0 done; 1 done, with items needing attention; 2 refused.

**The rules block's place and language are yours.** `--agents-file F` puts the block in its own file (link to it
from `AGENTS.md` in your words); `--agents-lang ru` writes it in Russian, with the same commands. Both work on
`init` and, later, on `update`: a moved block leaves its old file when it is untouched, and stays there with a
note when you edited it. A translated block replaces an untouched one; an edited one is kept and reported.

**What the devkit trusts (R1-C121).** `.codemap-devkit.json` and `.mcp.json` come with the repository, so the
devkit treats them as input. It runs or writes into the hook only a pin of the shape it writes itself — the
absolute path of a `codemap` console script, or an absolute python as `-I -m codemap` — that exists and is not a
file of the repository; any other command in `.mcp.json` is not run and is replaced, with a note. Every path it
stores is relative, stays inside the repository after symbolic links are followed, and uses only
`[A-Za-z0-9._/@+-]`; a state naming anything else is refused (exit 2) before anything is written. Values rendered
into the hook and the CI file are shell-quoted as well.

**The pin is yours.** `.mcp.json`, the hook and CI name one codemap. `init` pins the codemap it runs from; `update`
keeps your pin; `update --repin` moves it. `status` tells you when the pinned version is behind the installed one,
and when the pinned interpreter cannot import `mcp` (install `codmap[mcp]`), which is why `serve --mcp` would not
start.

## The ratchet: `allowed`

```toml
[architecture]
allowed = [
  { from = "entities", to = "commands" },
  { from = "journals", to = "sales" },   # settle reads the sale; the reason is written here
]
```

When `allowed` is present, every import between two layers must be a listed pair. Imports at every scope count:
module level, inside a function, under `TYPE_CHECKING`. Any other import is a violation, and the edges are named.
A listed pair nothing uses any more is a note, never a violation; removing a dependency must not turn a gate red.

A project whose layers are tangled cannot declare `layers`. `allowed` freezes what exists, so every new
dependency between layers has to be argued in review. Measured on a 196k-line Django project with 53 layers:
624 pairs, and the gate named exactly the one import a test added.

`codemap devkit ratchet` writes the list from the graph into a marked region. Edit the region by hand freely: add a
pair with a reason comment. `--tighten` removes exactly the pairs no import uses and keeps every other line,
comments included. An edit that would leave an invalid contract writes nothing.

## The cycle ratchet: `known_lazy_cycles`

```toml
[architecture]
known_lazy_cycles = [
  ["pkg.orders", "pkg.pricing"],
  ["pkg.auth", "pkg.roles", "pkg.sessions"],
]
known_type_only_cycles = [
  ["pkg.models", "pkg.views"],
]
```

`no_lazy_cycles` and `no_type_only_cycles` are all or nothing. A tree that already has such cycles can list them
instead: a declared list turns its gate on (even beside `no_lazy_cycles = false`). A cycle whose modules all sit
inside one listed group passes; one that has split or shrunk still does. Any other cycle fails, including a known
one that grew a module: the line says which group it grew from. A listed group with no cycle left in it is a
note, never a violation.

`codemap devkit ratchet --cycles` writes both lists from the graph into a marked region; once the region exists,
every `ratchet` run adds the cycles the graph has and `--tighten` removes the groups that hold none. Hand-added
groups and comments in the region are kept.

## Is it used? `codemap devkit usage`

It counts `mcp__codemap__*` tool calls against grep (the Grep tool and `grep`/`rg` in Bash) in the project's local
Claude Code transcripts, sessions and subagents, for the last N days (`--days`). It reads names and counts only.
Codex transcripts are not read. Grep also covers searches that are not about structure, so the share is a floor,
not a score. If it stays near zero, the rules block is not doing its job: say so to the codemap maintainers.

## Keeping the devkit current

This is codemap's job, enforced by its suite (`tests/test_r1c108_devkit.py`):
- every command in every template parses with the CLI parser;
- every MCP tool the rules name exists;
- a template cannot change unless `DEVKIT_VERSION` rises with it, checked over git history too.

When `DEVKIT_VERSION` moves, the release note says "run `codemap devkit update`".
