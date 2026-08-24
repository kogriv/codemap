# codemap build-story — the blog series (editorial plan)

**What this is.** The production plan for a Markdown dev-blog series (dev.to / Hashnode /
Medium) that turns the build-story track into published articles. It is the *editorial
layer*: order, working titles, hooks, beats, evidence, and per-post status. It is **not**
new source material — every fact comes from [`../positioning.md`](../positioning.md)
(narrative) which itself reproduces from the cards in [`../tools/`](../tools/) and
[`../comparison.md`](../comparison.md) (evidence). If a number here and a card disagree,
the card wins.

**Chain of custody (keep it this way):**

```
research/tools/*.md   →  research/comparison.md  →  research/positioning.md  →  research/blog/NN-*.md
(measure, evidence)      (comparison hub)           (narrative, "hot" prose)   (published articles)
```

Realizes the publication half of **R1-C14** (positioning → articles).

---

## The through-line (what makes it a series, not five posts)

One idea threads every article: **measurements, not verdict.** codemap's whole pitch is a
code graph an agent can *trust* — deterministic, diffable, provenance-aware — so the blog
has to earn trust the same way the tool does: every claim carries a number and a link, the
gaps section is load-bearing, and rival authors are treated as potential collaborators, not
enemies. The recurring beat readers should feel by post 3: *this author measures before he
concludes — even against himself.*

**Canonical positioning line** (use as the standing one-liner / sub-head; do not reword
per post):

> A code graph an agent can trust: source-only, deterministic, diffable — no index to go
> stale, no LSP to provision.

**Audience.** Developers building AI coding agents / MCP tooling; Python infra people;
anyone who has been burned by a stale embeddings index or an LSP that won't provision.

**Venue & tags.** Primary dev.to (canonical), cross-post Hashnode/Medium.
Tags: `#python`, `#ai`, `#devtools`, `#showdev` (+ `#opensource` on the launch post).

**Standing CTA (foot of every post).** One line to the repo (MIT), one line to the
comparison hub for the receipts, one invitation: *"Measured your tool and I got it wrong?
Open an issue — the harness is public."*

---

## Publish order

Two valid orders; I recommend **A**.

