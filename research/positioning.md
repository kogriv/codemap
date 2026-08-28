# positioning & build-story

**What this is.** The *publication layer* of the research track — article-ready narrative distilled from the
raw measurements. It answers "what is codemap, why does it exist, and how does it actually compare?" in prose
you can cut straight into a blog post, README intro, or talk.

**What this is not.** Not the source of truth. Every number here reproduces from a card
(`research/tools/*.md`) or the [comparison hub](comparison.md) — those are the evidence; this is the story.
If a fact here and a card disagree, the card wins. Keep it that way: measure in cards, narrate here.

**House rules (so it stays publishable):**
- Every claim carries a number and a link to where it was measured.
- Honesty first — the gaps section is load-bearing. A build-story that only flatters isn't believed.
- "Measurements, not verdict; other authors are potential collaborators, not enemies." (inherited from the
  разбор convention, `research/README.md`).

Realizes the **R1-C14** backlog item (positioning docs).

---

## The thesis (one paragraph)

codemap is **the precise structural leg for index-free AI agents**: a source-only, deterministic,
Python-deep code graph exposed as agent/MCP verbs. It does not compete with embeddings-RAG or Repomix-style
packing — it complements them. The field has already conceded that *structural precision + freshness beats a
vector index for code navigation*; codemap's bet is to be the best **deterministic, diffable, provenance-aware**
graph in that slot, and to interoperate outward (SCIP, ctags) rather than lock its graph away.

Positioning line, tight enough for a headline:
> **A code graph an agent can trust: source-only, deterministic, diffable — no index to go stale, no LSP to provision.**

---

## Story Zero — codemap and the road here

### The itch
Agents navigating code have two bad options: **grep** (exact but blind to structure — it can't tell you *who
calls this* or *what breaks if I change this signature*) and **embeddings/RAG** (fuzzy, non-deterministic, and
perpetually stale against a moving repo). The interesting third path — a *precise structural graph* — kept
getting built as an opaque, non-diffable index (LSIF, vendor DBs) that rots the moment code changes and can't
be reviewed in a PR.

codemap's bet: build that graph **source-only** (no compile, no venv), make its artifact **canonical and
diffable** (sorted, timestamp-free JSON — a graph you can `git diff`), tag every node with **provenance**
(is this core, tests, docs, examples, scripts?), and hand agents **native verbs** over MCP instead of a query
language to learn.

### The arc (M0 → M19)
- **M0–M5 — the graph exists.** Canonical structure (imports/exports/inherits), a query API, a behavioral
  call graph, deep call resolution via jedi, and render views (RAG/vault/mermaid). The foundation:
  *deterministic graph out of pure source*.
- **M6–M12 — the graph gets opinionated.** Multi-root **provenance** and impact/blast-radius; registry-aware
  call bridging; **provenance-aware dead-code** (vulture without the dominant false-positive source);
  call-site argument contracts; string-key column dataflow. This is where codemap stops being "a parse tree"
  and starts answering real questions.
- **M13–M16 — ergonomics and altitude.** Discovery ops (search/families/source/resolve); soundness
  (ambiguity surfaced, not silently resolved); **diff/change-review** (a diff → a risk-sorted dossier);
  **architecture overview** (layers, coupling, god-objects).
- **M17–M18 — agent-native + honest about time.** The **MCP adapter** (the graph as ~18 agent tools); graph
  **freshness** (a static graph now reports its own age so an agent knows the map may be stale) — determinism
  preserved by keeping the build recipe in a sidecar.
- **R1 + R1-C1 — look outward.** A grounded survey of the whole field (this research track), then the
  highest-value interop move: **SCIP export**, so Sourcegraph/Glean light up over codemap's graph.
- **M19.A — deterministic about the input, too.** codemap was already deterministic on its *output*;
  `scope_id` makes it deterministic on its *input* — a content hash of exactly the files that went in, with a
  git binding. (Same id ⇒ provably identical input — the thing that makes tool-vs-tool comparison honest.)

Schema **0.11**, ~**369 tests**, warm serve (29 ops / 26 MCP tools) + SCIP export.

### Where it sits in the field (measured, not asserted)
The R1 survey placed codemap in an **under-served spot**: a *semantic (resolved) code graph* that is
*deterministic*, *source-only*, *Python-deep*, and *agent-facing*. Neighbours each miss one axis — embeddings
tools aren't deterministic; ctags/LSIF aren't resolved; LSP is ephemeral; the heavy graph DBs (Kythe/Glean)
need a compiler. Full matrix: [00_landscape.md](00_landscape.md).

### Honest gaps (the part that earns trust)
- **No cross-boundary resolution into dependencies.** codemap is source-only-*of-target*; it won't tell you
  "what pandas API does this call." graphlens can. By design, but a real limit. ([gap](comparison.md))
- **No true incremental graph.** codemap rebuilds; it doesn't yet watch-and-patch. M18/M3.2 (freshness
  sidecar + `refresh`) is the partial answer.
- **Python only.** The peers that span 5+ languages do so by leaning on tree-sitter/LSP; codemap's depth is
  bought with Python-specificity.

---

## Build-story #1 — "The competitor wasn't broken. We were." (graphlens-mcp)

_Evidence: [graphlens card](tools/graphlens.md). Every number below reproduces there._

