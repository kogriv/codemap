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

## 3. Reconciled (2026-11-03)

80 runs, all completed, **$5.08** in total by the CLI's own meter. Raw rows:
[`bench/agent_pack_pilot_results.jsonl`](bench/agent_pack_pilot_results.jsonl).

```
arm       runs  errors  recall(mean)  precision(mean)  cost/run  turns(mean)
baseline    40       0         0.392            0.805     0.055          5.5
pack        40       0         0.395            0.676     0.072          5.8
repeat spread: mean |recall(rep0) - recall(rep1)| over 40 task-arm pairs = 0.019
per-task paired difference (pack - baseline): mean +0.003, sd 0.058, n 20
pack arm runs that called pack: 1 of 40
```

| | expected | measured | |
|---|---|---|---|
| P1 | errors < 10 % per arm | 0 and 0 | holds |
| P2 | $0.05–1.00 per run | $0.055 and $0.072 | holds |
| P3 | the pack arm calls `pack` in ≥ half its runs | **1 of 40** | **fails, and it decides the pilot** |
| P4 | spread reported, tasks needed computed | repeats differ by 0.019 recall on average; paired sd 0.058, which gives 6 tasks for a 0.05 difference | reported, but see below |

**What the pilot says, and what it does not:**
- **The arm did not test `pack`.** In 39 of 40 runs the agent solved the task with `Grep`, `Glob` and `Read`
  (128, 34 and 28 calls in the pack arm). It called `pack` once, on task 14 (recall 0.2). The recall
  difference, +0.003, is the difference between two arms that did the same thing. A full run in this form
  would measure the presence of a tool the agent ignores, which is exactly what P3 was written to catch.
- **P4's arithmetic stands but has no subject.** The spread between repeats is small (0.019), so a full run
  could detect a difference of 0.05 with few tasks *if the arms differed in what the agent did*. They did
  not.
- **Precision differed, 0.805 against 0.676, with `pack` almost never called.** The only other difference
  between the arms is the prompt's extra paragraph. So the paragraph itself changed what the agent named:
  more files, less precisely. Not tested further.

**Two things about my harness, found in the rows:**
- **The pack arm saw all of codemap's MCP tools, not only `pack`.** `--allowedTools` controls what runs
  without asking, not what is offered. One run tried `mcp__codemap__search`, which was then denied. The
  arm was therefore "baseline + `pack` allowed + the other codemap tools visible but denied". The
  pre-registration said "the same, plus `mcp__codemap__pack`". This did not change the result, because
  one call is one call, but it is not what was written.
- **Two host tools appeared** (`ToolSearch` once, `ReportFindings` once). These are built into the CLI and
  not removed by `--setting-sources local`. That applies to both arms alike.

**What would make a full run measure `pack`:** that is a protocol decision, and the owner's. Options:
- tell the agent to start with `pack`;
- run `pack` for it, on seeds taken from the message, and put the result in the prompt;
- offer `pack` as the only search tool in that arm.

Each changes the question, from "would an agent choose it" to "does its output help". That is why it is
not decided here.

## 4. Pilot 2: `pack` handed over, not offered. Pre-registered 2026-11-03, before any run

**The owner chose this protocol after pilot 1** ("hand `pack` over in advance"). The question changes from
"does an agent choose `pack`" to **"does `pack`'s output help an agent locate a change, compared with grep
output of the same size over the same names"**. Same 20 tasks, same trees, model, isolation, budget, 2 repeats.

**Seeds.** The words of the commit message (4+ characters) that are the short name of a node of the graph
(function, class, module, attribute), in order of appearance, at most 8. Every task has at least one; 7 tasks
have 1, and 6 have 8. Some seeds are generic words that happen to name a module (`validation`, `zones`,
`bquant`). That is what a mechanical rule picks, and it is kept.

**Arms**, both without any MCP server (empty `--strict-mcp-config`), both with `Read`, `Grep`, `Glob`:
- **pack_ctx:** the prompt ends with `codemap pack --seed …` (budget 2000 tokens, the default, two-way walk),
  as markdown;
- **grep_ctx:** the prompt ends with the files matching any seed as a word, ranked by total matches, cut to the
  same number of characters as that task's pack. When the matches run out first, the grep context is
  shorter. That happens in 11 tasks: pack 644–9791 characters, grep 386–9737. The cap is equal, the size is not.
- Both arms use the same header: "Context gathered automatically from the names in the message (seeds: …)".

The contexts are computed before any run and are part of the input (`t*/context_*.md`). No refusal occurred.

**Expectations (about the protocol, as in pilot 1, plus the reading):**
- **Q1.** Errors under 10 % per arm.
- **Q2.** Cost per run between $0.05 and $1.00. The prompts are now 1–10 k characters longer.
- **Q3, uptake.** It is reported how often a run's named files include a file that appears in its own arm's
  context. If uptake is near zero in both arms, the context was ignored, and the arms do not differ in what
  the agent used.
- **Q4.** The per-task paired recall difference (pack_ctx − grep_ctx) is reported as the **pilot
  difference**, with its sd and the number of tasks a full run would need for a 0.05 difference.
  - It decides nothing at n = 20.
  - If that number exceeds the 38 leak-free tasks available, the report says that a full run on this
    selection cannot resolve the question.
- Precision and cost are reported beside recall. A context that adds recall by adding files costs precision,
  and that trade is part of the answer.
