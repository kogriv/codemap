# Dead-code candidates (graded)

`codemap report dead-code` flags **private functions with no incoming resolved call**
— triage, never proof (call resolution is partial by design; dynamic dispatch, CLI
entry points and test targets are blind spots). What sets codemap apart from a
call-only tool (vulture) is that its cross-root graph lets it **grade** each candidate
and say *why*, so you can tell a real corpse from a framework-wired function.

## Confidence

| Level | Meaning | Typical reason |
|---|---|---|
| **high** | No inbound edge of any kind, no decorator, no registry | `no inbound calls, references, or decorators` |
| **medium** | A decorator or registry membership could invoke it implicitly | `decorated by @route — may be invoked implicitly` · `registered as 'x' — may be dispatched` |
| **low** | Something *references* it (re-export, a name in a list, a registration) → likely alive | `referenced (references) by tests×3` |

The **low** tier is the false-positive cut: a private helper that a test, a re-export,
or a registry points at is *referenced*, so codemap says so and grades it down instead
of listing it as dead. The reason names who references it, across roots (core / tests /
docs / …) when the graph was built repo-scoped.

```bash
codemap report dead-code --build ./pkg                 # all tiers, grouped
codemap report dead-code --build ./pkg --min-confidence high   # only the strongest signals
```

## Whitelist

Some functions are wired by machinery codemap's static edges can't see — argparse
`set_defaults(func=...)`, a hand-rolled dispatch dict, a plugin loader. Suppress them
in `codemap.toml` (exact id or `fnmatch` glob):

```toml
[dead_code]
whitelist = [
  "pkg.cli._cmd_*",          # argparse-wired subcommands
  "*.Session._op_*",         # dispatch-dict methods
  "pkg.plugins._register_*",
]
```

Whitelisted candidates are dropped from the report (the header shows how many patterns
applied). The whitelist is read relative to the report's root (cwd, or the serve
`source_root`). Same surface over MCP/serve: the `report` op takes `kind: "dead-code"`
plus an optional `min_confidence`, and reads the whitelist from `[dead_code]`.