### The setup
graphlens-mcp is the nearest twin to codemap: a code-graph-for-agents, over MCP, with an *ambitious* backend
— Astral's `ty` (an LSP-grade type checker) plus tree-sitter, persisted to SQLite. If anything in the field
should beat codemap at impact analysis, it's this.

First hands-on pass, on a fair scope (the same 6 directories codemap indexes). It indexed in **12 seconds**.
Then the core query — *who calls `MACDZoneAnalyzer`?* — came back **empty**. Zero callers. Zero references.
codemap answered the same question with a full provenance breakdown. Easy verdict, and we almost shipped it:
*graphlens degrades to grep on a real source tree; learn-only; nothing to take.*

### The itch that saved us from a cheap conclusion
One detail nagged. graphlens's own response didn't *lie* — it flagged `resolver_status: "degraded"`. It was
telling us its type resolver never came up. A tool this carefully built doesn't ship with impact analysis
that just… doesn't work. Either the author shipped something broken, or **we were holding it wrong**.

So we opened the hood. The Python resolver spawns `ty` like this:

```python
ty_bin = shutil.which("ty") or "ty"        # graphlens_python/_resolver.py:34
```

graphlens *bundles* `ty` at `~/.local/share/uv/tools/graphlens-mcp/bin/ty`. But `uv tool install` only puts
the declared `graphlens-mcp` entry point on `PATH` — **not** the bundled `ty`. So `shutil.which("ty")`
returned `None`, the spawn raised `FileNotFoundError`, and `prepare()` swallowed it (`except Exception:`) and
fell back to tree-sitter-only. **Silent degrade.** The empty impact wasn't graphlens's weakness — it was our
`PATH`.

The fix was one line: put the bundled bin on `PATH`.

### What happened when we ran it fair
`ty server` came up. `resolver_status` flipped to **`ok`**. And everything changed:

| | tree-sitter only (broken) | **ty-resolved (fixed)** |
|---|---|---|
| index time | 12 s | **2 m 20 s** (12×) |
| DB size | 17.5 MB | 31 MB |
| nodes / edges | 16 796 / 20 889 | **32 399 / 55 691** |
| `relations(MACDZoneAnalyzer)` | **empty** | **9 callers + 1 callee + 2 refs** |

Those extra ~35 000 edges are the resolved calls and references that were missing. The impact engine wasn't
broken — it had never run.

### The honest head-to-head (same staging, both tools)
- **codemap** `impact`: **31 references, one call**, split by provenance — core 2 / docs 7 / examples 1 /
  scripts 2 / **tests 19**.
- **graphlens** `relations`: 9 callers + 1 callee + 2 refs (`resolver_status: ok`) — but it **auto-hides test
  call-sites by default** (a *deliberate* choice, commented in `lean.py:53`, to keep an agent's context budget
  from drowning in tests).
- On the **non-test resolved call graph** the two nearly agree: codemap 12, graphlens ~9–11. The engine is
  **sound**.

### The lesson (this is the reusable bit)
1. **A graph tool can silently degrade to grep.** The single most important thing to check before trusting —
   or benchmarking — a resolved-graph tool is *did the resolver actually come up?* (`resolver_status == ok`).
   This is now a hard rule for our benchmark harness (R1-C13).
2. **"It returned nothing" is a hypothesis, not a finding.** The cheap verdict (*competitor is broken*) was
   wrong and would have been unfair to a well-built tool. The extra hour turned a false takedown into a real,
   respectful comparison.
3. **Bundling a binary but resolving it via `shutil.which` is a trap** — a genuine, reportable packaging bug
   in graphlens, worth a friendly upstream note.

### What we take, what we keep
- **Take (learn):** cross-boundary resolution *into* dependencies (a real capability we lack); the
  context-budget test-de-emphasis heuristic; watch-mode incremental re-index (feeds our freshness work).
- **Keep (our edge, now measured against a *working* competitor):** determinism (a 3.6 MB diffable JSON vs a
  31 MB SQLite DB), single-call provenance-complete impact, works with no LSP to provision and offline, and
  T4/T5 (call-contracts, architecture) that graphlens has no tool for.
- **Verdict:** not "nothing to take" — a **competent peer** we learn from but don't integrate (overlapping
  thesis, heavier, non-deterministic, layout-fragile, LSP-dependent).

---

## Build-story #2 — "The one that does more, and why that's fine" (GitNexus)

### The setup
R1 filed GitNexus in one line: *"repo → knowledge graph (3D map) + CLI + MCP, non-commercial license."* Easy
to shelve as a visualization toy with a bad license. Then we installed it — **v1.6.9**, and it is nothing like
the desk note. `npm install gitnexus` pulls **1.7 GB** of `node_modules`: tree-sitter grammars for 14
languages, an ONNX runtime, a native LadybugDB graph engine, transformers.js embeddings. This is not a toy.
It's a **hybrid semantic+structural engine** — BM25 + vector search fused with a symbol graph, Leiden
community clustering, entry-point process-flow tracing, transitive risk-rated impact. On the R2 scope
(materialized staging, `scope_id` verified identical to ours) it indexed 280 files into **6 344 nodes /
14 661 edges / 276 clusters / 294 flows** in ~25 s.

