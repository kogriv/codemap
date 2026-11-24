# R1-C131 — profile ranking and context packs

**Status:** preregistered and measured 2026-11-24. [Results](RESULTS.md).
**Gap:** [rank and pack cost](../../../gaps/rank_pack_cost_2026-11-24.md).

## Inputs and scope

Install the published `codmap[mcp]==0.0.49` in a clean Python 3.12 environment.
Reuse the public revisions pinned in [R1-C130](../r1c130/DESIGN.md#inputs) and
build fresh graphs in a dedicated `~/jobs/codemap/` directory. Use more-itertools
fast, rich deep, and pytest deep with `src/pytest`, `testing`, and `scripts` as
full consumer roots. Build one Jedi sample per deep graph. Run sequentially on
`m99` with two pinned logical CPUs under the shared slot and journal protocol,
after agreement with `tgsh`. Record wheel digest, dependency and host details.

Use the R1-C130 canonical symbols as seeds. Measure a global request, a seeded
request with `direction=uses`, and the same seed with `direction=both`. Use a
2000-token budget and the normal MCP currency TTL. All tools run on static
source graphs. Profiling adapters and cache prototypes live in the harness.

## Protocol

1. **Uninstrumented baseline.** After one warmup per case, collect 20 wall/CPU
   samples of direct `Query.rank`, 20 of direct `build_pack`, and 20 wall and
   reply-byte samples over real MCP STDIO. Validate the outcome and compare
   MCP result contents with the direct pack for the same arguments.
2. **Attribution.** Wrap the direct calls in a separate series of three
   repetitions per case. Measure exclusive time in graph construction,
   PageRank, seed resolution, reachability, sorting/selection and rendering
   or their enclosing residual where appropriate. Count calls to `_rank_graph`
   so nested construction is counted once. Collect a separate `cProfile`
   snapshot per pack case with total and cumulative function time. Report
   uninstrumented latencies separately from profiled timings. Compare measured
   pack and MCP to describe the residual transport/envelope cost.
3. **Cache experiments on pytest/deep.** Compare uncached, an eight-entry
   per-Query LRU of graph projections, and a 32-entry per-Query LRU of rank
   results. Projection keys include root and edge kinds. Rank keys include
   seeds, direction, root and edge kinds, with a copy on return to preserve
   caller ownership. Use fresh Query objects and deterministic 24-request
   streams: 24 distinct rank keys, 12 distinct followed by the same 12, and
   three distinct followed by 21 repeats. Alternate budgets so a repeated
   rank key can still need a different pack. Report lookups, hits, P50/P95,
   cold cost and retained Python allocations after population. Run memory
   instrumentation separately. Verify exact pack/rank output equality with
   the baseline, including a refused seed and different directions and roots.
   Check that a fresh Query on a different graph starts with empty caches.
4. **Decision.** Record whether a permitted real-query aggregate exists with
   enough requests to estimate repeat frequency. Treat synthetic hit rates as
   scenario results. The result-cache decision requires a representative
   repeat rate and measured gain. Graph projection reuse can be assessed on
   distinct requests because it can hit across seeds. For the telemetry check,
   inspect direct named `pack` calls in this Codemap conversation and recent
   Claude Code logs for the Codemap workspace only. Retain counts and coverage
   limitations, with no raw prompts, arguments or third-party session data.

P50 is the median and P95 uses nearest rank `ceil(0.95*n)`. Show the sample
count and max for the three profiled repetitions. Keep raw JSONL, harness
and results under this research directory. Record any timeouts and deviations.

## Predictions and decision thresholds

- H1. The PageRank and projection steps together account for most of `pack`
  latency on pytest/deep. The default seeded case builds the projection three
  times. Rendering and MCP transport are measured as separate terms.
- H2. Reusing the graph projection improves distinct seeded requests. Reusing
  ranks helps repeat-heavy streams more than the all-distinct stream.
- A prototype qualifies for implementation review at **at least 20% lower P95
  or 50 ms saved** on its intended pytest workload, **at most 10% median cold
  overhead** and **at most 16 MiB retained Python allocations** at its configured
  capacity. Exact output equality and snapshot invalidation are hard criteria.
  A bounded rank cache additionally needs evidence of suitable repeat frequency
  from real traffic. Otherwise record the candidate conditions and keep the
  decision open. The thresholds guide engineering review and carry no SLA.

## Acceptance

| ID | Evidence |
| --- | --- |
| E1 | Three fresh graphs with source and wheel identities. Nine cases with complete direct rank, direct pack and MCP baseline samples. |
| E2 | Exclusive attribution and function profile for every case, with projection count and untouched baseline latencies. |
| E3 | Three controlled hit-rate streams for both prototypes and baseline. Output parity, cold latency, retained allocation and new-snapshot controls recorded. |
| E4 | Compare H1/H2 and thresholds. State the evidence for real repeats or its limits. Give a concrete decision for projection reuse and for result caching, with raw data and reproduction instructions. |

## R1-C150 and R1-C151

The [profile](RESULTS.md#where-the-time-went) identified two independent paths.
R1-C150 prepares sorted successors and degrees before the PageRank loop.
Preserve the vertex and successor order, floating-point operations, dangling
redistribution, and convergence rule. R1-C151 reuses a projection across seed
resolution, reachability and ranking inside a pack request. The request owns
the projection. The bidirectional walk keeps its reversal separate from it.

Acceptance for each candidate uses exact `rank` and `pack` equality against
the same Git baseline. Cover global, `uses`, and `both` and include different
seed IDs, unresolved and ambiguous seeds, root restrictions and token budgets.
Check that seeded pack projects once, with no reuse across requests or graph
snapshots. Explicitly preserve the public Query entry points. The correctness
matrix applies to both candidates separately and to their combination.

For performance, reuse the published 0.0.49 pytest/deep graph from R1-C131
and compare its release baseline, each candidate, and their combination in
fresh warm MCP servers on `m99`. Keep graph bytes, Python, CPU affinity, request
sequence and response checks identical. Use 32 distinct rankable core seed IDs,
including the R1-C131 fixture symbol, in a fixed order and a 2000-token budget.
Measure `both` as the primary case. Measure global and `uses` as controls on the
same graph. Record unrounded wire-time samples and nearest-rank P95. The goal
for each candidate is **50 ms or 20% lower P95** in the primary workload, with
exact results. Compare the candidates separately before attributing a combined
gain. Retain any candidate that misses the performance gate as a measured patch
outside the product tree pending a further decision.
