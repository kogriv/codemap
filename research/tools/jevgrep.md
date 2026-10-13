# jevgrep (`jg`)

**Verdict:** learn (different bet) · **Feeds:** R1-C6, **R1-C61** (reinforced, still priced), R1-C13,
R1-C14, **one new candidate** (a dependency that answers wrongly ≠ one that is absent) · **Card status:**
**hands-on (Stages A–B of four)** — §0 pre-registered before the run, reconciled in §0.5 (2026-10-13)

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

### 0.5 Reconciliation — Stages A and B (2026-10-13, `@dzhng/jevgrep` 0.8.0)

**Controls**

| # | outcome | how |
|---|---|---|
| **C1** | ✅ holds | `canonical scope_id: sha256:300e0a01…`, `280 files, 4331679 bytes, 112457 loc`, `git cb89a2434092 dirty=False`, `verify: staging scope_id == canonical ✓` |
| **C2** | ✅ holds | `MACDZoneAnalyzer` at `bquant/indicators/macd.py:48`, `analyze_zones` at `bquant/analysis/zones/pipeline.py:718`, both at cb89a24 |
| **C3** | ✅ holds | codemap ground truth re-run on this tree (fast 9.9 s / deep 3 m 40 s) in the 0.0.21 cycle; commands in [`rag_for_git`](rag_for_git.md) §Hands-on and repeated here where quoted |
| **C4** | ✅ holds | the only substituted component is the judge behind `/systemone`; `jg` is the unmodified published 0.8.0 from npm, and every number below produced with a stand-in judge says so |
| **C5** | ✅ holds, **measured not trusted** | `strace -f -e trace=socket,connect` over `jg files`: **zero** socket calls of any family — not merely no `AF_INET`. Their printed claim *"No provider requests were made."* is verifiable and verified |

**Predictions**

| # | outcome | measurement |
|---|---|---|
| **P1** | ❌ **refuted, and the refutation is the better finding** | The role tags are **real per-file verdicts**. On the wire each file gets **six questions in one request**: *"…directly executes or controls the CURRENT behavior…"* (implementation), *"Calls, integrates, or configures that implementation."* (caller), *"Contains executable tests…"* (test), *"Provides data, example classes, or test helpers…"* (fixture), *"Provides supporting behavior or abstractions…"* (helper), and *"Should this file be read early as primary evidence…"*. With a judge that answers those five **differentially by path**, the rendered tags follow exactly: `test`, `caller`, `implementation, helper`, … and, where no role question came back positive, an explicit **`relevant; role uncertain`**. Their committed example looked constant because in it every role answer was positive. The output also labels the whole column up front: *"Roles are estimates"* |
| **P2** | ✅ holds | 280 files eligible, **257 sent and reported**, and **no line anywhere** states that 23 were not. `grep -icE 'skip\|prun\|not visited\|considered\|eligible'` over the answer: **1**, and that one is a filename (`tests/SKIPPED_TESTS.md`). A reader cannot tell "the rest were judged irrelevant" from "the walk did not reach them", and cannot learn there is a rest |
| **P3** | ✅ holds, by **5×** more than predicted | With the judge logging every upload: **9.39 MiB of `state` sent** for a 4.13 MiB scope — **2.3× the entire repository** — against a 256 KB printed answer, i.e. **38×**. The permissive judge (everything relevant) sent **12.27 MiB / 2.97× the repo**, 50× the answer. 631–731 requests carrying **9 765–12 364 questions** |
| **P4** | ✅ **and it is the finding of the run** | With a provably deterministic judge, five runs at the default concurrency returned **254, 257, 257, 257, 254** relevant files; five runs with `--concurrency 1` returned **257 five times and were byte-identical**. So the variance is **jevgrep's own request scheduling, not Jev**. It is not the request ceiling either: at `--max-requests 5000` the spread persists (257, 254, 254, 257, 254), and nothing in the output mentions a ceiling. The serialised answer is the *complete* one — parallelism **drops** three files about 40% of the time. A real key could never separate this from model variance; a stand-in judge settles it in ten runs |
| **P5** | ✅ holds, and **structurally**, so the stub settles it | The answer schema is fixed by their renderer: summary → `Symbols use name@start-end. Roles are estimates…` → file list with roles and `source below` / `locations only` / `source omitted` → `Declaration locations:` with `Symbol.method@start-end` → source blocks → `End context.` There is **no slot** for per-call-site arguments (T4) or for a whole-graph property (T5): declarations carry a name and a line span, nothing else, and `cycle`/`layer` appear nowhere in a full untruncated answer. **Seven tools, seven cards, both columns still ours** |
| **P6** | ✅ holds | `jg files` names an upper bound **before** the search (281 eligible / 4.2 MiB, including the one `manifest.json` my own harness writes into the staging root — my artifact, not their defect; excluded from the runs). Nothing **after** the search names what actually left the machine. The 257 uploaded paths are knowable here only because I was the gateway |

