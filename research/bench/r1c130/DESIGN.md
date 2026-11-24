# R1-C130 — Codemap scalability benchmark

**Status:** preregistered and measured on 2026-11-24. [Results and reconciliation](RESULTS.md).
**Gap:** [scalability](../../../gaps/scalability_2026-11-24.md). **Backlog:** R1-C130.

## Inputs

Use the published `codmap[mcp]==0.0.48` on Python 3.12. Record the resolved runtime
dependencies, wheel digest, local filesystem, CPU affinity, and release build flags.
Analyze local clones of these public revisions. Do not import or run the target
packages or their test suites.

| Class | Repository and exact commit | Core | Consumer roots | Edited file | MCP symbol |
| --- | --- | --- | --- | --- | --- |
| Small package | more-itertools `4aeb4338ae1407d8da9723e86da99efeb446f719` (v11.2.1) | `more_itertools` | package only | `more_itertools/recipes.py` | `more_itertools.recipes.flatten` |
| Large library | rich `6ac483cbea39cab124dfd3483bba70ffafb71050` (v15.0.0) | `rich` | package only | `rich/style.py` | `rich.console.Console.print` |
| Multi-package repository | pytest `3d10b5148e03eb82b3ee29181dbdc73cf82699e2` (9.0.2) | `src/_pytest` | `src/pytest`, `testing`, `scripts`, full consumer mode | `src/_pytest/timing.py` | `_pytest.fixtures.FixtureRequest.getfixturevalue` |

Use real Python trees and an added, isolated function with a constant return for
one reversible source edit. Apply the same edit for both tiers and confirm that the
graph follows the change. The consumer-root scenario includes cross-root scan and
index costs. Project size, shape and scope differ across the three rows, so this
is an observational comparison of workflows with no fitted complexity exponent.

## Protocol

1. **Build.** Three fresh-process full builds per project/tier, each with a new
   output path. Use one Jedi sample per deep build. The first pass warms filesystem
   caches and remains a labeled sample. No OS cache flush. Record external wall
   time, GNU `time` user/system CPU, peak RSS and filesystem input/output counts.
   Record graph/sidecar bytes, nodes, edges, input file/byte counts and the reported
   tier. Compute P50 and show all three full samples. A three-sample P95 would
   just be the largest observation, so report that observation as a maximum.
2. **Incremental.** Per project/tier, take 20 timed `build --incremental` samples
   with the edit toggled between trials, and 5 separate no-change samples. Reuse the
   last full graph at its original output path. Time only the command, excluding
   the file edit and validation. Log Codemap's mode, reason and recompute count.
   On fast, compare the core call edges for the reverted snapshot to the baseline
   and check that the symbol follows each edit in both tiers. Incremental wall
   times include the work on all applicable roots.
3. **Load and MCP.** Three fresh MCP server processes per project/tier. Measure
   spawn through a successful MCP `initialize` reply for each. Separately time
   three loads of the graph and index construction via a short fresh Python
   process per sample (include imports only in the spawn-to-ready figure).
   Keep one of the servers warm. Use one client, one request at a time, actual
   MCP STDIO, normal schemas and the default 10 s currency TTL. After one named
   warmup per operation, collect 20 samples per request for `stats`, `search`,
   `impact` with `limit=0`, default `limit=40` and `full=true`, and `pack` with
   and without a seed. Use the table's symbol for impact and seeded pack. Run
   repeats per operation contiguously. Record monotonic latency and bytes on the
   JSON-RPC wire, including text and structured content. The default-TTL sample
   includes any naturally expired checks. On a separate fast server per project
   with `--currency-ttl 0`, repeat `stats` (20 samples) to isolate currency cost.
   Record RSS/HWM of each warm server. Warm repeats are a controlled workload for
   R1-C131; they do not measure the frequency of repeat queries in production.
4. **Watch.** With a current fast graph and both watchers on their default poll
   and debounce settings, let them settle for two seconds and measure 15 seconds
   of idle CPU ticks, current/peak RSS, logical and physical I/O per process.
   CPU includes reaped children, such as `git` processes in the source watcher.
   Check that graph and sidecar timestamps remain stable. Apply one edit; poll
   actual MCP `resolve` until the symbol is served and currency is current.
   Record save→first verified answer and the rebuild/reload log, then restore the
   input. Treat that latency as one observed sample per project, with an upper
   bound from the observation interval and currency checking on each probe.
