# R1-C106 — dead-code and definitions retained by a framework

**Preregistered 2026-11-24 before implementation.**
[Gap and audit evidence](../../gaps/registered_definitions_dead_code_2026-11-24.md).

## Design

1. Keep R1-C46's record of which line's binding was replaced. On the earlier
   definition, a decorator can retain the original object. Separate such lines
   from the report's definite `shadowed` findings. The later definition's
   decorator does not qualify an earlier undecorated object. Use source-derived
   optional graph metadata in both core and consumer builds, preserve it across
   incremental rebuilds and repeated samples, and keep older graphs readable.
   The existing graph still has a single canonical definition ID. Do not merge
   calls from different bodies under that ID. Keep call-site conservation and
   the existing overload, property, and singledispatch rules. Document what a
   rebuilt graph can establish about the earlier object.
2. For an otherwise `high` private method, an independently source-verified
   same-name method on an external ancestor is evidence for possible framework
   dispatch. Grade it at most `medium` and explain the ancestor evidence. Keep
   the existing stronger evidence from internal ancestors, references and
   decorators. An external base by itself supplies no same-name evidence.
   Inspect only readable Python source or stubs and keep work bounded to
   relevant qualified modules/classes. Do not import or execute a dependency.
   Record the qualified ancestor and method, without absolute host paths, and
   document the source availability and rebuild limits. Allow absence of
   source evidence in an older graph or on a missing dependency.

The current graph shows 10 direct core calls to `_shadow_map`, including
core behavior and consumer extraction, and two test calls to
`Query.shadowed_definitions`. `Query._grade_dead` already applies R1-C55.
Verify both extraction paths, JSON and text reports, and public tier defaults.

## Acceptance

| ID | Evidence |
| --- | --- |
| D1 | On the pinned 0.0.50 wheel, reproduce the definite shadow finding for a truly retained decorated function and the `high` finding for an externally dispatched private override. Show the functions running in a synthetic fixture. |
| D2 | After the change, separately registered same-name functions can both run and the earlier line leaves the definite findings in fast and deep, including a consumer root. A mixed sequence reports plain earlier lines while omitting decorated earlier lines. A decorator on the later definition alone does not protect an earlier plain one. |
| D3 | A source-verified stdlib or installed Python base declares the overridden name. The child method leaves `high` with an understandable reason. An unrelated unused private method in the same class stays `high`. Existing reference and internal override grades stay intact. Include unresolved dependency and source that must never be executed during extraction. |
| D4 | Text and JSON agree. Fast full and incremental reports stay aligned after adding/removing a decorator, and the repeated sample path preserves evidence. Existing binding scoping, call-site conservation, and regular shadow controls pass. |
| D5 | Confirm on `m99` against the published wheel, run the targeted and full suites in the shared slot, and verify the architecture contract on the exact tested patch. The historical 41 → 3 estimate is reconciled separately when the pinned consumer snapshot can be replayed. |

Synthetic source, patch, and acceptance evidence may be stored in the project.
The original consumer evidence is reported as aggregate counts.

## Verification on m99

| Criteria | Observed result |
| --- | --- |
| D1–D2 | Both registered bodies ran. With the published 0.0.50 wheel, both fast and deep put the earlier `_hook` line in `shadowed`. The candidate omitted that line and retained the plain duplicate and the earlier line when only the later definition was decorated. Consumer and mixed-sequence controls passed. |
| D3 | `ArgumentParser.print_help()` called the synthetic private override. The baseline reported it `high`. Both candidate tiers reported `medium` with the source-verified `argparse.ArgumentParser._print_message` reason. The unused neighbour remained `high`. A source-only installed-package fixture passed without executing the dependency. |
| D4 | Text and JSON agreed. Incremental, repeated, older-graph and call-site controls passed. The patch also carries bound-method `self` references across incremental splices, preserving the existing reference-based grade. |
| D5 | The independent replay and 35 targeted checks passed. Full pytest on Python 3.12.16 reported **1531 passed, 3 skipped** in 275.93 s. `codemap check --require-contract --require-current` passed, and `codemap review` covered 43 changed symbols. The historical consumer snapshot was unavailable for a 41 → 3 replay. |

The agreed two-CPU m99 slot ran from 16:01:22 to 16:06:34
Asia/Novosibirsk on 2026-11-24, exited 0 and was released. The optional
`ccc`, `readtags` and `scip` executables account for the three skips.
The candidate patch against `5901519` had SHA-256
`b673ba2d8cf0c9445f8931a6d964d0fe703c01ee40802bca2bbdc8290d3cd76f`.

[Independent replay](../../research/bench/r1c106/replay.py) ·
[Observed output](../../research/bench/r1c106/results/replay.json).
