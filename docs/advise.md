# `advise` — what to use where codemap stops

codemap answers structural questions about Python. An agent's next question is often outside that: a
TypeScript call graph, duplicated code, a security pattern, how many queries a view makes. `advise` answers
it from the codemap lab's catalog. The catalog says what codemap covers for each need and which other
tools exist, and for each tool what the lab actually saw. Design and acceptance:
[`design/advise.md`](design/advise.md) (R1-C110).

```bash
codemap advise                          # every need: codemap's coverage and the best other tool
codemap advise "ts call graph"          # one need, by id or free words
codemap advise --root .                 # the languages here, and the needs codemap does not cover for them
codemap advise --tool import-linter     # one tool: every claim, the latest release seen, news
codemap advise --news --days 30         # the feed
codemap advise --refresh                # the lab's current catalog from main, no codemap release needed
```

Through MCP: `advise(need, languages, tool, news_days)` returns the same answer as JSON. The server's
instructions tell the agent to call it for questions outside the Python graph.

## Reading a claim

Each claim is about one tool and one need, and carries a status:

| Status | What the lab did |
|---|---|
| `measured` | scored it against the lab's truth for this need; the evidence link opens the card section with the numbers |
| `probed` | ran it on a real tree for this need, without scoring |
| `read` | knows it from its docs or a survey; **nobody here has run it** |
| `rejected` | tried it and found it unusable for this need, with the reason |

Measured on Python says nothing about TypeScript. A tool measured for the Python call graph is `read` for
the TypeScript one until someone runs it there.

Two flags say a claim may be out of date:
- `stale` means it was checked more than `stale_after_days` before the catalog's date;
- `drift` means a release newer than the measured version has come out since.

**Asked about a language** (`--lang`, `--root`, MCP `languages`), `advise` shows only tools whose recorded
languages include it, or that are language-agnostic, and it lists the others as `excluded`. A measurement
counts for the language it ran on. The lab's truth so far is Python, so for Rust a tool measured on Python
shows as `read`, with the note "measured on python only".

Before relying on a `read` or `probed` tool, ask it a question whose answer you know on your own tree.

codemap's own coverage is part of every answer: `covered`, `partial` (with the caveat and its backlog id)
or `none`. A `covered` or `partial` claim names the tests in codemap's suite that prove it.

## The boundary in other answers

A not-found answer whose input names a file codemap does not read (`web/app.ts`, `cmd/main.go::Run`) carries
`outside_graph: {language, advise}`. The file is not in the graph, which does not mean nothing uses it.
`codemap devkit` writes the same rule into the project's agent rules block. That block also names the
languages found outside Python.

## How the catalog stays current

The catalog is `codemap/advise/data/matrix.toml` (reviewed claims) plus `feed.json` (latest releases, news).
Both ship in the package and are published on `main`, and `--refresh` caches the newer copies. The inventory
page [`research/matrix.md`](../research/matrix.md) is generated from them.

- **Every week** a script reads PyPI, npm and GitHub for every watched tool. It records the latest release and
  flags claims whose tool has moved on (`research/tools/_watch/releases.py`). A routine also scouts for new
  tools and advisories. What it adds arrives as `read` claims and `verified: false` news on a branch for
  review.
- **On drift or staleness**, a claim is re-measured with the card procedure on the lab's frozen tree.
- **codemap's suite guards the data:**
  - every evidence link resolves to a heading in a card;
  - every claim meets its status's requirements;
  - every test codemap cites exists;
  - every card has a tool;
  - the inventory page equals its render.

`advise` installs and runs nothing. It is a lookup over reviewed data, with no model involved.
