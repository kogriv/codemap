# R1-C130 — scalability results for Codemap 0.0.48

Measured on 2026-11-24 using the [preregistered protocol and acceptance criteria](DESIGN.md).
The [gap record](../../../gaps/scalability_2026-11-24.md) tracks the observed product divergence.

## Environment and measurement boundaries

The measured release is the published `codmap 0.0.48` wheel, confirmed against its
PyPI SHA-256. The three source revisions are pinned in the design. The workload
analyzes source statically, including the designated consumer roots. Full and
incremental builds start fresh processes and share the host filesystem cache.
Deep uses one Jedi sample per build.

The measurement host has two Intel Xeon E5-2696 v3 sockets, 72 logical CPUs and
121 GiB available to the OS. Builds and the harness ran sequentially on logical
CPUs 0 and 1, on separate physical cores of NUMA node 0, within a shared two-CPU
slot. The ext4 filesystem and the rest of the host were shared. GNU `time`
provides build and load CPU, peak RSS and filesystem I/O counters. MCP timing
ends on receipt of the complete JSON-RPC reply line. Wire size includes both
structured and text output. The current/peak RSS figures for the warm server
come from its process counters.

For idle `watch`, CPU counters include reaped children. Logical and physical I/O
are sampled from `/proc`. Each save-to-answer figure is a single observation on
the actual watcher pair with currency forced fresh for each verification probe.

## What the measurements show

### Rebuild and artifact behavior

The small package fell back to a full rebuild on every one-file edit in both
tiers. The edit affected all three modules. In deep, the median was 9.56 s for
the full command and 10.22 s through the incremental command. The larger cases
used actual incremental rebuilds. On rich/deep, 31 affected modules gave a
25.26 s median beside 32.83 s full. On pytest/deep, five affected core modules
with all consumer scans gave 19.48 s beside 61.94 s full. These are 1.30× and
3.18× gains for these specific edits.

The no-op controls recomputed zero core modules. In pytest/deep, the 5.23 s
median includes consumer scans and writing a graph of roughly 8.4 MiB. The CLI touched
artifact metadata even on byte-identical outputs. The idle source watcher
checks scope before building, so unchanged inputs left the artifacts in place.

### MCP work and transport

On rich/deep, `impact` with limits 0 and 40 and then `full=true` had P95
3.80, 4.08 and 5.26 ms. Median response sizes were 3.3, 25.7 and 63.8 kB.
Compact defaults already control transport volume. A future compute budget
would need checks inside traversal and flow calculation. This series supports
keeping the compact defaults and measuring larger fan-out cases before choosing
a hard ceiling or a pagination policy.

On pytest/deep, repeated global `pack` reached P95 279 ms. The seeded case
reached 488 ms despite a smaller reply. Profile ranking and context assembly in
R1-C131 and measure repeated-query rates on a representative workload before
choosing a cache scope. The measured repeat rate in this study was set by the
harness.

Forced-fresh fast `stats` P95 rose from 21.75 ms on the small package to 46.56 ms
on rich and 104.23 ms on the multi-root fixture. With the default TTL those
P95s were 2.57, 8.07 and 18.23 ms. Keep the default currency reuse for ordinary
queries and force a fresh comparison when the operation requires it.

### Watch latency and idle cost

The source watcher consumed 1.20%, 2.20% and 3.87% of one core across the three
trees. The artifact watcher accrued zero CPU ticks in all three 15 s windows.
The input cache was warm and the idle process counters recorded no physical I/O.
The largest scope still caused 49 MB of logical reads by the source watcher and
its children. The observed save-to-current-answer times were 4.46, 7.40 and
11.20 s, respectively. The watcher logs place the rebuild inside each interval.
These are single save observations. A distribution for the save-to-answer path
would require repeated edits and a workload with concurrent calls.

### Correctness finding