### The two cheap conclusions we had to resist
Graphlens taught us not to dismiss a competitor too fast. GitNexus taught the **opposite** discipline —
not to *panic* too fast. Two lazy verdicts were on the table:
1. *"It's just a non-commercial 3D-map, nothing to take."* — false; it does several things we don't.
2. *"It does semantic search, clustering, flows, 14 languages, risk ratings — they've lapped us."* — also
   false, and the more dangerous one, because it's the kind of thing you half-believe at 2 a.m.

The only way out of both was the harness: **same input, same five questions, measure what each tool is
actually _for_.**

### What the measurements actually said
- **T1 (where is `analyze_zones`)**: GitNexus's `context` returned **ambiguous — 2 candidates**
  (`pipeline.py` function + `analyzer.py` method), exactly the two defs codemap surfaces. Both tools are
  honest about the ambiguity. Dead heat. ✅
- **T2 (who calls `MACDZoneAnalyzer`)**: here the models diverge. GitNexus says `incoming: {imports: 22}`.
  codemap says 65 references, split **core 2 · docs 7 · examples 1 · scripts 2 · tests 53**. GitNexus counts
  *file imports*; codemap counts *symbol references, tagged by role*. Ask "what actually breaks in core?" and
  only one of them answers. ◐
- **T3 (impact)**: GitNexus shines — a **transitive** upstream import closure: **48 impacted**, depth
  histogram **5 / 15 / 28**, **risk: MEDIUM**, and a per-answer `epistemic: exact` label. Richer than
  codemap's one-hop count *in depth and risk framing* — but file-level and **provenance-blind**. Different
  bet, both correct. ✅
- **T4 (signature-change surface)**: GitNexus has **no** per-call argument contract. Its `detect-changes` is a
  git-diff→symbol mapper (our `review`, not our `call_contract`) — and it **errored without `.git`**. ✖
- **T5 (architecture)**: `check --cycles` found 3 real import cycles; 276 clusters + 294 flows add a narrative
  layer we lack — but there's no coupling / instability / god-object metric. ◐

### The determinism test that cut both ways
GitNexus *claims* deterministic indexing. We didn't take the claim — we materialized **two** independent
clean-room stagings (identical `scope_id`) and indexed each. Result: **identical counts, and a byte-identical
`impact` answer.** The claim holds. But two caveats we'd have missed without looking: the artifact is a
**123 MB binary LadybugDB** (WAL) — the *answer* is reproducible, the *store* is not something you `git diff`;
and re-`analyze` **without** `clean` is **non-idempotent** (it merged and drifted 6 344 → 6 356 nodes). So:
deterministic answer ✅, diffable artifact ✖. That distinction *is* codemap's differentiator, now measured
against a tool that gets the first half right.

### Postscript: we took it home and ran it (2026-08-16)
The R2 pass measured GitNexus against codemap on a shared scope. Then we did the other thing — we stood it up
**as users**, on the *whole* bquant repo, and lived with it. Two payoffs. First, the R2 card had honestly
flagged one thing unmeasured: *did semantic search retrieve the **right** things, or just run?* On the fully
indexed repo (13k nodes, 4.5k embedding chunks), it did — a concept query pulled the relevant MACD-zone flows,
a clear lift over keyword noise. The retrieval half of our sentence isn't hypothetical; we watched it work.
Second, we felt the tax that the thesis is built around: a full embedding pass is **~18 minutes** on CPU; the
ANN index needs a network install to exist at all; and getting it onto the GPU meant side-loading a **CUDA-13
runtime + cuDNN 9** just to light up a 1080 Ti. None of that is a knock — it's *why the split is the right
call*. codemap stays a source-only, deterministic, provisions-nothing graph; a retrieval engine with models and
a 1.7 GB footprint is exactly the kind of thing you **wrap behind an opt-in router**, not absorb into the core.
The day of setup didn't change the verdict — it made the verdict felt.

### The lesson (reusable)
1. **"They do more" is not "they win."** A tool that does semantic search + clustering + flows + 14 languages
   isn't beating a tool that does deterministic, diffable, provenance-precise Python structure — it's playing
   an *adjacent* game. The harness is what lets you say that with numbers instead of nerves.
2. **The most valuable competitor is the one that proves your thesis.** codemap's positioning is "the precise
   structural leg for index-free agents, that *interoperates with* retrieval rather than replacing it."
   GitNexus is a working retrieval+structure hybrid — it is the concrete other half of that sentence. It
   doesn't threaten the thesis; it *demonstrates* it.
3. **Claims decompose.** "Deterministic" split into deterministic-*answer* (true) and diffable-*artifact*
   (false). Measure the parts, not the slogan.

### What we take, what we keep
- **Take (learn):** per-answer **`epistemic` + edge `confidence`** labels (R1-C13 honesty); **transitive,
  depth-bucketed, risk-rated impact** as an opt-in mode; **flow/community narrative** as a higher-altitude
  view (feeds R1-C15 living docs); **one-command MCP setup** into every editor (adoption ergonomics, R1-C14).
- **Keep (our edge, measured against a richer tool):** **MIT** vs PolyForm-NC; a **4.83 MB diffable JSON** vs
  a **123 MB binary DB**; **provenance-split, symbol-level impact** vs a file-import closure; **T4 call
  contracts** it has no answer for; **no git required** and **no 1.7 GB / no embedding models** to provision.
