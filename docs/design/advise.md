# Design — `advise`: the lab's verified tool expertise, delivered to the agent

**Status:** ✅ **done** (2026-11-21, 0.0.40), pre-registered in a9e2c32 before code, reconciled below. **Backlog:** R1-C110.
**Gap:** [`gaps/tool_expertise_unreachable_2026-11-21.md`](../../gaps/tool_expertise_unreachable_2026-11-21.md).

## Problem in one paragraph

codemap answers structural questions about Python. Its lab has measured 13 neighbouring tools on one truth
and read about dozens more. None of that reaches an agent working in another repository: it lives in
markdown here. A question codemap cannot answer (a TypeScript call graph, duplicates, DB query counts) gets
the same "not found" as an absent symbol. A project that adopted codemap had its "what covers the rest"
section written by hand, mixing measured tools with tools nobody ran, and nothing will tell it when that
section is out of date. The owner's decision (2026-11-21): the verified expertise is the broader product;
it has to be reachable by the agent through its tools, current, with a lab flow that keeps it so.

## Decisions

### D1 — one matrix: needs × tools, every claim with a status and its evidence

The source of truth is `codemap/advise/data/matrix.toml` (package data, hand- and agent-edited, reviewed).
Three tables:

- **`[[need]]`** — what an agent wants done, not a tool name: `py-callers`, `import-gate`, `duplicates`,
  `multi-lang-graph`, `db-query-count`, … Fields: `id`, `title`, `keywords` (for matching a free query),
  `languages`, and **codemap's own coverage**: `codemap = "covered" | "partial" | "none"`, `codemap_how`
  (the MCP tool and CLI command), `codemap_tests` (test ids that prove it), `codemap_caveat` (what is not
  covered, with backlog ids). Optional `note` for needs no static tool meets.
- **`[[tool]]`** — identity: `id`, `name`, `url`, `license`, `languages`, `interface`, `watch` (where its
  releases are published: `pypi` / `npm` / `github` / `none`), `card` (the research card, if any).
- **`[[claim]]`** — one per (tool, need): `status`, `version`, `checked`, `evidence`, `summary`,
  `vs_codemap`, `reason` (rejected), `probe` (how to check it on your own tree before relying on it).

The status vocabulary is closed:

| Status | Means | Requires |
|---|---|---|
| `measured` | scored against the lab's truth for this need | `version`, `checked`, `evidence` → a card heading with the numbers |
| `probed` | run on a real tree for this need, not scored | `version`, `checked`, `evidence` |
| `read` | known from its docs or a survey only | `url`; `evidence` optional (the survey that names it) |
| `rejected` | tried and unusable for this need | `checked`, `reason`, `evidence` |

A claim is per need: a tool measured on Python and never run on TypeScript is `measured` for `py-imports`
and `read` for `multi-lang-graph`. That is the distinction the hand-written memo lost.

### D2 — the inventory a person reads: `research/matrix.md`, generated

`research/matrix.md` is rendered from the matrix and the feed (D5): per need, codemap's coverage and the tools
in status order (`measured`, `probed`, `read`, then `rejected` apart), each with version, date and a link to
the evidence; then a per-tool index; then the last news. It is never edited by hand. A test renders it and
compares (D7). This is the "what is covered, what is measured, what is only read" navigation page.

### D3 — `codemap advise` and the MCP tool `advise`

```
codemap advise                      # the compact matrix: each need, codemap's coverage, best tool
codemap advise "ts call graph"      # match a need by id, title or keywords
codemap advise --lang typescript    # needs that apply to a language
codemap advise --root .             # detect the repository's languages, show what codemap does not cover there
codemap advise --tool import-linter # a tool: claims, latest release seen, news
codemap advise --news [--days 30]   # the feed
codemap advise --refresh [--from URL]
```

MCP: `advise(need=None, languages=None, tool=None, news_days=None)` → the same answer as JSON.

Every answer carries `catalog: {as_of, source: packaged|refreshed, age_days}` and per claim `stale: true`
when `checked` is older than `meta.stale_after_days`, and `drift: {measured, latest}` when the feed has seen a
newer release than the one measured. Evidence comes out as a URL into this repository on GitHub. A query that
matches no need says so and lists the need ids; it never falls back to a guess.

`advise` does not install or run anything. It names tools, what the lab saw, and how to check the claim on
the user's own tree (the `probe` field — the lab's rule: a known-answer question first).

### D4 — the boundary shows in codemap's answers

- The MCP server instructions gain one sentence: questions outside the Python graph go to `advise`.
- A not-found resolution whose input names a non-Python source file (`.ts`, `.tsx`, `.js`, `.go`, `.rs`, …,
  optionally with `:line` or `::symbol`) carries `outside_graph: {language, advise: "<need id>"}`. A Python
  name gets no such key. This is a new key in the answer, so `ANSWER_FORMAT` becomes **11**.
