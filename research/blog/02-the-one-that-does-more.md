# The one that does more — and why that's fine

*A rival code tool that does semantic search, clustering, call-flows, transitive risk-rated impact, and 14 languages, in a 1.7 GB install. At 2 a.m. it feels like they lapped you. Measured, it turned out to be the other half of my own sentence.*

**codemap build-story · post 2** · [Русская версия](02-the-one-that-does-more.ru.md) · [Series index](README.md) · [The repo](https://github.com/kogriv/codemap)

---

> Part of a series on building **[codemap](https://github.com/kogriv/codemap)** — a code
> graph an agent can trust: source-only, deterministic, diffable. The rule stays the same:
> *measurements, not verdict.* Last time the rule saved me from a false takedown. This time
> it saved me from a false panic.

The [previous post](01-the-competitor-wasnt-broken.md) was about a competitor I nearly called broken. This one is the
opposite failure mode: a competitor I nearly called *unbeatable*.

## The setup

My research notes had **GitNexus** filed in a single dismissive line: *"repo → knowledge
graph (3D map) + CLI + MCP, non-commercial license."* Easy to shelve as a visualization toy
with a bad license. Then I installed it — **v1.6.9** — and it is nothing like the desk note.

`npm install gitnexus` pulls **1.7 GB** of `node_modules`: tree-sitter grammars for 14
languages, an ONNX runtime, a native LadybugDB graph engine, transformers.js embeddings.
This is not a toy. It's a **hybrid semantic + structural engine** — BM25 plus vector search
fused with a symbol graph, Leiden community clustering, entry-point process-flow tracing,
transitive risk-rated impact. On the shared benchmark scope (a materialized staging with a
`scope_id` verified identical to mine — more on that below) it indexed 280 files into
**6 344 nodes / 14 661 edges / 276 clusters / 294 flows** in about 25 seconds.

## The two cheap conclusions I had to resist

The graphlens teardown taught me not to dismiss a competitor too fast. GitNexus taught the
opposite discipline — not to *panic* too fast. Two lazy verdicts were on the table:

1. *"It's just a non-commercial 3D-map, nothing to take."* — false; it does several things I
   don't.
2. *"It does semantic search, clustering, flows, 14 languages, risk ratings — they've lapped
   us."* — also false, and the more dangerous one, because it's the kind of thing you
   half-believe at 2 a.m.

The only way out of both was the harness: **same input, same five questions, measure what
each tool is actually _for_.**

## What the measurements actually said

Five questions, on the same target, GitNexus vs codemap:

- **T1 — where is `analyze_zones` defined?** GitNexus's `context` returned **ambiguous — 2
  candidates** (a function in `pipeline.py`, a method in `analyzer.py`) — exactly the two
  definitions codemap surfaces. Both tools are honest about the ambiguity instead of guessing.
  Dead heat. ✅
- **T2 — who calls `MACDZoneAnalyzer`?** Here the models diverge. GitNexus says
  `incoming: {imports: 22}`. codemap says 65 references, split **core 2 · docs 7 · examples 1
  · scripts 2 · tests 53**. GitNexus counts *file imports*; codemap counts *symbol references,
  tagged by role*. Ask "what actually breaks in core?" and only one of them answers. ◐
- **T3 — impact / blast radius.** GitNexus shines: a **transitive** upstream import closure —
  **48 impacted**, a depth histogram of **5 / 15 / 28**, **risk: MEDIUM**, and a per-answer
  `epistemic: exact` label. Richer than codemap's one-hop count *in depth and risk framing* —
  but file-level and **provenance-blind**. Different bet, both correct. ✅
- **T4 — what breaks if a signature changes?** GitNexus has **no** per-call-site argument
  contract. Its `detect-changes` is a git-diff → symbol mapper (that's my `review`, not my
  `call_contract`) — and it **errored without a `.git` directory**. ✖
- **T5 — architecture.** `check --cycles` found 3 real import cycles; 276 clusters and 294
  flows add a narrative layer codemap lacks — but there's no coupling / instability /
  god-object metric. ◐

Read the row honestly and the picture isn't "who wins." It's two tools optimized for
different questions, each strong exactly where the other shrugs.

## The determinism test that cut both ways

GitNexus *claims* deterministic indexing. I didn't take the claim — I materialized **two**
independent clean-room stagings (identical `scope_id`, so provably the same input bytes) and
indexed each. Result: **identical counts, and a byte-identical `impact` answer.** The claim
holds.

But two caveats I'd have missed without looking:

- The artifact is a **123 MB binary LadybugDB** (with a WAL). The *answer* is reproducible;
  the *store* is not something you `git diff`.
- Re-running `analyze` **without** `clean` is **non-idempotent** — it merged and drifted
  6 344 → 6 356 nodes.

So: deterministic *answer* ✅, diffable *artifact* ✖. That distinction is exactly codemap's
differentiator — a 4.83 MB canonical JSON you can review in a PR versus a 123 MB binary blob —
and here it is, measured against a tool that gets the first half right and the second half
differently.

## Then I took it home and ran it for real

The benchmark measured GitNexus on a shared scope. Then I did the other thing — I stood it up
**as a user**, on the *whole* codebase, and lived with it. Two payoffs.

First, the benchmark had honestly flagged one thing unmeasured: *did semantic search retrieve
the **right** things, or just run?* On the fully indexed repo (13k nodes, 4.5k embedding
chunks), it did — a concept query pulled the relevant zone-analysis flows, a clear lift over
keyword noise. The retrieval half of my thesis isn't hypothetical; I watched it work.

Second, I felt the tax the whole thesis is built around. A full embedding pass is **~18
minutes on CPU**; the ANN index needs a network install to exist at all; and getting it onto
the GPU meant side-loading a CUDA-13 runtime plus cuDNN 9. None of that is a knock — it's
*why the split is the right call*. codemap stays a source-only, deterministic,
provisions-nothing graph; a retrieval engine with models and a 1.7 GB footprint is exactly
the kind of thing you **wrap behind an opt-in router**, not absorb into the core. The day of
setup didn't change the verdict — it made the verdict *felt*.

## The three lessons

1. **"They do more" is not "they win."** A tool that does semantic search + clustering +
   flows + 14 languages isn't beating a tool that does deterministic, diffable,
   provenance-precise Python structure — it's playing an *adjacent* game. The harness is what
   lets you say that with numbers instead of nerves.
2. **The most valuable competitor is the one that proves your thesis.** codemap's positioning
   is "the precise structural leg for index-free agents, that *interoperates with* retrieval
   rather than replacing it." GitNexus is a working retrieval + structure hybrid — the
   concrete *other half* of that sentence. It doesn't threaten the thesis; it demonstrates it.
3. **Claims decompose.** "Deterministic" split into deterministic-*answer* (true) and
   diffable-*artifact* (false). Measure the parts, not the slogan — the slogan is where two
   tools sound identical and behave nothing alike.

## What I take, and what I keep

**Take (learn from it):** per-answer **`epistemic`** and per-edge **`confidence`** labels (an
honesty feature I'm adopting); **transitive, depth-bucketed, risk-rated impact** as an opt-in
mode; the **flow / community narrative** as a higher-altitude view; **one-command MCP setup**
into every editor (adoption ergonomics I under-invested in).

**Keep (my edge — measured against a *richer* tool, not a weaker one):** **MIT** versus a
non-commercial license; a **4.83 MB diffable JSON** versus a **123 MB binary DB**;
**provenance-split, symbol-level impact** versus a file-import closure; **per-call-site
contracts** it has no answer for; and **no git required**, **no 1.7 GB**, **no embedding
models** to provision.

**Verdict:** *learn — a strong, adjacent peer.* Complementary, not competing, and the best
evidence yet that codemap's "precise leg" positioning is real — because here's the retrieval
half, built by someone else, working.

---

*codemap is open source (MIT): [github.com/kogriv/codemap](https://github.com/kogriv/codemap).
The full teardown — every command, version, `scope_id`, and number — is public, so you can
reproduce it or catch me where I'm wrong. Built one of these and I measured it unfairly? Open
an issue. The harness is public.*
