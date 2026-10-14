# Context pack — ranking + token budget

`codemap pack` turns the graph into a **token-budgeted context slice** for an AI agent:
the most relevant symbols, ranked, rendered to fit within N tokens. It closes the two
things a point-query API lacks — *ranking* (what to show) and a *budgeted render* (how
much).

## Ranking

Symbols are scored by **personalized PageRank** over usage edges (`calls`, `imports`,
`references`, `inherits`, `implements`), directed user→used — so heavily-depended-upon
symbols accumulate rank:

- **No seeds → global importance.** On bquant the top hubs are `logging_config`,
  `config`, `exceptions`, `BaseAnalyzer` — exactly the most-depended-upon modules.
- **`--seed X` → relevance to a context.** Restart is biased to the seed(s) (aider's
  repo-map trick), so the seed's neighbourhood ranks first instead of the global hubs. A
  seed is a symbol id, a short name, or a file path.
- **A seeded walk goes both ways by default** (`--direction both`): what the seeds use
  *and* what uses them — callers, tests, examples — ranked by closeness to the seed
  whichever way the edge points. `--direction uses` keeps the one-way walk, for "what does
  this code need". The default was decided by a rule written down before it was measured
  (see the end of this page).

The PageRank is a **pure-Python power iteration** — no numpy/scipy dependency (codemap
stays lightweight) — and deterministic (nodes processed in sorted order, scores rounded).

## Budgeted pack

```bash
codemap pack --graph graph.json --budget 2000                 # global, 2000 tokens
codemap pack --build ./pkg --seed analyze_zones --budget 1500 # relevance to a symbol, both ways
codemap pack --graph graph.json --seed analyze_zones --direction uses  # only what it uses
codemap pack --graph graph.json --budget 500 --format json    # structured
```

Symbols are added highest-rank-first until the budget is spent; an item that would
overflow is skipped so smaller relevant items still fit. Output **never exceeds the
budget** and **top hubs land before leaves** (the acceptance). Token count is a
deterministic heuristic (~4 chars/token) — no tokenizer to install.

Each line is a compact context digest: `id (kind) signature — docstring-first-line`.
The JSON form returns `{budget, used_tokens, total_ranked, included, truncated,
items:[{id, kind, rank, tokens, text}], seeds, unreachable_from_seeds, coverage}`.

## What a pack is not — and says so

A pack is a ranked slice of **modules, classes and functions**, and with a seed it is a slice of
**what the seed is connected to by use** — by default both ways, with `--direction uses` only what it
uses. Every answer says that in so many words (answer format 2, [design](design/pack_honesty.md),
[direction](design/pack_direction.md)):

- **`coverage.never_in_pack`** — node kinds that can never appear, with counts: documents, attributes,
  columns. On the benchmark tree that is 1 685 of 2 880 nodes. If documentation is part of your
  question, a pack will not carry it.
- **`coverage.walk`** and **`coverage.direction`** — the walk taken (`both`, `uses`, or `null` without
  seeds) and the same in words. With `both`: what the seeds use and what uses them, directly or
  transitively — but **not a sibling** that only shares a dependency with a seed. With `uses`: **a
  seed's callers are never in its pack.** An exact "who calls X" list is still `callers` / `impact`;
  a pack ranks and cuts to a budget.
- **`unreachable_from_seeds`** — how many ranked symbols the walk does not reach; they are left out
  rather than used to fill the budget. Decided by walking the graph, not by a zero rank (ranks are
  rounded, and a far reachable symbol can round to zero). `null` without seeds.
- **`seeds`** — for each seed: how it was read (`id` / `file` / `name` / `none`), the ranked ids it
  became (`matched`), whether a name matched more than one definition (`ambiguous` — the pack is then
  biased to all of them), and what it matched that is never ranked (`unrankable`). Seeds that matched
  nothing rankable are listed in `unresolved`.
- **No seed resolved → a refusal.** `{error, budget, seeds, coverage}`, no items, and the CLI exits 1
  — as `codemap query` does on an unknown name. Before answer format 2 an unknown name, a `.md` path
  or an attribute id returned the global pack byte for byte under a header naming the seed.

```bash
$ codemap pack --graph graph.json --seed no_such_symbol
# Context pack — `bquant` · refused
...
$ echo $?
1
```

**Measured against git history, not against an agent.** For a commit that changed a package file,
seed the pack with that file on the graph of the commit's *parent*, and count how many of the other
files the commit changed land in the pack's first 10 files (recall@10):

| | benchmark repository, 108 commits | codemap itself, 83 commits (held out) |
|---|---|---|
| pack, `--direction uses` | 18.9 % · tests 0 % | 20.2 % · tests 0 % |
| **pack, `--direction both` (default)** | **41.6 %** · tests 42.6 % | **59.9 %** · tests 46.6 % |
| `impact` | 33.2 % | 40.6 % |
| grep by names | 35.4 % · tests 51.2 % | 38.7 % · tests 51.6 % |
| random | 5.6 % | 15.0 % |

The two-way walk was chosen on the first repository from four shapes and checked unchanged on the
second ([V2](../research/pack_usefulness.md), [V3](../research/pack_direction.md)). Against grep it is
ahead on both, but on the first repository the 95 % interval of the difference includes zero
(+6.1 points, [−1.9, +14.1]); on the second it does not (+21.2, [+12.9, +29.6]). Grep by names still
finds tests best — a test names what it tests. Lists were scored whole; at a 2 000-token budget the pack
holds the head of the list, which is what recall@5/@10 describe. Whether a pack helps an agent solve a
task is **not** measured.

**MCP / serve:** the `pack` tool (and serve op) takes `budget`, optional `seeds` and optional
`direction` (`both` | `uses`; an error without seeds), so
an agent can pull a budgeted context slice natively — codemap as a first-class context
provider, not just a point-query API.
