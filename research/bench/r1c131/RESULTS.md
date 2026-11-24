# R1-C131 — ranking and context pack profile

Measured 2026-11-24 using the [preregistered protocol](DESIGN.md) and the
published `codmap 0.0.49` wheel. The harness built three fresh public graphs.
The measurements ran on `m99` in a shared two-CPU slot, with affinity to logical
CPUs 0 and 1. Direct Python and real MCP STDIO requests used the same pack
arguments and produced equal payloads. Direct baselines, exclusive stage timing
and `cProfile` were separate series.

## Where the time went

On pytest/deep the MCP median was 269 ms for global `pack`, 256 ms for the
seeded `uses` walk and 427 ms for seeded `both`. The global pack built one
ranking projection. Both seeded variants built three. In the instrumented
`both` pack, those projections took about 45 ms and PageRank took about 350 ms.
Across the three pytest modes, these two stages accounted for 91.5–96.7% of the
instrumented pack time. The MCP P95 for seeded `both` was 494 ms.
MCP delivered the same payload as the direct call. Differences between the
direct and client baselines include process and envelope variation, so they are
reported as a difference of medians rather than an isolated transport timer.

`cProfile` identifies `_pagerank` and neighbor processing as hot code. The
algorithm walks NetworkX successors and sorts them during its power iterations.
These call profiles include profiler overhead. The exclusive stage timings and
uninstrumented baselines give the latency comparison.

## Cache decision

The eight-entry projection prototype hit across distinct seeds. On the
24-distinct-key stream it saved 38.82 ms of P95, or 7.3%. At capacity it retained
21.94 MiB, above the 16 MiB criterion. One projection retained 3.05 MiB. The
measured prototype falls short of the distinct-request gain and capacity
criteria. Sharing a projection within one pack or a narrower snapshot-scoped
projection remains a separate candidate to measure.

The rank cache had zero hits on distinct keys and exact expected hit counts on
the two repeat streams. With 12 repeats it saved 64.48 ms P95. With 21 repeats
the median went from 426.81 to 36.05 ms and P95 went from 462.64 to 448.70 ms.
The observed P95 came from a cache miss. At 32 entries the prototype retained
11.05 MiB. Its median cold overhead was 4.3%, within the 10% threshold. These
streams vary in both repeat rate and choice of seeds. Compare each cache to the
uncached run with the same requests. A representative repeat-rate measurement
is still needed for a product rank cache.

Keep the cache decision open in R1-C131. The `both` profile puts PageRank
iteration and its neighbor traversal ahead of the projection cache as a
performance investigation. Any reuse of rank data in the server needs to keep
the tested snapshot and mutable-result boundaries.

## Repeat telemetry

One Codemap conversation log and one recent Claude Code log for the Codemap
workspace had zero directly recorded `pack` calls. The Codex log had 496 wrapper
calls. Their nested call identities and arguments were outside the direct-event
check. There is no representative repeat-rate estimate from these sources.
Only aggregate counts were retained. The test streams below measure behavior
at specified repeat rates.

## Predictions and acceptance

| Criterion | Evidence |
| --- | --- |
| E1 | Three pinned source revisions and one published wheel digest. All nine cases have 20 samples each for direct rank, direct pack and MCP pack. The MCP call checked matching structured and text data, currency and direct-result equality. |
| E2 | 54 exclusive attribution records and nine separate function profiles. H1 confirmed on pytest/deep. Seeded pack built three projections per request. |
| E3 | 216 controlled stream requests, 36 cold requests and five allocation measurements. H2 holds in the tested streams. Both prototypes passed exact output parity, key-variant, mutable-result and fresh-snapshot checks. The cold measurements start with an empty cache and include reuse inside the first pack. |
| E4 | Both prototype decisions are above with the telemetry scope and limits. The main run exited successfully and recorded all planned groups. |

The two-CPU slot was held from 14:07:26 to 14:13:32 local time. The sampled
10-second CPU pressure was at most 0.08%, with sampled I/O and memory pressure
at 0.00%. The test stream order was fixed, so small differences remain sensitive
to run-order and shared-host variation. Retention figures are traced Python
allocations after collection, measured separately from latency.

## Reproduce

Inside an agreed two-CPU slot on Linux, create an isolated work directory and run
the following commands from the repository root. `R1C130_REPOS` can point to
existing clones of the pinned public repositories. `R1C131_RUN` sets a new output
directory name relative to the work directory for an independent repeat.

