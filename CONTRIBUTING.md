# Contributing to codemap

Thanks for your interest. codemap is a static code-graph analyzer; it stays small, deterministic,
and honest about its approximations.

## Development setup

```bash
uv venv && uv pip install -e '.[mcp,scip]'
uv pip install pytest
.venv/bin/python -m pytest -q          # full suite (~2-3 min; deep tests dominate)
```

Python **3.11+**. CI runs the suite on 3.11–3.14 plus a determinism check, a wheel smoke test
and the ctags/SCIP interop tests — see [docs/ci.md](docs/ci.md) for what each job defends and,
just as importantly, what it does not catch.

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
