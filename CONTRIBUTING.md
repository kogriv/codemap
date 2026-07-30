# Contributing to codemap

Thanks for your interest. codemap is a static code-graph analyzer; it stays small, deterministic,
and honest about its approximations.

## Development setup

```bash
uv venv && uv pip install -e .
uv pip install pytest
.venv/bin/python -m pytest -q          # full suite (deep tests take ~1 min)
```

## Principles (please preserve them)

- **Source-only.** Never import the target package at analysis time — static `ast`/`griffe` only.
  codemap must work on a package it cannot execute.
- **Deterministic output.** `graph.json` is canonical: sorted, no timestamps, diffable. Any change to
  the JSON shape bumps `SCHEMA_VERSION` in `codemap/model.py` (add a history line).
- **CLI-AI-first.** JSON by default, stable exit codes; human/text output is secondary.
- **Honest approximations.** Call resolution, registry bridging, and string-key dataflow are
  best-effort over-approximations — label them (`resolution=…`, disclaimers), never present a guess as
  fact. The `serve` envelope surfaces ambiguity (`resolved.ambiguous`) rather than answering silently.

## Workflow

- **Dogfood-driven.** New capability is justified by a dogfood run under `gaps/`: pre-register
  hypotheses, run on a live graph, record findings, then implement the milestone that closes them.
  See [gaps/dogfood_axes.md](gaps/dogfood_axes.md) for the axis register.
- **Tests required.** Each milestone ships acceptance tests (`tests/test_mNN_*.py`) with fixtures under
  `tests/fixtures/`. Keep the full suite green.
- **One milestone per change.** Update [BACKLOG.md](BACKLOG.md) and [CHANGELOG.md](CHANGELOG.md).

## Reporting issues

Include the target package (or a minimal repro package), the exact `codemap` command, and the
observed vs expected graph/output. A failing case that a static analyzer *could* resolve is the most
useful kind of report.