**Score:** five controls hold; of six predictions five hold — one of them (P4) decisively — and the refuted one (P1) replaced a suspicion with a better fact about their design.

### Surprises — none of these were on the list

**S1 — their documented wire format is narrower than their client.** The README's minimal example shows
`"state": "source context"`, a string. The real client sends `state` as an **object**, whose shape is the
first thing a gateway implementer sees: `{guidance, path, preview, query}` for the file stage,
`{criteria, declarations, guidance, path, query, source}` for the declaration stage, `{guidance, items,
query}` and `{candidates, guidance, query}` for the other two. A gateway written to the documented example
crashes on the first real request; mine did.

**S2 — `doctor` checks the judge's *semantics*, not connectivity.** It sends a synthetic
`{"source": "export function recordEvent(event) { events.push(event); }"}` with the question *"Does this
source implement recording an event?"* and **refuses a wrong answer**: a stub that answered `0.0` got
*"Custom endpoint (…) returned an unexpected answer to the connection check."* Connectivity alone is not
accepted. For a tool whose whole output depends on a judge, that is the right check and an unusually
thorough one.

**S3 — the truncation notice names the exact cost.** The default `--max-output-bytes 256000` cut the
answer and said so: *"Output truncated at the byte limit (256000 bytes); 4030896 original bytes omitted."*
Not "truncated" — the omitted byte count. That is R1-C28 satisfied, and it is better than two tools we have
measured: CodeGraph truncated silently at `--limit 20`, OntoIndex printed "no hubs found" over a
10 745-node graph.

**S4 — the whole walk is visible from the wire, and it is four stages.** Per search:
~17 questions batched per request, four distinct `state` shapes, one file-level request per eligible file,
~300 declaration-level requests carrying full `source`, plus item- and candidate-level stages. Jev's
parallel typed-question feature is used as intended rather than as one call per fact.

**S5 — the cache is excellent, and it masks S6.** Cold run: **631 requests, 46.8 s**. Immediate rerun of
the same question: **5 requests, 11.6 s**, byte-identical answer, 2.6 MB on disk — 99.2% of the requests
gone. Which means the scheduling variance of P4 is invisible in ordinary repeated use and shows on a
**fresh** question or under `--no-cache`. Both halves have to be said together: the cache makes repeats
stable, and it is not a fix for the variance.

**S6 — `relevant; role uncertain` is a third state, and a good one.** A file can be selected while no role
question came back positive, and the answer says precisely that rather than guessing a role or dropping
the file. Together with `locations only` and `source omitted` that is three declared kinds of partial
answer in one output — the discipline this project spent two months building, arrived at independently.

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
- Install (exact command):
  ```bash
  npm install --prefix ./npm --no-fund --no-audit @dzhng/jevgrep@0.8.0     # 3 packages, 7 s
  jg auth --provider custom --base-url http://127.0.0.1:PORT --model stub/jev --stdin
  jg doctor && jg files ./staging
  ```
  **reproduced: yes**, first attempt. **Install footprint 7.3 MB** (`@dzhng` 2.7 MB + `web-tree-sitter`
  4.6 MB) and **three packages total** — the lightest install of any tool in this roster by two orders of
  magnitude (CodeGraph 283 MB, GitNexus 1.7 GB).

## What it is

An **index-free, model-judged retrieval CLI** for coding agents. Mechanism measured on the wire rather
than read: a four-stage walk over the directory tree where every decision is a **typed question to a
classifier** — Jev returns a probability, never text — batched ~17 questions per request.

| stage | `state` carries | what it decides |
|---|---|---|
| items | `guidance`, `items`, `query` | which branches of the tree to follow |
| file | `guidance`, `path`, `preview`, `query` | six verdicts per file: implementation · caller · test · fixture · helper · read-early |
| declaration | `criteria`, `declarations`, `guidance`, `path`, `query`, **`source`** | which declarations are relevant, against criteria it carries |
| candidate | `candidates`, `guidance`, `query` | whether a candidate's full source goes into the answer |

Declarations are parsed **locally**: three tree-sitter wasm grammars ship in the package —
`tree-sitter-python`, `tree-sitter-go`, `tree-sitter-rust` — and TypeScript/JavaScript is covered by the
`typescript` 5.9.3 runtime dependency rather than a grammar, which is why the README's four languages come
from only three grammars. Everything else falls back to text.

**No embeddings, no vector store, no index, no local model.** Runtime dependencies are exactly
`typescript` and `web-tree-sitter`; the judge is remote. One search on a 280-file scope uploads **2.3–3× the
whole repository** as `state` and spends 631–731 requests (measured, §0.5 P3).

## Coverage vs codemap