- **Verdict:** **learn (strong, adjacent peer).** Complementary, not competing — and the best evidence yet
  that codemap's "precise leg" positioning is real, because here's the retrieval half, built by someone else.

---

## Build-story #3 — "The competitor that does *less* — and that's why we take it" (cocoindex-code)

_Evidence: [cocoindex-code card](tools/cocoindex-code.md). Every number below reproduces there._

### The setup
GitNexus was the tool that did *more*. cocoindex-code (`ccc`) is the opposite bet: it does *less* than
anything we'd measured. No call graph. No impact. No architecture. No symbols. Point it at a repo and it
does exactly one thing — embed the code with tree-sitter chunking and answer a natural-language query with
the nearest chunks. On the R2 task-set, **four of five tasks are structurally N/A**: ask `ccc` "who calls
`MACDZoneAnalyzer`?" and it returns semantically-similar *docs and tests*, not a caller list, because there
is no graph to have callers in. By the coverage matrix, it's the emptiest row we've filled.

### The surprise: the emptiest row is the most useful тool
And it's the most valuable разбор for the roadmap so far. Because the story isn't the feature set — it's the
**license**. GitNexus does everything `ccc` does *and* a structural graph *and* 14 languages — but it's
PolyForm-Noncommercial, so codemap can only ever **route** to it (opt-in subprocess, answer passed through
untouched), never **adapt** it (translate its output into our graph contract). `ccc` is **Apache-2.0**. It
does less, but it's the first semantic-search tool we are legally free to *wrap* — the first one that can
sit behind the R1-C16 router as an owned capability, not a borrowed one. "Does more" lost to "does less,
under a license we can build on."

### The measurement that shows the fit
Two queries tell the whole story. Ask for a *concept* — "detect swing high/low pivot points within a zone" —
and `ccc` nails `bquant/analysis/zones/strategies/swing/pivot_points.py` at rank 1 (0.72) with **zero
knowledge of the name**. That is precisely the fuzzy leg codemap refuses to grow. Ask for an *exact symbol* —
`analyze_zones` — and `ccc search` returns a relevant spread where the real definition ranks #5, not #1;
it's `ccc grep` (tree-sitter, no index) that pinpoints it. The boundary is crisp: **semantic retrieval for
"what's this about," exact structure for "where is X" — and they're different tools, not the same one graded
differently.** That's the composition thesis, measured on one repo.

### The aside that cut the other way (GPU)
A footnote worth keeping. GitNexus's embeddings ran on the 1080 Ti after we side-loaded a CUDA-13 runtime —
its onnxruntime EP has Pascal kernels. `ccc`'s `[full]` extra pulled **torch 2.13/cu130**, whose wheels are
compiled for sm_75+ only; the same GPU, same model family, **hard-fails** with `no kernel image for device`.
Two tools, same embedding model (`snowflake-arctic-embed-xs`), opposite GPU outcomes — because the runtime,
not the card, decides. So `ccc` embedded 6403 chunks on CPU in ~9 minutes. The redeeming number: a re-index
of unchanged content takes **~1 second** — content-hash delta processing, a working proof of the incremental
graph we've deferred as R1-C9.

**Sequel (2026-08-22).** We got a second box with an RTX 3070 and settled it. `torch.cuda.get_arch_list()`
prints the verdict without ceremony: `sm_75, sm_80, sm_86, sm_90, sm_100, sm_120`. Not a hardware limit — a
list someone chose at build time, and sm_61 is simply not on it. On sm_86 the same cold build drops from
**216 s to 48 s**. Two footnotes came out of the measuring, and both are the kind that quietly falsify a
benchmark: `ccc` keeps a **background daemon** holding the model, so three "different" device settings all
returned the same 34 s because they hit the same warm process — the daemon has to die between arms. And the
device **auto-detects**, so the honest CPU number only appears if you pin `device: cpu` on purpose. The first
number we believed was measuring nothing at all.

### The lesson (reusable)
1. **"Does less" can be worth more than "does more."** Capability is not the axis that decides integrate /
   wrap / learn — **fit × license** is. A tool that does one thing cleanly, composes with your core, and
   carries a license you can build on beats a richer tool you can only admire from behind a subprocess.
2. **The wrap/route/learn triad is a licensing decision as much as a technical one.** Same capability
   (semantic search), two tools: GitNexus → route-only (NC); cocoindex-code → adaptable (Apache-2.0). The
   verdict flipped on the license file, not the feature list.
3. **Measure the boundary, not just the hit.** The finding wasn't "semantic search works" — it was *where it
   stops* (exact-symbol lookup goes fuzzy), which is exactly what tells you to wrap it as opt-in, beside the
   structural answer, never instead of it.

### What we take, what we keep
- **Take (wrap + learn):** cocoindex-code itself as the **R1-C16 semantic-search adapter** — the first
  license-clean tool for the fuzzy-retrieval leg codemap lacks by design; and its **content-hash incremental
  re-index** (~1 s) as the concrete pattern behind our deferred **R1-C9** (Merkle/incremental).
