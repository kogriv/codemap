# R1-C136 — receiver evidence and Werkzeug holdout results

The second candidate reduced the precision loss on Click and Jinja. Only
Click cleared the original recall threshold. Jinja and the independent
Werkzeug holdout exceeded the 3-point precision limit, so the measured patch
is archived and R1-C136 stays open. [Preregistered design](FOLLOWUP.md).

| Project | Explicit pairs found before → after | Recall gain (pp) | Decided precision before → after | Precision loss (pp) | Complete caller sets before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| Click | 473 → 508 / 646 | +5.42 | 97.13% → 95.49% | 1.64 | 240 → 267 / 357 |
| Rich | 1018 → 1041 / 1240 | +1.85 | 96.06% → 95.53% | 0.53 | 363 → 378 / 495 |
| Jinja | 886 → 922 / 1476 | +2.44 | 98.23% → 93.63% | 4.60 | 300 → 315 / 611 |
| Werkzeug | 684 → 716 / 931 | +3.44 | 98.00% → 94.98% | 3.02 | 322 → 340 / 506 |

| Project | Novel pairs | Confirmed | Contradicted | Undecided | Gain / loss in the first candidate (pp) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Click | 47 | 35 | 10 | 2 | +9.29 / 4.43 |
| Rich | 33 | 23 | 7 | 3 | +2.58 / 0.67 |
| Jinja | 87 | 36 | 47 | 4 | +8.94 / 22.53 |
| Werkzeug | 68 | 32 | 24 | 12 | — |

The released 0.0.50 wheel and the ablated candidate matched on recall,
precision outcomes and caller completeness for all four projects. Fast
preserved all original caller–target–route identities (432, 1018, 801 and
788) and added 19, 5, 69 and 50 `override` routes, respectively.

The upstream Werkzeug suite returned 947 passed and one skipped in all three
runs, one plain and two traced. The traces matched byte-for-byte, observed
931 explicit pairs and reached 670 of 900 package functions. There were 56
decided novel pairs. Two setup attempts were discarded before scoring. The
upstream tests launch isolated subprocesses, which require the editable
install used in the final clean directory.

The `pde` implementation passed 95 targeted checks on k99. On m99, the 56
targeted tests covered original calls, exact-only filters, heuristic impact,
concrete type and method-order controls, and the repeated and incremental
paths. The full suite and integration were conditional on the quality gate.
The m99 slots used CPU affinity `0,1`, with the clean holdout run at
15:40:51–15:42:04 and the comparison at 15:45:34–15:50:09
Asia/Novosibirsk on 2026-11-24. Both exited 0 and released their slots.

- [Measured patch](results/v2/candidate.patch.gz) against `5901519`,
  uncompressed SHA-256 `d5b95a1f6db3beff8581aaeade3c3578bb57141b3f791d37fcb971b0efd3073e`.
- [22 raw records](results/v2/samples.jsonl.gz), including dependency pins,
  original trace and graph digests and the decision. The thresholds used
  unrounded values, including the Werkzeug precision loss of 3.0227 pp.
- [Werkzeug trace](results/v2/werkzeug-trace.json.gz), with the local
  `package_root` normalized to `src/werkzeug`. Record contents used for
  scoring are unchanged. Both source trace digests are in the raw records.
- [Comparison driver](evaluate.py) accepts `--holdout <werkzeug-run>` in
  addition to the [first study's replay arguments](RESULTS.md#reproduction-and-evidence).
  [Holdout trace runner](trace_werkzeug.sh) generates the two traces and control logs.