- **A — hook-first (recommended).** Lead with the graphlens detective story (#1). It's the
  most self-contained and the most viral, needs zero prior knowledge of codemap, and its
  moral ("did the resolver even start?") is useful to *anyone* benchmarking a graph tool —
  so it pulls a cold audience in, then the closing CTA hands them the launch post. Publish
  order: **P1 → P0 → P2 → P3 → P4 → P5.**
- **B — canonical.** Classic launch order, Story Zero first as the anchor, then the
  build-stories in sequence: **P0 → P1 → P2 → P3 → P4 → P5.** Safer, lower first-day reach.

Either way the *numbering below is by narrative role* (P0 = intro), not by publish date.

---

## The posts

Status legend: 🔲 not started · ✍️ drafting · 🔎 review · ✅ published

### P0 — "A code graph an agent can trust" (the launch / Story Zero)
- **Status:** 🔎 draft approved, ready to publish (EN + RU, kept out of repo)
- **Role:** the anchor — what codemap is, why it exists, where it sits in the field.
- **Hook:** agents navigating code have two bad options — grep (exact but structure-blind)
  and embeddings/RAG (fuzzy, non-deterministic, perpetually stale). The third path, a
  precise structural graph, kept shipping as an opaque non-diffable index that rots on the
  next commit. codemap's bet is the third path done *diffable*.
- **Beats:** the itch → the bet (source-only / canonical & diffable / provenance / native
  MCP verbs) → the arc M0→M19 (four sentences, not a changelog) → where it sits (the
  under-served axis: resolved + deterministic + source-only + Python-deep + agent-facing) →
  honest gaps (no cross-boundary resolution; Python-only; rebuild-not-watch, now softened
  by C9+#3) → what's next.
- **Evidence:** [positioning.md](../positioning.md) §Story Zero + [00_landscape.md](../00_landscape.md).
- **Length:** ~1500 words. **Depends on:** nothing.
- **Note:** the arc must cite *current* facts — schema 0.11, 369 tests, 29 ops / 26 MCP
  tools, and the freshness story now includes C9 (incremental) + `reload` (issue #3), no
  longer just "rebuild."

### P1 — "The competitor wasn't broken. We were." (graphlens)
- **Status:** 🔎 draft approved, ready to publish (EN + RU, kept out of repo)  ← **first to publish**
- **Role:** the trust-builder. A near-takedown we talked ourselves out of.
- **Hook:** we almost published that a rival's impact analysis was broken — it returned
  *zero* callers for a class codemap mapped fully. The bug was our `PATH`.
- **Beats:** the setup (graphlens = nearest twin, ambitious `ty`+tree-sitter backend) →
  the empty result and the cheap verdict we nearly shipped → the nagging detail
  (`resolver_status: "degraded"` — the tool told us) → opening the hood (`shutil.which("ty")`
  vs a bundled bin `uv tool install` never put on PATH → silent `except Exception:` degrade)
  → the one-line fix → the fair re-run (12s→2m20s, 20.9k→55.7k edges, empty→9 callers) →
  the honest head-to-head (codemap 31 refs by provenance vs graphlens hides tests by
  default — both defensible) → **the reusable lesson** (a graph tool can silently degrade
  to grep; "it returned nothing" is a hypothesis, not a finding; check `resolver_status`
  before you trust *or* benchmark).
- **Evidence:** [graphlens card](../tools/graphlens.md), positioning §Build-story #1.
- **Length:** ~2000 words. **Depends on:** nothing (self-contained; that's why it leads).

### P2 — "The one that does more — and why that's fine." (GitNexus)
- **Status:** 🔎 draft approved, ready to publish (EN + RU, kept out of repo)
- **Role:** thesis-proving. The richer rival that turns out to *demonstrate* the pitch.
- **Hook:** a rival that does semantic search + clustering + flows + 14 languages, in a
  1.7 GB install. The 2 a.m. fear: they lapped us. The measured answer: they're the other
  half of our own sentence.
- **Beats:** the setup (v1.6.9, 1.7 GB, hybrid semantic+structural, 6344 nodes on shared
  scope) → the two verdicts to resist ("nothing to take" / "they've lapped us") → the
  harness (same input, same 5 questions, measure what each is *for*): T1 dead heat, T2
  imports-vs-provenance, T3 GitNexus's transitive risk-rated impact (richer in depth,
  provenance-blind), T4 no call-contract, T5 flows/clusters vs coupling metrics → the
  determinism test that cut both ways (deterministic *answer* ✅ / diffable *artifact* ✖ —
  123 MB binary DB vs 4.83 MB JSON; non-idempotent re-analyze) → the "ran it for real"
  postscript (semantic retrieval *works*; the ~18-min CPU embed + CUDA side-load is exactly
  *why* you wrap it, not absorb it) → **lesson** ("they do more" ≠ "they win"; the best
  competitor is the one that proves your thesis; claims decompose).
- **Evidence:** [GitNexus card](../tools/gitnexus.md), positioning §Build-story #2.
- **Length:** ~2200 words. **Depends on:** P0 for the "wrap vs absorb" framing (link it).

### P3 — "The competitor that does *less* — and that's why we take it." (cocoindex-code)
- **Status:** 🔎 draft approved, ready to publish (EN + RU, kept out of repo)
- **Role:** the composition/licensing turn. The emptiest coverage row = the most useful find.
- **Hook:** the tool that did *less* than anything else we measured — four of five tasks
  N/A — is the one we're actually adopting. Not for its features. For its license.
- **Beats:** the setup (`ccc` = embed + NL-query, no graph) → the surprise (emptiest row,
  most valuable разбор) → why: **fit × license**, not capability — GitNexus does more but is
  PolyForm-NC (route-only); `ccc` is Apache-2.0 (wrap-able, the first ownable semantic leg)
  → the measurement that shows the fit (concept query nails pivot_points.py rank 1 with zero
  name knowledge; exact-symbol query goes fuzzy — the boundary *is* the point) → the GPU
  aside that falsifies a lazy benchmark (torch arch-list lottery; warm daemon returned the
  same 34s for three "different" device settings; auto-detect hides the honest CPU number) →
  **lesson** ("does less" can be worth more; wrap/route/learn is a licensing decision;
  measure the *boundary*, not the hit).
- **Evidence:** [cocoindex-code card](../tools/cocoindex-code.md), positioning §Build-story #3.
- **Length:** ~2000 words. **Depends on:** P2 (contrast NC-route vs Apache-wrap; link it).

### P4 — "A code graph you can `git diff`." (the determinism story)
- **Status:** 🔲 — **needs one dogfood episode before it can ship** (see Gaps below).
- **Role:** the single deepest differentiator, told as a concrete win, not a slogan.
- **Hook:** every other graph tool hands you a binary index — 31 MB SQLite, 123 MB
  LadybugDB. codemap hands you canonical JSON you can read in a PR. Here's the day that
  mattered.
- **Beats:** why timestamp-free canonical JSON → "deterministic" decomposed (answer vs
  artifact; recall the GitNexus split) → **the missing piece: a real "graph diff caught X"
  episode** from dogfooding → schema-versioned, sorted, insertion-independent (C9's
  `to_dict` sort) → the cost we pay (Python-only, jedi's deep-tier variance — tell it
  honestly).
- **Evidence:** [comparison.md](../comparison.md); needs a new episode in `gaps/`.
- **Length:** ~1600 words. **Depends on:** capturing the episode (blocking).

### P5 — "Impact that knows tests from core." (the provenance story)
- **Status:** 🔲 — has the facts (M8–M12), needs a narrative episode.
- **Role:** the "opinionated graph" payoff — provenance-aware dead-code and impact.
- **Hook:** "48 things could break, medium risk" vs "12 non-test references — 2 in core,
  7 in docs — and 53 in tests." Same repo. Depth-and-risk vs provenance — pick your question.
- **Beats:** multi-root provenance (core/tests/docs/examples/scripts) → dead-code without
  the dominant false-positive source (vulture comparison) → impact tagged by role → why an
  agent needs "what breaks in *core*" not "what breaks" → the honest limit (one-hop by
  default; transitive is GitNexus's bet).
- **Evidence:** positioning §Future stories (provenance) + M8–M12 facts.
- **Length:** ~1600 words. **Depends on:** a concrete before/after episode.

### (later) P6 — "#4: the next tool" + a possible methods post
- The positioning doc keeps a slot for build-story **#4** (next R2 tool: CodeGraph /
  OntoIndex / Sentrux / …) — same shape (setup → surprising measurement → head-to-head →
  lesson → take/keep). Becomes a post when that разбор lands.
- Optional **methods post** — "How to benchmark a code-graph tool without fooling yourself":
  the harness itself (identical `scope_id`, `resolver_status` gate, warm-daemon trap,
  claims-decompose). Strong standalone SEO piece; pull the reusable lessons from P1–P3.

---

## Where the drafts live (and why not here)

Drafts are written **outside this repository** and are never committed: the repo is public
and mirrored, and unfinished prose has no business in public git history. Only this
editorial plan lives in-repo (a plan, not a draft) — the same way `positioning.md` already
carries the narrative publicly.

Each post is written **bilingually**, as two sibling files: `NN-slug.md` (EN, the canonical
publish) and `NN-slug.ru.md` (RU mirror — a full translation, same frontmatter, same
numbers).

**Current state:** P0, P1, P2, P3 drafted and approved in both languages (~10k words). Not
yet published anywhere — inter-post cross-links are still `[...](#)` placeholders, to be
filled with real URLs as each post goes live (recommended order: P1 → P0 → P2 → P3).

**One editorial note carried into the drafts:** the GPU aside in P3 names hardware by
*architecture* ("an older Pascal card", "a newer Ampere card"), not by machine or model
inventory. The technical point — the `sm_61` vs `sm_75+` arch lottery — survives intact; the
infrastructure specifics don't travel.

## Ready to draft now vs blocked

- **Drafted & approved (EN + RU):** P0, P1, P2, P3 — done; awaiting publication only.
- **Blocked on a dogfood episode:** P4 (needs a "graph diff caught X" story), P5 (needs a
  concrete provenance before/after). Capture these opportunistically while dogfooding on
  bquant, into `gaps/`, then promote to positioning §Future stories, then draft. **This is
  the only remaining writing work in the series** — it is deliberately not forced: the
  episodes have to happen, not be invented.

## Per-post checklist (before a post goes 🔎→✅)

- [ ] Every number reproduces from a linked card or positioning.md.
- [ ] Gaps/limits section present and honest (not an afterthought).
- [ ] Rival framed as peer/collaborator, no takedown tone.
- [ ] Canonical positioning line as sub-head; standing CTA at the foot.
- [ ] Current facts (schema 0.11 / 369 tests / 29 ops-26 MCP), not a stale snapshot.
- [ ] Code snippets runnable / faithfully quoted (file:line where quoted from source).
- [ ] Cross-links to sibling posts added once they exist.