- **Keep (our edge):** a **diffable** graph vs a binary LMDB/SQLite blob; **exact, re-export-resolving**
  symbol lookup vs a fuzzy spread; **provenance-split structural impact** it has no notion of; and a graph
  that **provisions nothing** — no 1 GB torch, no embedding model, no GPU-arch lottery.
- **Verdict:** **wrap (opt-in semantic adapter) + learn (incremental engine).** The retrieval half we can
  finally *own*, not just point at.

---

## Build-story #4 — "The determinism test went red, and the tool was fine" (ourselves)

*Source: [gaps/graph_provenance_2026-08-25.md](../gaps/graph_provenance_2026-08-25.md), R1-C25. The first
build-story whose subject is codemap rather than a rival — and the only one where the measurement was
forced on us instead of planned.*

### The setup

Determinism is the headline claim. Same source in, byte-identical `graph.json` out — that is what makes the
artifact reviewable in a pull request, and it is the property every other claim leans on. There is a test
that pins it: build the dogfood target twice, compare the bytes.

On 2026-08-24, mid-way through an unrelated fix, it went **red**.

### The half-hour of being wrong about which thing was broken

The obvious reading is that the extractor is nondeterministic — some dict ordering, some set iteration, some
cache warmth. We had already documented one real case of exactly that (jedi's deep tier is
cache-sensitive; two full deep builds differ by a handful of edges). So the first instinct was to go hunting
in our own sorting code.

The cause was elsewhere: **another process was editing the target between the two builds.** A neighbouring
agent was committing to `bquant` while the test read it. Files vanished between the two `extract()` calls.

Nothing in the artifact could distinguish those two explanations. Two `graph.json` files that differ, and no
field in either one says *which tool read which tree at which revision*. It took a manual rebuild on a frozen
copy to settle it — a snapshot of the same sources, built twice: byte-identical.

### The measurement that came out of it

Once we asked the question properly, it got worse. Take a **frozen** tree — nothing moving, byte-identical
input — and build it with codemap at two commits four apart:

| | edges | `report dead-code` **high** |
|---|---|---|
| built at `4858899` | 30 | **12** |
| built at `16fe7de` | 38 | **7** |

Five functions that one graph calls dead and the other calls live. **Both files declare
`codemap_schema: "0.11"`**, and the tool loaded either without a word.

And the schema field was *right* not to move. The change in between (R1-C22) added no node kind and no edge
type — only keys under `extras`, which the design deliberately leaves open. **The semantics changed
correctly and the version correctly stayed put.** That is the whole finding: a schema version describes the
*shape* of a file; nothing described the *process* that produced it.

`codemap diff` on that pair answers:

```
✅ **No breaking changes.** 0 added, 0 removed, 0 changed.
```

True at the API level, and exactly why it could not be the safety net. Two graphs that disagree about which
functions are dead are, to `diff`, the same program.

### Why the sidecar didn't already cover it

We had provenance — in `graph.json.meta.json` (M18/M19.A): `argv`, `built_at`, `cwd`, and a scope block with
a content-hash `scope_id`. Four reasons it did not close the hole:

1. **It is a separate file**, and every way a graph actually travels — attached to a ticket, committed to a
   sibling repo, handed to an agent — moves `graph.json` and leaves the sidecar behind.
2. **It is `.gitignore`d**, so it is precisely the half you cannot share.
3. **It is best-effort.** The sidecar sitting in our own working tree had no `scope` key at all.
4. **It records `cwd`** — an absolute personal path, which makes it the one file that must *not* be
   published. An awkward home for data meant to travel.

### The fix, and the two rules it obeys

A `provenance` block **inside** the graph (schema 0.11 → 0.12): tool name/version/commit/dirty, tier, the
input `scope_id`, and the target's VCS commit and dirty flag.

- **No clock.** A `built_at` field would destroy the byte-identity this exists to make checkable. Wall time
  stays in the sidecar.
- **No absolute paths.** The graph is the half that travels, so `build_provenance` raises on one and a test
  enforces it.

`codemap_schema` is finally *read*: a mismatch raises a warning through the same channel every other build
diagnostic uses — CLI, `stats`, and the report headers. A warning, never a refusal; every stored graph
predates 0.12, and turning an upgrade into an outage is not the honest option. And `diff` now compares
provenance before it compares symbols.

### The finding we could not have asked for before

With the block in place, one more question became askable: what does `build --incremental` do when the
*tool* changes and the source does not? It decided from the source tree alone — no `.py` changed, return the
old graph — so after an upgrade it would hand back yesterday's graph, built by yesterday's extractor, and
report `mode: unchanged` while doing it. It now compares the recorded builder and falls back to a full
rebuild.

### The lesson (reusable)

**A test that reads a moving target measures the target.** Four of our `test_determinism_*` tests built the
live sibling checkout twice; they now build a frozen snapshot, which is the same discipline the provenance
block applies at the artifact level. Freeze the input, or you are measuring something else.

And the sharper half: **determinism is a claim about a pair of builds, so it is unfalsifiable unless the
artifact carries the identity of its input.** We had spent months making the output reproducible and had
never made it *checkable*.

### What we take, what we keep
- **Take:** the input identity we already computed (`scope_id`, M19.A) and were throwing away — it now
  travels inside the graph.