```bash
work=$(mktemp -d "$HOME/jobs/codemap/r1c131.XXXXXX")
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
bash research/bench/r1c131/prepare.sh "$work"
"$work/.venv/bin/python" research/bench/r1c131/profile_rank_pack.py "$work"
python3 research/bench/r1c131/summarize.py "$work/run/samples.jsonl"
```

[Raw observations](results/samples.jsonl.gz) contain 882 JSONL records, including
the environment, per-call wall and direct CPU times, and the top cumulative and
self-time functions for every profiled pack. Render them with `summarize.py`.

## Detailed measurements

Python 3.12.16, Linux 7.0.0-43-generic, affinity `0,1`. codmap 0.0.49, griffe 2.4.1, jedi 0.20.1, mcp 2.3.0, networkx 3.7.

| Project | Tier | Nodes | Edges | Graph MiB | Build wall s |
| --- | --- | --- | --- | --- | --- |
| more-itertools | fast | 362 | 838 | 0.55 | 1.02 |
| rich | deep | 2160 | 8792 | 3.17 | 35.82 |
| pytest | deep | 7490 | 20010 | 8.38 | 63.18 |

### Baseline and stage attribution

Baseline time is median / nearest-rank P95 in ms, n=20. The MCP/direct pack difference is the difference of medians from separate processes.

| Project | Route | Direct rank | Direct pack | MCP pack | MCP − direct P50 | Reply bytes P50 |
| --- | --- | --- | --- | --- | --- | --- |
| more-itertools | global | 2.52 / 2.78 | 3.29 / 4.22 | 5.29 / 6.17 | 2.00 | 35,793 |
| more-itertools | uses | 0.82 / 0.89 | 1.70 / 1.91 | 2.93 / 3.10 | 1.22 | 2,671 |
| more-itertools | both | 21.31 / 21.83 | 22.14 / 22.65 | 24.44 / 27.14 | 2.31 | 4,185 |
| rich | global | 59.66 / 70.11 | 61.20 / 63.55 | 65.33 / 71.69 | 4.13 | 39,529 |
| rich | uses | 47.43 / 51.52 | 56.68 / 65.65 | 59.25 / 63.42 | 2.57 | 33,615 |
| rich | both | 75.13 / 86.50 | 85.06 / 95.56 | 87.76 / 108.52 | 2.71 | 37,471 |
| pytest | global | 258.28 / 273.73 | 265.72 / 283.30 | 268.56 / 296.79 | 2.84 | 43,785 |
| pytest | uses | 218.23 / 236.68 | 258.08 / 296.31 | 256.36 / 322.42 | -1.73 | 15,323 |
| pytest | both | 400.54 / 425.61 | 438.66 / 451.16 | 426.86 / 494.27 | -11.81 | 17,764 |

Exclusive instrumented stages in ms, n=3. Projection count is per call. `pack_other` includes sorting, token estimates and selection. `rank_other` includes reversal and score finalization when applicable.

