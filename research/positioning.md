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
build-story's argument, and the piece the README now leads with. Published as blog post
**[06 — two empty columns](blog/06-two-empty-columns.md)** ([RU](blog/06-two-empty-columns.ru.md)).

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

### The epilogue the post promised (2026-09-08)

Every post in this series ends on the same standing line: *measured your tool and got it wrong? open an
issue.* Two of ours were open in CodeGraph's tracker when post 6 went out — [#1639](https://github.com/colbymchenry/codegraph/issues/1639)
(`callers`/`callees`/`query` truncating at `--limit 20` with nothing in the response saying so) and a
comment on [#1566](https://github.com/colbymchenry/codegraph/issues/1566) (name-matched receivers
fabricating call edges, hence **136 reported cycles where the package has 1**).

**Both were answered and fixed on the same day, eleven days in.** #1639 closed as completed by
[PR #1772](https://github.com/colbymchenry/codegraph/pull/1772) in the morning; #1566 itself at 19:01,
implemented in [PR #1790](https://github.com/colbymchenry/codegraph/pull/1790) — receiver inference now
stops guessing when a known built-in has no matching project method, with a four-fixture before/after
table, **nine negative regression cases that failed before the fix**, and 920 + 889 tests across the native
and wasm engines. The author evaluated a community patch and did not use it; the `this.<field>.method()`
family stays open under #1496/#1691.

Three things there are worth keeping, and only one of them is about them.

1. **The mechanism got its name from a third party, not from us.** `inth3shadows` reproduced #1566 on 1.6.0
   with a five-line TypeScript fixture and localised it: every `instance-method` resolution funnels through
   `resolveMethodOnType`, which validates that the method *exists on the named type* — which is why a wrong
   inference usually yields nothing — but never asks whether the inferred type is a **project** type at all.
   `Map` is not, so `Map.get` gets matched against project classes by name. A report with a repro attracts
   people who can localise; a report with a verdict attracts nobody.
2. **Our numbers are not stale yet, and the condition under which they become stale is now written down.**
   All four PRs are merged to `main` and **none is released** — npm `latest` is still 1.6.0 (2026-08-26),
   and the author says so himself: *"re-index after upgrading once it is released."* Every figure in the card
   still describes shipping behaviour. Backlog item **R2-codegraph** holds the obligation: when a release
   ships, re-measure before quoting 136-vs-41 or the truncation behaviour again. Publishing a fixed defect's
   numbers is the same offence as an unmarked truncation.
3. **One line of ours was wrong, in this series' characteristic direction.** An earlier revision of the card
   read *"still zero comments, eleven days on, while the author closed two other issues that morning"* —
   written at midday and already false by the afternoon. The waiting was real; the shape read into it was
   not. Struck through and dated in place rather than deleted, because the correction is the content.

And the same question asked of ourselves, which was not free: their Python repro, run against codemap 0.0.16
on both tiers, produces **no fabricated edge** — and the fast tier pays for that refusal with recall,
dropping **2 real calls** their resolver finds, which deep recovers. Two prices for the same refusal to
guess, and the second one is ours.

### What we take, what we keep
- **Take:** the watcher loop (M3.2 reranked up — the cost is no longer unknown, it is 121 ms), the
  inline signature on symbol lookup, and the two-arm benchmark contamination control, which is not
  optional for any with/without-agent measurement we ever publish.
  **Taken, same day:** the loop shipped as `codemap watch` + `serve --watch`, and the resulting number
  is worse than theirs — **8.1–8.7 s** save→answer against **0.33 s**, because our rebuild is 4.3 s and
  theirs is a Rust kernel. That second number is itself a correction: the first version of this paragraph
  compared our end-to-end against their *manual* 121 ms sync, which flattered them by 3× and was measured
  against something the card had explicitly listed as not checked. Running their watcher properly makes
  the gap ~20–25× instead of ~70×, and hands us the cheap half of it — their debounce is adaptive, ours
  is flat (M3.2-f1). Publishing all of that is the point: the borrowed idea was the loop, not the speed,
  and a comparison that flatters *either* side undoes the credibility this разбор was built on.
- **Keep:** the honest-nothing rule — now with an eighth application that we found in someone else's
  tool first, and the discipline of running the probe back at ourselves before writing the card.
- **Verdict:** learn-only (strong). Nothing to depend on; the first peer that beats us outright on an
  axis we care about while matching us on correctness where we overlap, and the first whose
  documentation practice is a model rather than a foil.

---

## Build-story #7 — "Two graphs that share no code agreed exactly, and one tool disagreed with itself"

Facts: [OntoIndex card](tools/ontoindex.md). Measured 2026-09-01 on the R2 scope
(`scope_id sha256:300e0a01…5e47d2`, bquant@cb89a24).

### The agreement

`MACDZoneAnalyzer` has been the probe symbol of this whole track. codemap says **57 callers** — griffe for
structure, jedi for call resolution, months of fixes behind that number. OntoIndex is a tree-sitter parser
over an embedded graph store, written in TypeScript, sharing not one line of code with us.

`ontoindex impact MACDZoneAnalyzer --include-tests`, depth-1 CALLS edges: **57**. Not approximately —
set-identical, nothing on either side alone. Repeated on `get_sample_data`: **78 versus 78**.

One thing had to be checked before that sentence was allowed to stand, and it was checked a day late.
Our 57 came off a **deep** build, and the deep tier is not byte-stable (R1-C42) — a set-identity claim
resting on a single build rests on a sample. Three builds of the pinned scope: the artifacts were not
byte-identical (one `accesses` edge of 12190 came and went), and the caller sets were **57 and 78 every
time, the same elements**. The noise exists and does not reach the number the story is about. Had it
reached it, this section would say something else.

That is the strongest external check either tool has had, and it is worth being precise about what it
validates. Not that either is *complete* — both could miss the same call in the same way. But two
independent implementations converging exactly on two answers of that size is not something a shaky graph
produces.

### The disagreement, inside one product

The same tool has a second op for the same question. `context` is its "360-degree view of a symbol", and it
returns **30** callers — with a block named `contextCompleteness` whose `truncated` field says **`false`**.

30 of 57. And on `get_sample_data`, 30 of 78: forty-eight callers dropped, `truncated: false`.

Below the cap it is exact — `NotebookSimulator` 28 of 28, `calculate_macd` 6 of 6 — which is precisely what
makes it invisible. Nothing in the response shape distinguishes "all six" from "thirty of seventy-eight".

Then the second index. Two stagings materialized from byte-identical input returned **different**
30-element subsets of the same 57. So the missing callers are not even stable: diff two runs over an
unchanged repository and callers appear and vanish.

We have shipped this bug's cousin twice — `search` truncating at 20 with no marker, and a limit that never
declared itself (R1-C28). The rule we wrote afterwards was *always declare the limit, including when nothing
was cut.* Here is the version of that failure we had not imagined: not a missing field, but a present one,
computed separately from the cut it describes, confidently saying no.

### And the graph that reported itself empty

`ontoindex report hubs` — the most-central-symbols view, on a graph of **10 745 nodes**:

```
no hubs found (index missing, empty graph, or no connected nodes)
```

Three explanations offered, none of them the real one. The real one is four lines further down, under
`warnings`: the generated Cypher uses `NOT n:Label`, and the vendored store's parser does not support label
negation. Exit code 0. `--json` returns `"hubs": []`. Same failure in `report surprising-connections`.

Confirmed from outside in one line — `cypher "MATCH (s) WHERE NOT s:File RETURN count(s) LIMIT 10"` fails
with the identical parser exception, while `MATCH (s) RETURN count(s)` answers 10 745.

### The uncomfortable part

This is the most careful tool about honesty measured in the whole track. Every call edge carries **how** it
was resolved and how much to trust it — `same-file` 0.95, `import-resolved` 0.9, `global` 0.5, the last one
being name-matching, the exact resolution codemap refuses to emit unflagged. Its `report --help` declares
its own lossiness and routes the reader to the authoritative op. A file skipped for size at index time is
re-announced in the warnings of *every subsequent answer*.

And in the same binary: a completeness field that says the opposite of what happened, and a parser error
dressed as an empty result.

That is the lesson worth carrying, and it is about us, not them. Discipline is not a property a project
*has*; it is a property each answer has to be given, one at a time, by something that checks. Three places
had it. The fourth was written by the same people and nothing caught it — because what catches it is a test
that asks *can this field ever be wrong*, and the absence of exactly that test is what our own release
earlier the same week was about (R1-C38-f1).

Published as blog post **[07 — two graphs that agreed](blog/07-two-graphs-agreed.md)**
([RU](blog/07-two-graphs-agreed.ru.md)).

- **Take:** per-edge resolution *reason* with graded confidence (R1-C39); the first broken step on affected
  flows (R1-C40) — "what stops working" rather than "who references".
  **Taken, both shipped in 0.0.16 (2026-09-09).** R1-C39 landed as `model.RESOLUTIONS`, keyed by
  `(edge type, resolution)` and carrying `means` / `confidence` / `how`, with confidence an **ordinal**
  (`exact | inferred | heuristic`) rather than the float this card admired — a 0.9 invites arithmetic that
  the evidence does not support, which is the one thing we did not copy. R1-C40 landed as `flows_to`, and
  the field is named `first_step`, not `earliest_broken_step`: the sketch's name promised an ordering over
  breakage we cannot compute, and the honest answer is the first step of the route we did find. The sketch
  being renamed by the implementation is the normal case, not a slip.
- **Keep:** the `limit` block computed from the same numbers that did the cutting, never maintained beside
  them. And the diffable, byte-stable artifact: their graph is not reproducible from identical input
  (10 745/20 232 versus 10 747/20 227 nodes/edges), which no amount of labelling compensates for.
- **Verdict:** learn (strong). AGPL-3.0 closes wrap and integrate regardless of merit.

---

## Build-story #8 — "Eight of my last twelve fixes were the same bug" (ourselves)

Facts: [`docs/design/narrowing_audit.md`](../docs/design/narrowing_audit.md) (the matrix),
[`docs/design/deterministic_rendering.md`](../docs/design/deterministic_rendering.md),
[`gaps/flow_entry_points_2026-09-10.md`](../gaps/flow_entry_points_2026-09-10.md),
[`gaps/cycle_rotation_nondeterminism_2026-09-12.md`](../gaps/cycle_rotation_nondeterminism_2026-09-12.md).
Shipped 2026-09-12 in 0.0.18, schema 0.13 unchanged. Suite 918 → 928 → 938.
Published as blog post **[08 — eight of twelve](blog/08-eight-of-twelve.md)**
([RU](blog/08-eight-of-twelve.ru.md)).

### The count that started it

Twelve backlog items closed in a row, R1-C41…R1-C52, each from a real report, each written up, each with
a guard test. Laid out by **cause** instead of by place, **eight of the twelve are one defect**:

| | what it was |
|---|---|
| R1-C28 | a limit cut the answer and did not say |
| R1-C30-f2 | a gate did not name what it had not judged |
| R1-C39 | the route was on the edge; what the route is worth was not |
| R1-C44 | an empty answer did not say which kind of empty |
| R1-C49-f1 | a rule fired and did not name itself |
| R1-C50 | the emptiness of flows did not distinguish two cases |
| R1-C51 | a filter answered with silence and did not declare itself |
| R1-C52 | `diff` silently judged someone else's root |

One sentence covers all eight: **the answer is narrower than it looks, and it is silent about that.** And
**four of the last five were found by consumers**, not by us. At which point fixing them one at a time, as
somebody trips over each, stops being a strategy and becomes a symptom.

### The message that was three findings

The trigger was [#19](https://github.com/kogriv/codemap/issues/19) from the dogfood consumer, the day after
0.0.16, and it arrived as one report with three things in it. The headline: **a library has no entry point.**

```
fast:  ### Flows reached (1 of 285 entry point(s) in root `core`)
deep:  ### Flows reached (0 of 252 entry point(s) in root `core`)
       _No entry point reaches it within 5 step(s)._
```

Same tree, same version, same command but `--deep`. `analyze_macd_zones` is the public function a user calls
to enter the package; it has **43 callers and all 43 are in `tests`/`examples`/`scripts`/`research`**. Our
definition required `in_degree == 0`, counting inbound edges regardless of which root they came from — so a
public API stops being an entry point exactly because someone uses it. Inside the package nobody calls it,
which is the signature of a public API, not of unreachability. And the second mechanism is worse: deep
resolves `build → run`, `run` loses its entry status, and the head of the chain moves to distance 6 — past
the default `--flow-depth 5`. **The better the graph resolves, the smaller the set of entry points**; on fast
it had been working by accident.

The other two findings in the same message were a filter answering with silence and a `diff` judging a root
nobody asked about. Three findings, one shape.

### The decision: audit the mechanism, not the next instance

So the pass was not "fix #19". It was: ask all **31 operations** one question — *what does this answer narrow,
and does it say so?* — with a closed vocabulary of narrowing classes, the way the edge vocabulary is closed:
`limit`, `filter`, `scope`, `bound`, `tier`, `edge-class`, `definition`. Four undeclared narrowings came out
of it, every one **measured rather than suspected**:

- **`columns` was hiding the larger half.** On the dogfood tree it returned **331 keys of 1057** as a plain
  list. The narrowing was deliberate (subscripted keys really are the column-ish set); being undeclared is a
  different thing. Now a `filter` block with `basis`, `total`, `dropped`.
- **`communities` judged one root and said nothing.** True since R1-C18 in the code, nowhere in the answer.
  Invisible on a single-root graph — 91 of 91 — and silent on a repo-scoped one.
- **The entry-point list did not name its definition** — the very definition #19 had just forced us to
  change.
- **`export mermaid --scope` cut the diagram 144 lines → 47 with no mark**, and the result read as "the
  package's class diagram". Now a `%% scope:` line: Mermaid ignores `%%` when rendering, so it costs nothing
  in the picture and is visible in the source people diff and paste into issues.

### The one that ran the other way

Three of those column operations read `reads`/`writes`, and their partiality points in the **opposite**
direction: a literal subscript key is indistinguishable from a dict-literal key, so the set is **larger**
than the truth. Calling that a lower bound is worse than saying nothing — a consumer acting on "at least
these" will prune too little. It got its own wording rather than borrowing the label that happened to exist.

### The pass nearly broke the rule it was defending

The first version added `query` to the partial-operations list, which meant the label "this answer is a lower
bound" on a dossier whose `defined_at`, `matches` and signatures are **exact**; only `used_by` comes from the
better-than-nothing call layer. That label would have said the symbol's *definition* was in doubt.
**Over-declaring partiality is the same defect as hiding it, pointed the other way.** So a mixed answer
declares **per field** — and what caught the slip was `test_structural_ops_have_no_label`, written a month
earlier for a different rule (R1-C13: *absence* of a label means the answer is exact).

### And then the axis the matrix did not have

The next day the lab raised their pin to 0.0.17 and filed [#20](https://github.com/kogriv/codemap/issues/20).
The graph was inert exactly as promised — **1904 nodes, 4652 edges**, the whole JSON byte-identical but for
`provenance.version`; verdicts stable 20 runs out of 20. And the **printed cycle chains** differed between
runs: five runs per version, three distinct md5s, the same three on both versions.

```
0.0.16:  3d8ea0fb  3d8ea0fb  3d8ea0fb  7c4ee567  a9ae9dc7
0.0.17:  3d8ea0fb  7c4ee567  7c4ee567  a9ae9dc7  a9ae9dc7
```

`nx.simple_cycles` enters a cycle wherever set iteration — i.e. string hashing — happens to put it. `arch.py`
then sorted the cycles by `(len, c)`, which **looked** like canonicalisation and could not be: the key moves
with the rotation. Our own reproduction widened the perimeter the report had drawn — under eight hash seeds
**three of seven surfaces** diverged, one of them the structured `architecture` answer the MCP tool returns,
while `report dependencies` and the living docs were stable because they print counts rather than chains. So
the fix went in at the source (`query.py`, where cycles are born), not at the consumer the report pointed at.

**The part that cost the most to notice:** the reporter nearly filed this as a *behavioural change* in the
release, and did not only because they re-measured within one version before writing their conclusion. Our
own release procedure verifies every claim by comparing the output of **two published versions on one tree** —
so the next person to read a rotation as a behaviour change would have been us, with the message already sent.

### The lesson (reusable)

**An audit is complete along the axes it has.** The narrowing matrix was full — 31 operations, no cell reading
"applies and is not declared" — and it could not find the axis it lacked, because it asked whether the answer
*declares* itself and never whether the answer is the *same twice*. `reproducibility` is now the eighth class,
and its declaration is a guard across hash seeds in spawned processes (`PYTHONHASHSEED` is read once at
interpreter start, so an in-process patch cannot produce the condition).

Two smaller rules, each bought with a specific error:

- **A claim about text is verified under a fixed hash seed.** The release procedure now says so, because the
  procedure that verifies releases was this defect's second victim.
- **A guard checked with invented data is not checked.** The CI step that now guards the README's test count
  was first dry-run against a pytest summary I had written from memory; the real numbers differed. The guard
  existed to stop exactly that.

### What this bought
- **Kept:** the closed vocabulary, now over narrowings as well as edges — a new class has to be added here,
  not arrive silently. And the habit of counting one's own closed items by cause, which is what made the
  pattern visible at all; no single one of the eight looked like anything but its own bug.
- **Given up:** the idea that a completed audit closes a mechanism. It closes the mechanism *as modelled*.
  What found the ninth instance was a consumer raising a pin, twenty-four hours later.
- **Shipped:** 0.0.16, 0.0.17, 0.0.18 across three days, schema **0.13** untouched — the seventh consecutive
  release without a schema change, which is the point of having the envelope carry these blocks additively.

---

## Build-story #9 — "464,109 cycles, every one real" (ourselves, axis B4)

Facts: [`gaps/third_shape_2026-09-12.md`](../gaps/third_shape_2026-09-12.md) (pre-registration §1–§5,
reconciliation §6), [`docs/design/stub_files.md`](../docs/design/stub_files.md),
[`docs/design/cycle_tangles.md`](../docs/design/cycle_tangles.md), BACKLOG R1-C55…R1-C58.
Shipped 2026-09-12 in 0.0.19 + 0.0.20, schema 0.13 unchanged (ninth consecutive release). Suite 938 → 972.
Published as blog post **[09 — true and worthless](blog/09-true-and-worthless.md)**
([RU](blog/09-true-and-worthless.ru.md)).

### The run

Both existing dogfood trees are code written by the author, for consumers written by the author. Axis **B4** —
*other people's idioms* — fed the same questions to three frozen third-party checkouts, each breaking a
different assumption: **pytest** (façade and implementation as two top-level packages, 52 hooks nobody calls by
name), **attrs** (9 `.pyi` describing the public API, classes finished at runtime), **Pillow** (compiled
modules with no Python source, plugin registration as an import side effect).

Pre-registered: six controls, five predictions, a stop rule. Score — **one control failed on the first target**
(`build attrs/src/attrs` → exit 1, `Could not resolve alias attrs.field`), two predictions confirmed, **two
refuted**, one inverted, and **four findings that were not on the list.** The two refuted ones matter most:
they predicted the stubs would be *silently ignored* — the defect class of the previous month — and the stubs
were instead read as full modules, which was worse.

### The finding: correct and worthless

| tree | modules | hard | lazy | type-only |
|---|---|---|---|---|
| codemap | 52 | 0 | 0 | 0 |
| bquant | 92 | 0 | 9 | — |
| **`_pytest`** | **78** | **1080** | **95 001** | **464 109** |

Every one of those cycles is real. The numbers are not *large*, they are **combinatorial**: the report spent
1632 lines and 10.3 s enumerating paths through one knot in order to print twenty of them. The reader's action
in all 464,109 cases is the same one action. And E11 came back inverted in the same output: the two *less*
severe lists truncate at 20 and declare it, while the **most** severe prints all 1080 lines.

Beside it, the mirror image: `PIL` reported **one** hard cycle — the flagship number — and it was assembled
out of `from . import ImageFont` in **`_imagingft.pyi`**, a file Python never executes, pointing at a C
extension. **100% false positive on the one number that is unambiguously actionable.**

### The guard that refused the fix

Replacing the count with strongly connected components glues two loops that share a module into one blob — and
a guard written two weeks earlier went red. That guard came from **our own worst reported defect**
([#11](https://github.com/kogriv/codemap/issues/11), 2026-08-28): `report architecture` printed *"Import
cycles: 0 — import graph is acyclic"* on a consumer tree with two real cycles, because the import map was
module-level only and **26% of their intra-package import graph was invisible** — the invisible part being
function-local imports, i.e. exactly what developers use to break a cycle. Both of their cycles ran through one
shared module, so the repair pinned *two loops sharing a module are two problems*. Hence **cycle rank**,
`E − V + 1`: linear, non-explosive, and equal to the old count where the old count meant something (bquant
9 → 9, attr 10 → 10; `_pytest` 1080 → 57).

**We were two weeks from swallowing a cycle for the second time, from the opposite end** — first by not seeing
the edges, then by blurring the loops. Nothing in the second attempt resembled the first, and the only reason
it failed loudly is that the first had been written down as a **property** rather than as a fix.

### What the other three findings were

- **R1-C55** — 40 of 63 `high` dead-code verdicts on `PIL` override a base method with an inbound call in the
  same graph (191 `inherits` edges available). Template method, 63% of the most confident grade false.
  `PIL` 63 → 15; codemap 31 → 31, bquant 2 → 2.
- **R1-C56** — `.pyi` had three answers in one tool (extractor / manifest / dead-code), each a deliberate
  decision made at a different time. Fourth import scope `stub`; `PIL` hard cycles 1 → 0; `_pytest` byte-identical.
- **R1-C57** — the façade: `api-surface` printed "1 public symbols across 1 modules" over 90 lines of
  re-export, and the build's warning never reached the report. Now 88 named as re-exported from outside the
  root, and not judged there.

### The lesson (reusable)

**Measurement cannot tell a true number from a meaningful one.** *Measure, never assert* has no opinion about
this class: 464,109 was measured, the assertions were green, the artifact was byte-stable, the schema was
untouched, and the answer was garbage. Build-story #5 concluded *the target is a shape, not a sample* about
defects; this is the same sentence one level up, about **definitions** — a metric is known to be meaningful
only on the shapes it has been fed, and ours had been fed two, both written by us.

The fourth verification rule, bought here: **a fixture is a claim too.** The guard for the façade crash passed
with the fix mutated off, because reproducing it needs `@overload` in a stub over a name the runtime module
merely aliases — what `attrs/__init__.pyi` has and a hand-written fixture did not.

### What this bought
- **Kept:** the pre-registration discipline, which earned its keep by being wrong in public — a list of
  expectations is not a forecast to be proud of, it is what makes "I was surprised" unrevisable afterwards.
- **Given up:** the simple-cycle count, deliberately, and any promise about which single edge breaks a knot
  cheapest (minimum feedback arc set, NP-hard).
- **Shipped:** 0.0.19 and 0.0.20 in one day, four findings closed, suite 938 → 972, schema **0.13** untouched
  for the ninth consecutive release — which is why four repairs of this size were answer-layer changes rather
  than a migration.

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

- "Two code graphs that share no line of code — tree-sitter over an embedded store, griffe plus jedi over
  sorted JSON — returned the same 57 callers, and then the same 78. Neither is proof of completeness; both
  stopped being one implementation's opinion." → build-story #7
- "A field named `truncated` reported `false` while thirty of seventy-eight callers were dropped. A limit
  that forgets to declare itself is a bug we have shipped; a completeness field maintained beside the cut
  instead of by it is worse, because it converts an unknown into a confident no." → build-story #7
- "The most careful tool about honesty we have measured also printed 'no hubs found — index missing, empty
  graph' over a graph of 10 745 nodes, because its query would not parse. Discipline is not a property a
  project has; it is one each answer has to be given by something that checks." → build-story #7

---

- "I laid my last twelve bug fixes out by cause instead of by place, and eight of them were the same bug:
  the answer is narrower than it looks and is silent about that. Four of the last five had been found by
  consumers, not by me." → build-story #8
- "A public function with 43 callers, every one of them in tests or examples, stopped being an entry point
  because somebody used it. Nobody inside the package calls it — which is the signature of a public API, not
  of unreachable code." → build-story #8
- "One operation returned 331 of 1057 keys as a plain list. The narrowing was deliberate; being undeclared
  is a different thing, and the consumer cannot tell those apart." → build-story #8
- "Over-declaring partiality is the same defect as hiding it, pointed the other way — a blanket 'lower bound'
  on a mixed answer says the symbol's definition is in doubt. The slip was caught by a test written a month
  earlier for the opposite rule." → build-story #8
- "Three operations read a set that is *larger* than the truth, not smaller. Calling that a lower bound is
  worse than silence: the consumer prunes too little." → build-story #8
- "A completed audit closes the mechanism as modelled. Mine was full — 31 operations, no undeclared cell —
  and twenty-four hours later a consumer found the axis it did not have: the answer can be complete,
  declared, and different from run to run." → build-story #8
- "The graph was byte-identical but for one version field, the verdicts were stable 20 runs out of 20, and
  the printed cycle chains had three distinct md5s. The reporter nearly filed it as a behavioural change —
  and my own release procedure, which compares two published versions' output on one tree, would have been
  the next victim." → build-story #8
- "My tool reported 464,109 import cycles and every one of them was real. Two mutually-dependent modules make
  one cycle; a third in the same knot multiplies the paths. The report spent 1632 lines and 10.3 s enumerating
  half a million of them to print twenty." → build-story #9
- "On the next package it reported exactly one hard import cycle — the flagship number, the one that is
  unambiguously actionable — and that cycle was assembled out of a `.pyi`, a file Python never executes,
  pointing at a C extension. 100% false positive." → build-story #9
- "Measurement cannot tell a true number from a meaningful one. The assertions were green, the artifact was
  byte-stable, the schema was untouched, the guards were satisfied, and the answer was garbage." →
  build-story #9
- "I was two weeks from swallowing a cycle for the second time, from the opposite end: first I could not see
  the function-local edges, then I would have blurred two loops into one blob. What stopped me was that the
  first repair had been written down as a property rather than as a fix." → build-story #9
- "40 of 63 'no inbound calls, references, or decorators' verdicts were overrides of a base method the same
  graph records a call to. The template method, and 63% of my most confident grade was false." →
  build-story #9
- "Declaring a defect does not discharge it: the tool said 'read the input identity as unknown' in plain
  words, and on every tree that ships stubs `--incremental` and `watch` silently degraded to 'I don't know'
  anyway." → build-story #9
- "My guard test passed with the fix mutated off, because my hand-written fixture did not carry the defect's
  shape. A fixture is a claim too, and it has to be verified against the old version." → build-story #9

## Future stories (skeletons — fill on разбор)

- **#10 …** next tool from R2.2 (rag_for_git / Understand-Anything / …). Same shape: setup → the surprising
  measurement → head-to-head → lesson → take/keep. (#1 graphlens, #2 GitNexus, #3 cocoindex-code,
  #6 CodeGraph, #7 OntoIndex done; #4, #5, #8, #9 are about ourselves.)
- **The determinism story.** ✅ Told twice, neither time as sketched: #4 (a determinism *test* went red and
  the tool was fine) and #8 (the artifact was byte-stable and the *rendering* was not). The sketch asked for
  "graph diff caught X" and the episodes that happened were both sharper than that.
- **The provenance story.** dead-code without false positives; impact that knows tests from core. Has the
  facts (M8–M12), still needs a narrative episode — the only sketch left, and it has now been outrun by
  five posts that had one (P5, P6, P7, P8, P9). Note that P9 delivered a *piece* of it and did not unblock
  it: R1-C55 is dead-code false positives measured on a third-party tree (63 → 15 on `PIL`), which is the
  first beat of the sketch. What is still missing is the beat where a **provenance split changed a
  decision** — role-tagged impact, not grading.

_When a разбор produces a surprise worth telling, write it here **while it's hot** — the numbers are cheap to
record now and expensive to reconstruct later._
