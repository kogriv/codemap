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
items:[{id, kind, rank, tokens, text}]}`.

**MCP / serve:** the `pack` tool (and serve op) takes `budget` and optional `seeds`, so
an agent can pull a budgeted context slice natively — codemap as a first-class context
provider, not just a point-query API.