| Project | Route | Case | Projections | Projection + PageRank | P50 / max | Stage medians |
| --- | --- | --- | --- | --- | --- | --- |
| more-itertools | global | rank | 1 | 95.0% | 2.55 / 2.57 | pagerank 2.02, projection 0.37, rank_other 0.13 |
| more-itertools | global | pack | 1 | 70.3% | 3.39 / 3.40 | pagerank 2.01, item_render 0.46, pack_other 0.38, projection 0.36, rank_other 0.12, coverage 0.04 |
| more-itertools | uses | rank | 1 | 83.9% | 0.85 / 0.88 | projection 0.38, pagerank 0.34, rank_other 0.13, rank_seed_expansion 0.00 |
| more-itertools | uses | pack | 3 | 79.7% | 1.78 / 1.96 | projection 1.05, pagerank 0.35, rank_other 0.13, pack_other 0.09, coverage 0.04, seed_resolution 0.04, reachability 0.04, item_render 0.00, rank_seed_expansion 0.00 |
| more-itertools | both | rank | 1 | 96.5% | 21.47 / 21.56 | pagerank 20.31, rank_other 0.74, projection 0.38, rank_seed_expansion 0.00 |
| more-itertools | both | pack | 3 | 95.4% | 22.21 / 22.38 | pagerank 20.18, projection 1.03, rank_other 0.73, pack_other 0.12, reachability 0.05, coverage 0.04, seed_resolution 0.04, item_render 0.01, rank_seed_expansion 0.00 |
| rich | global | rank | 1 | 99.1% | 65.06 / 69.59 | pagerank 59.73, projection 4.77, rank_other 0.56 |
| rich | global | pack | 1 | 94.6% | 62.78 / 62.92 | pagerank 55.53, projection 3.86, pack_other 1.47, item_render 1.03, rank_other 0.56, coverage 0.26 |
| rich | uses | rank | 1 | 98.8% | 48.43 / 51.01 | pagerank 43.73, projection 4.27, rank_other 0.61, rank_seed_expansion 0.00 |
| rich | uses | pack | 3 | 96.5% | 58.36 / 69.79 | pagerank 43.31, projection 12.87, rank_other 0.58, pack_other 0.53, reachability 0.28, coverage 0.25, seed_resolution 0.22, item_render 0.13, rank_seed_expansion 0.00 |
| rich | both | rank | 1 | 90.7% | 74.97 / 77.11 | pagerank 63.91, rank_other 6.98, projection 4.09, rank_seed_expansion 0.00 |
| rich | both | pack | 3 | 89.8% | 85.23 / 86.40 | pagerank 64.58, projection 11.85, rank_other 6.82, pack_other 0.74, reachability 0.38, coverage 0.26, seed_resolution 0.23, item_render 0.23, rank_seed_expansion 0.00 |
| pytest | global | rank | 1 | 98.8% | 252.86 / 268.99 | pagerank 234.97, projection 15.61, rank_other 3.04 |
| pytest | global | pack | 1 | 93.3% | 276.64 / 288.77 | pagerank 235.90, projection 15.72, pack_other 9.62, item_render 4.40, rank_other 3.84, coverage 0.62 |
| pytest | uses | rank | 1 | 98.5% | 222.74 / 229.45 | pagerank 198.08, projection 16.53, rank_other 3.32, rank_seed_expansion 0.00 |
| pytest | uses | pack | 3 | 96.7% | 256.91 / 284.08 | pagerank 204.95, projection 43.79, rank_other 3.39, pack_other 2.30, reachability 1.00, seed_resolution 0.94, coverage 0.65, item_render 0.04, rank_seed_expansion 0.00 |
| pytest | both | rank | 1 | 92.5% | 404.60 / 417.99 | pagerank 343.33, rank_other 31.34, projection 22.78, rank_seed_expansion 0.00 |
| pytest | both | pack | 3 | 91.5% | 440.62 / 462.40 | pagerank 349.78, projection 44.70, rank_other 30.55, pack_other 3.83, reachability 1.00, seed_resolution 0.96, coverage 0.68, item_render 0.05, rank_seed_expansion 0.00 |

| Project | Route | cProfile total ms | Top self time functions, ms |
| --- | --- | --- | --- |
| more-itertools | global | 7.2 | _pagerank 1.8, <built-in method builtins.sorted> 0.7, <genexpr> 0.6, successors 0.6 |
| more-itertools | uses | 3.8 | add_node 0.9, _rank_graph 0.5, add_edge 0.4, _pagerank 0.3 |
| more-itertools | both | 52.5 | _pagerank 19.1, <built-in method builtins.sorted> 6.9, successors 5.8, <genexpr> 5.8 |
| rich | global | 115.1 | _pagerank 46.0, <built-in method builtins.sorted> 17.5, successors 11.2, <genexpr> 10.6 |
| rich | uses | 110.3 | _pagerank 35.6, <built-in method builtins.sorted> 13.2, add_edge 10.1, successors 8.6 |
| rich | both | 167.2 | _pagerank 50.6, add_edge 22.7, <built-in method builtins.sorted> 20.9, successors 10.3 |
| pytest | global | 519.7 | _pagerank 200.8, <built-in method builtins.sorted> 66.6, successors 55.7, <genexpr> 54.6 |
| pytest | uses | 511.1 | _pagerank 171.7, <built-in method builtins.sorted> 57.5, successors 47.9, <genexpr> 47.7 |
| pytest | both | 823.4 | _pagerank 285.1, <built-in method builtins.sorted> 98.3, <genexpr> 70.4, successors 68.3 |

### Isolated cache experiments on pytest/deep

