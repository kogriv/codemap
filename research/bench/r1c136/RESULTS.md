# R1-C136 — results on the public runtime traces

The candidate met the recall threshold and exceeded the allowed precision
loss on Click and Jinja. The measured patch stays in research and R1-C136
stays open. [Preregistered criteria](DESIGN.md).

## Deep comparison

The control is the candidate graph with only `override` edges removed. The
independent 0.0.50 wheel matched the control on explicit recall, precision
outcome counts and caller completeness in all three trees. Recall counts
observed explicit call and construction pairs. Decided precision is confirmed
pairs divided by confirmed plus contradicted pairs. A contradiction here
means every matching syntactic call site ran and the trace did not enter
that target from that caller. It describes this workload's observations.
[R1-C132 scoring](../r1c132/compare.py).

| Project | Explicit pairs found before → after | Recall gain (pp) | Decided precision before → after | Precision loss (pp) | Callers complete before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| Click | 473 → 533 / 646 | +9.29 | 97.13% → 92.70% | 4.43 | 240 → 292 / 357 |
| Rich | 1018 → 1050 / 1240 | +2.58 | 96.06% → 95.39% | 0.67 | 363 → 387 / 495 |
| Jinja | 886 → 1018 / 1476 | +8.94 | 98.23% → 75.70% | 22.53 | 300 → 326 / 611 |

| Project | Novel pairs | Confirmed | Contradicted | Undecided |
| --- | ---: | ---: | ---: | ---: |
| Click | 90 | 60 | 28 | 2 |
| Rich | 44 | 32 | 9 | 3 |
| Jinja | 508 | 132 | 312 | 64 |

Every deep `override` edge was a novel caller–target pair in these graphs.
A post hoc count by target method name places 249 of Jinja's 312 contradicted
pairs under `as_const`. It accounts for 84 of Jinja's 132 confirmed pairs, too.
In Click, `to_info_dict` accounts for 15 of 28 contradictions and two of 60
confirmations. These groups show where more precise receiver evidence could
reduce the fan-out. The comparison used the full candidate on all three trees.

## Acceptance

| ID | Result |
| --- | --- |
| V1 | Passed. The original fast calls retained all 432 Click, 1018 Rich and 801 Jinja caller–target–route identities. The candidate added 48, 17 and 75 `override` routes, respectively. Synthetic tests covered supported receivers, transitive subclasses, bounds, and excluded dispatch forms. |
| V2 | Passed. Synthetic `callers` and `callees` queries excluded candidates with `min_confidence="exact"` and retained genuine exact paths. The `impact` response included the possible path and marked the heuristic basis. Controls passed for repeated deep sampling and for adding and removing an override through incremental builds. |
| V3 | Failed. Two trees cleared the +5 pp recall threshold. Click and Jinja exceeded the 3 pp precision loss limit. |
| V4 | The 52 targeted tests passed on m99. The full suite was conditional on V1–V3, and the promotion path stopped at V3. |

The targeted m99 run used `test_r1c136_override_dispatch.py`,
`test_r1c39_edge_resolution.py`, `test_r1c45_repeat_union.py` and
`test_r1c47_incremental_resample.py`. An additional k99 development check of
`test_r1c9_incremental.py` with its cached environment reported the same two
deep incremental parity failures on the candidate and the release baseline.

## Reproduction and evidence

The Codex `pde` agent implemented the measured patch on k99 against
`5901519d64a2deb730dbf4110163107925de373c`. The m99 slot used CPU affinity
`0,1` on 2026-11-24 from 15:00:32 to 15:03:51 Asia/Novosibirsk and exited 0.
The environment used Python 3.12.16, Griffe 2.4.1, Jedi 0.20.1 and NetworkX
3.7. Both variants used the same environment. The control ran the published
wheel and the candidate used `PYTHONPATH` pointing to the patched checkout.
Fast builds used the default tier and deep builds used `--deep --repeat 2`.

- [Measured patch](results/candidate.patch.gz), uncompressed SHA-256
  `ce5548c8451a355fac5a77ec2b2c81953fb4f29769a6c2fc67ff00218b507644`.
- [17 raw records](results/samples.jsonl.gz) with source and trace identities,
  the wheel, patch and graph digests, build time and memory, and the decision.
- [Comparison driver](evaluate.py). Install `codmap==0.0.50` in a Python 3.12
  virtual environment. In a fresh run directory, save the verified wheel
  checksum to `wheel.sha256`, decompress the patch to `r1c136.patch`, and apply
  it to the release commit in `candidate/`. On two CPUs, run
  `PYTHONPATH=<run-dir>/candidate <venv>/bin/python evaluate.py <run-dir> <r1c132-work>`.
  The second directory contains `click/`, `rich/` and `jinja/`, each with a
  pinned `src/` checkout and both `trace1.json` and `trace2.json` from R1-C132.
