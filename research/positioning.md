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

Schema **0.9**, ~**159 tests**, warm serve + MCP + SCIP export.

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

---

## Future stories (skeletons — fill on разбор)

- **#3 …** next tool from R2.2 (CodeGraph / OntoIndex / Sentrux / …). Same shape: setup → the surprising
  measurement → head-to-head → lesson → take/keep. (#1 graphlens, #2 GitNexus done.)
- **The determinism story.** Why a diffable graph matters in a PR — needs a concrete "graph diff caught X"
  episode from dogfooding (`gaps/`).
- **The provenance story.** dead-code without false positives; impact that knows tests from core. Has the
  facts (M8–M12), needs a narrative episode.

_When a разбор produces a surprise worth telling, write it here **while it's hot** — the numbers are cheap to
record now and expensive to reconstruct later._