| Distinct rank keys | Repeat requests | Strategy | Lookup hits | Entries | P50 / P95 ms | P95 saved ms (%) |
| --- | --- | --- | --- | --- | --- | --- |
| 24 | 0 | uncached | — | 0 | 400.31 / 535.35 | 0.00 (0.0%) |
| 24 | 0 | projection | 71/72 | 1 | 352.50 / 496.53 | 38.82 (7.3%) |
| 24 | 0 | rank | 0/24 | 24 | 392.69 / 547.81 | -12.46 (-2.3%) |
| 12 | 12 | uncached | — | 0 | 393.39 / 535.76 | 0.00 (0.0%) |
| 12 | 12 | projection | 71/72 | 1 | 349.96 / 485.37 | 50.38 (9.4%) |
| 12 | 12 | rank | 12/24 | 12 | 59.84 / 471.28 | 64.48 (12.0%) |
| 3 | 21 | uncached | — | 0 | 426.81 / 462.64 | 0.00 (0.0%) |
| 3 | 21 | projection | 71/72 | 1 | 378.77 / 395.79 | 66.85 (14.4%) |
| 3 | 21 | rank | 21/24 | 3 | 36.05 / 448.70 | 13.94 (3.0%) |

| Cold strategy | P50 / max ms | Median overhead |
| --- | --- | --- |
| uncached | 399.92 / 542.69 | +0.0% |
| projection | 382.53 / 510.66 | -4.3% |
| rank | 417.14 / 534.33 | +4.3% |

| Strategy | Entries | Retained MiB | Peak traced MiB |
| --- | --- | --- | --- |
| projection | 1 | 3.05 | 3.05 |
| projection | 8 | 21.94 | 21.95 |
| rank | 1 | 0.35 | 6.30 |
| rank | 8 | 2.77 | 8.48 |
| rank | 32 | 11.05 | 16.66 |

Exact output, argument variants, caller mutation and new-snapshot controls passed.

## R1-C150 and R1-C151 results

Two Codex `pde` agents on `k99` implemented the candidates independently from
commit `c5a0198`. On `m99`, the comparison used the original pytest/deep graph
from this study and the released 0.0.49 Python environment. Candidate servers
loaded source overrides from independent worktrees. The client rotated server
order and issued one request at a time on the same two-CPU affinity. Each row
has 32 measurements per variant. The seeded routes used 32 distinct IDs. Global
uses the same arguments each time and serves as a control.

| Request | Baseline P50 / P95 ms | PageRank P50 / P95 ms | Projection P50 / P95 ms | Combined P50 / P95 ms |
| --- | --- | --- | --- | --- |
| seeded `both` | 484.21 / 667.49 | 358.24 / 437.43 | 448.23 / 608.71 | 329.40 / 416.90 |
| seeded `uses` | 251.56 / 582.83 | 185.22 / 411.28 | 204.36 / 540.40 | 162.25 / 377.76 |
| global | 278.46 / 327.92 | 192.04 / 263.33 | 276.88 / 331.55 | 188.78 / 243.40 |

On the primary `both` workload, PageRank preparation saved 230.06 ms of P95
(34.5%) and projection reuse saved 58.78 ms (8.8%). Both met the 50 ms absolute
criterion. The combined variant saved 250.59 ms (37.5%). Projection reuse won
about 20.5 ms in P95 after PageRank preparation on this run. The global
projection-only control varied by +3.63 ms at P95. Each figure is from one
32-request series on a shared host. The 58.78 ms result clears the threshold by
8.78 ms, so its margin is smaller than that of the PageRank change.

Direct comparisons produced byte-identical serialized ranks and pack results
for all four variants. The cases included distinct directions, root restrictions,
ambiguous, duplicate, unresolved and file seeds, and a zero budget. The seeded
projection count dropped from three to one on successive calls. Each of the
384 MCP comparisons matched its corresponding pack payload. Warm resident RSS
was 125.0 MiB for the baseline and PageRank variants, 127.0 MiB for projection
reuse and 127.1 MiB for the combination.

The combined candidate passed the full Codemap suite on `m99` with Python
3.12.16 and the pinned bquant fixture. There were 1524 passes and three skips
for the optional `ccc`, `readtags` and `scip` executables. The slot ran from
14:27:24 to 14:34:46 local time and was released after exit status 0.

[Comparison harness](compare_pack.py) and [398 raw records](results/followup_samples.jsonl.gz).
The harness takes the work directory containing `page`, `projection` and
`combined` source worktrees, followed by the pinned pytest checkout and the
original graph path. Use the published 0.0.49 virtual environment and the
same affinity for replay. The raw data includes the graph and parity digests.