- The devkit rules block (D4 of the devkit design) gains a paragraph: codemap reads Python only; for the
  rest call `advise`; the languages found outside Python at install time are named. This is a template change,
  so `DEVKIT_VERSION` becomes **3** and the release note says "run `codemap devkit update`".

### D5 — delivery without a codemap release: the feed and `--refresh`

Knowledge moves faster than releases. Two files ship in the package and are also published on `main`:

- `matrix.toml` (D1);
- `feed.json` — machine-written: per watched tool the latest release seen (`version`, `date`, `seen`), and the
  news list `{date, kind: release|card|finding|advisory|new-tool, tool, text, source, verified}`.

`codemap advise --refresh` downloads both from the repository's `main` on GitHub (or `--from` a base URL) into
the user cache (`$XDG_CACHE_HOME/codemap/advise/`, default `~/.cache/…`). They are accepted only when they
parse, pass the same schema checks as the packaged ones, and are newer (`as_of`, an ISO timestamp in both files: two catalogs on one day must still order). Afterwards `advise` reads
whichever of packaged and cached is newer, and says which. A failed download leaves the packaged copy in use
and says why; exit stays 0. A plain GET of two public files; nothing is sent. The MCP tool never downloads on
its own: refresh is explicit (CLI, or the agent running it).

Unverified news (`verified: false`, from scouting) is shown, marked as such.

### D6 — the lab flow that keeps it current

Three layers, by cost:

1. **Releases** (`research/tools/_watch/releases.py`, weekly): for each tool with `watch`, the latest
   version from PyPI JSON, the npm registry or GitHub releases. Writes `feed.json`: `latest`, and a `release`
   news item for each new version. A source that fails is named in the output, never skipped in silence.
   Lab-side; not shipped.
2. **Re-measure** (on drift or staleness, at backlog review): a claim whose tool has drifted from the
   measured version, or that is past `stale_after_days`, is listed by `releases.py --report`. Re-measuring
   uses the card procedure on the frozen R2 scope; the card and the claim's `version`/`checked` move together.
