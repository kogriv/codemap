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
- **The devkit's templates are a product surface.** `codemap/devkit/templates/` is installed into other
  repositories by `codemap devkit`. Renaming a command, flag or MCP tool fails `tests/test_r1c108_devkit.py`
  until the templates follow. Changing a template means raising `DEVKIT_VERSION` and updating
  `TEMPLATES_SHA256`; that release's note then says "run `codemap devkit update`".
- **The tool catalog is a product surface too.** `codemap/advise/data/` is what `advise` serves to agents.
  A new or re-measured card moves its claims in `matrix.toml` in the same commit: status, version, `checked`,
  evidence anchor. Then regenerate the inventory (`codemap advise --matrix > research/matrix.md`) and update
  the README counts. `tests/test_r1c110_advise.py` fails until all of it agrees. Nothing is marked `measured`
  without a card section that has the numbers, and nothing from a private project goes in.

## Reporting issues

Include the target package (or a minimal repro package), the exact `codemap` command, and the
observed vs expected graph/output. A failing case that a static analyzer *could* resolve is the most
useful kind of report.
