# codemap build-story — the series

Field notes from building **codemap**: how the tool came to be, and what happened when it
was measured — honestly, on a shared target — against the nearest rival tools. Every post
is published **here, in the repository**; each one exists in English and Russian.

One rule threads all of them: **measurements, not verdict.**

> A code graph an agent can trust: source-only, deterministic, diffable — no index to go
> stale, no LSP to provision.

## Read the series

| # | Post | EN | RU |
|---|------|----|----|
| 0 | **A code graph an agent can trust** — what codemap is, the bet it makes, where it sits in the field, and the honest limits. | [EN](00-a-code-graph-an-agent-can-trust.md) | [RU](00-a-code-graph-an-agent-can-trust.ru.md) |
| 1 | **The competitor wasn't broken. We were.** — I nearly published that a rival's impact analysis was broken. The bug was my `PATH`. | [EN](01-the-competitor-wasnt-broken.md) | [RU](01-the-competitor-wasnt-broken.ru.md) |
| 2 | **The one that does more — and why that's fine.** — a 1.7 GB hybrid rival that turned out to prove the thesis instead of threatening it. | [EN](02-the-one-that-does-more.md) | [RU](02-the-one-that-does-more.ru.md) |
| 3 | **The competitor that does *less* — and that's why I take it.** — the emptiest coverage row was the most useful find. Not for its features; for its license. | [EN](03-the-one-that-does-less.md) | [RU](03-the-one-that-does-less.ru.md) |
| 4 | **My determinism test went red. The tool was fine.** — the input was moving under it, and nothing in the artifact could tell that from a real bug. | [EN](04-the-determinism-test-that-was-right.md) | [RU](04-the-determinism-test-that-was-right.ru.md) |
| 5 | **A month of dogfooding. Then one more repository found seven bugs in two days.** — eleven pre-registered axes, all asked of one tree. What was missing was not an angle but a shape. | [EN](05-the-second-repository.md) | [RU](05-the-second-repository.ru.md) |
| 6 | **I measured the 68,000-star competitor. It was faster than mine. That wasn't the finding.** — four rivals, and the same two columns empty in all of them. Point questions have a seed symbol; whole-graph questions don't. | [EN](06-two-empty-columns.md) | [RU](06-two-empty-columns.ru.md) |

Suggested reading order for a newcomer: **1 → 0 → 2 → 3 → 4 → 5 → 6** (the detective story needs no
prior knowledge of codemap and explains the method the rest depend on). Chronological
readers can start at 0. Posts 4, 5 and 6 are the ones where the method is turned on the author — 4 on a
claim of his, 5 on the limits of how he was testing it, 6 on three differentiators he had to give up.

---

## Where these come from

The posts are the *publication layer* of the research track. They introduce **no new
facts** — every number reproduces from a tool card or the comparison hub:

```
research/tools/*.md   →  research/comparison.md  →  research/positioning.md  →  research/blog/NN-*.md
(measure, evidence)      (comparison hub)           (narrative, "hot" prose)   (the articles)
```

If a number in a post and a number in a card disagree, **the card wins**. Realizes the
publication half of **R1-C14**.

**The through-line.** codemap's pitch is a code graph you can *trust* — deterministic,
diffable, provenance-aware — so the writing has to earn trust the same way the tool does:
every claim carries a number and a link, the limits section is load-bearing, and rival
authors are treated as potential collaborators, not enemies. The beat a reader should feel
by post 3: *this author measures before he concludes — even against himself.*

**Venue.** The repository (GitHub + GitLab) is the venue. External syndication (dev.to /
Hashnode / Medium) is deliberately **not** done for now; if it ever is, the posts get
frontmatter and canonical URLs pointing back here.

**How they're written.** Bilingual, as sibling files: `NN-slug.md` (EN) and `NN-slug.ru.md`
(a full translation — same structure, same numbers). Work-in-progress drafts stay **outside
the repo** until approved; only finished posts land here, so public git history never
carries half-formed prose.

