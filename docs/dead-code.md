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

### What counts as a reference

Grading is only as good as the edges it can see, and three source-visible forms used to
produce none — so a live function landed in **high**, the band a reader acts on
([#7](https://github.com/kogriv/codemap/issues/7); measured at 20 of 51 candidates across
two real packages, codemap's own included). All three are modelled now:

| Form | Example | Edge |
|---|---|---|
| **function as a value** | `PANELS = {"a": _panel_a}`, `json.dumps(o, default=_json_default)` | `references`, `extras.resolution="name"` |
| **type annotation** | `def render(...) -> Report:` | `references`, `extras.resolution="annotation"` |
| **module-level call** | `_register_all_indicators()` at import time | `calls`, sourced from the **module** node |
| **call inside a closure** | a call in a nested `def` or a dynamically-built class body | `calls` from the innermost enclosing definition, `extras.via="nested"` |
| **used through a function-local import** | `def go(): from .leaf import helper; return helper(x)` | `calls` / `references`, `extras.resolution="imported"` (R1-C30) |

The last one is the youngest, and it is the form most likely to hide a live symbol: a lazy
import is what a developer writes when the dependency is awkward, which usually means it is
load-bearing. Before R1-C30 the fast tier could not see it, so such a symbol could be graded
dead while being called on every run. Measured when it landed, the honest version: on both
dogfood trees the **banded lists did not change** — but three symbols went from zero inbound
edges to one, among them codemap's own `DebouncedPoller`, which the whole `codemap watch`
loop is built on and which its own graph showed as used by nothing.

Two of those are missing **call** edges, so this was never only a dead-code question:
`impact`, `callers` and `flows` were reading a call graph with import-time work and
closure bodies cut out of it.

Annotations are labelled apart from values on purpose: a dispatch table implies the
function runs, an annotation implies a contract. Both keep a symbol out of **high**, and
the distinction is on the edge if you want to weigh them differently. `extras.via="nested"`
marks the one approximation here — the call's *existence* is certain, only the definition
it is attributed to is inferred (a closure that is built and returned but never invoked
still yields an edge from its enclosing function).

```bash
codemap report dead-code --build ./pkg                 # all tiers, grouped
codemap report dead-code --build ./pkg --min-confidence high   # only the strongest signals
```

## Shadowed definitions — certain, not graded

A name defined twice in one scope — a method written twice in a class, a function
repeated at module level — is listed in its own section ahead of the graded candidates:

```
## Shadowed definitions — certain: 1

- `pkg.Thing.get` — defined at line 11 shadows the definition at line 8; the earlier body can never run.
```

It is not a candidate because it is not a heuristic: Python binds the later body and the
earlier one cannot run whatever calls it. The surviving node carries `extras.shadows`
(the shadowed line numbers), and the extractor walks only the body that can run — before
this, both bodies' calls were attributed to the one node, so the graph claimed a call
from code that never executes (R1-C46, found by a consumer as a `contains` record that
appeared twice).

Three idioms rebind a name on purpose and are exempt by decorator, never by guess:
`@overload` before the implementation, `@x.setter` / `.getter` / `.deleter`, and a
`@f.register` (or the singledispatch `_`) after the base. A definition under `if` or
`try` — `if TYPE_CHECKING:`, an `except ImportError` fallback — neither shadows nor is
shadowed; both bodies keep being walked.

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
