# Dead-code candidates (graded)

`codemap report dead-code` flags **private functions with no incoming resolved call**
— triage, never proof (call resolution is partial by design; dynamic dispatch, CLI
entry points, test targets and [nested definitions](#nested-definitions-are-not-judged-r1-c60)
are blind spots). What sets codemap apart from a
call-only tool (vulture) is that its cross-root graph lets it **grade** each candidate
and say *why*, so you can tell a real corpse from a framework-wired function.

## Confidence

| Level | Meaning | Typical reason |
|---|---|---|
| **high** | No inbound edge of any kind, decorator, registry membership, or detected ancestor method | `no inbound calls, references, or decorators` |
| **medium** | A decorator or registry membership could invoke it implicitly, or it overrides a base method that is uncalled here or declared in external source | `decorated by @route — may be invoked implicitly` · `overrides Base._open, which is itself uncalled here — dead only if the base is` |
| **low** | Something *references* it (re-export, a name in a list, a registration), or it **overrides a called base** → likely alive | `referenced (references) by tests×3` · `overrides PIL.ImageFile.ImageFile._open, which has 1 inbound call(s) — reached by dispatch, not by name` |

### Overrides are reached through the base (R1-C55)

A method that overrides an ancestor's method is not called by its own name — the base is
called and dynamic dispatch lands in the override. So "no inbound calls" is a statement
about the **name**, not about the body, and it cannot carry the strongest grade.

Measured on Pillow, where the shape is the whole architecture: **40 of 63** `high`
candidates were `_open` implementations overriding `ImageFile.ImageFile._open`, which the
same graph records as called from `ImageFile.__init__` (`self._open()`). 63 % of the band a
reader acts on, wrong — on the most ordinary shape in object-oriented Python. After the fix
that package's `high` band is 15. On codemap's own tree and on the second dogfood target the
band is **unchanged**, which is precisely why a month of dogfooding never produced it: neither
tree has a private override of a called base.

The walk is transitive and prefers the ancestor that is actually *called*: in a three-deep
chain the middle link is an override too, so it has no inbound call of its own, and naming it
would report "the base is itself uncalled" while the call sits one level further up.

The **low** tier is the false-positive cut: a private helper that a test, a re-export,
or a registry points at is *referenced*, so codemap says so and grades it down instead
of listing it as dead. The reason names who references it, across roots (core / tests /
docs / …) when the graph was built repo-scoped.

### Source-verified external overrides (R1-C106)

An otherwise high-confidence private method moves to **medium** when a qualified
external ancestor declares the same method in readable Python source or a stub.
The reason names the canonical ancestor method, for example
`overrides argparse.HelpFormatter._format_usage, declared in external source — may be reached by dispatch`.
References, decorators, and internal override evidence retain their existing grades
and reasons. An external base edge alone supplies no method evidence.

Fast and deep core builds follow qualified bases, static import aliases, and ancestor
declarations by reading the relevant module files. They do not import dependencies.
Missing or unreadable source, compiled-only dependencies, dynamic aliases, and
unresolved ancestry can leave an override undetected. The graph stores the qualified
method ID in `extras.external_override`, with no dependency file path. This is
evidence of a possible dispatch route. The dependency's actual calls are outside the
graph. Full consumer roots still supply their existing cross-root references and
do not build an inheritance graph.

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

The fast tier also follows a call such as `self._worker._work()` when the constructor
assigns the field once from a parameter annotated with a concrete class in the same
module (R1-C147). The edge is `annotated-field` with grade `inferred`. A visible
reassignment, ambiguous annotation, or missing target leaves the call unresolved.
The resulting absence of an edge still needs corroboration before deletion.

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

### Nested definitions are not judged (R1-C60)

A function or class defined **inside a function body in the package** — a closure's
`wrapper`, a `decorator` returned by a registering method, a class built inside a
factory — is **not a node**: the package is read by griffe, which does not enter function
bodies. Such a definition can never be a candidate, and it is in no list at all — neither
dead nor alive. The report says so in its blind-spot line.

What the graph keeps: calls made **from** inside the nested body, attributed to the
enclosing function (`extras.via="nested"`, the closure row above). What it loses: the
definition itself (`search`/`query` do not find it) and calls **to** it, which are counted
unresolved rather than pointed at a node that does not exist.

The narrowing is **per root**, not per graph: consumer roots built with `--mode full`
(`--consumer tests …`) are read by codemap's own AST scanner and **do** carry nested
definitions as nodes (`tests.test_x.test_it._local_helper`). Measured on one real scope
(`bquant@cb89a24`, package + four consumer roots): 49 nested definitions in the package,
none of them nodes; 35 in the consumer roots, all 35 nodes. Design:
[design/nested_definitions.md](design/nested_definitions.md).

## Shadowed definitions — definite binding replacements

A name defined twice in one scope — a method written twice in a class, a function
repeated at module level — is listed in its own section ahead of the graded candidates:

```
## Shadowed definitions — certain: 1

- `pkg.Thing.get` — defined at line 11 shadows the definition at line 8.
```

The surviving node's `extras.shadows` records every earlier line whose binding it
replaced. When an earlier definition has a decorator, the extractor also records its
line in `extras.decorated_shadows`. A decorator may retain that object, so the text
and JSON reports omit that line from the definite list. In a mixed sequence, plain
earlier definitions are still listed. A decorator on the later definition alone
does not protect an earlier binding. The record establishes rebinding and the
presence of a decorator. Object retention and execution depend on runtime behavior.

The graph has one canonical node for the surviving definition. When definitions
share that ID, calls inside replaced bodies stay out of the surviving node's call
edges. The core call-site report accounts for them in `shadowed_not_walked`, including
calls in bodies a decorator may have retained. Full consumer roots also record
binding lines and filter their definite findings.

Three idioms rebind a name on purpose and are exempt by decorator, never by guess:
`@overload` before the implementation, `@x.setter` / `.getter` / `.deleter`, and a
`@f.register` (or the singledispatch `_`) after the base. A definition under `if` or
`try` — `if TYPE_CHECKING:`, an `except ImportError` fallback — neither shadows nor is
shadowed; both bodies keep being walked.

### Rebuild for the new evidence

Older graphs remain readable and use the evidence recorded when they were built.
Make a fresh build to populate the two optional fields. A no-op incremental build
reuses the old artifact. If an external dependency is installed, removed, or changed
without an edit to the analyzed source, rebuild to refresh ancestor evidence.

## Called only from outside the package (R1-C118)

A function a test calls is not a candidate — but if every call and reference to it comes from a consumer root
(`tests`, `scripts`…), the package itself never reaches it. The report lists those apart, with the roots and the
count: a test helper that lives in the package, or code that outlived its production caller. Private functions
are listed by default; public ones are counted (in a library, API that only tests call is normal) and listed with
`--public`.

## Public functions (R1-C118)

A public function with no caller may be API for code outside the graph, so it is not a candidate. In an
application nothing outside imports the package, and these are the main class of dead code. The report always
says how many module-level public functions have no inbound edge; `codemap report dead-code --public` lists them,
graded like the private ones. Public **methods** are not judged: they are mostly called on an instance the static
resolver cannot type, and listing them would be noise.

A bound method handed on as a value — `bus.on("event", self._handler)`, `run(prepare=self._migrate)` — is a
`references` edge (resolution `self`), so such a method is **low**, not **high**.

**Dispatch by name is an over-approximation (R1-C120).** A module that calls `import_module("pkg.sub." + x)`
(or an f-string with that literal prefix) and reads `getattr(<anything>, "run")` anywhere in the same module is
taken to reach every `pkg.sub.<mod>.run`. No data flow is traced from the imported module to the `getattr`
argument: the two halves are paired within the module, because the usual runner keeps the factory and the
readers in different functions. So an unrelated `getattr(obj, "run")` in a module that also loads plugins makes
every plugin's `run` look reached. The edges carry the route `references:dispatch`, graded **heuristic**; a
function kept alive only by them is **low**, never certain.

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
