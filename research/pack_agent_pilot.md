# Does an agent with `pack` locate a change better? V4 pilot (R1-C61)

**Status:** pre-registered 2026-11-03, before any run. Harness:
[`bench/agent_pack.py`](bench/agent_pack.py).

## 0. Why this is open, and what kind of number it gives

**This door was closed by our own rule.** V3 (R1-C66) wrote down, before its run, that V4 opens only if
two-way `pack` beats `grep` with confidence on *both* repositories. On bquant the interval of the
difference included 0, so V4 was closed. **The owner reopened it on 2026-11-03.** This text says so,
because a measurement that slips past its own decision rule is the thing this project refuses everywhere
else. When I proposed the step, I did not say the door was closed; that was caught before any run.

**A model is in the loop.** Every number here depends on the model, the harness, the prompt and the
sampling. Nobody can re-derive it from a frozen tree, unlike every other measurement in this project.
It must never be quoted as one of our ordinary measurements (`positioning.md` included) without saying
so.

**This is a pilot.** It estimates three things:
- the cost of one run;
- the spread between repeats;
- how often the protocol breaks.

From these the owner decides whether a full run is worth its price. **It makes no claim that `pack`
helps or does not.**

## 1. Task

The agent is put in a checkout of bquant at the parent of a commit and is given that commit's message.
Without editing anything, it must name every Python file the commit modifies or deletes. The truth comes
from git, not from our graph: V2's oracle (`pack_usefulness.md` §1). Here the truth includes V2's seed,
because the agent is not given a seed.

**Selection, fixed:**
- V2's 108 commits on the pinned ref `40839156608c…`. Selection hash `2197505e653a…`, reproduced before
  this text was written.
- Minus every commit whose message names a file of its own answer: its path, or its module stem as a
  word. That leaves 38.
- A seeded sample (seed 61) of **20**: `0b6ee3c2423c 0c785cfbef0d 202e17318607 2354d023480f 348de4404d70
  3fbb40492f72 4150cc1a46fe 4464d87afec3 44ad0fc49de7 55c9a8b65188 68618bdc6977 7287cd6a0d2f
  733d5de17999 9015fb3df266 9241384398dd 9297ca0c720f aabb989c44a9 ac650aee4c2d caa96f58141d
  ed35194fb13c`. sha256 of the list: `3a15b65fe8c8…`.

**Arms.** Everything is identical except one tool:
- **baseline:** `Read`, `Grep`, `Glob`.
- **pack:** the same, plus `mcp__codemap__pack`, served from a graph built at the parent: repo-scoped,
  with consumers `tests examples scripts research`.
- Both arms: `Edit`, `Write`, `NotebookEdit` and `Bash` disallowed. The tree is a `git archive` export,
  so there is no history to read.
- The prompt is fixed in the harness. The pack arm gets one extra paragraph naming the tool and what it
  does, and no instruction to use it.

**Isolation.** Headless Claude Code, model `sonnet`, at most 40 turns, with
`--setting-sources local --strict-mcp-config --no-session-persistence`, run from a fresh copy of the tree
in a temporary directory. A probe beforehand confirmed that this session sees no MCP server, no memory
file and no CLAUDE.md. `--bare` would be cleaner, but it requires an API key, and this account uses OAuth.

**Runs.** 20 tasks × 2 arms × 2 repeats = **80**. The order is shuffled with seed 61, so the arms
interleave. There is a hard stop at **$50** spent.

**Scored per run:**
- recall and precision of the named files against the truth;
- cost (`total_cost_usd`), turns, seconds;
- tool calls by name, to see whether the pack arm called `pack` at all;
- errors (no final JSON list, or a CLI error).

**Contamination, stated:** bquant is public on GitHub. Some of these commits may predate the model's
training data. That affects both arms alike, and the size of the effect is unknown.

## 2. Pre-registered expectations: about the protocol, not about `pack`

- **P1.** Each arm has errors in fewer than 10 % of runs. Otherwise the protocol is fixed before any full
  run, and the pilot says what broke.
- **P2.** Cost per run is between $0.05 and $1.00 in each arm.
- **P3.** The pack arm calls `pack` in at least half of its runs. If not, that arm does not test `pack`,
  and a full run in this form would measure the presence of a tool the agent ignores.
- **P4.** The spread between repeats (mean |Δrecall| of the same task and arm) is reported. From it and
  the per-task paired difference, the report computes how many tasks a full run needs to see a 0.05
  difference.

**What happens after:**
- The pilot's recall difference is reported as it comes, and called the **pilot** difference.
- With 20 tasks it decides nothing. No result of it goes into `positioning.md`.
- Whether to spend on the full run, and how much, is the owner's decision, made on P2–P4.
