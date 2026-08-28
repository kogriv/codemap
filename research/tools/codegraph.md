# CodeGraph (colbymchenry)

**Verdict:** learn-only (strong) · **Feeds:** R1-C28 (new), M3.2, R1-C13, R1-C6, R1-C14 ·
**Card status:** hands-on

**Scope:** `sha256:300e0a010e351d0a91a7e006c3cc18047d7d400c94a525ddbe727f796a5e47d2` (R2 benchmark
`bquant.scope.json` — 280 files, 207 .py / 73 .md, bquant@cb89a24) · run mode: **materialized**
(staging verified `== canonical ✓`; a second identical staging was materialized for the clean-room A/B)

> The single most-adopted tool in the field surveyed so far — **68 420 ★ / 4 362 forks**, seven months
> old — measured on the same 280 files as every other card. It is not a smaller peer: on the questions
> it answers it is fast, correct, and in one case finds a reference codemap classifies differently.
> The differences that matter are about *what a caller is* and *what an answer admits about itself*.

## Identity

- **Repo / site:** [colbymchenry/codegraph](https://github.com/colbymchenry/codegraph) ·
  [docs](https://colbymchenry.github.io/codegraph/) · npm `@colbymchenry/codegraph`
- **License:** MIT
- **Version measured:** **1.6.0** (npm, released 2026-08-26). Repo created 2026-01-18;
  68 420 ★ / 4 362 forks / 445 open issues at time of measurement (2026-08-28).
- **Stack:** native **Rust kernel** with tree-sitter grammars compiled in (20 languages), Node CLI/MCP
  wrapper with a bundled runtime, **SQLite + FTS5** store. (GitHub reports the repo language as `C` —
  that is the vendored runtime, not the analyzer.)
- **Install (exact command):** `npm i --prefix <dir> @colbymchenry/codegraph` — **reproduced: yes**,
  first try, no build step, **283 MB** on disk. The advertised `curl … | sh` bootstrap was deliberately
  not used, and neither was `codegraph install` — that subcommand rewrites the MCP config of every
  agent it detects (Claude Code, Cursor, Codex, Copilot…), which is not something a benchmark should do
  to the host machine. Everything below runs from the CLI directly.
- **Telemetry:** **on by default**, asked at install time. It honours `DO_NOT_TRACK=1` — verified, not
  assumed: `codegraph telemetry` reported `disabled (DO_NOT_TRACK environment variable)`. It still
  writes `~/.codegraph/telemetry.json`. All measurements below ran with telemetry off.

## What it is

A pre-built symbol graph aimed squarely at agent consumption. The Rust kernel parses each file once,
extracting nodes (function/method/class/variable/import/file) and edges (calls, imports, extends,
implements); a resolution pass then links references to definitions and adds framework-specific and
dynamic-dispatch hops. Everything lands in `.codegraph/codegraph.db` (SQLite, WAL, FTS5). A file
watcher keeps it incrementally in sync — nominally a 2-second debounce, in practice **adaptive**: a lone
save fires after a 300 ms quiet window, bursts coalesce on the full 2 s.

There is a **third interface** beyond CLI and MCP — an importable library — and it carries queries the
other two do not expose. The first pass of this card missed it; see the library section.

The product thesis is unusual and worth stating plainly, because it is the opposite of codemap's:
**one big tool beats a menu of small ones.** The MCP surface exposes a *single* tool by default,
`codegraph_explore`, which answers "how does X work" with verbatim source, call paths and a blast-radius
summary in one call. Seven narrower tools (`node`, `search`, `callers`, `callees`, `impact`, `files`,
`status`) exist and work but are **unlisted** unless `CODEGRAPH_MCP_TOOLS` re-enables them. codemap ships
the opposite bet — 31 ops, 28 of them exposed.

Source-only: yes, it never builds or runs the target. Deterministic: see below — partly.

## Coverage vs codemap

| Capability | codemap | CodeGraph 1.6.0 |
|---|---|---|
| symbol lookup (T1) | ✅ | ✅ (+ fuzzy neighbours, + inline signature) |
| callers/callees (T2) | ✅ | ✅ symbol-level |
| impact / blast-radius (T3) | ✅ | ✅ (more nodes, untagged) |
| signature-change surface (T4) | ✅ | ✖ blast radius, not an argument contract |
| architecture / layers (T5) | ✅ (recall 11% — R1-C29) | ✖ on CLI/MCP. **Library-only** `findCircularDependencies()` — 136 reported, 6 of 9 real: precision 4%, recall 67% (see below); no layers, no violations |
| determinism | ✅ answer **and** artifact | ◐ answers stable except one timestamp field; artifact binary |
| provenance by root role | ✅ declared roots | ✖ heuristic, and it misfires (see T3) |
| docs as first-class refs | ✅ | ✖ `.md` not indexed at all |
| MCP | ✅ 28 tools | ✅ **1** tool by default (7 more opt-in) |
| incremental sync | ✅ `build --incremental` **+ watcher since M3.2** (this разбор is why) | ✅ + file watcher |
| languages | Python | 20 (Rust kernel) |
| license | MIT | MIT |

## Hands-on measurements (target: bquant @ cb89a24, the R2 scope)

**Index build.** codegraph: **207 files → 5 113 nodes / 15 247 edges in 1.4 s** (3.95 s wall incl.
startup; 858 ms on the second staging), 337 MB peak RSS, **15.46 MB** SQLite.
codemap on the same 280 files: **4 225 nodes / 12 136 edges**, **12.3 s** fast tier / **95.8 s** deep
tier, 327 MB peak RSS, **5.5 MB** JSON.

Two things make those node counts non-comparable, and both are findings rather than caveats:
codegraph indexed **207 of the 280 scope files** — the 73 `.md` are outside its model entirely — while
codemap's count includes 47 `doc` nodes and 1 007 `column` nodes from layers codegraph has no analogue
for. On raw speed codegraph is **~9× faster than codemap's fast tier and ~68× faster than its deep tier**,
which is what a compiled kernel without type inference buys.

| Task | Correct? | Cost | Latency | Deterministic? | Notes |
|---|---|---|---|---|---|
| T1 where defined (`analyze_zones`) | ✅ | 7.1 KB, 1 call | 0.33 s | ◐ | Finds both real definitions (`analyzer.py:122`, `pipeline.py:718`) — identical lines to codemap — plus fuzzy neighbours (`analyze_zones_visually`) and an inline `signature`. Ranks the *method* above the flagship function. Ambiguity is visible as a ranked list but **is never flagged as ambiguity**; codemap returns `defined_at` with 2 entries and carries a `resolved.ambiguous` signal. |
| T2 callers (`MACDZoneAnalyzer`) | ✅ (1 disputed) | 1 call | 0.33 s | ✅ byte-identical A/B | **58 symbol-level callers** vs codemap's 57. codemap's 57 are a **complete subset** — they agree on every one. The extra is `tests/unit/test_macd_analyzer.py::test_convenience_functions`, which does `assert isinstance(analyzer, MACDZoneAnalyzer)` — a *reference*, never a call. See "the disputed one" below. |
| T3 impact (`MACDZoneAnalyzer`) | ✅ | 14.8 KB, 1 call | 0.36 s | ✅ byte-identical A/B | 89 affected / 146 edges at depth 2, flat `{name, kind, filePath, startLine}`. codemap: 69 refs, each tagged `type` (calls 60 / references 9), `root` (core 3 · docs 7 · examples 1 · scripts 2 · tests 56), `distance` (1: 66, 2: 3), plus `risk: high`. More reach, less structure. |
| T4 sig-change (`analyze_zones`) | ✖ | 26.5 KB, 1 call | 0.41 s | not measured | `explore` returns blast radius + verbatim line-numbered source — genuinely useful, and *adjacent*, but it never says how each call site passes its arguments. codemap's `call_contract` returns per-caller `posargs` / `kwargs` / `splat` / `callsites` (e.g. `examples.02a_universal_zones.main` → 9 call sites, 1 positional). Different question. |
| T5 architecture | ✖ (CLI) · ◐ (library) | — | 0.29 s · 76 ms | — | No layers, cycles or violations anywhere in the CLI or the MCP tools; `files` prints the file tree. The **importable library** does expose `findCircularDependencies()` — **136 reported where 9 are real**, on false call edges; its recall (67%) nonetheless beats codemap's (11%), whose import map is module-level only (see the library section). Still no layers, no violations, no coupling report. codemap's `report architecture`: 89 core modules, 634 import edges, 8 layers, 13 inter-layer dependency counts, layer violations. |

### The disputed one (T2)

The single caller codegraph reports and codemap does not is worth the paragraph, because it is not a
scoring difference — it is a definitional one, and codemap's own history says so.

```python
# tests/unit/test_macd_analyzer.py:415
assert isinstance(analyzer, MACDZoneAnalyzer)
```

The symbol is passed **as a value**. `codegraph callers --help` says "Find all functions/methods that
**call** a specific symbol", so by its own contract this is a reference counted as a call. codemap keeps
the two apart and does surface it — as `type: "references"` inside `impact`, not inside `callers`.

That exact mechanism — *a function passed as a value* — is the first of the three that made codemap's
own `dead-code` `high` band wrong 39% of the time (bquant issue #7). One tool learned to separate
reference from call; the other has not yet needed to.

### Silent truncation — the finding that nearly became a false one

The first T2 run returned exactly **20** callers, all of `kind: "file"` at `startLine: 1`. Read at face
value that says CodeGraph has a *file-import* model of callers, like GitNexus — a clean, publishable,
**wrong** conclusion.

`--limit` defaults to `20`. At `--limit 500` the same query returns **79 entries — 55 methods, 3
functions, 21 files** — a genuinely symbol-level answer. The file-kind rows simply sort first, so the
default cut the answer exactly along the line that misrepresents the model.

Nothing in the JSON says so: the payload is `{symbol, callers}` with **no total, no `truncated` flag**.
This is the *confident-partial* sibling of the confident-empty class codemap spent a month hunting —
and the second time in this research track that a default nearly produced a false verdict about someone
else's tool (the first was graphlens's `ty` binary being off `PATH`). The rule that caught both is the
same: when a number looks round, check whether it is a limit.

**Verified to the source before reporting** (`src/bin/codegraph.ts`, MIT, tag at `6a056ec`):

```ts
const limit = parseInt(options.limit || '20', 10);              // :1957
...
const limited = allCallers.slice(0, limit);                     // :1991
if (options.json) {
  console.log(JSON.stringify({ symbol, callers: limited }, …)); // :1994 — no total
} else {
  console.log(chalk.bold(`\nCallers of "${symbol}" (${limited.length}):\n`)); // :1998
}
```

Two things this settles. `allCallers.length` — the true total — is **in scope at the truncation site
and discarded**, so the fix costs nothing. And the human-readable header prints `limited.length`, i.e.
it renders `Callers of "MACDZoneAnalyzer" (20)` when there are 79: **not a missing marker but an
affirmatively wrong count.**

Scope of the defect, measured rather than assumed:

| symbol | default answer | full answer | symbol-level callers hidden |
|---|---|---|---|
| `MACDZoneAnalyzer` | 20 (0 symbols) | 79 (58 symbols) | **all 58** |
| `ZoneInfo` | 20 (0 symbols) | 62 (33 symbols) | **all 33** |
| `ZoneFeaturesAnalyzer` | 20 (11 symbols) | 51 (42 symbols) | 31 |
| `analyze_zones` | 20 (20 symbols) | 72 (49 symbols) | 29 |
| `get_logger` | 20 (20 symbols) | 104 (40 symbols) | 20 |

`getCallers` returns `imports`, `calls`, `references` and `instantiates` edges in one undifferentiated
list, and the file-kind rows (from `imports`) occupy the **first 21 positions**, so on a
sufficiently-referenced symbol a default-limit query returns *nothing but files*. Same code shape in
`callees` (`:2069`); `query` truncates 909 hits to 10 and returns a bare array, with no envelope a
total could even live in.

**Filed upstream as [#1639](https://github.com/colbymchenry/codegraph/issues/1639)** (2026-08-28), with
a 26-file minimal repro alongside the real-repository table. Building that minimal repro corrected one
of our own claims: there the survivors of the cut are all `function`, not `file` — so "file rows sort
first" is not a property of the tool, it is edge-insertion order, and what a default answer loses is
**arbitrary with respect to kind**. That is a weaker mechanism claim and a stronger defect: a consumer
cannot tell a complete answer from a slice of one.

**And the project already does this right on its main surface.** `codegraph_explore` — the one tool the
MCP server exposes by default — marks its own elisions inline (`+5 more`, `+27 more`). So this is not a
philosophical difference about honest partial answers; it is that pattern not being applied on the
`callers`/`callees`/`query` path. Checked against 400 upstream issues: no duplicate. The adjacent
[#1512](https://github.com/colbymchenry/codegraph/issues/1512) is a different defect in the same
function (same-named definitions merged, no `--file`).

### The library surface — the third interface, and nobody is using it

**Added 2026-08-28, on a second pass.** The first разбор measured the CLI and reasoned about the MCP
surface. The card's own Identity section says *"CLI + MCP + an importable library"* — and the library was
never opened. It should have been, because it changes an answer.

`main` is `npm-sdk.js` → the exported `CodeGraph` class, and it carries three methods that appear nowhere
on the CLI and nowhere in the MCP tool list:

```ts
findCircularDependencies(): string[][]   // src/graph/queries.ts:226 — DFS over file dependencies
findDeadCode(kinds?): Node[]             // src/index.ts:1818
getNodeMetrics(nodeId)                   // incoming/outgoing edge counts, per node
```

Grepped across their source: **none of the three is called anywhere else** — not by a CLI command, not by
an MCP tool. They are a public API their own product does not surface.

That matters for one of codemap's own claims. "No cycles anywhere" was true of the **CLI**, and the
coverage row above said it without that qualifier. On the library surface CodeGraph **does** answer *"is
there an import cycle?"* — the archetypal whole-graph question. So the claim had to be narrowed, and
this is what narrowing it looks like when the number is then measured:

| on the same staging | cycles reported | time |
|---|---|---|
| codemap `report architecture` | **1** — `zones.cache → zones.pipeline → zones.cache` | in-pass |
| CodeGraph `findCircularDependencies()` | **136** | 76 ms |

**That table was scored the wrong way, and the correction arrived the same day** — from
[issue #11](https://github.com/kogriv/codemap/issues/11), filed off a different target. Taking codemap's
answer as the reference is exactly the mistake this track exists to avoid. Scored instead against every
intra-package import, function-local ones included (AST walk, 88 modules, 266 edges of which **35 are
function-local**), there are **9** cycles on this tree:

| | reported | of the 9 true ones | precision | recall |
|---|---:|---:|---:|---:|
| codemap | 1 | 1 | **100%** | **11%** |
| CodeGraph (library API) | 136 | 6 | **4%** | **67%** |

codemap's import map is module-level only, so a `from x import y` written inside a function is invisible
to it — and that is precisely the import a developer writes *to break a cycle*. CodeGraph's much-criticised
mechanism is what bought it the recall: walking call edges means the call tier's understanding of
function-local imports comes along for free. **The over-reporting is still theirs and the framing problem
is still ours** — until #11, `report architecture` printed `_none — import graph is acyclic._` over a
partial map. Both are being fixed on our side as R1-C29
([gap](../../gaps/import_map_module_level_2026-08-28.md)); the point for this card is that the
"136 vs 1" line, read as a precision win, was flattering us by construction.

The 136 are not 136 findings. `getFileDependencies` — by its own source comment — deliberately does not
follow import edges; it walks *"the resolved calls/references/instantiates/extends edges"*. That graph
binds unqualified method calls **by name**, with no type inference, so it manufactures dependencies that
the imports contradict. Read straight out of their DB, the six `calls` edges that make
`core/config.py ⇄ core/cache.py` look like a cycle:

```python
# bquant/core/config.py:315   → resolved to MemoryCache::get in bquant/core/cache.py
mapped_timeframe = TIMEFRAME_MAPPING[data_source].get(timeframe, timeframe)
# bquant/core/config.py:615   → same
config = get_analysis_params('zone_features').get('swing_strategy', {})
```

Both are `dict.get`. **Six of six sampled edges into that method are false**, and `config.py` imports
nothing from `cache.py` at all — the reverse import (`cache.py:20 from .config import get_cache_config`)
is real and one-way. One of the reported "cycles" even runs through a research notebook
(`core/cache.py → research/notebooks/02_ind_factory.py`, from `method:stats` → `variable:values`).

The exposure is structural rather than incidental — the call-edge targets cluster exactly on the
polymorphic band that [`docs/accuracy.md`](../../docs/accuracy.md) §(b) measures grep against:

```
log 1654 · info 691 · warning 222 · step 164 · get 164 · debug 156 · error 155 · calculate 114
```

codemap asked the same question of the same symbol returns **0 callers** on the fast tier — it does not
resolve `.get` at all, and stamps the answer `epistemic: partial`. That is the trade in one line, now
measured from both sides: **CodeGraph over-reports and says nothing; codemap under-reports and says so.**
Neither is free, and the 9× speed is partly *bought* with this.

`findDeadCode()` returns **1 207** unreferenced symbols on the same staging as one flat list; codemap's
`report dead-code` bands its candidates by confidence with a whitelist and a printed blind-spot notice.
Their precision was **not** measured — only the shape is recorded here.

**Reportable? Not as anything new — and checking that is the whole discipline.** Searching their tracker
before writing a word:

- [#1566](https://github.com/colbymchenry/codegraph/issues/1566) (open, 0 comments) is *this exact
  defect*, filed for TypeScript: *"built-in `Map.get/set/has` calls resolve to unrelated project
  methods … An unresolved external/built-in call would be safer than a confident wrong project edge."*
  That is codemap's own honest-partial argument, made by someone else, in their tracker, first. Our
  finding is the **Python instance** of it — `dict.get`, same shape — not a new defect.
- [#888](https://github.com/colbymchenry/codegraph/issues/888),
  [#889](https://github.com/colbymchenry/codegraph/issues/889) and
  [#1012](https://github.com/colbymchenry/codegraph/issues/1012) (all open) ask for circular-dependency
  detection on the CLI/MCP. So the library-only surface is known to their community too — we were late
  to it, not first.

What is in neither thread is the join between them: the cycle finder those three issues want shipped is
computed from the edges #1566 is about, so exposing it before fixing them ships **136 cycles where there
is 1**. That was worth one comment on #1566 and nothing more — no new issue. Same rubric as `updatedAt`
below, applied in the other direction: report what fails the author's own standard, and *only* what is
not already on his list.

**Posted 2026-08-28** as [a comment on #1566](https://github.com/colbymchenry/codegraph/issues/1566#issuecomment-5451387031),
with two minimal Python repros. The second one is the contribution: **two files, fifteen lines, a one-way
import**, and `findCircularDependencies()` reports a cycle —

```
settings.py deps: [ 'cache.py' ]      # from DEFAULTS.get() resolving to LRUCache.get
cache.py    deps: [ 'settings.py' ]   # the real import
findCircularDependencies: [["cache.py","settings.py"]]
```

— which is the whole argument for fixing the edges before exposing the feature, in fifteen lines instead
of a 207-file table. **No response yet**; this card claims no verdict on the author's behalf.

### Determinism — split the way GitNexus's was

Two clean-room stagings, materialized from the same manifest, indexed independently:

- **Structure:** identical — 5 113 nodes / 15 247 edges, and the DB is the same size to the byte
  (16 211 968).
- **Artifact:** **different md5.** A 15.5 MB binary SQLite is not reviewable in a PR either way.
- **Answers:** `callers` and `impact` are **byte-identical** across the two builds. `query` is **not** —
  and the entire difference is one field, `updatedAt`, a wall-clock index timestamp carried on every
  node (`1787897858897` vs `1787898304266`). Strip it and the two answers are equal.

Confirmed to the source rather than inferred: `updatedAt` is set from `Date.now()` at index time
(e.g. `src/resolution/frameworks/go.ts:87`), persisted as `updated_at`, read back into the node
(`src/db/queries.ts:180`) — and **never used in a `WHERE`, `ORDER BY` or comparison anywhere in the
codebase**. It is not load-bearing for incremental sync; it simply rides out into `query` results. And
it is not file mtime: the two stagings were copied with `copy2`, so their source mtimes are identical,
while the field moved by the 7.4 minutes between the two index runs.

**This is a contract difference, not a defect, and it is not being reported upstream.** CodeGraph makes
exactly one byte-for-byte claim — that the Rust kernel's graphs match the reference engine's — and it
holds. Run-to-run reproducibility of an answer is *codemap's* commitment, not theirs; filing it as a bug
would be marking someone's homework against a rubric they never signed. It is recorded here because it
is the sharpest available illustration of what the two determinism contracts actually differ on, and
because it is the property R1-C25 exists to protect: *a stable output is worthless if you cannot tell
"the code changed" from "the clock did".*

### Incremental sync and the watcher — the M3.2 feed, measured end to end

Appending one function to `bquant/core/config.py` and running `codegraph sync` by hand:
**121 ms, 1 file modified, 52 nodes**, and the new symbol was immediately queryable (0.66 s wall).

**The watcher itself was then run** (second pass, 2026-08-28 — the first разбор listed it under *not
checked* and this card compared against the manual number anyway, which was wrong in both directions).
Driving `cg.watch()` in a resident process and polling until the new symbol answers, three runs:

| | save → answerable |
|---|---|
| CodeGraph, watcher running | **327 / 337 / 424 ms** |
| codemap `watch` + `serve --watch`, defaults | **8.1–8.7 s** (of which 4.3 s is the rebuild) |

So the honest ratio is **~20–25×**, not the ~70× that comparing our end-to-end against their *manual sync*
implied. Their number is lower than the 2-second debounce would suggest because of a design worth
stealing: **the debounce is adaptive** — `QUICK_SYNC_MAX_PENDING = 2`, `QUICK_SYNC_QUIET_MS = 300`, so a
lone save fires after 300 ms while a burst still coalesces on the full 2 s window
(`src/sync/watcher.ts`). Their implementation is `fs.watch` with no third-party dependency, watching each
directory individually on Linux (where recursive `fs.watch` is unsupported) and degrading with an
actionable message when inotify watch counts are exhausted.

**Consequence, recorded the same day:** codemap built its own loop (M3.2 — `codemap watch` +
`serve --watch`) precisely because this разбор priced it. The gap that remains is not the loop, it is the
**rebuild floor**: their sync is ~120 ms against our 4.3 s fast-tier incremental. The flat 2 s debounce is
the cheap half of the difference and is now a backlog candidate (adaptive debounce, M3.2-f1).

## Quality (on the covered part)

- **accuracy** — high on T1–T3 *for well-named symbols*. Its caller set for `MACDZoneAnalyzer` is a strict
  superset of codemap's and the one extra is a definitional disagreement, not noise; no false paths were
  found in the T2/T3 sets checked by hand. But that symbol is a unique class name, where no collision was
  possible. On **polymorphic names** the resolver binds by name with no type inference and produces
  demonstrably false call edges (`dict.get` → `MemoryCache::get`, 6 of 6 sampled) — measured on the second
  pass, see the library section. The accuracy verdict is therefore: high where the name is unique, and
  unmeasured-to-poor where it is not, with nothing in the answer distinguishing the two cases.
- **determinism** — ◐. Structure reproduces exactly; the artifact does not; one answer field is a clock.
- **cost** — one call per question, 7–27 KB per answer. `explore` is dense on purpose; the project
  documents (see below) that this *raises* resident context even as it lowers tokens processed.
- **speed** — the strongest axis. 1.4 s cold index, ~0.3 s queries, 121 ms incremental sync, and
  **327–424 ms** save→answerable with its watcher running (measured, second pass).
- **setup friction** — low: one npm command, no build, no service, no API key. 283 MB is heavy for a CLI
  but light against GitNexus's 1.7 GB.
- **language coverage** — 20 via the Rust kernel, vs codemap's one.
- **license** — MIT, the same as codemap. No non-commercial clause to work around, unlike GitNexus.
- **interface** — CLI + MCP + an importable library. The deliberate one-tool MCP surface is a design
  position, not an omission.
- **honesty of its own claims** — **the highest encountered in this track so far.** See below.

## Разбор

- **What we'd take.**
  1. **The watcher loop (M3.2).** A 2-second debounce over native OS file events, feeding an incremental
     re-index, is exactly the glue codemap deferred. A 121 ms sync makes the case that the loop is worth
     closing rather than left as "take it when a scenario appears".
  2. **Inline `signature` on symbol lookup.** codemap makes you ask `call_contract` separately; putting
     the signature on the `query` node costs nothing and answers the next question before it is asked.
  3. **The benchmark's contamination control.** Their harness blocks the `codegraph` CLI in *both* arms
     via a sanitized `PATH` plus a `PreToolUse` hook, because they measured the control arm reaching the
     tool through Bash in **26 of 28 runs**. Any future codemap benchmark that compares "agent with" to
     "agent without" must do this or it is measuring nothing.
  4. **Adaptive debounce** (second pass). `QUICK_SYNC_MAX_PENDING = 2` / `QUICK_SYNC_QUIET_MS = 300`: a
     lone save syncs after 300 ms, a burst still coalesces on the full 2 s. codemap shipped a flat 2 s,
     which costs ~1.7 s on the common case for no benefit. Cheap, and it is most of why their measured
     save→answerable is 0.33 s rather than the 2 s their headline debounce implies. Backlog: **M3.2-f1**.

- **What we'd do differently, and why.**
  1. **Never emit a truncated list without saying so.** `--limit 20` with no `truncated` marker turns a
     symbol-level answer into a file-level-looking one. codemap's `_PARTIAL_OPS` already marks lower
     bounds machine-readably (R1-C13); this is the argument for keeping that discipline everywhere,
     including on any limit we add later.
  2. **No clock in an answer.** `updatedAt` on every node makes `query` non-reproducible for a reason
     that has nothing to do with the code. codemap keeps timestamps in the sidecar precisely so the
     artifact can be diffed.
  3. **Roles should be declared, not guessed.** `explore` reported `examples/02_macd_zone_analysis.py`
     and four siblings under **"tests:"**. They are examples — a declared root in codemap's scope spec,
     tagged `examples`. Heuristic role inference gets this wrong in a way the consumer cannot detect;
     that is the whole argument of the deferred **P6** post, now with someone else's tool as the
     illustration.
  4. **Keep the many-tool MCP surface.** Their one-tool bet is defensible and measured, but it presumes
     the answer shape is known in advance. codemap's value is a caller who can ask `call_contract` or
     `check` specifically.

- **What the author knows that we didn't** — the most valuable part of this разбор, and it is not
  technical:
  - They **published the number that makes their product look worse.** The README states that CodeGraph
    leaves about **80% more retrieval context resident** at end of session (67k vs 18k tokens on VS Code)
    and explains the mechanism — one dense payload that stays in the window versus many small results
    that get evicted — directly beneath the headline win. Volunteering the axis on which you lose is the
    stance this project has been claiming as a differentiator. It is not a differentiator. Someone with
    68k stars does it too.
  - They **invalidated their own earlier published figures.** "Earlier published figures were produced
    without this block" — after discovering the control arm was contaminated 26/28. That is R1-C25's
    lesson (a moving input is indistinguishable from a real result) arrived at independently, in a
    benchmark rather than a graph.
  - **Release provenance.** npm trusted publishing (OIDC, no long-lived tokens) with provenance
    attestations, and SLSA v1.0 Build Level 2 attestations on the GitHub bundles, verifiable with
    `gh attestation verify`. codemap publishes by hand from a laptop (a deliberate, recorded decision —
    D7 in `docs/design/release_engineering.md`). This is the concrete picture of what the automated
    alternative buys, for when that decision is revisited.

- **What we did NOT check.**
  - The MCP path. Everything here is the CLI. `codegraph_explore` was exercised via its documented CLI
    equivalent, not through an agent session, so **no token or tool-call figure of our own** was
    produced — the cost column is answer bytes, not tokens.
  - Their headline benchmark (88% fewer tool calls / 53% faster / 62% fewer tokens across 7 repos) was
    **not reproduced**. It needs a two-arm headless agent harness with the CLI blocked; that is its own
    piece of work, and it is the natural next step if the claim ever needs independent standing.
  - The claim that all 20 Rust-kernel languages produce **byte-for-byte identical graphs** to the
    reference engine. Only Python was measured, on one repository.
  - ~~The file watcher itself.~~ **Checked on the second pass** — `cg.watch()` driven in a resident
    process, save→answerable measured at 327–424 ms across three runs.
  - The MCP `codegraph_explore` path end to end, and therefore whether the library-only queries above are
    reachable by an agent at all (they are not listed as tools; nothing in their source calls them).
  - The **precision** of `findDeadCode()` (1 207 symbols) — only its shape was recorded. The cycle
    finder's false edges were sampled (6 of 6 into one method), not exhaustively classified.
  - Whether the false-edge rate materially changes T2/T3 for *polymorphic* names. `MACDZoneAnalyzer` is a
    unique class name, so this разбор's headline correctness numbers do not probe it. Doing that properly
    means a labelled call-site suite on their output, which is `research/bench/callgraph_accuracy.py`'s
    job and was not run against a second tool.
  - Anything outside Python, and any repo other than bquant at one commit.
  - Whether the author agrees. The truncation defect is filed as
    [#1639](https://github.com/colbymchenry/codegraph/issues/1639) (400 issues scanned first, no
    duplicate); **no response yet**, and this card will not claim a verdict on his behalf. The
    `updatedAt` observation is deliberately *not* filed; see the determinism section for why.
  - Why `allCallers` is ordered as it is. It is stable within a build, but the kind-grouping differs
    between targets (files first on bquant, functions first on the minimal repro), so the ordering is
    edge-insertion order rather than any rule we have identified. The issue does not ask for a
    particular order — only that the cut be visible.

## Verdict & backlog effect

**learn-only (strong).** Nothing here is a dependency codemap should take — it is a different language
tier (20 vs 1), a different determinism contract, and a different MCP philosophy. But it is the first
tool in this track that beats codemap outright on an axis codemap cares about (**speed**, ~9–68×) while
matching it on correctness where they overlap, and it is the first whose *documentation practice* is a
model rather than a foil.

Backlog effect:

- **M3.2 (watcher)** — rerank **up**. The stop-criterion was "wait for a live scenario". A peer shipping
  a 121 ms debounced sync loop, with codemap's three prerequisite bricks (`--incremental`, `reload`,
  honest `freshness`) already built, is the argument that the remaining glue is worth closing.
- **R1-C28 (new, S) — "a limit is partiality too."** The truncation trap above was turned back on
  codemap and it is there as well: `search "zone"` returns **50 hits of a true 1259**, envelope
  `{"ok": true}`, in the op documented as the discovery entry point for an agent that does not yet know
  any names. `_PARTIAL_OPS` cannot catch it — that marks partiality of *resolution*; a limit is an
  independent second source of lower-boundness. Fix: a `limit {applied, returned, total, truncated}`
  block in the envelope of every op that takes a limit, always, including when nothing was cut. Gap:
  [`gaps/limit_truncation_2026-08-28.md`](../../gaps/limit_truncation_2026-08-28.md). This is the eighth
  application of the honest-nothing rule and the first found in someone else's tool first.
- **R1-C13 (partial-answer honesty)** — **reinforced**. It established the machine-readable lower-bound
  marker for approximations; R1-C28 is the same commitment extended to the other way an answer can be a
  lower bound.
- **R1-C6 (relevance ranking)** — a second sighting of scored symbol lookup (after HippoRAG's PPR).
  CodeGraph ranked the `UniversalZoneAnalyzer` method above the flagship `pipeline.analyze_zones`, which
  is a reminder that a score is only as good as what it optimises for.
- **R1-C14 (positioning)** — sharpened, then corrected on the second pass. Against this tool the honest
  differentiators narrow to: **byte-diffable artifact**, **declared-root provenance** (calls vs references,
  core vs docs vs tests), **argument-level call contracts**, **architecture contracts**, and **docs as
  first-class references**. Speed, license, and multi-language are no longer available as differentiators.
  **"Nobody else answers whole-graph questions" is not available either, as stated** — their library does
  answer the cycle question. What survives measurement is narrower and stronger: nobody else answers them
  *on a surface a caller can reach*, and the one implementation that exists is wrong by two orders of
  magnitude on our target because it inherits name-resolved call edges. Claim the accuracy, not the absence.
- **M3.2-f1 (new, XS) — adaptive debounce.** A flat 2 s window taxes the common case (one file saved) for
  a burst that rarely happens. Their split (≤2 pending → 300 ms quiet; more → full window) is the whole
  fix, and it is the difference between our 8.5 s and something near 6.5 s without touching the rebuild.
- **P6 (blog)** — the role-provenance post now has a concrete illustration: a widely-adopted peer that
  labels `examples/` as `tests`, beside codemap's `by_root` split. Still not the "provenance changed a
  real decision" episode the post is waiting for, so **P6 stays blocked** — but this is the strongest
  material it has.

---

*Measured 2026-08-28 (first pass: CLI; **second pass same day**: the importable library, the watcher
end to end, and the resolver's behaviour on polymorphic names — the first pass had measured two of three
interfaces and compared our end-to-end loop against their manual sync) · CodeGraph 1.6.0 · bquant@cb89a24 ·
`scope_id sha256:300e0a01…5e47d2` · every command and number above reproduces from a clean staging.*
