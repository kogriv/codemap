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
  repo-map trick), so the seed's dependency neighbourhood ranks first. Seeding on
  `analyze_zones` surfaces `ZoneAnalysisBuilder`, `ZoneAnalysisResult`, … instead of
  the global hubs. A seed is a symbol id, a short name, or a file path.

The PageRank is a **pure-Python power iteration** — no numpy/scipy dependency (codemap
stays lightweight) — and deterministic (nodes processed in sorted order, scores rounded).

## Budgeted pack

```bash
codemap pack --graph graph.json --budget 2000                 # global, 2000 tokens
codemap pack --build ./pkg --seed analyze_zones --budget 1500 # relevance to a symbol
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
**what the seed uses**. Every answer says that in so many words (answer format 2,
[design](design/pack_honesty.md)):

- **`coverage.never_in_pack`** — node kinds that can never appear, with counts: documents, attributes,
  columns. On the benchmark tree that is 1 685 of 2 880 nodes. If documentation is part of your
  question, a pack will not carry it.
- **`coverage.direction`** — with seeds the walk runs from the seeds to what they use, directly or
  transitively. **A seed's callers are never in its pack.** "Who calls X" is `callers` / `impact`,
  not `pack`.
- **`unreachable_from_seeds`** — how many ranked symbols the seeds cannot reach; they are left out
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

**Measured against git history, not against an agent** ([research](../research/pack_usefulness.md)):
on 108 commits of the benchmark repository, with the graph built on each parent, a pack seeded with the
changed package file put **18.9 %** of the other files that commit changed into its first 10 files —
below grep by names (35.4 %) and `impact` (33.2 %), and **0 %** of the co-changed tests, by the
direction above. Restricted to the package's own files it is level with `impact` (0.31 vs 0.32) and
finds files neither `impact` nor grep finds; interleaved with `impact` it is the best method measured
(36.6 %). Whether a pack helps an agent solve a task is **not** measured.

**MCP / serve:** the `pack` tool (and serve op) takes `budget` and optional `seeds`, so
an agent can pull a budgeted context slice natively — codemap as a first-class context
provider, not just a point-query API.