The fast parity control exposed a product regression. Two full baselines agreed
on each affected project. After an edit/revert, rich lost one core call and
pytest lost five. All six missing edges use `annotated-field`. A four-module
synthetic package reproduced the loss after editing an unrelated module. A full
build restored the edge. The same released version was used for all performance
samples. [R1-C149 and synthetic reproduction](https://github.com/kogriv/codemap/issues/26).

## Predictions and acceptance

| Prediction | Observed |
| --- | --- |
| H1 | Confirmed. Deep full-build wall and CPU were higher in all three cases. The 7.98–8.38 MiB multi-root graph had the highest load-plus-index time and resident RSS. |
| H2 | Partial. Rich and pytest gained 1.30× and 3.18×, respectively, on the deep one-file edit. More-itertools fell back to full in both tiers. Consumer scans contribute to the costs on pytest, as seen in its 5.2–5.4 s no-op medians. |
| H3 | Confirmed. Full `impact` grew the response in all three trees. Compact limits reduced payload more clearly than latency. Forced-fresh `stats` costs increased by tree. |
| H4 | Confirmed for the observed windows. On the multi-root fixture the source watcher used 3.87% of one core, and the artifact watcher recorded zero ticks. |
| H5 | Confirmed. Global `pack` P95 reached 272–279 ms on pytest. This crosses the registered profiling threshold for R1-C131. |

| Criterion | Evidence |
| --- | --- |
| E1 | Six complete full-build groups, 18 samples. Exact source commits, runtime, dependencies, host and wheel digest recorded. |
| E2 | 120 one-file builds and 30 no-ops. All edits reflected the marker and restored source scope as expected. Two fast parity controls exposed R1-C149. Both affected cohorts have complete performance samples and explicit false parity flags on all ten reverts apiece. |
| E3 | 18 MCP initializations, 18 load/index samples and 900 warm MCP calls, including 60 forced-fresh `stats`. Protocol, symbol, structured content and currency checks passed. |
| E4 | Six idle process observations. All artifact timestamps stayed stable at idle. Each of the three single-save runs reached a current MCP answer. |
| E5 | The detailed tables, raw observations, deviations and replay instructions are linked below. R1-C149 stays open as a product fix. |

The recorded one-minute host load ranged from 0.90 to 4.04. The highest sampled
10-second `some` pressure for CPU and I/O was 0.01%, and memory pressure was
0.00%. The runs shared the host and retained its filesystem cache.

## Raw data and replay

- [Final observations](results/samples.jsonl.gz) contain 1,133 JSONL records.
  Attempt `run-v3` supplied the small-package fast series and all deep series.
  Attempt `run-v4` supplied the rich and pytest fast series. Both used the same
  published wheel, dependency versions, CPU affinity and measurement protocol.
- [Pilot and incomplete series](results/attempts.jsonl.gz) contain 297 records.
  The first pilot stopped at the mtime assertion on both tiers, the second pilot
  passed, and the first main attempt stopped for the polling-timer correction.
  The corrected run then recorded two fast parity failures before the replay.
  No final sample reached a timeout. See the [deviations](DESIGN.md#pilot-deviation-2026-11-24).
- [Setup](prepare.sh), [measurement](measure.py) and [table generation](summarize.py)
  can be used to replay the study. Render these tables from the repository root with
  `python3 research/bench/r1c130/summarize.py research/bench/r1c130/results/samples.jsonl.gz`.

## Detailed measurements

Python 3.12.16, Linux 7.0.0-43-generic, ext4, CPU affinity `0,1`. codmap 0.0.48, griffe 2.4.1, jedi 0.20.1, mcp 2.3.0, networkx 3.7.

### Scope and graph size

| Project | Tier | Files | Lines | Input MiB | Nodes | Edges | Graph MiB | Sidecar KiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| more-itertools | fast | 6 | 8526 | 0.25 | 362 | 838 | 0.55 | 3.5 |
| more-itertools | deep | 6 | 8526 | 0.25 | 362 | 843 | 0.56 | 3.5 |
| rich | fast | 100 | 38515 | 1.16 | 2160 | 7900 | 2.96 | 29.1 |
| rich | deep | 100 | 38515 | 1.16 | 2160 | 8792 | 3.17 | 29.1 |
| pytest | fast | 239 | 103340 | 3.28 | 7490 | 18547 | 7.98 | 73.0 |
| pytest | deep | 239 | 103340 | 3.28 | 7490 | 20010 | 8.38 | 73.0 |

### Build and startup

Times in ms. Cells show median / P95 for n≥20, median / maximum otherwise. Full samples are listed in run order. CPU and filesystem I/O counters are medians, RSS is maximum KiB converted to MiB.

**more-itertools, fast.** Full runs (ms): 996.98, 988.92, 1,023.58.

| Phase | n | Wall ms | CPU s | Peak MiB | FS in/out | Modes |
| --- | --- | --- | --- | --- | --- | --- |
| Full | 3 | 996.98 / 1,023.58 | 0.99 | 56.8 | 0/1160 | — |
| Edited | 20 | 1,036.01 / 1,082.14 | 1.02 | 59.0 | 0/1176 | full×20 |
| Unchanged | 5 | 340.49 / 356.98 | 0.33 | 47.8 | 0/1168 | unchanged×5 |
| Load + index | 3 | 191.97 / 217.71 | 0.18 | 39.0 | 0/8 | — |
| MCP initialize | 3 | 934.61 / 946.53 | 0.93 | 91.3 | — | — |

Internal graph load + index median / max: 11.59 / 12.11 ms.

No-op control: 4/5 graph payloads byte-identical, artifact metadata touched on 5/5 calls.

Reverted fast core calls matched the full graph in 10/10 samples.

**more-itertools, deep.** Full runs (ms): 9,670.06, 9,501.00, 9,559.73.

| Phase | n | Wall ms | CPU s | Peak MiB | FS in/out | Modes |
| --- | --- | --- | --- | --- | --- | --- |
| Full | 3 | 9,559.73 / 9,670.06 | 9.55 | 189.6 | 0/1168 | — |
| Edited | 20 | 10,219.05 / 10,837.64 | 10.21 | 191.0 | 0/1844 | full×20 |
| Unchanged | 5 | 363.71 / 394.16 | 0.35 | 49.2 | 0/1168 | unchanged×5 |
| Load + index | 3 | 208.65 / 213.69 | 0.20 | 38.9 | 0/8 | — |
| MCP initialize | 3 | 976.08 / 987.43 | 0.96 | 91.3 | — | — |

Internal graph load + index median / max: 12.48 / 13.90 ms.

No-op control: 4/5 graph payloads byte-identical, artifact metadata touched on 5/5 calls.

**rich, fast.** Full runs (ms): 5,061.40, 5,025.54, 4,988.68.

| Phase | n | Wall ms | CPU s | Peak MiB | FS in/out | Modes |
| --- | --- | --- | --- | --- | --- | --- |
| Full | 3 | 5,025.54 / 5,061.40 | 5.01 | 90.9 | 0/6136 | — |
| Edited | 20 | 3,973.17 / 4,004.65 | 3.95 | 91.6 | 0/6324 | incremental×20 |
| Unchanged | 5 | 721.60 / 724.41 | 0.70 | 76.7 | 0/6144 | unchanged×5 |
| Load + index | 3 | 259.74 / 263.19 | 0.25 | 50.8 | 0/8 | — |
| MCP initialize | 3 | 958.07 / 980.89 | 0.94 | 99.4 | — | — |

Internal graph load + index median / max: 77.02 / 77.46 ms.

No-op control: 5/5 graph payloads byte-identical, artifact metadata touched on 5/5 calls.

Reverted fast core calls matched the full graph in 0/10 samples.

**rich, deep.** Full runs (ms): 35,082.20, 32,735.68, 32,834.30.

| Phase | n | Wall ms | CPU s | Peak MiB | FS in/out | Modes |
| --- | --- | --- | --- | --- | --- | --- |
| Full | 3 | 32,834.30 / 35,082.20 | 32.82 | 273.9 | 0/6576 | — |
| Edited | 20 | 25,256.35 / 27,429.93 | 25.26 | 260.8 | 0/7280 | incremental×20 |
| Unchanged | 5 | 730.76 / 738.18 | 0.71 | 79.4 | 0/6576 | unchanged×5 |
| Load + index | 3 | 273.63 / 276.92 | 0.26 | 52.4 | 0/8 | — |
| MCP initialize | 3 | 969.42 / 992.18 | 0.96 | 100.3 | — | — |

Internal graph load + index median / max: 82.65 / 82.67 ms.

No-op control: 5/5 graph payloads byte-identical, artifact metadata touched on 5/5 calls.

**pytest, fast.** Full runs (ms): 10,488.21, 10,373.66, 10,406.60.

| Phase | n | Wall ms | CPU s | Peak MiB | FS in/out | Modes |
| --- | --- | --- | --- | --- | --- | --- |
| Full | 3 | 10,406.60 / 10,488.21 | 10.37 | 139.8 | 0/16504 | — |
| Edited | 20 | 8,077.51 / 8,186.55 | 8.04 | 141.7 | 0/16568 | incremental×20 |
| Unchanged | 5 | 5,375.19 / 5,657.27 | 5.33 | 135.2 | 0/16504 | unchanged×5 |
| Load + index | 3 | 453.37 / 478.84 | 0.44 | 74.9 | 0/8 | — |
| MCP initialize | 3 | 1,090.88 / 1,132.38 | 1.08 | 113.2 | — | — |

Internal graph load + index median / max: 237.11 / 242.33 ms.

No-op control: 5/5 graph payloads byte-identical, artifact metadata touched on 5/5 calls.

Reverted fast core calls matched the full graph in 0/10 samples.

**pytest, deep.** Full runs (ms): 62,964.38, 61,943.05, 61,853.83.

| Phase | n | Wall ms | CPU s | Peak MiB | FS in/out | Modes |
| --- | --- | --- | --- | --- | --- | --- |
| Full | 3 | 61,943.05 / 62,964.38 | 61.90 | 369.2 | 0/17328 | — |
| Edited | 20 | 19,477.99 / 19,569.59 | 19.43 | 278.6 | 0/17568 | incremental×20 |
| Unchanged | 5 | 5,228.42 / 5,246.22 | 5.19 | 139.6 | 0/17320 | unchanged×5 |
| Load + index | 3 | 426.47 / 432.52 | 0.41 | 76.8 | 0/8 | — |
| MCP initialize | 3 | 1,116.90 / 1,121.27 | 1.10 | 114.8 | — | — |

Internal graph load + index median / max: 225.71 / 237.01 ms.

No-op control: 5/5 graph payloads byte-identical, artifact metadata touched on 5/5 calls.

### Warm MCP STDIO

Each cell is median / P95 wall time (ms). Wire size is median / maximum in bytes, including both output representations.

- more-itertools/fast warm resident RSS 92.7 MiB, peak (92.7 MiB).
- more-itertools/deep warm resident RSS 92.8 MiB, peak (92.8 MiB).
- rich/fast warm resident RSS 101.8 MiB, peak (101.8 MiB).
- rich/deep warm resident RSS 103.2 MiB, peak (103.2 MiB).
- pytest/fast warm resident RSS 121.5 MiB, peak (121.5 MiB).
- pytest/deep warm resident RSS 122.5 MiB, peak (122.8 MiB).

| Project | Tier | Operation | n | Wall ms | Wire bytes |
| --- | --- | --- | --- | --- | --- |
| more-itertools | fast | stats | 20 | 2.41 / 2.57 | 4,008 / 4,008 |
| more-itertools | fast | search | 20 | 0.98 / 1.10 | 1,366 / 1,366 |
| more-itertools | fast | impact0 | 20 | 1.43 / 1.64 | 2,589 / 2,589 |
| more-itertools | fast | impact40 | 20 | 1.43 / 1.77 | 3,891 / 3,891 |
| more-itertools | fast | impact_full | 20 | 1.60 / 1.76 | 7,688 / 7,689 |
| more-itertools | fast | pack_global | 20 | 5.22 / 5.84 | 35,794 / 35,794 |
| more-itertools | fast | pack_seed | 20 | 25.84 / 28.71 | 4,186 / 4,186 |
| more-itertools | fast | stats_forced | 20 | 20.75 / 21.75 | 4,008 / 4,008 |
| more-itertools | deep | stats | 20 | 2.65 / 2.87 | 6,811 / 6,811 |
| more-itertools | deep | search | 20 | 1.01 / 1.17 | 1,366 / 1,366 |
| more-itertools | deep | impact0 | 20 | 1.58 / 1.75 | 3,262 / 3,262 |
| more-itertools | deep | impact40 | 20 | 1.71 / 1.84 | 4,564 / 4,564 |
| more-itertools | deep | impact_full | 20 | 1.69 / 1.78 | 8,361 / 8,362 |
| more-itertools | deep | pack_global | 20 | 6.07 / 6.50 | 35,993 / 35,993 |
| more-itertools | deep | pack_seed | 20 | 26.56 / 28.10 | 4,186 / 4,186 |
| rich | fast | stats | 20 | 7.67 / 8.07 | 4,551 / 4,551 |
| rich | fast | search | 20 | 1.33 / 1.49 | 2,726 / 2,726 |
| rich | fast | impact0 | 20 | 2.86 / 2.96 | 2,573 / 2,573 |
| rich | fast | impact40 | 20 | 2.98 / 3.07 | 6,839 / 6,839 |
| rich | fast | impact_full | 20 | 3.24 / 3.46 | 12,211 / 12,212 |
| rich | fast | pack_global | 20 | 52.55 / 57.18 | 39,858 / 39,858 |
| rich | fast | pack_seed | 20 | 83.37 / 118.58 | 32,590 / 32,590 |
| rich | fast | stats_forced | 20 | 41.62 / 46.56 | 4,551 / 4,551 |
| rich | deep | stats | 20 | 8.57 / 8.88 | 7,305 / 7,305 |
| rich | deep | search | 20 | 1.53 / 1.77 | 2,726 / 2,726 |
| rich | deep | impact0 | 20 | 3.63 / 3.80 | 3,326 / 3,326 |
| rich | deep | impact40 | 20 | 3.83 / 4.08 | 25,730 / 25,730 |
| rich | deep | impact_full | 20 | 5.08 / 5.26 | 63,774 / 63,775 |
| rich | deep | pack_global | 20 | 63.60 / 66.47 | 39,530 / 39,530 |
| rich | deep | pack_seed | 20 | 86.52 / 102.03 | 37,472 / 37,472 |
| pytest | fast | stats | 20 | 17.16 / 18.23 | 5,463 / 5,463 |
| pytest | fast | search | 20 | 2.28 / 2.65 | 5,000 / 5,000 |
| pytest | fast | impact0 | 20 | 6.75 / 7.58 | 2,693 / 2,693 |
| pytest | fast | impact40 | 20 | 6.31 / 6.46 | 3,413 / 3,413 |
| pytest | fast | impact_full | 20 | 7.37 / 7.66 | 6,977 / 6,978 |
| pytest | fast | pack_global | 20 | 256.07 / 271.59 | 44,521 / 44,521 |
| pytest | fast | pack_seed | 20 | 427.73 / 484.04 | 10,251 / 10,253 |
| pytest | fast | stats_forced | 20 | 81.12 / 104.23 | 5,465 / 5,465 |
| pytest | deep | stats | 20 | 17.00 / 17.86 | 8,362 / 8,362 |
| pytest | deep | search | 20 | 2.07 / 2.27 | 5,000 / 5,000 |
| pytest | deep | impact0 | 20 | 6.60 / 6.83 | 3,625 / 3,625 |
| pytest | deep | impact40 | 20 | 6.76 / 6.96 | 6,082 / 6,082 |
| pytest | deep | impact_full | 20 | 7.56 / 7.70 | 10,407 / 10,408 |
| pytest | deep | pack_global | 20 | 268.74 / 278.94 | 43,786 / 43,786 |
| pytest | deep | pack_seed | 20 | 438.37 / 487.54 | 17,757 / 17,759 |

### Watch

- more-itertools: save to current MCP answer 4.46 s (18 probes).
- rich: save to current MCP answer 7.40 s (28 probes).
- pytest: save to current MCP answer 11.20 s (39 probes).

| Project | Watcher | Window s | CPU % of one core | RSS MiB | Peak MiB | Logical bytes r/w | Physical bytes r/w |
| --- | --- | --- | --- | --- | --- | --- | --- |
| more-itertools | source | 15.00 | 1.20 | 41.9 | 41.9 | 4,465,650/9,495 | 0/0 |
| more-itertools | artifact | 15.00 | 0.00 | 91.8 | 91.8 | 0/0 | 0/0 |
| rich | source | 15.00 | 2.20 | 42.6 | 42.6 | 18,998,715/108,405 | 0/0 |
| rich | artifact | 15.00 | 0.00 | 99.9 | 99.9 | 0/0 | 0/0 |
| pytest | source | 15.00 | 3.87 | 43.0 | 43.6 | 49,063,042/336,980 | 0/0 |
| pytest | artifact | 15.00 | 0.00 | 114.2 | 114.2 | 0/0 | 0/0 |

Recorded failures: 0.
