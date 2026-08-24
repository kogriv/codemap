# The competitor that does *less* — and that's why I take it

*It does less than anything else I measured — four of five benchmark tasks are structurally N/A. It's also the one tool I'm actually adopting. Not for its features. For its license.*

**codemap build-story · post 3** · [Русская версия](03-the-one-that-does-less.ru.md) · [Series index](README.md) · [The repo](https://github.com/kogriv/codemap)

---

> Part of a series on building **[codemap](https://github.com/kogriv/codemap)** — a code
> graph an agent can trust: source-only, deterministic, diffable. Rule unchanged:
> *measurements, not verdict.*

The [last post](02-the-one-that-does-more.md) was about the tool that did *more* — GitNexus, a 1.7 GB hybrid engine that
turned out to prove my thesis rather than threaten it. This one is the opposite bet, and the
more surprising result.

## The setup

**cocoindex-code** (`ccc`) does *less* than anything else I'd measured. No call graph. No
impact. No architecture. No symbols. Point it at a repo and it does exactly one thing: embed
the code with tree-sitter chunking, and answer a natural-language query with the nearest
chunks.

On my five-task benchmark, **four of the five are structurally N/A.** Ask `ccc` "who calls
`MACDZoneAnalyzer`?" and it returns semantically-similar *docs and tests* — not a caller list,
because there is no graph for anything to have callers *in*. By the coverage matrix, it's the
emptiest row I've ever filled.

## The surprise: the emptiest row is the most useful teardown

And it's the most valuable teardown for my roadmap so far — because the story isn't the
feature set. It's the **license.**

GitNexus does everything `ccc` does *and* a structural graph *and* 14 languages — but it's
PolyForm-Noncommercial. So codemap can only ever **route** to it: call it as an opt-in
subprocess and pass its answer through untouched. I can never **adapt** it — translate its
output into my own graph contract — without crossing the license.

`ccc` is **Apache-2.0**. It does less, but it's the first semantic-search tool I'm legally
free to *wrap* — the first one that can sit behind codemap's semantic-search router as an
**owned capability**, not a borrowed one. "Does more" lost to "does less, under a license I
can build on."

## The measurement that shows the fit

Two queries tell the whole story.

Ask for a **concept** — *"detect swing high/low pivot points within a zone"* — and `ccc`
nails `.../zones/strategies/swing/pivot_points.py` at rank 1 (score 0.72) with **zero
knowledge of the file's name**. That is precisely the fuzzy leg codemap refuses to grow.

Ask for an **exact symbol** — `analyze_zones` — and `ccc search` returns a relevant spread
where the *real definition* ranks #5, not #1. It's `ccc grep` (tree-sitter, no index) that
actually pinpoints it.

The boundary is crisp: **semantic retrieval for "what's this about," exact structure for
"where is X" — and they're different tools, not the same one graded differently.** That is the
composition thesis, measured on one repo. codemap owns the second half; it should *wrap* a
tool for the first, not grow a worse version of it.

## The aside that cut the other way (GPU)

A footnote worth keeping, because it quietly falsifies a benchmark if you miss it.

GitNexus's embeddings ran on an older Pascal GPU after I side-loaded a CUDA-13 runtime — its
onnxruntime execution provider still ships Pascal kernels. `ccc`'s `[full]` extra pulled
torch 2.13/cu130, whose wheels are compiled for `sm_75+` only; the **same GPU, same model
family, hard-fails** with `no kernel image for device`. Two tools, the same embedding model
(`snowflake-arctic-embed-xs`), opposite GPU outcomes — because the *runtime*, not the card,
decides. So `ccc` embedded 6 403 chunks on CPU in ~9 minutes. The redeeming number: a
re-index of unchanged content takes **~1 second** — content-hash delta processing, a working
proof of the incremental graph I'd deferred on my own roadmap.

**Sequel.** I got a second machine with a newer Ampere card and settled it.
`torch.cuda.get_arch_list()` prints the verdict without ceremony: `sm_75, sm_80, sm_86,
sm_90, sm_100, sm_120`. Not a hardware limit — a list someone chose at build time, and the
older card's arch is simply not on it. On the supported arch the same cold build dropped from
**216 s to 48 s**. And two footnotes came out of the measuring, both the kind that quietly
falsify a benchmark: `ccc` keeps a **background daemon** holding the model, so three
"different" device settings all returned the same 34 s — they hit the same warm process; the
daemon has to die between runs. And the device **auto-detects**, so the honest CPU number only
appears if you pin `device: cpu` on purpose. The first number I believed was measuring nothing
at all.

## The three lessons

1. **"Does less" can be worth more than "does more."** Capability is not the axis that decides
   integrate / wrap / learn — **fit × license** is. A tool that does one thing cleanly,
   composes with your core, and carries a license you can build on beats a richer tool you can
   only admire from behind a subprocess.
2. **The wrap / route / learn triad is a licensing decision as much as a technical one.** Same
   capability (semantic search), two tools: GitNexus → route-only (non-commercial);
   cocoindex-code → adaptable (Apache-2.0). The verdict flipped on the license file, not the
   feature list.
3. **Measure the boundary, not just the hit.** The finding wasn't "semantic search works" — it
   was *where it stops* (exact-symbol lookup goes fuzzy), which is exactly what tells you to
   wrap it as an opt-in beside the structural answer, never instead of it. (And measure with
   the daemon dead and the device pinned, or you're timing a warm cache and calling it hardware.)

## What I take, and what I keep

**Take (wrap + learn):** cocoindex-code itself as codemap's **semantic-search adapter** — the
first license-clean tool for the fuzzy-retrieval leg codemap lacks by design; and its
**content-hash incremental re-index** (~1 s) as the concrete pattern behind the incremental
graph I've since built.

**Keep (my edge):** a **diffable** graph versus a binary index blob; **exact,
re-export-resolving** symbol lookup versus a fuzzy spread; **provenance-split structural
impact** it has no notion of; and a graph that **provisions nothing** — no gigabyte of torch,
no embedding model, no GPU-arch lottery.

**Verdict:** *wrap (opt-in semantic adapter) + learn (incremental engine).* The retrieval half
I can finally *own*, not just point at.

---

*codemap is open source (MIT): [github.com/kogriv/codemap](https://github.com/kogriv/codemap).
The full teardown — every command, version, and number — is public, so you can reproduce it or
catch me where I'm wrong. Measured your tool and I got it wrong? Open an issue. The harness is
public.*
