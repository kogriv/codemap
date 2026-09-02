# OntoIndex

**Verdict:** learn (strong peer; the closest epistemic model in the field so far)  ·  **Feeds:** R1-C13, R1-C28, R1-C14  ·  **Card status:** hands-on (2026-09-01)

**Scope:** `sha256:300e0a010e351d0a91a7e006c3cc18047d7d400c94a525ddbe727f796a5e47d2`
(R2 benchmark `bquant.scope.json` — 280 files, 207 .py / 73 .md, bquant@cb89a24) ·
run mode: **materialized** (byte-identical staging via `_scope/materialize.py`, `scope_id` verified
`== canonical ✓`; a second identical staging was materialized for the clean-room A/B).

The pinned commit needed one step no earlier card needed: the dogfood tree has moved far past `cb89a24`, so
materializing from the live checkout would have produced a different `scope_id`. The staging was built from
`git archive cb89a24 | tar -x` into a scratch directory and materialized from **that** — read-only on the
target repository, and the harness re-derived the canonical id from it unchanged. Any future card has to do
the same; the spec's `root` still points at the live tree, which now drifts.

One file — `bquant/data/samples/embedded/tv_xauusd_1h.py` (538 KB) — is skipped by OntoIndex's default
512 KB cap. Not a scope deviation: the file is in the manifest, OntoIndex declines to parse it **and says
so**, both at index time and inside every later answer (see *Honesty*).

## Identity
- **Repo / site:** `ontograph/ontoindex` (GitHub, 40 ★ at measurement)
- **License:** **AGPL-3.0-or-later**. (codemap: MIT. GitNexus, its ancestor: PolyForm NC.) Descends from
  GitNexus with attribution preserved in `NOTICE` — the same tree-sitter + LadybugDB spine, reworked and
  extended well past it.