**One editorial rule carried into the posts.** Hardware is named by *architecture* ("an
older Pascal card", "a newer Ampere card"), never by machine inventory. The technical point
— the `sm_61` vs `sm_75+` arch lottery — survives intact; infrastructure specifics don't
travel.

---

## Status & what remains

Legend: 🔲 not started · ✍️ drafting (out of repo) · ✅ published here

| Post | Status | Evidence |
|---|---|---|
| P0 — launch / Story Zero | ✅ EN + RU | [positioning](../positioning.md) §Story Zero, [landscape](../00_landscape.md) |
| P1 — graphlens | ✅ EN + RU | [graphlens card](../tools/graphlens.md) |
| P2 — GitNexus | ✅ EN + RU | [GitNexus card](../tools/gitnexus.md) |
| P3 — cocoindex-code | ✅ EN + RU | [cocoindex-code card](../tools/cocoindex-code.md) |
| P4 — the determinism story | ✅ EN + RU | [graph_provenance_2026-08-25](../../gaps/graph_provenance_2026-08-25.md) §2, §6; [positioning](../positioning.md) build-story #4 |
| P5 — the second repository | ✅ EN + RU | issues #4–#10 (all closed); [positioning](../positioning.md) build-story #5 |
| P6 — two empty columns | ✅ EN + RU | [CodeGraph card](../tools/codegraph.md), [comparison](../comparison.md) matrix, [docs/whole-graph-questions.md](../../docs/whole-graph-questions.md); [positioning](../positioning.md) build-story #6 |
| P7 — the role-provenance story | 🔲 **blocked** | has the facts (M8–M12), needs a concrete before/after episode. R1-C24 (`codemap tests`) is the likeliest source of one |
| P8 — next tool / methods post | 🔲 later | lands when the next R2 разбор does |

A post's number is its filename slot, assigned **on publication** — a planned post takes the next
free number when it actually lands, not when it is sketched. Which is why the role-provenance story
has now been P5, P6 and P7 without a word of it being written: waiting costs it a number each time a
post that *did* have an episode goes out first. That is the rule working, not failing.

**P7 is the only writing left, and it is deliberately not forced.** It needs an episode that
actually *happened* — a provenance split that changed a real decision. Inventing one would break
the single rule the series rests on. Capture it opportunistically while dogfooding, into `gaps/`,
then promote to [positioning.md](../positioning.md) §Future stories, then write the post.

**Both published posts departed from their sketch, and that is worth recording** — it is the
series' own method turned on its plan. P4 was going to be "a graph diff caught a regression"; the
episode that landed (2026-08-24) was the sharper inverse — a determinism *test* went red, and the
cause was the input moving under it, not the tool. Nothing in the artifact could tell those two
apart: the same source tree, built by two codemap versions four commits apart, yields 30 vs 38
edges and 12 vs 7 `high` dead-code verdicts, and **both files declare `codemap_schema: "0.11"`**.
Written up in [graph_provenance_2026-08-25](../../gaps/graph_provenance_2026-08-25.md); the fix is
**R1-C25, shipped 2026-08-25** (schema 0.12), so the post ends with the repair rather than the
complaint — including the finding the repair made *askable*: `--incremental` had the same blind
spot one level down. P5 was not planned at all: it came from pointing the tool at a second
repository, which produced seven issues in forty-eight hours. Neither was P6, which came from
measuring the field's most-adopted tool and losing three differentiators in the process. Three
published posts, none of them writable from its sketch — which is the argument for not forcing P7.

Sketch for the one that remains:

- **P7 — "Impact that knows tests from core."** *"48 things could break, medium risk"* vs
  *"12 non-test references — 2 in core, 7 in docs — and 53 in tests."* Beats: multi-root
  provenance → dead-code without the dominant false-positive source → impact tagged by role
  → why an agent needs "what breaks in *core*" → the honest limit (one-hop by default).

## Per-post checklist (before a post goes ✍️ → ✅)

- [ ] Every number reproduces from a linked card or `positioning.md`.
- [ ] Limits/gaps section present and honest — not an afterthought.
- [ ] Rival framed as peer/collaborator; no takedown tone.
- [ ] Positioning line near the top; the standing invitation at the foot ("measured your
      tool and I got it wrong? open an issue").
- [ ] Current facts (schema 0.12 / 580 tests / 31 ops — 28 MCP tools), not a stale snapshot.
- [ ] Code snippets runnable or faithfully quoted (`file:line` where quoted from source).
- [ ] Both language files updated together; cross-links and the index table above updated.