- **Keep:** timestamp-free canonical JSON. The block had to be squeezed in without breaking it, which is why
  it carries a content hash and a commit rather than a clock.
- **Verdict:** the headline property survived, but only after being made falsifiable. Until then it was a
  claim we believed rather than one we could check.

---

## Build-story #5 — "A month of dogfooding, then one more repository found seven bugs in two days" (ourselves)

*Sources: [gaps/flat_layout_gap_2026-08-24.md](../gaps/flat_layout_gap_2026-08-24.md),
[gaps/dead_code_high_band_2026-08-24.md](../gaps/dead_code_high_band_2026-08-24.md),
[gaps/deep_tier_regression_2026-08-25.md](../gaps/deep_tier_regression_2026-08-25.md); issues
[#4](https://github.com/kogriv/codemap/issues/4)–[#10](https://github.com/kogriv/codemap/issues/10);
R1-C21, R1-C21-f1, R1-C21-f2, R1-C22, R1-C22-f1, R1-C26.*

### The setup

By 2026-08-24 codemap had been dogfooded for a month, deliberately and systematically: **eleven axes
closed** (A1–A11, B1), each a pre-registered angle with hypotheses written before the run — reverse
impact, call chains, extension recipes, string dataflow, change-sets, RAG self-sufficiency, reachability,
an agent working through the warm `serve` process, whole-graph architecture, diff review, soundness.
Twenty-one findings, each closed by a milestone.

And the failure class was **already known**. "A confident *nothing* where the honest answer is *I don't
know*" had been the standing enemy for weeks: `impact` on a class attribute answering `risk:"none"` (#1),
`canonical` silently picking one symbol out of twenty-five (F14), 71% of `column` nodes turning out to be
dict-literal keys rather than columns (F15). We were not naive about it. We were hunting it.

Then the same author pointed the tool at a **different repository** — a second real target whose engine
lives in a flat directory of sibling modules rather than a package.

### The first twenty minutes

Two defects, on the very first build, before a single question had been asked of the graph.

Without `__init__.py` it **crashed**: griffe classifies such a directory as a namespace package whose
`filepath` is a `list[Path]`, and **five** separate consumers handed that straight to `Path()`. The error
message named none of it.

With an `__init__.py`, worse — it **succeeded**. Zero `imports` edges, and every report then built a
confident story on that emptiness: `architecture` announced *no layer violations* and *acyclic*;
`dead-code` called every live module in the engine an orphan. A graph of nothing, rendered as a clean bill
of health.

### Then it kept going

Seven issues in roughly forty-eight hours: the crash (#4), the silent zero (#5), consumer-root imports
still resolving to nothing so `impact` answered *isolated* for every symbol (#6), a diagnostic whose
consequence sentence had gone stale and told the reader the findings came from an empty import graph while
that graph held 404 edges (#8), the dead-code `high` band (#7), its mirror-image follow-up (#9), and the
deep tier (#10).

**Four of the seven were about the shape. Three were bugs the shape merely made visible** — and those
three are the interesting ones.

### The one that stung

Issue #7 arrived with a line worth quoting: *"a working graph is what made this visible."* Fixing #5 had
given the reporter a functioning import graph for the first time, and the first thing that graph did was
expose a defect with nothing to do with flat layouts.

`report dead-code` grades an uncalled private function `high` — "no inbound calls, references or
accesses". Checked against the source: **20 of 51 `high` candidates were false, 39%**, through three
distinct mechanisms — a function passed as a value, a call at module level, a call from a nested `def`.
And the detail that makes the point: **each package exhibited only two of the three.** No single target
could have shown the whole defect.

It reproduced on **codemap's own package** — 46 `high` candidates of its own, 17 of them wrong. That code
had been sitting under our own dogfood for a month.

### And the one that was pure waste

Issue #10: `--deep` returned *less* than the free `--fast` tier. On the reporter's target fast found 487
call edges, 158 of them crossing a module boundary; deep found 336, of which **zero** did. The tiers had
been mutually exclusive — jedi *instead of* the name resolver — so deep silently lost real edges on
properly packaged targets too, five on codemap and five on bquant. Anyone paying a minute for the
expensive tier had been getting a worse answer for months.

### The lesson (reusable)

**A dogfood target is a shape, not a sample.** Coverage of *questions* is not coverage of *inputs*. Eleven
axes were eleven ways of asking, and all eleven were asked of one tree laid out one way; no amount of care
in choosing the next question substitutes for a second shape. What changed here was not a fresh pair of
eyes — same author, same instincts, same known failure class. Only the input was new.

The corollary is measured, not hoped: **the second shape cost the first nothing.** R1-C21 left bquant's
graph *byte-identical*. R1-C22 was additions only (+364 edge pairs on bquant, **0 removed**). The
deep-tier union lost no true edge. Adding a shape did not trade one target's correctness for another's —
it revealed work that had simply never been done.

And the smaller, sharper habit: **treat "0 of anything" as a diagnostic, not a datum.** Zero import edges
across two or more modules is not a finding about the code; it is a finding about the tool. That check now
fires at build time, in `stats`, and in three reports.

### What we take, what we keep
- **Take:** a permanent second target of a different shape, and a `flat` label on every edge inferred from
  a layout rather than stated by the source — the inference stays visible instead of being swallowed.
- **Keep:** the honest-nothing rule, now with seven more applications behind it. Every one of these seven
  was that same rule violated in a different subsystem.
- **Verdict:** the most productive stretch of the project came from using it for real work on a tree we did
  not choose. The suite went 369 → 512 across the arc, and not one of those tests would have been written
  from our own repository.

---

## Build-story #6 — "The 68 000-star tool measured fair, and then found a bug in ours"

Facts: [CodeGraph card](tools/codegraph.md). Measured 2026-08-28 on the R2 scope
(`scope_id sha256:300e0a01…5e47d2`, bquant@cb89a24).

### The setup

Every tool measured before this one was a peer of comparable weight — graphlens in alpha, GitNexus,
cocoindex-code. CodeGraph is not that. Seven months old, **68 420 stars, 4 362 forks**, MIT, a Rust
kernel with tree-sitter compiled in, twenty languages, one npm command, no service. It is what a person
reaches for *instead of* codemap. Measuring it was going to be uncomfortable in one of two directions.

### It measured fair

On the same 280 files: **1.4 seconds** to index, against codemap's 12.3 s fast tier and 95.8 s deep —
roughly 9× and 68×. Queries in ~0.3 s. Incremental sync in **121 ms**, behind a debounced file watcher
that codemap has deferred for a month. T1 found both definitions of `analyze_zones` at the exact lines
codemap reports, with the signature inline. T2 returned 58 symbol-level callers, and **codemap's 57 are
a complete subset of them** — no disagreement, anywhere, on a symbol we have been probing for months.

The one extra was `assert isinstance(analyzer, MACDZoneAnalyzer)` — a reference counted as a call, and
its own `--help` says "call". That is the same *function-passed-as-a-value* mechanism that made our
`dead-code` `high` band wrong 39% of the time (build-story #5). Not a gotcha; a thing one tool has had
to learn and the other has not needed to yet.

### The half-hour of being wrong, again

The first T2 run returned exactly **20** callers, every one a *file* at line 1. That reads as a clean,
publishable finding: CodeGraph models callers as file-import fan-in, not call sites.

`--limit` defaults to 20. The file-kind rows sort first. The default had cut the answer **exactly along
the line that misrepresents the model** — and nothing in the payload said so: no total, no `truncated`
flag. At `--limit 500` it is 79 entries, symbol-level, and the picture inverts.

Second time in this track that a default nearly produced a false verdict about someone else's tool. The
first was graphlens's bundled `ty` being off `PATH` (build-story #1). The rule that caught both is
embarrassingly cheap: **when a number looks round, check whether it is a limit.**

### Then we asked our own tool the same question

`search "zone"`, default limit: **50 hits.** True count: **1259.** Envelope: `{"ok": true}`. No total,
no marker, no echo of the limit — in the op whose docstring calls it *"the discovery entry point for a
cold agent that does not yet know exact names."* The one operation whose entire job is to say what
exists answers with 4% of it and looks complete.

`_PARTIAL_OPS` does not catch it, and could not: it marks partiality of *resolution*. A limit is a
second, independent source of lower-boundness. `callers` is marked and has no limit; `search` has a
limit and is marked by nothing.

Eighth application of the honest-nothing rule — the first found by measuring a competitor and then
turning the same probe inward. Logged as R1-C28, gap `gaps/limit_truncation_2026-08-28.md`.

### What the author knows that we didn't

Not technique. Practice.

The README publishes the axis on which the product **loses**: CodeGraph leaves ~80% more retrieval
context resident at end of session (67k vs 18k tokens on VS Code), stated directly under the headline
win, with the mechanism explained. And it **retracts its own earlier published benchmark figures** —
after discovering the control arm reached the tool through Bash in 26 of 28 runs, it rebuilt the harness
to block its own CLI in *both* arms and re-published lower numbers.

"Volunteering the axis where you lose" has been on our differentiator list. It is not a differentiator.
Someone with 68 000 stars does it too, and did it before we noticed.

### The thesis this crystallised

Four hands-on cards in, the same two columns are empty for every peer, and the reason is structural
rather than incidental. The field is built for **point questions** — name a symbol, walk outward a
few steps, hand the agent a slice of source. Whole-graph questions have no seed symbol and no slice
to return: a cycle is invisible from inside every file that participates in it, and "which module is
most expensive to change" is a property of 634 edges, not of any node.

Written out in full, with the limits, as user-facing doc
**[docs/whole-graph-questions.md](../docs/whole-graph-questions.md)** — the long form of this
build-story's argument, and the piece the README now leads with.

### The lesson (reusable)

**A comparison that only ever flatters you is not a measurement.** This разбор took speed, license, and
multi-language off our list of differentiators, and took "unusually honest about its own claims" off it
as well. What is left is narrower and provable: a byte-diffable artifact, declared-root provenance
(calls vs references; core vs docs vs tests — CodeGraph labels `examples/` as "tests"), argument-level
call contracts, architecture contracts, docs as first-class references, and no clock anywhere in an
answer.

That last one is not rhetorical. CodeGraph's `query` carries a wall-clock `updatedAt` on every node, so
two builds of identical source return different bytes. One field, probably a one-line fix — and exactly
the property build-story #4 was about.

### What we take, what we keep
- **Take:** the watcher loop (M3.2 reranked up — the cost is no longer unknown, it is 121 ms), the
  inline signature on symbol lookup, and the two-arm benchmark contamination control, which is not
  optional for any with/without-agent measurement we ever publish.
- **Keep:** the honest-nothing rule — now with an eighth application that we found in someone else's
  tool first, and the discipline of running the probe back at ourselves before writing the card.
- **Verdict:** learn-only (strong). Nothing to depend on; the first peer that beats us outright on an
  axis we care about while matching us on correctness where we overlap, and the first whose
  documentation practice is a model rather than a foil.

---

## Article-ready sound bites (each backed by a card)

- "We almost published that a competitor's impact analysis was broken. It was our `PATH`. The hour we spent
  proving ourselves wrong is the most honest paragraph in the whole comparison." → build-story #1
- "Same input, same question — *who calls this class?* codemap: one call, 31 references tagged by role.
  graphlens: two tools and tests hidden by default. Neither is wrong; they're different bets." →
  [graphlens card](tools/graphlens.md)
- "A code graph you can `git diff`: 3.6 MB of canonical JSON versus a 31 MB SQLite database." →
  [comparison](comparison.md)
- "The one check before you trust any resolved-graph tool: did the resolver actually start? Ours never
  provisions one; that's the point." → build-story #1
- "The competitor that does *more* — semantic search, clustering, 14 languages — turned out to be the best
  proof our positioning is right. It's the retrieval half of the sentence; we're the precise-structure half."
  → build-story #2
- "'Deterministic' has two halves. GitNexus nails the first — same input, byte-identical answer. The second,
  a 123 MB binary index you can't `git diff` versus our 4.83 MB of canonical JSON, is where we differ." →
  [GitNexus card](tools/gitnexus.md)
- "Their impact says *48 things could break, medium risk*. Ours says *12 non-test references — 2 in core,
  7 in docs — and 53 in tests*. Depth-and-risk versus provenance — pick your question." →
  [GitNexus card](tools/gitnexus.md)
- "Then we ran it for real: ~18 minutes to embed on CPU, a CUDA-13 runtime side-loaded to use the GPU. The
  retrieval half works — and its cost is exactly why you wrap it, not absorb it." → build-story #2
- "A determinism test went red and the tool was fine — the input was moving under it. Nothing in the artifact
  could tell those two apart, which is when we learned that 'deterministic' is unfalsifiable unless the graph
  says what it was built from." → build-story #4
- "One frozen source tree, two builds of our own tool four commits apart: 30 edges versus 38, and 12 versus 7
  functions graded confidently dead. Both files declared the same schema version — correctly, because only
  open `extras` had changed. Provenance is not schema." → build-story #4
- "The emptiest row in our matrix — four of five tasks N/A — is the most useful tool we found. Not for what
  it does, but for its license: it's the first semantic search we're free to *wrap*, not just route to." →
  build-story #3
- "Same embedding model, two tools, opposite GPU outcomes: GitNexus's onnxruntime ran on a 1080 Ti, ccc's
  torch hard-failed. The runtime, not the card, decides." → [cocoindex-code card](tools/cocoindex-code.md)
- "A month of dogfooding across eleven pre-registered axes, then one more repository produced seven bugs in
  forty-eight hours. Not a fresh pair of eyes — the same author, the same known failure class. Only the
  input was new." → build-story #5
- "A dogfood target is a shape, not a sample. Three of those seven bugs had nothing to do with the new
  layout; they reproduced on our own package, where they had been sitting under our own dogfood for a
  month. One of them was wrong 39% of the time, and no single target exhibited more than two of its three
  mechanisms." → build-story #5
- "The first T2 run said the 68 000-star tool had a file-level model of callers. It did not — `--limit`
  defaults to 20 and the file rows sort first, so the default cut the answer exactly along the line that
  misrepresents the model. When a number looks round, check whether it is a limit." → build-story #6
- "We asked our own tool the same question. `search \"zone\"` returns 50 hits. The true count is 1259, and
  the envelope is `{\"ok\": true}` — in the operation whose whole job is to tell a cold agent what exists.
  A limit is partiality too, and we were marking only the other kind." → build-story #6
- "Publishing the axis where you lose was on our differentiator list. It isn't a differentiator: the
  most-adopted tool in the field states that it leaves 80% more context resident than a file-reading
  agent, and retracted its own benchmark after finding the control arm contaminated in 26 runs of 28."
  → build-story #6

---

## Future stories (skeletons — fill on разбор)

- **#7 …** next tool from R2.2 (OntoIndex / rag_for_git / …). Same shape: setup → the surprising
  measurement → head-to-head → lesson → take/keep. (#1 graphlens, #2 GitNexus, #3 cocoindex-code,
  #6 CodeGraph done.)
- **The determinism story.** Why a diffable graph matters in a PR — needs a concrete "graph diff caught X"
  episode from dogfooding (`gaps/`).
- **The provenance story.** dead-code without false positives; impact that knows tests from core. Has the
  facts (M8–M12), needs a narrative episode.

_When a разбор produces a surprise worth telling, write it here **while it's hot** — the numbers are cheap to
record now and expensive to reconstruct later._