| Capability | codemap | this tool |
|---|---|---|
| symbol lookup (T1) | ✅ exact, ambiguity declared | ◐ **by design not its question** — returns files, roles and declaration spans; their own README says a direct read or `rg` is enough for a known symbol. Relevance quality **not measured** (Stage C/D) |
| callers/callees (T2) | ✅ role-tagged | ◐ a `caller` verdict per **file**, never an edge; no call sites |
| impact / blast-radius (T3) | ✅ symbol-scoped, by root, with distance | ✖ not expressible: the unit is "files worth reading for this question" |
| signature-change surface (T4) | ✅ per-caller `posargs`/`kwargs`/`splat` | ✖ **structural**: declarations carry `name@start-end` and nothing else |
| architecture / layers (T5) | ✅ | ✖ **structural**: no cycle, layer or coupling vocabulary anywhere in a full answer |
| determinism | ✅ artifact byte-identical (fast tier) | ✖ **measured**: 254/257/257/257/254 at default concurrency with a deterministic judge; byte-identical only at `--concurrency 1`; the cache masks it on repeats |
| declared partiality | ✅ limit/filter/scope/epistemic blocks | ✅ **strong**: exact omitted-byte count on truncation, `locations only`, `source omitted`, `relevant; role uncertain`, "Roles are estimates" |
| what it did **not** judge | ✅ (gate and reports name it) | ✖ 23 of 280 eligible files were never sent and the answer never says so |
| offline / no account | ✅ | ✖ a provider key is required and **2.3–3× the repository is uploaded per search** |
| install footprint | `pip install codmap` | **3 packages, 7.3 MB** — the lightest measured |
| MCP | ✅ 28 tools | ✖ CLI + an agent skill (`jg skill`) |
| languages | Python | Py (grammar) · Go (grammar) · Rust (grammar) · TS/JS (tsc) · text fallback |
| license | MIT | MIT |

## Hands-on measurements (target: bquant)

**Scope:** `sha256:300e0a01…`, 280 files, bquant@cb89a24, materialized staging; `--exclude manifest.json`
so the uploaded set is exactly our scope. **Every row below was produced with a stand-in judge** (§0.2
Stage B) and therefore measures **their pipeline, not Jev's relevance**. Rows that need a real judge are
marked and left for Stage C/D rather than filled with a number that would not mean what it says.

| Task | Answer shape | Cost (measured) | Latency | Deterministic? | Notes |
|---|---|---|---|---|---|
| T1 where defined | 257 files with roles + `Declaration locations` + source blocks, capped at 256 KB with the omitted count named | 631 req / 9 765 questions / **9.39 MiB uploaded** | 13.8 s serialised, 46.8 s cold at 32 | ✖ at default, ✅ at `--concurrency 1` | relevance **not measured** |
| T2 callers | `caller` is a per-file verdict; no edges, no call sites | same pipeline | — | as above | shape measured, content needs a judge |
| T3 impact | not expressible | — | — | — | the unit is files-to-read |
| T4 sig-change | **✖ structurally**: `Symbol.method@start-end` only | — | — | — | seven tools, still only codemap |
| T5 architecture | **✖ structurally**: no cycle/layer vocabulary in a full untruncated answer | — | — | — | — |
| upper bound (permissive judge) | 280 of 280 files "relevant" | 731 req / 12 364 questions / **12.27 MiB** | 25.5 s | — | the ceiling of exploration |
| warm cache, same question | byte-identical to the cold answer | **5 req**, 2.6 MB on disk | 11.6 s | ✅ | 99.2% of requests removed |

## Quality (on the covered part)

- **accuracy** — not measured (needs a real judge). What *is* measured: the walk reaches 257 of 280
  eligible files and silently omits the rest.
