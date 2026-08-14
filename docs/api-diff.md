# API diff & breaking-change (`codemap diff`)

Compare two `graph.json` snapshots — a *before* and an *after* — and get what moved
on the **public API surface**: symbols added / removed, and for symbols present in
both, the signature-level changes, each classified **breaking**, **warning**, or
**info**. "What broke between these two commits", at the API level. It complements
[`codemap check`](architecture-contracts.md): `check` guards internal structure, `diff`
guards outward compatibility.

## What counts as breaking

Signatures are parsed with the stdlib `ast` (each stored signature is read as
`def <sig>: …`), so parameter analysis is exact, not string-diffing. Only **public**
symbols participate — private churn is not an API change.

| Change | Severity | Why |
|---|---|---|
| public symbol removed | **breaking** | callers referencing it break |
| public → private | **breaking** | removed from the public API |
| kind changed (function ↔ class) | **breaking** | usage form changes |
| parameter removed | **breaking** | callers passing it break |
| required parameter added | **breaking** | existing calls omit it |
| parameter made required (default dropped) | **breaking** | calls relying on the default break |
| `*args` / `**kwargs` removed | **breaking** | calls using them break |
| parameter type changed | warning | may narrow — needs a human's eye |
| return type changed | warning | may narrow — needs a human's eye |
| newly `@deprecated` | warning | signals coming removal |
| optional parameter added | info | backward-compatible |
| symbol added | info | new API |

A signature `ast` cannot parse degrades to a conservative `signature-changed`
warning — never a false "breaking".

## Usage

```bash
# render the delta between two snapshots
codemap diff old.json new.json

# release gate: exit 1 if any breaking change is found
codemap diff old.json new.json --exit-code
```

Build the two snapshots from two revisions and diff them:

```bash
git stash            # or check out the baseline in a worktree
codemap build ./yourpkg -o /tmp/old.json
git stash pop
codemap build ./yourpkg -o /tmp/new.json
codemap diff /tmp/old.json /tmp/new.json --exit-code
```

Example output:

```
# API diff — `pkg` → `pkg`

❌ **2 breaking change(s).** 1 added, 1 removed, 1 changed.

## Removed public symbols — breaking (1)
- `pkg.api.Old`

## Breaking signature changes (1)
- `pkg.api.run` — parameter `verbose` is now required

## Added public symbols (1)
- `pkg.api.New`
```

## In review and over MCP

The diff folds into change-set [`review`](../codemap/serve/review.py): hunk-based
review sees only *modified* lines, so `--base` adds the symbols hunks miss — removed
and added public symbols, and breaking signature changes:

```bash
git diff | codemap review - --graph new.json --base old.json
```

The same is a serve op and an MCP `diff` tool (`base` = path to the baseline
graph.json; the session graph is the *after*), returning
`{ok, added, removed, changes:[{symbol, kind, severity, detail}], summary}` — the
structured "did this change break the API?" check an agent runs after an edit.

## CI example

```yaml
# fail the PR if it introduces a breaking API change vs the base branch
- run: codemap build ./yourpkg -o new.json
- run: git checkout "$BASE_SHA" && codemap build ./yourpkg -o old.json
- run: codemap diff old.json new.json --exit-code
```

Deterministic — same pair of graphs ⇒ same verdict.
