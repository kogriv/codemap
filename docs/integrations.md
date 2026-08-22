# Integrations — external tools, opt-in (DESIGN §13.1)

codemap does one thing precisely: a deterministic, source-only structural graph. Some
capabilities are outside that scope on purpose — semantic (concept) search, many
languages, flow/community narrative. Rather than reimplement them, codemap can call a
**user-installed** external tool. The core never depends on it: every integration is
**off by default**, reached only when you opt in and the tool is installed.

## Two modes

| Mode | What it does | License rule | Output |
|---|---|---|---|
| **router** | Forward the question, return the tool's answer **as-is** | any (opt-in + notice) | passthrough, never enters the graph |
| **adapter** | Call the tool, **translate** its output into codemap's own contract | **permissive only** (MIT/Apache/BSD…) | codemap-native (e.g. symbols) |

The rule is machine-enforced: registering a non-permissive **adapter** raises — a tool
whose output we absorb must be MIT/Apache-class; a non-commercial tool can only be a
**router** (we forward, never incorporate). codemap **bundles nothing** — calling an
installed tool is not distributing it — so the core stays clean MIT.

Two tools ship wired today:

- **gitnexus** — router (PolyForm-Noncommercial): `semantic-search`, `flow-narrative`,
  `community-clusters`. Forwarded as-is.
- **cocoindex** — adapter (Apache-2.0): `semantic-search`, enriched to codemap symbols.

## Opt-in

Nothing runs until you enable it in `codemap.toml`:

```toml
[integrations]
enabled = ["cocoindex", "gitnexus"]   # opt-in, not default
acknowledged = ["gitnexus"]           # non-commercial notice already accepted (shown once)
```

Resolution is **capability-first**: you ask for a capability (`semantic-search`) and
codemap picks an integration that (a) provides it, (b) is enabled, and (c) is installed —
the concrete tool stays behind the capability. Nothing satisfies all three → the feature
is simply unavailable, never an error.

## Semantic search (adapter, R1-C16)

codemap has no fuzzy layer by design. An **adapter** fills it and — crucially — resolves
each fuzzy hit to the **exact codemap symbol** at that location, so a concept query comes
back as ranked codemap symbols, not just line ranges. That composition (fuzzy retrieval →
exact structure) is what neither tool gives alone.

```bash
# one-time: install + index the repo with the adapter's tool
uv tool install 'cocoindex-code[full]'
cd your-repo && ccc index

# then, from codemap:
codemap semantic "detect swing high/low pivot points" \
    --build ./your-repo --root your-repo
```

```
# semantic: 'detect swing high/low pivot points'  (via cocoindex)
  0.720  pkg.zones.strategies.swing.pivot_points.PivotPointsSwingStrategy  [pkg/.../pivot_points.py:1-19]
  0.673  pkg.zones.strategies.swing.pivot_points.PivotPointsSwingStrategy.detect  [.../pivot_points.py:127-149]
  ...
```

Each hit carries `symbol` (the codemap node id, or `null` when the location isn't in the
graph — kept honestly as `unresolved`), `score`, and `file:lines`. Hits are de-duplicated
per symbol (best score wins) and sorted by score. `--format json` for the raw envelope.

- `--root` is the repo the tool's index was built in **and** where file paths resolve
  (it also holds `codemap.toml`); default cwd.
- **MCP:** the same capability is exposed as the `semantic_search` tool, so an agent gets
  codemap symbols from a concept query natively.
- **Router alternative:** a router-only semantic tool (e.g. gitnexus, NC-licensed) can't be
  enriched — use `codemap route semantic-search "<query>"` to get its passthrough answer.

## Adding an integration

Subclass `codemap.integrations.base.Integration`, declare `name` / `mode` / `license` /
`capabilities`, implement `is_available()`, and the surface for your mode:

- router → `route(capability, question) -> RawAnswer`
- graph adapter → `extract_fragments(target) -> GraphFragment` (nodes/edges into a
  non-canonical sidecar, stamped `provenance: external`)
- retrieval adapter → `search(capability, query, *, root, limit) -> list[dict]` (raw
  `{file, start_line, end_line, score}` hits; codemap enriches them to symbols)

`register(...)` it (enforces the license policy); import it from
`codemap/integrations/__init__.py` so it self-registers. The core keeps working without it.