- **determinism** — ✖ by scheduling, not by model: see §0.5 P4. `--concurrency 1` is byte-stable.
- **cost** — 631 requests and 9.39 MiB uploaded per cold search on 280 files; their own
  [#38](https://github.com/dzhng/jevgrep/issues/38) reports ~5M tokens / 65 s / ~$0.2 on 2.7k files.
- **speed** — 13.8–46.8 s cold, 11.6 s warm, on a 280-file tree.
- **setup friction** — lowest in the roster: three packages, 7 s, one `auth`. A provider key is the only
  real gate.
- **language coverage** — Py/Go/Rust grammars + TS/JS via tsc; text fallback elsewhere.
- **license** — MIT, same as ours.
- **interface** — CLI to stdout plus an installable agent skill; no MCP.
- **honesty of claims** — **high, and measurably so**: the credential-free pre-check makes zero socket
  calls, truncation names the omitted bytes, roles are labelled estimates, three kinds of partial answer
  are distinguished, `doctor` refuses a judge that answers a known question wrongly, and the README states
  the filters are not a guarantee. The gaps are the two things only a gateway can see — the uploaded set
  and the unvisited remainder — plus the scheduling variance.

## Разбор

- **What we'd take.** Two things, and neither is code. (1) **Their evaluation discipline** — ten tasks, one
  frozen package, published methodology, and the release where their own combined cost rose 2–3% printed in
  the README against their own headline. That is the shape [R1-C61](../../BACKLOG.md) asks for, now sighted
  a third time. (2) **`doctor` as a semantic check**: a synthetic input whose correct answer is known, which
  refuses a backend that connects and judges wrongly. codemap's `--require-contract` and schema warnings
  check *presence*; nothing of ours checks that a dependency still answers correctly. For a tool that
  delegates to jedi and griffe, that is a real gap and it is cheap to close.
- **What we'd do differently and why.** The two things a consumer cannot see: **what was sent** and **what
  was not visited**. The answer names 257 relevant files out of 280 eligible and never mentions the 23, and
  `jg files` — the only disclosure — runs *before* the search and counts by directory. For a tool whose own
  README says *"choose a search root you intend to send"*, the sent set is the one list the user most needs
  afterwards, and it is the cheapest line in the whole output to print. Same reasoning as R1-C28 and
  R1-C30-f2 on our side: a partial answer that does not name its own remainder makes the reader's
  conclusion wider than the fact.
- **What the author knows that we didn't.** That **relevance can be a typed classifier instead of an
  embedding or a graph** — one probability per declared question, batched, with no text generation — and
  that this is enough to give an agent a useful starting set. It is a genuinely different answer to the
  question codemap's `pack` answers, and it needs no index, no build and no parser for most of its reach.
  Also: that **six questions per file** (implementation/caller/test/fixture/helper/read-early) buys a
  role-tagged file list without a graph, with an honest `role uncertain` for the cases the questions do not
  settle.
- **What we did NOT check** (§0.6 plus what the run added):
  - **Relevance quality — the thing the tool is for.** Every number here comes from a stand-in judge.
    Stages C and D are not run: Stage C needs an OpenAI key (a declared substitution; measures their
    pipeline with a different judge, never Jev), Stage D needs a Jev-capable provider key and is the only
    configuration that describes jevgrep as shipped.
  - **Their SWE-bench results**, agent-level cost and task success, and their speed study — theirs, quoted
    as theirs, not re-run.
  - **The scheduling variance against a real judge**: with a model in the loop the same experiment would be
    inconclusive, which is why it was done with a stub. Whether Jev's own variance adds to it is unknown.
  - **Why the parallel walk drops files.** Diagnosed to scheduling and excluded as a request-ceiling
    effect (`--max-requests 5000` keeps the spread); the mechanism inside their code is not read.
  - **Languages other than Python** on this scope, Windows/macOS, the agent skill's effect on an agent,
    provider-side caching, and whether the 23 unvisited files were pruned deliberately or missed.
  - **`--include-sensitive` and the credential filter's coverage**: bquant is public and carries no
    secrets, so [their #51](https://github.com/dzhng/jevgrep/issues/51) could not be reproduced here. A
    tree with real secrets would be the honest test and is not ours to use.

## Verdict & backlog effect

**learn — and the clearest "different bet" in the roster since GitNexus.** Not a competitor on structure:
T3, T4 and T5 are absent *by construction*, and seven measured tools later both whole-graph columns are
still codemap's alone. It is a real competitor for the one job codemap's `pack` also does — put the right
code in front of an agent — and it does that job with no index, no build, no graph and a 7 MB install, at
the price of a key, money per search, 2.3–3× the repository uploaded, and an answer that is not reproducible
unless you serialise it.

- **R1-C61 reinforced, not closed.** Third external sighting of a usefulness measurement with a cost axis
  (after intent-continuity and RepoAtlas), and the first measuring an **agent's** cost. The door stays
  priced: their experiment needs a model in the loop, which is exactly what makes our own version
  non-reproducible for a reader.
- **New backlog candidate — a dependency that answers wrongly is not a dependency that is absent.** Their
  `doctor` sends a synthetic question with a known answer and refuses a backend that gets it wrong. We check
  that jedi/griffe are *importable*, never that they still resolve a known fixture correctly. Filed as a
  candidate, small, and in the family of R1-C13.
- **Nothing to integrate.** The capability overlaps `pack`; the mechanism is remote and paid; our thesis is
  the opposite trade. Adopting any part of it would cost the differentiator (local, free, deterministic,
  offline) that the measurement above makes concrete.
- **One defect worth reporting to the author**, with the reproducer this card already contains: a
  deterministic judge shows the default concurrency dropping files from the answer, and `--concurrency 1`
  fixing it. Not filed — reporting someone's defect is the owner's call, and the convention is to show the
  author before publishing.
