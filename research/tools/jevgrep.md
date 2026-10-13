# jevgrep (`jg`)

**Verdict:** — (not yet measured) · **Feeds:** R1-C6, **R1-C61** (the priced door this tool measures),
R1-C13, R1-C14 · **Card status:** **§0 pre-registered, run not started** (2026-10-13)

**Scope:** `sha256:300e0a010e351d0a91a7e006c3cc18047d7d400c94a525ddbe727f796a5e47d2` (R2 benchmark
`bquant.scope.json` — 280 files, 207 .py / 73 .md, bquant@cb89a24) · run mode: **materialized staging**
(`jg` takes a directory root and reads it with its own filters, so it gets the byte-identical staging
rather than the live checkout; both harness lines checked)

---

## 0. Pre-registration (written and committed **before** the run)

These measurements will be published, so the run carries pre-registered expectations: **controls** that
must hold, **predictions** I expect to fail, a **stop rule**, and a declared boundary. Reconciliation goes
in §0.5 with anything unlisted reported as a surprise.

### 0.1 Why this tool, and what reading it already showed

Everything here is desk material, read from the public repository and its npm package; nothing is measured.

- **Repo:** [dzhng/jevgrep](https://github.com/dzhng/jevgrep) · MIT · TypeScript · created **2026-09-26**,
  **2647 ★ / 194 forks / 29 open issues** seventeen days later, pushed 2026-10-12 · npm
  `@dzhng/jevgrep` **0.8.0** · Node 22+.
- **What it is:** a CLI for coding agents. You ask a repository question in words; `jg` walks the
  directory hierarchy, follows qualifying branches, and prints a summary, a file list with "reading
  leads", verbatim source excerpts with line numbers, and declaration/call locations. Their own framing:
  *"The output is evidence for the agent to use, not a generated answer or a guarantee that every relevant
  file was found."*
- **The mechanism is the interesting part, and it is neither a graph nor RAG.** Relevance is judged by
  **Jev** — TypeSafe AI's "System One" model on Vercel AI Gateway — which **does not generate text**: it
  returns typed decisions with probabilities (`noul` 0–1 for boolean, choice, score), evaluated in
  parallel ([what Jev is](https://vercel.com/i/what-is-jev),
  [gateway changelog](https://vercel.com/changelog/typesafe-ai-jev-now-available-on-ai-gateway)). So `jg`
  is a **tree walk with a classifier at each level**: is this folder relevant, is this file relevant, is
  this declaration relevant. Core dependencies are `ai`, `@ai-sdk/typesafe-ai`, `ignore` and
  `web-tree-sitter` — **no embeddings, no vector store, no index**.
- **Declarations are parsed locally** (`web-tree-sitter` 0.27) for **Python, TypeScript/JavaScript, Go and
  Rust**; anything else falls back to text.
- **A fourth camp for our map.** [R1.0](../00_landscape.md) has three: deterministic structural graph
  (ours), embeddings RAG, index-free agentic grep. This is index-free like the third and **model-judged**
  rather than agent-driven — and it goes after the same consumer need as codemap's `pack` with no graph at
  all. That makes it the sharpest competitor in the roster for *"give the agent the right context"*, and
  complementary for everything structural.
- **It measures the thing [R1-C61](../../BACKLOG.md) says we never measured.** Ten tuned Python SWE-bench
  tasks, one frozen package, their public skill: **8/10 solved with and without**, agent cost
  **$7.62 → $5.44 (−28.6%)**; a 0.4.3 rerun including their own model's cost **−25.8%** at the same 8/10;
  and in 0.5.0 their model cost fell ~59% while **combined cost rose 2–3%** — published, in the README,
  against their own headline. Their disclaimer is explicit: *"These single-run observations do not
  establish statistical equivalence or a speed improvement."* Third external sighting of the shape R1-C61
  asks for, after intent-continuity and RepoAtlas, and the first whose metric is the cost of the agent's
  work.
- **The costs are in their own tracker, not in my speculation.** [#51](https://github.com/dzhng/jevgrep/issues/51)
  — API keys in ordinary config files are sent to the provider; [#38](https://github.com/dzhng/jevgrep/issues/38)
  — on a 2.7k-file repo a search measured ~5M tokens, ~65 s, ~$0.2 and grows steeply;
  [#39](https://github.com/dzhng/jevgrep/issues/39) — `jg files` counts by directory and therefore cannot
  name the file you would want to exclude.
- **The lever that makes an exhaustive run possible without their model.** Their CLI README documents a
  **custom endpoint** for gateway implementers — `jg auth --provider custom --base-url … --model …`,
  `http://localhost` explicitly accepted, `/systemone` appended, Bearer token — with the wire format
  spelled out: a request carries `state` (the source context) plus named boolean questions, and a response
  must return `{"answers": {"q": {"type": "noul", "noul": 0.9}}}` for every question id. A local
  stand-in gateway therefore lets us measure **their whole pipeline** — the walk, the filters, the output,
  the determinism, and *exactly what source would leave the machine* — with the judge replaced and that
  replacement declared.

### 0.2 Four stages, cheapest first, and what each can honestly answer

| stage | needs | can answer | cannot |
|---|---|---|---|
| **A** — offline | Node 22, npm | install reproducibility, `jg files` eligibility and filters, `jg doctor` failure modes, local declaration parsing, that nothing is sent without a key | anything about relevance |
| **B** — local stand-in gateway (**declared substitution**) | A + a ~100-line `/systemone` server of mine returning fixed `noul` values | the pipeline end to end: walk shape, request count, **the exact bytes of source uploaded**, output format, cache behaviour, and whether two runs are byte-identical with a deterministic judge | relevance quality — a fixed judge has none |
| **C** — OpenAI-backed judge (**declared substitution**) | B + the owner's OpenAI key | T1–T5 answer quality against codemap ground truth, cost in tokens, repeat-to-repeat variation with a real judge | *their* retrieval quality: a different model is a different tool |
| **D** — their configuration | a key for Vercel AI Gateway / TypeSafe / OpenRouter / OpenCode Zen | the only numbers that describe **jevgrep as shipped** | nothing further |

**Stop rule, fixed here.** If Stage D's key is unavailable, publish as **hands-on (A–C)** with the
substitution named **per row**, never as Jev's quality, and never by swapping in another model and calling
the result theirs. If Stage C's key is unavailable too, stop after B and say so. Under no circumstances is
a stand-in number carried into [`../comparison.md`](../comparison.md) as a relevance measurement.

**What must not happen:** no write of any kind to their repository; no edit to the bquant checkout (the
pinned tree comes from `git clone` + `checkout`, which read); the staging tree is the only thing `jg` is
pointed at, so nothing outside the declared scope can be uploaded even by accident.

### 0.3 Controls — must hold; a failed control means my apparatus is wrong, not their tool

| # | control | refuted by |
|---|---|---|
| **C1** | staging resolves to the canonical `scope_id` and the harness prints both the id line and `verify: staging scope_id == canonical ✓` | any other id |
| **C2** | both probe symbols exist at cb89a24 — `analyze_zones` and `MACDZoneAnalyzer`, the latter since **removed** from bquant | either absent |
| **C3** | codemap's ground truth is **re-run** on this tree, not transcribed from older cards (R1-C25) | a ground-truth number without a command in this card |
| **C4** | in Stages B and C the **only** substituted component is the judge behind `/systemone`; the walk, filters, parsing, output and caching are their published 0.8.0 code | any other local patch |
| **C5** | `jg files` performs **no** network request — established by observation (no outbound connection while it runs), not by trusting the README | any outbound request |

### 0.4 Predictions — I expect these to fail; that is the point of the run

| # | prediction | refuted by |
|---|---|---|
| **P1** | **The per-file role tags are not per-file verdicts.** Their committed example output prints the identical list — *"implementation, caller, test, fixture, helper"* — for all three files, including a test file tagged "implementation". On our scope, where roles genuinely differ (core / tests / examples / research / scripts / docs), I expect the same constant string regardless of the file. *Deliberately not settled by reading their renderer first, so the run decides it on a tree whose roles our own graph knows.* | tags that vary per file and track the real roles |
| **P2** | **The walk does not declare its own pruning.** The output says how many files are relevant; I expect no count of the branches it declined to follow — so a reader cannot tell "nothing else qualified" from "the walk stopped early". `jg files` counts eligibility *before* the walk and is a different number | any statement of pruned/unvisited counts in the search output |
| **P3** | **What leaves the machine exceeds what comes back, by a lot.** With my gateway logging every `state` payload, I expect **uploaded source bytes > 10× the bytes printed as excerpts** on this 280-file scope | a ratio under 10× |
| **P4** | **Non-determinism is not only the model's.** With a deterministic judge, I expect two consecutive runs to be byte-identical — and if they are **not**, the variance lives in their pipeline (concurrency, ordering, batching), which no amount of model determinism would fix. This is the one question a stand-in gateway answers better than their own key would | — (either outcome is a finding; the prediction is that the stub makes it decidable) |
| **P5** | **T4 and T5 are not expressible.** No phrasing returns a call contract (per-caller `posargs`/`kwargs`) or a whole-graph answer (cycles, layers). Six tools, six cards, both columns still ours | any answer carrying per-call-site arguments or a cycle/layer set |
| **P6** | **The eligible set and the uploaded set differ, and the gap is unreported.** `jg files` names an upper bound; the walk uploads a subset; I expect no line anywhere that tells the user which files were actually sent | the search output naming the uploaded set or its size |

If all six hold, the run still produced a result; if none does, a different one. At least one expectation
must fail if the tool is behaving as its documentation claims.

### 0.5 Reconciliation

*Empty by design — filled after the run, with a separate "surprises" block for anything not listed above.*

### 0.6 What this run will not cover

- **Their SWE-bench numbers are not re-run.** Ten tuned tasks, a frozen installed package and an agent
  harness are their experiment; re-running it would be a project of its own, and quoting it as ours would
  be worse. Where their figures appear in this card they are labelled as theirs.
- **Agent-level cost and task success** — the metric their headline is about — needs an agent in the loop
  and is out of scope here. This card measures the retrieval tool, not the agent that consumes it.
- **Their speed study** and the local optimisations it covers.
- **Windows and macOS**: Linux only.
- **Languages other than Python** on this scope, though the tool parses declarations for TS/JS/Go/Rust —
  the shared benchmark scope is Python and `.md`, and changing the scope would break comparability with
  the six existing cards.
- **The agent skill's effect on an agent's behaviour**: the skill is read and quoted, not A/B-tested.
- **Cache behaviour across versions** and the provider-side caching we cannot observe.

---

## Identity

- Repo / site: [dzhng/jevgrep](https://github.com/dzhng/jevgrep)
- License: **MIT**
- Last commit / release: pushed 2026-10-12 · npm `@dzhng/jevgrep` **0.8.0**
- Stack / language: TypeScript, Node 22+ · `web-tree-sitter` 0.27 for local declaration parsing ·
  `@ai-sdk/typesafe-ai` + `ai` 7.x for the judge · `ignore` for filters · no embeddings, no vector store,
  no index
- Install (exact command): *Stage A of §0.2 — not yet run*
- reproduced? *not yet*

## What it is

*Desk reading in §0.1; nothing measured yet.*

## Coverage vs codemap

*Filled after the run.*

| Capability | codemap | this tool |
|---|---|---|
| symbol lookup (T1) | ✅ | ? |
| callers/callees (T2) | ✅ | ? |
| impact / blast-radius (T3) | ✅ | ? |
| signature-change surface (T4) | ✅ | ? |
| architecture / layers (T5) | ✅ | ? |
| determinism | ✅ artifact byte-identical (fast tier) | ? |
| offline / no account | ✅ | ✖ (a provider key is required; source is uploaded) |
| MCP | ✅ 28 tools | ✖ CLI + an agent skill |
| languages | Python | Py / TS / JS / Go / Rust declarations, text fallback |
| license | MIT | MIT |

## Hands-on measurements (target: bquant)

*Not yet run. Expectations are in §0.4 and must be reconciled in §0.5 before this section is trusted.*

| Task | Correct? | Cost | Latency | Deterministic? | Notes |
|---|---|---|---|---|---|
| T1 where defined (`analyze_zones`) | | | | | |
| T2 callers (`MACDZoneAnalyzer`) | | | | | |
| T3 impact (`MACDZoneAnalyzer`) | | | | | |
| T4 sig-change (`analyze_zones`) | | | | | |
| T5 architecture | | | | | |

## Quality (on the covered part)

*Filled after the run.*

## Разбор

- **What we'd take:** *after the run — the candidate going in is their evaluation discipline, specifically
  publishing the release where their own combined cost got worse.*
- **What we'd do differently and why:** *after the run.*
- **What the author knows that we didn't:** *after the run.*
- **What we did NOT check:** *§0.6 is the pre-run version of this list; it gets extended, never trimmed.*

## Verdict & backlog effect

*After the run.*
