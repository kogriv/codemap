# Design — every served answer says whether its graph matches the tree

**Status:** ✅ **done** (2026-11-06, fix 737e334; `ANSWER_FORMAT` 9), acceptance reconciled below. Pre-registered in 79a7fd2. **Backlog:** R1-C85. **Gap:**
[`gaps/mcp_graph_currency_2026-11-06.md`](../../gaps/mcp_graph_currency_2026-11-06.md).

## D1 — `currency` in every envelope

Every serve/MCP response (`ok: true`) carries `currency`, computed by the same `graph_currency` that
`check --graph` uses (R1-C70). The graph compared is the **served** one, the `scope_id` in memory, not the file
on disk.

```
"currency": {"status": "current" | "behind" | "unknown", ...R1-C70 fields..., "checked_seconds_ago": 3}
```

- `behind` carries the R1-C70 counts (`added`, `removed`, `changed`) and a `hint`: rebuild, then `reload` (or
  `serve --watch`).
- `unknown` always carries a `reason`. A server built in-process (`serve --build`) says
  "served from an in-process build; no build recipe to compare against".
- The field is always present (R1-C28): a field that appears only when something is wrong cannot be relied on.

## D2 — cached, with its age stated

The check costs 40–110 ms (median), up to ~0.3 s (gap §4). The result is cached for `--currency-ttl` seconds
(default **10**). `checked_seconds_ago` says how old the answer about the tree is. `--currency-ttl 0` checks on
every call. `reload` (and the `--watch` auto-reload) drops the cache, so the first answer after a reload is
checked afresh.

## D3 — `stats` shows it next to `freshness`

`stats` already reports `freshness` (time). It gains the same `currency` block, so the two are read side by
side. Its description in the MCP tool docstring says what each one means.

## D4 — cold CLI reads warn when behind

A CLI command reading `--graph` (`query`, `tests`, `review`, `report`, …; not `check`, which has its own currency
line) prints one stderr line when the graph is **behind**: `[warning] graph.json is behind its source tree (N
added, M changed, K removed since it was built) — answers describe the older tree; rebuild`. Nothing is printed
when it is current or unknown, stdout is untouched, and exit codes are unchanged.

**`ANSWER_FORMAT` 8 → 9**: every envelope gains a field. Schema unchanged.

## Pre-registered expectations

Run on the branch against 0.0.32. E1, E3, E4 and E6 fail on 0.0.32, so the list cannot pass if nothing was
done.

| # | Expectation |
|---|---|
| E1 | Fixture repo, graph built with a sidecar: every op envelope has `currency.status == "current"`; after a source file is edited, a call beyond the TTL says `behind` with `changed: 1`; `serve --build` (in-memory) says `unknown` with the in-process reason |
| E2 | TTL: with the default, two calls within 10 s compute the scope once (counted); with `--currency-ttl 0`, every call computes it |
| E3 | `reload` drops the cache: edit, rebuild, `reload` → the next answer says `current` without waiting for the TTL |
| E4 | CLI: `codemap query X --graph g.json` after an edit → one `[warning] … behind …` line on stderr, stdout byte-identical to before the edit; on a current graph stderr is empty |
| E5 | Cost on the bquant repo graph: 50 served calls with the default TTL add a median below 5 ms over `--currency-ttl` infinity; one uncached check is of the order measured in gap §4 |
| E6 | bquant: a graph built at an older commit with Python changes since, served over the current tree → `behind` with non-zero counts; rebuilt at the current tree → `current` |
| E7 | `check` on bquant and the bquearch gate: identical apart from the trailer (`answer format 9`) |
| E8 | Full suite passes; guards for D1, D2 (TTL and invalidation on reload), D3 and D4 go red when reverted; a cosmetic control stays green |

Surprises are reported in the reconciliation.

## Reconciliation (2026-11-06, 93afcd0)

| # | Result |
|---|---|
| E1 | ✅ fixture: `stats`, `search`, `query` envelopes say `current`; after an edit, `behind` with `changed: 1` and the hint; `serve --build` says `unknown` with the in-process reason |
| E2 | ✅ default TTL: 5 calls, 1 check; `--currency-ttl 0`: 3 calls, 3 checks; `checked_seconds_ago` present |
| E3 | ✅ `reload` drops the cache: after a rebuild and `reload`, the next answer is checked afresh |
| E4 | ✅ `codemap query --graph` after an edit: one `[warning] … behind its source tree (… 1 changed …)` line, stdout byte-identical; nothing on a current graph; `check` gets no second warning |
| E5 | ✅ bquant repo graph, 50 `search` calls: median 2.78 ms with the default TTL (1 check), 2.78 ms with an infinite TTL, overhead −0.01 ms; with TTL 0, 73.29 ms per call (51 checks), i.e. an uncached check costs ~70 ms, in line with gap §4 |
| E6 | ✅ bquant: graph built at `d9a2a4f`, served over `cf039ef` → `behind`, `changed: 4` (four files across the roots; first call 111 ms); rebuilt at `cf039ef` → `current` |
| E7 | ✅ bquant `check` and the bquearch gate identical apart from the trailer (`answer format 9`) |
| E8 | ✅ suite 1246 passed / 3 skipped; mutations (no envelope field; disk graph judged instead of served; no cache; TTL ignored; reload keeps the cache; no `stats` field; no CLI warning; `check` warned twice) red; control green |

**Surprises.**
- A first mutation (`ttl 0` treated as cached) survived. It was equivalent: `now - t >= 0` is always true, so the
  extra `ttl <= 0` clause did nothing. The clause was removed.
- A first "served versus disk" mutation was a NameError, which tests nothing. It was replaced with a guard
  that rebuilds the file on disk without `reload` and requires `behind` for the served graph.