- **Last commit / release:** installed **2.2.0** (2026-09-01). The README documents `2.1.4` as latest.
- **Stack / language:** TypeScript / Node.js **22.12–25.x** (the range is enforced by the installer, with a
  reason: `commander@15` needs ≥22.12, and Node ≥26 is untested against the vendored tree-sitter runtime).
  Tree-sitter ASTs → **LadybugDB** embedded graph store; BM25 + optional local embeddings with RRF.
  14 languages (TS/JS/Py/Java/Kotlin/C#/Go/Rust/PHP/Ruby/Swift/C/C++/Dart).
- **Install (exact command):** `wget -qO- .../scripts/install-ontoindex-latest.sh | bash` · reproduced? **yes**
  — 489 MB, ~7 min, plus a prefetch of two LadybugDB extension binaries (`libfts`, `libvector`) verified
  against a published `SHA256SUMS.txt`.
  **The README's second install path does not exist:** `npm install -g ontoindex@2.1.4` returns
  **404 from the registry** — the package is not published there. The shell installer resolves the latest
  **GitHub release tarball** and hands *that* to npm. It works, and it is the only path that works.

## What it is
A code-graph engine for agents: tree-sitter parse → symbols, calls, imports, inheritance, routes, doc
sections → LadybugDB → Leiden **communities** → **process/flow tracing** → BM25/vector retrieval.
Interfaces: **CLI**, **MCP** (60+ tools), HTTP server, browser UI. Source-only (never imports or builds the
target), and git-*flavoured*: indexing runs fine with `--skip-git`, but `audit` and `review diff` require a
repository, and commit mining (`CO_CHANGED_WITH`) is silently empty without one.

Surface is unusually wide for this field: besides `analyze`/`query`/`context`/`impact` it ships `audit`
(architecture + dead code + drift), `check` (repo checks from `.ontoindex/checks.yml`), `review diff`,
`export` (snapshot artifacts), `packs` (user-authored analysis suites), `wiki`, `memory`, and `cypher` —
raw Cypher against the graph, which is what made several findings below measurable from outside.

## Coverage vs codemap

| Capability | codemap | OntoIndex |
|---|---|---|
| symbol lookup (T1) | ✅ | ✅ (+ native ambiguity status; **0-based line numbers**) |
| callers/callees (T2) | ✅ | ◐ via `context` (**silently capped at 30**) · ✅ via `impact` |
| impact / blast-radius (T3) | ✅ | ✅ (set-identical to codemap on both probes) |
| signature-change surface (T4) | ✅ | ✖ (no parameters on nodes, no arguments on edges) |
| architecture / layers (T5) | ✅ | ◐ via `audit` (git-required); the two graph-central `report` views are broken |
| determinism | ✅ | ◐ (see below — three different answers to "is it deterministic") |
| MCP | ✅ | ✅ (60+ tools) |
| languages | Python | 14 (tree-sitter) |
| license | MIT | AGPL-3.0-or-later |

## Hands-on measurements (target: bquant @ cb89a24, the R2 scope)

**Index build.** OntoIndex: 280 files (279 parsed, 1 over the size cap) → **10 745 nodes / 20 232 edges /
254 clusters / 300 flows** in **49.1 s** cold (**22.3 s** on the second staging, warm caches), **1.0 GB**
peak RSS, **62 MB** `.ontoindex/`.
codemap on the same 280 files: **4 225 nodes / 11 502 edges**, **11.4 s** fast tier (117 MB RSS) /
**111.2 s** deep tier (325 MB), **5.4 MB** JSON.

Node counts are not comparable and the reason is a finding, not a caveat: OntoIndex's graph includes
markdown heading trees (2 132 `CONTAINS … markdown-heading` edges), Leiden community membership (1 854),
process steps (1 368) and a recursive summary tree (400) — layers codemap does not model at all. codemap's
count includes 1 007 `column` nodes and 47 `doc` nodes, which OntoIndex does not model. On the part both
model — symbols and calls — they agree far more closely than the totals suggest (see T3).

| Task | Correct? | Cost | Latency | Deterministic? | Notes |
|---|---|---|---|---|---|
| T1 where defined (`analyze_zones`) | ✅ (lines off by one) | 2.4 KB, 1 call | 6.6 s cold / 2.2 s warm | ✅ | Both definitions found, and **`status: "ambiguous"`** with an explicit "use uid/file_path/kind to disambiguate" — the second tool measured that flags ambiguity rather than ranking it away. Returns `uid`s and `suggestedNextCalls`. But `startLine` is **121** and **717** where `def analyze_zones` is on **122** and **718**: the field is 0-based and named as if it were not. |
| T2 callers (`MACDZoneAnalyzer`) | ◐ | 13.9 KB, 1 call | 2.2 s | **✖** | `context` returns `incoming.calls` = **30 of the 57 real callers**, `incoming.imports` = 22 file-level importers — and `contextCompleteness.truncated: **false**`. Two index builds of byte-identical input return **different 30-element subsets** of the same 57. Under the cap it is exact: `NotebookSimulator` 28 = 28, `calculate_macd` 6 = 6. |
| T3 impact (`MACDZoneAnalyzer`) | ✅ | 19.5 KB, 1 call | 1.9 s | ◐ (set-stable, order-unstable) | `impact --include-tests --depth 2`: 113 impacted, `risk: CRITICAL`, per-edge `relationType`/`confidence`/`provenance`. **At depth 1 the CALLS set is exactly codemap's 57 — zero difference in either direction.** Repeated on `get_sample_data`: **78 = 78**. Defaults matter: without `--include-tests` the same call returns 55 and never mentions that a test suite exists. |
| T4 sig-change (`analyze_zones`) | ✖ | — | — | — | Structural, and checkable from outside: `MATCH (n:Function) RETURN keys(n)` → `id, name, filePath, startLine, endLine, isExported, content, description`; `MATCH ()-[r:CodeRelation]->() RETURN keys(r)` → `type, confidence, reason, step`. No parameter list, no call-site arguments. codemap's `call_contract` answers 61 sites with posargs/kwargs per caller. **Five hands-on cards, five tools, T4 still unanswered by anyone but codemap.** |
| T5 architecture | ◐ | — | 17.0 s (`audit`) | not measured | `audit` (needs git) emits Import Cycles, Coupling Outliers, Boundary Violations, Verification Gaps, Dead Code, Recent Drift — the right *shape*. The contents do not survive reading: see below. The two `report` views that would answer the graph-central question fail on a Cypher the store cannot parse and print "no hubs found". |

### T2, in detail: a completeness field that says `false` while dropping 27 of 57

This is the finding worth the card. `context` is the tool's "360-degree view of a code symbol", and it
carries a block literally named `contextCompleteness` with a `truncated` boolean. On `MACDZoneAnalyzer` that
boolean reads `false` and the list holds 30 callers where 57 exist. On `get_sample_data`: 30 where **78**
exist — 48 dropped, still `truncated: false`. On symbols under the cap the same op is exact, which is what
makes the failure invisible: nothing in the response shape differs between "here are all 6" and "here are 30
of 78".

The cap is not the whole of it. Two indexes built from **byte-identical input** return different 30-element
subsets — `scripts.analysis.run_macd_analysis…` and `…test_hypotheses` in one run, two `test_macd_analyzer`
methods in the other. So the missing set is not stable across builds, and a caller diffing two runs sees
callers appear and vanish with no source change.

I spent a while looking for a rule behind which callers survive — file position, call form, nesting — and
there is none visible: hits and misses in the same file are syntactically identical
(`analyzer = MACDZoneAnalyzer()`, same class, same indentation). The rule is a cap plus an unstable order,
not a parse limitation, and the proof is that `impact` — over the same graph — returns all 57.

In codemap's own vocabulary this is R1-C28 (`limit` must always be declared, including zero) and R1-C23
(*unknown ≠ none*) violated in the same field: the answer is cut, and the field that exists to say so says
the opposite. We have shipped that bug's cousin twice; seeing it in a tool that otherwise labels everything
is a reminder that a completeness field is only worth what its computation is.

### T3, in detail: two independent graphs, the same 57

`ontoindex impact MACDZoneAnalyzer --include-tests --depth 2`, depth-1 CALLS edges, normalized to dotted
ids, against `codemap callers` on the deep graph: **57 vs 57, set-identical, no element on either side
alone.** On `get_sample_data`: **78 vs 78**. Two engines that share no code path — tree-sitter + LadybugDB
against griffe + jedi — agreeing exactly on a 57-element and a 78-element answer is the strongest external
check either has had.

**Re-verified 2026-09-02 against our own tier noise (R1-C42).** The codemap side of that comparison came
off a deep build, and the deep tier is not byte-stable — so a set-identity claim resting on one build is
resting on a sample. Three deep builds of the pinned scope: the two artifacts were **not** byte-identical
(one `accesses` edge of 12190 came and went), and the caller sets were **57 and 78 in all three, the same
elements each time**. The noise is real and did not touch the quantity the claim stands on. Stated because
the difference between "we got lucky" and "we checked" is exactly what this card is for. It also gives codemap something the earlier cards did not: CodeGraph's 58 needed a
paragraph to adjudicate one disputed entry; here there is nothing to adjudicate.

Two caveats kept from the same run. Their `--depth` default is **3** and tests are **excluded by default**:
`impact MACDZoneAnalyzer` alone reports 55 impacted where the same call with `--include-tests` reports 149.
A user asking "what breaks" gets an answer with the test suite structurally removed. And the depth-1 set is
stable while its **order** is not — 384 positional differences between two runs whose sets match exactly,
which makes the JSON unusable as a diff artifact even though the answer is identical.

### T5, in detail: the right sections, and what is inside them

`audit` reports **"Import Cycles (6 detected)"**. Reading them:

- **Cycle 1** is 38 `.md` files chained through markdown links — a documentation cross-reference ring,
  under a heading that says "Import".
- **Cycles 4 and 6** are *function* names (`_load_json → _load_parquet → _load_pickle → load`) — call
  cycles, in the same list.
- **Cycle 2** chains `__init__.py → __init__.py → __init__.py → …` — rendered by **basename**, so which
  packages participate is unrecoverable from the report.
- **Cycle 5** (`registry.py → config.py → logging_config.py`) is printed as a path that never closes.

codemap on the same scope: **1** import cycle, named in full module ids, plus **44** cycles closed only by a
function-local import, listed separately with the reason they do not break at import time — and the
distinction stated in the report itself. The two "6" and "45" are not competing measurements of one quantity;
they are different quantities under one label.

"Coupling Outliers (instability > 0.8)" has the same shape of problem: rows keyed by **community name**, with
`Unit` appearing four times and `Data` three, every row `Ca 0` and therefore every instability exactly 1.00.
codemap's coupling is per module with real afferent counts (`core.logging_config`, Ca 96). "Verification Gaps
(0) — No uncovered files detected" is a strong claim over a 90-module core and 81 test files, and nothing in
the report says how it was computed.

### The bug worth reporting upstream

`ontoindex report hubs` and `ontoindex report surprising-connections` — the two graph-central discovery
views — both print:

```
no hubs found (index missing, empty graph, or no connected nodes)
```

on a graph with **10 745 nodes**. The real cause is in `warnings`, below the answer:

```
degree query failed: Prepare failed: Parser exception: Invalid input <MATCH (s) … AND NOT s:>:
expected rule oC_SingleQuery
"         AND NOT s:File AND NOT s:Process AND NOT s:Community"
```

The vendored LadybugDB Cypher parser does not support label negation (`NOT n:Label`), confirmed directly:
`ontoindex cypher "MATCH (s) WHERE NOT s:File RETURN count(s) AS n LIMIT 10"` fails with the same parser
exception, while `MATCH (s) RETURN count(s)` returns 10 745. Exit code is **0** and `--json` returns
`"hubs": []`, so a pipeline reading the JSON sees a well-formed empty answer.

Every element of this is the failure family this project keeps cataloguing: a failure rendered as an empty
result, with three innocent explanations offered and the real one demoted to a warning nobody parses.
Reproducible on 2.2.0, Linux x86-64, Node 24.12.

## Quality (on the covered part)

- **accuracy** — high where it answers: T3 set-identical to codemap on both probes, T1 correct modulo the
  off-by-one. The `context` cap is a presentation defect over an accurate graph, not an extraction defect.
- **determinism** — three different answers depending on what you measure, and that spread is itself the
  result: the **graph** is not reproducible (10 745 / 20 232 / 254 vs 10 747 / 20 227 / 256 clusters from
  byte-identical input), `impact` is **set-stable but order-unstable**, and `context` is **neither**.
  codemap's canonical JSON is byte-identical across runs and CI asserts it.
- **cost** — 2–20 KB per answer, one call each; comparable to codemap's compact MCP payloads.
- **speed** — 49 s cold index vs codemap's 11.4 s fast / 111 s deep; queries 2–7 s vs codemap's warm-serve
  sub-second. Its index does much more per pass (communities, flows, summaries, BM25).
- **setup friction** — medium-high: 489 MB, ~7 min, one documented install path that 404s.
- **language coverage** — 14 vs codemap's 1.
- **license** — **AGPL-3.0-or-later**: readable and learnable, but nothing from it can be vendored into an
  MIT tool, and an integration would raise the network-copyleft question for anyone serving it.
- **interface** — the widest measured: CLI + 60 MCP tools + HTTP + UI + user-authored packs.
- **honesty-of-claims** — the best in the field on labelling, and the worst single lapse measured. Both are
  below.

## Honesty: what it labels, and where the labelling breaks

What it does that nobody else measured does:

- **Every edge carries the method that produced it and a confidence for it.** `CALLS` splits into
  `same-file` **0.95** (1 082 edges), `import-resolved` **0.9** (2 324) and `global` **0.5** (321) — the
  weakest tier being name-matching, exactly the resolution codemap refuses to emit unflagged. `IMPORTS`
  from markdown links carry **0.8**; community membership is stamped `leiden-algorithm`; process steps
  `trace-detection`. A caller can filter `confidence >= 0.9` and get a high-precision subgraph. codemap has
  a per-answer epistemic label and a per-edge `resolution`; this is finer, and the *reason* string is the
  part we lack.
- **The `report` commands announce their own lossiness in their `--help`**: "RANKED DISCOVERY VIEW — not a
  complete impact analysis… It never replaces or suppresses complete impact output from `ontoindex impact`",
  the JSON carries `isRankedDiscovery: true`, and the footer routes the reader to the authoritative op.
  That is codemap's "measurements, not verdict" rule applied to command design.
- **Skipped input survives into the answers.** The one file over the size cap is reported at index time
  *and* in the `warnings` of every `context`/`impact` response, with the env var that would include it.
  codemap records skipped inputs in `provenance.inputs.skipped` and raises `unread_inputs`; OntoIndex
  additionally repeats it at every read, which is stricter.

And where it breaks: `contextCompleteness.truncated: false` on a list cut from 78 to 30, and "no hubs found"
on a parser error. Both are in the same product as the labelling above, which is the uncomfortable lesson —
a project can hold the discipline in three places and lose it in the fourth, and the fourth is not marked.

## Разбор

- **What we'd take.**
  1. **Per-edge resolution *reason* with a graded confidence** (`same-file` 0.95 / `import-resolved` 0.9 /
     `global` 0.5). codemap's edges carry `resolution`, which says *whether* a call resolved, not *by what
     route* or *how much to trust it*. Naming the route is cheap for us — the extractor already knows which
     branch produced the edge — and it makes "give me only high-confidence callers" expressible. → new
     R1-C candidate.
  2. **`earliest_broken_step` on affected flows.** Their `impact` reports, per affected process, at which
     step the break first lands (`affected_process_count`, `total_hits`, `earliest_broken_step`). codemap
     has `flows`; it does not say where in a flow a change first bites. → new R1-C candidate.
  3. **Routing honesty in `--help`, not only in output.** "This view is lossy; the authoritative answer is
     `X`" belongs in the help text an agent reads before choosing the tool.
- **What we'd do differently, and why.** Their `context` and `impact` disagree about the same graph because
  one caps and the other does not. codemap's rule — every limited op returns `{applied, returned, total,
  truncated}` **always, including when nothing was cut** (R1-C28) — exists precisely so two ops cannot tell
  a caller different stories. Keep it, and keep computing `truncated` from the same numbers the cut used;
  a completeness field maintained by hand is worse than none, because it converts an unknown into a
  confident `false`. Likewise, we would not put doc-link rings, call cycles and import cycles in one list
  called "Import Cycles" — codemap separates hard import cycles from lazily-closed ones and says why, and
  that separation is the only reason its "1" and "44" are actionable.
- **What the author knows that we didn't.** That a code graph can carry *why* each edge exists as a first-class
  string, and that the cost of doing so is one column. Also the ergonomic invention we have no analogue for:
  `suggestedNextCalls` — every answer proposes the exact next tool call, with the resolved `uid` already
  filled in, which is a real token saving for an agent that would otherwise round-trip to resolve a name.
- **What we did NOT check.** The MCP surface (60+ tools) — everything here is CLI, so tool-level payloads and
  any per-tool caps are unmeasured. Embeddings and semantic retrieval (`--embeddings`, off by default) were
  not built, so BM25/vector quality is untested. `check`, `packs`, `wiki`, `export`, `review diff`, `pr` and
  `group` were read but not exercised. Incremental re-index (`--experimental-file-delta`) untested. No
  multi-language run: Python only. `audit --annotate` needs an LLM and was not run. Cycle recall was compared
  by *reading* their six against our forty-five, not by scoring both against an independent truth set — the
  CodeGraph card did that scoring and it is what turned a comfortable comparison into a real finding; the
  same work is owed here.

## Verdict & backlog effect

**learn (strong).** AGPL closes `wrap` and `integrate` regardless of merit — nothing here can be vendored,
and serving it would carry network copyleft into anyone's stack. What it gives us is a better epistemic
model to copy in kind (not in code) and a cross-validation of our own call graph that no other card has
produced.

- **Confirms R1-C13** (epistemic labels): a shipped, graded, per-edge implementation with the resolution
  method named — our per-answer label is coarser.
- **Confirms R1-C28** (`limit` block always declared) with the strongest counter-example measured: a
  `truncated: false` over a 78→30 cut.
- **Reranks R1-C14** (differentiators): determinism moves *up* — the graph itself is not reproducible here —
  while "epistemic honesty" can no longer be claimed as ours alone. License (MIT vs AGPL) and the deterministic,
  diffable artifact remain.
- **New candidates:** per-edge resolution reason + graded confidence; `earliest_broken_step` for flows.