3. **Scouting** (weekly routine, owner's decision 2026-11-21): run layer 1, search for new code-intelligence
   tools, releases and advisories, add `read` claims and `verified: false` news, and open a branch for
   review. The maintainer session checks each item before merging: a new tool becomes a card only when it is
   run. The routine's prompt carries the repository's public-only rule.

### D7 — guards

In codemap's suite (`tests/test_r1c110_advise.py`):
- every claim's `evidence` resolves: the file exists and the anchor matches a heading in it;
- the status requirements of D1 hold for every claim; every claim names an existing tool and need;
- every need with `codemap = covered | partial` names at least one test, and each named test exists
  (file present, function defined);
- every tool with a card is in the matrix, and every card file a tool names exists;
- `research/matrix.md` equals its render;
- `feed.json` passes its schema; every `tool` it names exists;
- `advise` is in `MCP_TOOLS` and the devkit block names only existing tools (the existing D7 guard);
- staleness is computed against `as_of`, never against today, so the suite does not turn red with time.

### D8 — positioning

README and `research/positioning.md`: codemap is the Python graph **and** the lab's measured map of the
field, served to the agent. Nothing is claimed as measured that the matrix does not mark `measured`. The
README states the counts the matrix renders.

### D9 — not in this design

- Running, installing or wrapping other tools (that is R1-C16's adapter route, unchanged).
- Popularity rankings or stars as a signal.
- An LLM in `advise`: it is a lookup over reviewed data.
- Data from private projects: the matrix is public and carries only what the public cards measured.

## Pre-registered expectations

Written before any code. Reconciled below after the run; anything unlisted is a surprise.

| # | Expectation | Fails if nothing was done? |
|---|---|---|
| E1 | The matrix holds every one of the 13 carded tools, each with ≥ 1 claim `measured`, `probed` or `rejected` whose evidence resolves; every tool named in the project-C memo's section 6 (jscpd, semgrep, bandit, knip, radon, lizard, GitNexus, CodeGraph, import-linter) is present, the uncarded ones as `read` | yes |
| E2 | `codemap advise "ts call graph"`: codemap `none`; GitNexus and CodeGraph listed as `read` for TypeScript, **not** `measured`; exit 0 | yes |
| E3 | `codemap advise import-gate`: codemap `covered` with a test id that exists; import-linter first among tools, `measured`, its summary carries 266/266 and 45/45 | yes |
| E4 | Mutations each turn the suite red, the control stays green: (M1) an evidence anchor renamed; (M2) a `measured` claim without `evidence`; (M3) `codemap_tests` naming a test that does not exist; (M4) `matrix.toml` edited without re-rendering `matrix.md`; (M5) a feed item naming an unknown tool; (M6) a status outside the vocabulary | yes |
| E5 | `--refresh --from` a local server: a newer valid catalog → `source: refreshed`; an older one → packaged, with the reason; an invalid one → packaged, with the reason; no server → packaged, exit 0 | yes |
| E6 | `releases.py` on the real registries returns a latest version for every watched tool or names the failure; nothing is skipped in silence | yes |
| E7 | MCP: `query("web/app.ts")` not found with `outside_graph.language = typescript`; `query("no_such_python_name")` not found **without** `outside_graph`; the server lists 29 tools; `advise` answers through MCP | yes |
| E8 | bquant and bquearch: graphs and `check` output identical to 0.0.39 (nothing in the graph changes) | no (stays) |
| E9 | devkit on a clone of bquant: `status` reports the block outdated (v2 → v3), `update` rewrites only the block, which now names `advise` | yes |
| E10 | `codemap advise --root` on a repository with Python and TypeScript names TypeScript and the needs codemap does not cover for it | yes |
| E11 | The scouting routine exists, its first run produces a reviewable change with ≥ 1 item, and the change carries no private names | yes |

## Reconciliation (2026-11-21)

| # | Result |
|---|---|
| E1 | ✅ with a correction to the expectation: `research/tools/` holds **12** cards, not 13 (the earlier count included the README). All 12 are in, each with a hands-on claim whose evidence resolves. grimp and scip-python carry claims measured inside other cards. All nine memo tools are present; the six without a card are `read` only. |
| E2 | ✅ `advise "ts call graph"` → `multi-lang-graph`, codemap `none`; GitNexus and CodeGraph `read`, with "only Python measured" in the summary. |
| E3 | ✅ codemap `covered` with two existing tests; import-linter first, `measured`. Its summary first lacked 266/266: those numbers were on grimp's `py-imports` claim. The gate's claim now states the graph under it (grimp, 266/266, 45/45), which the card supports. |
| E4 | ✅ M1–M6 in memory, each named by its guard. Code mutations K1–K5 are each red and the control is green: the session hint, status requirements, anchor check, the dotted-name rule and refresh validation. |
| E5 | ✅ against a local server: not newer → kept; invalid → refused, packaged served; newer feed → `source.feed: refreshed`; no server → reason, exit 0. A corrupt cache falls back too. |
| E6 | ✅ 48 watched tools. First run: 45 versions and 3 named failures, which were repositories with no releases and no tags. The fix falls back to the last commit; the second run had 0 failures. 36 claims show drift: import-linter is measured on 2.15 and the latest is 2.17, CodeGraph 1.6.0 vs 1.6.4. |
| E7 | ✅ on a live MCP spawn: 29 tools; `query("web/app.ts")` → `outside_graph.language = typescript`; `query("no_such_python_name")` has no `outside_graph`; `advise("duplicates")` answers; `answer_format` 11. |
| E8 | ✅ graphs: bquant 3408/10014 and bquearch 3475/9696 nodes/edges are identical to 0.0.39. **Surprise:** the `check` markdown differs in one line, `answer format 10` → `11`. It follows from the bump in D4 but was not listed. |
| E9 | ✅ on a clone of bquant installed by 0.0.39 (v2): `status` exit 1 with "outdated", and `update` rewrote only the block, which now names `advise`. **Surprise:** the first render named `shell` among the languages. Shell scripts are glue, so they are no longer named in the block; the CLI still counts them. |
| E10 | ✅ `codemap advise --root` on Python + TypeScript names `typescript 1` and `multi-lang-graph`. |
| E11 | ✅ The routine was created and its first run was fired by hand (158 s, Sonnet 5.5). It pushed `scout/2026-11-21`: two tools new to the catalog (fallow, roam-code), `read` only, with two `verified: false` news items; the README counts were updated and the advise tests passed there. No private names. Maintainer review checked both repositories (license, description, languages) and merged. Corrections: roam-code `languages = ["multi"]` became the real list, a `multi-lang-graph` claim was added, and the news is now verified. **Found by the run:** the GitHub API refuses anonymous calls from the cloud (15 × 403); the watcher now falls back to the version tags over `git ls-remote`, or the HEAD commit. `--report` imported codemap only with `PYTHONPATH`, and now puts the checkout on the path. The cloud image has two interpreters, so the prompt names `python -m pip`. |

**Surprises beyond E8/E9:**
- **Delivery defect, found reconciling E11.** The matrix `as_of` was a date. After a same-day scouting merge,
  `--refresh` would have taken the newer feed but not the matrix. The feed names the two new tools, the pair
  then fails its schema, and the whole cache was refused. Both files now carry an ISO timestamp, which 0.0.40
  already reads, and a guard keeps it so. The fix ships through the data on `main`, so no release is needed.
- A dotted Python name such as `a.b.c` first read as a C file. Without a path separator, only a single-dot
  name with an extension of two letters or more is now a file. The test lists both forms.
- `news(days=10**6)` overflowed the date ordinal; the window is clamped.
- One extracted claim was promoted too far: Understand-Anything × `py-callers` came from a 9-file pilot and is
  now `probed`. Two tools without a known URL were dropped rather than given a guessed one.