5. **Accounting.** Run sequentially on `m99` under an agreed slot, with process
   affinity bounded by the slot and one Jedi sample per build. Use an isolated
   `~/jobs/codemap/` directory, a dedicated venv, public inputs and a per-run JSONL
   file with partial results retained. Record enabled CPUs, kernel, load, CPU/IO
   pressure snapshots, exit status and timeouts. Acquire via the shared helper
   and journal `START`/`END` on `k99`. Other jobs may affect timings even with
   bounded affinity. Report pressure and visible run-to-run variation.

P50 is the median and P95 is the nearest-rank 95th percentile (`ceil(0.95*n)`),
reported alongside `n`. For groups below 20, report median and maximum. CPU as
percent of one core is `100 * (user + sys) / wall`. P95 estimates at this sample
size are descriptive. Keep all successful samples and record failed ones with
the corresponding step. Use ceilings of 900 s per build, 60 s per MCP call and
120 s save→answer. An interrupted or timed-out case is inconclusive, with a
rerun or a stated coverage gap in the results.

## Predictions, before running

- **H1.** Deep full builds cost more wall and CPU time than fast. The multi-root
  graph costs more to load and takes more bytes than either package-only graph.
- **H2.** Incremental deep beats full on single-file edits in all three cases.
  Repeated consumer scans narrow the speedup on the multi-root fixture.
- **H3.** `impact` full increases payload bytes. Compact limits can reduce output
  even if upstream work still consumes much of its time. Force-fresh `stats`
  gets more expensive as the manifest grows.
- **H4.** The source watcher consumes more idle CPU than the artifact watcher on
  the multi-root fixture. Report the absolute idle cost before proposing changes.
- **H5.** Repeated unseeded `pack` has a visible graph-dependent cost. Treat a warm
  P95 over 100 ms as a prompt to profile the ranking path, not as a cache decision.

## Acceptance criteria

| ID | Evidence required |
| --- | --- |
| E1 | Three public revisions verified. Six full-build series with wall, CPU, I/O, RSS, input scope and graph size. Release, dependencies and host details recorded. |
| E2 | Six one-file series of 20 and six no-op controls of 5. Edit detected each time, baseline restored, modes and fallbacks tabulated, unchanged control stays unchanged. |
| E3 | Both tiers on all three graphs pass real MCP handshake, symbol resolution and currency checks. Load/start times, warm P50/P95, sample counts, bytes and RSS recorded. Three forced-fresh comparisons. |
| E4 | Both watchers measured separately at idle for all three projects. Artifacts stable at idle and each edit reaches a current MCP answer. |
| E5 | Document predictions versus results, failure/timeout counts, host constraints and actionable findings for MCP limits and R1-C131. Link the harness and reusable raw data. |

Write the report to `RESULTS.md` alongside this document and update the gap and
backlog after reconciling each criterion. Harness changes after a run belong in a
dated deviation note. Product changes are a follow-up decision.

## Replay

On the measurement host, put the two scripts in a dedicated work directory and
run setup and measurement under the same agreed CPU affinity. For example, from
inside a two-CPU slot on Linux:

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
bash prepare.sh "$PWD"
.venv/bin/python -I measure.py "$PWD"
```

For a quick harness check, add `--projects more-itertools --tiers fast --smoke`.
For a rerun, use `--output <new-directory>` to keep earlier samples intact.
From the repository, render and validate a full measurement with
`python3 research/bench/r1c130/summarize.py <samples.jsonl-or-gz>`.

## Pilot deviation, 2026-11-24

Both tiers of the first small-package pilot reported `unchanged` and zero
recomputed modules, yet the CLI wrote the artifact again and changed its mtime.
The pilot originally treated mtime as a correctness condition, so it stopped
each series at the first no-op sample. The corrected harness records artifact
mtime/size, graph byte equality, logical scope equality and the CLI decision
separately. An idle watcher still has to leave both artifact timestamps stable.
Pilot samples are excluded from the full-series statistics.

The first main attempt exposed quantization in the command timer. Python's
timed process wait polls for completion and adds up to roughly 50 ms to short
builds. We stopped that attempt and changed the timer to wait for the Linux
process exit notification via a PID file descriptor. Its partial samples are
retained separately. The final attempt uses the corrected timer for every tier.

The corrected run reached parity failures on rich/fast and pytest/fast. The
reverted incremental graphs dropped one and five `annotated-field` calls from
unaffected modules, respectively. The harness stopped those series after
recording the mismatches and continued the other tiers. Keep the failing
controls and rerun the incomplete series separately
on the same published release. The rerun records parity flags for every sample
and measures the observed graph even when parity fails. The failure is an
acceptance finding and remains visible in the report. It has its own synthetic
reproduction and follow-up, [R1-C149](../../../BACKLOG.md).
