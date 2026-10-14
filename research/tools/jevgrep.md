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
| **P4** | ❌ **retracted 2026-10-14 (§0.9) — it was my stand-in, not their scheduler** | As first recorded: with a judge I believed deterministic, five runs at default concurrency returned 254, 257, 257, 257, 254 and five with `--concurrency 1` returned 257 five times. **That judge answered each request as a whole**, while the client puts a different number of files into a batch from run to run; a judge that answers each *question* about its own file gave **200 files, 12 runs, 12 byte-identical answers at default concurrency**. The variance lived in my judge, and the pipeline is deterministic given a per-question judge |
| **P5** | ✅ holds, and **structurally**, so the stub settles it | The answer schema is fixed by their renderer: summary → `Symbols use name@start-end. Roles are estimates…` → file list with roles and `source below` / `locations only` / `source omitted` → `Declaration locations:` with `Symbol.method@start-end` → source blocks → `End context.` There is **no slot** for per-call-site arguments (T4) or for a whole-graph property (T5): declarations carry a name and a line span, nothing else, and `cycle`/`layer` appear nowhere in a full untruncated answer. **Seven tools, seven cards, both columns still ours** |
| **P6** | ✅ holds | `jg files` names an upper bound **before** the search (281 eligible / 4.2 MiB, including the one `manifest.json` my own harness writes into the staging root — my artifact, not their defect; excluded from the runs). Nothing **after** the search names what actually left the machine. The 257 uploaded paths are knowable here only because I was the gateway |

**Score (as first written):** five controls hold; of six predictions five held — P4 "decisively" — and the refuted one (P1) replaced a suspicion with a better fact about their design. **P4 is retracted in §0.9**: of six predictions, four hold, one (P1) is refuted in the tool's favour, and one (P4) was a defect of my own apparatus.

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
gone — with the stand-in judge. (With real Jev the warm repeat was **not** a replay: §0.8 S8.) The earlier
claim here that the cache "masks" a scheduling variance is retracted with P4, §0.9.

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

### 0.7 Stage D — jevgrep as shipped (pre-registered 2026-10-14, **before the first paid request**)

**Configuration.** `@dzhng/jevgrep` 0.8.0 unmodified, provider **OpenRouter**, model `typesafe/jev-1.13`
(response model `typesafe/jev-1.13-20260917`), authenticated with the owner's key kept outside every
repository. This is the only configuration in the card that describes the tool as it ships: no stand-in
anywhere. One environmental fact is declared rather than hidden — the client does not read proxy variables
and direct egress to this provider is refused by the provider's own policy (`403 Access denied by security
policy`), so every run sets `NODE_USE_ENV_PROXY=1`. That changes the route, not the request: the body and
headers `jg doctor` sends were replayed byte for byte and answered 200.

**Observed before this section was written, and therefore not a prediction.** Eight probe requests with
identical input returned `noul` of 0.98 and 0.97, and 0.96 / 0.95 / 0.96 — the live judge is **not**
bit-stable at a fixed input, with a spread of about 0.01–0.02. `doctor` passes; a direct call costs
`$0.000012` for 292 input tokens, which is exactly the list price of $0.042 per million.

**Ground truth, frozen now, re-run on this tree** (codemap 0.0.21, repo scope, `--deep --repeat 3`,
consumers `tests` `examples` `scripts` `research`, docs `docs`; file-level, own file excluded):

| task | question as asked | truth | n | sha256 (sorted paths, `\n`-joined) |
|---|---|---|---|---|
| T1 | *Where is analyze_zones defined?* | `defined_at`: `zones/pipeline.py` (the function) and `zones/analyzer.py` (a same-named method) | 2 | `1de27ea2…` |
| T2 | *Which files call MACDZoneAnalyzer?* | files with a `calls` edge into the class or its members: tests 19, scripts 2, examples 1 | 22 | `0ae71b44…` |
| T3 | *What is the blast radius of changing MACDZoneAnalyzer: which files depend on it?* | `calls` ∪ `references` ∪ `accesses` ∪ `imports`: tests 19, docs 7, scripts 2, examples 1 | 29 | `12e14288…` |
| T4 | *What breaks if the signature of analyze_zones changes?* | `calls` ∪ `references`: docs 24, examples 9, tests 8, research 6, bquant 2 | 49 | `c4783414…` |
| T5 | *What are the architectural layers of the package, and are there import cycles?* | a whole-graph property, not a file set — scored present / absent | — | — |

The five questions are fixed here; no wording is changed after seeing an answer. Every truth path exists in
the 281-path staging tree (280 scope files plus the harness manifest, excluded with `--exclude`).

**Runs.** Ten cold searches (`--no-cache`), one question per run, in this order:
**A** — T1…T5 once each at default concurrency (5). **B** — T2 twice more at default concurrency, and T2
three times with `--concurrency 1` (5). Then one repeat of T1 *with* the cache, to price a warm search. At
$0.12–0.15 per cold search by my own byte count the plan is about $1.5 against a $5-per-day ceiling on the
key. **Stop rule:** the key's cumulative `usage` is read from the provider before and after every batch;
if it reaches **$3.50** the run stops and says so, and nothing further is run that day.

**Controls.**

| # | control | refuted by |
|---|---|---|
| **DC1** | the same staging tree as Stages A–B: `scope_id` line and `verify: staging scope_id == canonical ✓` printed before the first request | any other id |
| **DC2** | the table above is recomputed from a graph built in this session, hashes included | a different hash |
| **DC3** | spend is a measurement: provider `usage` before and after each batch, reconciled with the sum of per-request `cost` where the client exposes it | an unexplained gap larger than the rounding of the provider's own counter |
| **DC4** | the credential never appears in an output, a log or a diff | any occurrence — the run is void and the key rotated |

**Predictions — written to be wrong somewhere.**

| # | prediction | refuted by |
|---|---|---|
| **D1** | **T1 is hit and left unresolved.** `zones/pipeline.py` is in the answer; so is `zones/analyzer.py`; and nothing in the output says the name has two definitions or which one is meant | `pipeline.py` absent, or an explicit statement that `analyze_zones` is ambiguous |
| **D2** | **T2: found, with the haystack.** Recall ≥ 0.9 of the 22 call sites (≥ 20), **precision < 0.5** — the answer lists more than 44 files. A tool that asks "does this file relate to the query" cannot answer "which files call it" | recall < 0.9, or ≤ 44 files returned |
| **D3** | **The role tag does not separate call sites from mentions.** Of the T3 files, the seven `docs/*.md` ones are returned with a role no different from the tests'. Recall on the 7 docs files is **lower** than on the 19 tests | docs recall ≥ tests recall |
| **D4** | **T4 is half answered.** Recall of the 49 users ≥ 0.8 is *not* reached because 30 of them are docs and research notebooks, and — independently of recall — no per-call-site argument shape appears anywhere | recall ≥ 0.8; or any posargs/kwargs vocabulary in the answer |
| **D5** | **T5 is answered anyway.** The question has no file-set answer; I expect a list of files ranked by relevance rather than a statement that the question is outside the tool, and no cycle or layer vocabulary | an explicit refusal / "cannot answer", or a cycle or layer set |
| **D6** | **The scheduling effect survives a real judge, partly drowned by the model.** At default concurrency the spread (max − min of returned files over three T2 runs) is **larger** than at `--concurrency 1`; and the serialised runs are **not** all byte-identical, because the judge is not bit-stable | spread at default ≤ spread serialised; or three byte-identical serial runs |
| **D7** | **Cost is where the bytes said.** A cold search costs **$0.08–0.25** by the provider's own meter, and a warm repeat under 5% of it | outside that band |
| **D8** | **The remainder is still not named.** As in Stage B, no line states which eligible files were not sent or how many | any statement of the unvisited remainder |

D1, D2, D3, D4 and D8 are written to fail if the tool is better than the stub-era reading suggested; D6 and
D7 fail if the model is quieter or cheaper than I expect. If nothing was done, every one of them fails —
none can pass without a run.

**What Stage D will still not say.** Whether Jev *as a model* is good: five questions on one 280-file Python
tree is a sample of the tool on this scope, not a ranking of judges. Nor the agent-level effect their
headline reports (needs an agent in the loop), nor behaviour on any other tree, language or size.

### 0.8 Reconciliation — Stage D (2026-10-14, real Jev through OpenRouter, `typesafe/jev-1.13`)

Seventeen searches ran: the planned ten, the planned warm pair, and **five T5 runs added after D6 failed**
(batch C, exploratory — not in §0.7). Cumulative spend by the provider's own meter: **$1.14** of a $5
daily ceiling; the $3.50 stop rule never came near. Scorer and per-run files are in the scratch area, not
the repository; the numbers below are the scorer's output.

**Controls**

| # | outcome | how |
|---|---|---|
| **DC1** | ✅ holds | same staging tree as Stages A–B, `scope_id` line verified before the first request |
| **DC2** | ✅ holds | graph built in this session (`--deep --repeat 3`, 2 edges seen in < 3 runs, both declared by the tool); the file sets were frozen from that same graph before the first paid request — *not* re-derived by an independent second build |
| **DC3** | ⚠ holds **for the total, not per run** | the provider's counter **lags by about one run**: between the end of batch A (0.250) and the start of batch B (0.325) $0.075 appeared that no run claimed, and the next run was credited $0.0008. Per-search figures below are therefore ranges; only the cumulative sum is a measurement |
| **DC4** | ✅ holds | the credential string occurs in no output, no log and no tracked file (`grep` over the run directory and the repository) |

**Predictions**

| # | outcome | measurement |
|---|---|---|
| **D1** | ✅ holds | `zones/pipeline.py` at rank 1, `zones/analyzer.py` at rank 2 in all three T1 runs; **36 files returned** and no word about two definitions or which is meant. Both truth files found; precision 2/36 |
| **D2** | ❌ **refuted — in their favour, and by a wide margin** | T2 returned **26–27 files**, not > 44: **recall 21/22 in all six runs, precision 0.78–0.81**. The one file never found is `tests/unit/test_sample_data.py`. I predicted a haystack; what came back was a list a person could act on |
| **D3** | ✅ holds, and it is the pattern of the run | T3: tests **19/19**, scripts 2/2, examples 1/1, **docs 3/7**. T4: tests 8/8, examples 9/9, research 6/6 and **docs 2/24**. The role tag does not separate the kinds either: a markdown file that mentions the class is tagged `caller`, a test is `caller, test, fixture` |
| **D4** | ✅ holds | T4 recall **26/49 = 0.53**, entirely the 22 documents it did not return (code roots complete); precision 0.50; no `posargs` / `kwargs` vocabulary anywhere in the answer. The question T4 actually asks — *what breaks if the signature changes* — is answered with a list of files, not with how each call is written |
| **D5** | ✅ holds | T5 returned **156–163 files** with no cycle or layer vocabulary and no statement that the question is outside the tool: a different question answered silently |
| **D6** | ❌ **refuted on the pre-registered test; the exploratory one is unattributed (§0.9)** | **T2 (26–27 files):** spread 1 at default, 1 serialised, and the three serial runs have three different hashes. **T5 (155–163 files, batch C):** default **156 / 163 / 160** (spread 7), serial **156 / 158 / 155** (spread 3). Read at the time as "suggestive of Stage B's effect"; Stage B's effect has since been shown to be my judge's (§0.9), so this spread has **no attributed cause**: the model moves by about three files on its own, and whether batch composition adds to it under a real judge is not measured |
| **D7** | ❌ **refuted, low side and warm side** | cold cost per search by the cumulative meter: T1 **$0.06–0.08**, T2 **≈ $0.037**, T3 ≈ $0.054, T4 ≈ $0.026, T5 **$0.10–0.15** — mostly *under* the $0.08 floor I wrote. A warm repeat did **not** fall below 5%: it cost **$0.037 against $0.078 cold (47%)** and took 52 s against 75 s |
| **D8** | ✅ holds | no line in any of the seventeen answers names how many eligible files were not sent or which. The single regex hit for "skipped" is the file `tests/SKIPPED_TESTS.md` again |

**Score:** four controls hold (DC3 with a caveat); of eight predictions **five hold, three are refuted — and
all three refutations are the tool doing better than I expected on the thing it is for (D2), or the
scheduling story being narrower than Stage B made it sound (D6), or money behaving differently (D7).**

### Surprises — none of these were on the list

**S7 — a selective judge makes the walk small, and that changes the whole cost story.** Stage B's
permissive stub walked 257 of 280 files and uploaded 2.3× the repository. Real Jev returns **26–52** files
for the four code-shaped questions. The upload volume was **not observable** in Stage D (no gateway of mine
on the path), so "2.3× the repo" must not be quoted for Jev — it describes the stub's walk. What is
measured is the bill: cents.

**S8 — what is stable is the list; what the agent reads is not.** Same question, same set, same order — and
the answer's size moved from 28 731 to 23 022 to 19 128 bytes, because **which files carry their source**
changes: `source below` on 5, 3 and 4 of 36 files. Between two runs of the *cache pair* `analyzer.py` — a real
definition of `analyze_zones` — went from `source below` to `locations only`. The cache did not replay the
earlier answer (S5's byte-identical rerun was the stub). An agent that reads the first source block it is
given receives a different one each time.

**S9 — the rank-1 and rank-2 answer was perfectly stable, and nothing else was.** Across all runs of T1 and
T2 the truth files sat where they sat; what flickers is the tail (T5: 37 of 177 distinct files appear in
some runs and not others — tests 13, research 11, docs 8, examples 3, package 2).

**S10 — the output cap is reached on the question that is not theirs.** Two of six T5 runs hit the 256 000
byte cap and said so with the omitted count (*2007* and *340* bytes). The disclosure is exact; the cap is
what a wide question runs into.

### What Stage D settles, and for whom

- **Recall of code that uses a symbol is very good** on this scope (T2 21/22 with one real miss; tests,
  examples and scripts complete in T3 and T4) and **recall of documentation is poor** (docs 3/7 and 2/24). Anyone who treats the answer as the dependency set loses the documents, and the
  answer does not say that it is a relevance list, not a dependency list.
- **For "put the right files in front of an agent", it works**, for cents and in 20–60 s, with no index and
  no build. That is *exactly* `pack`'s job and it is a better result than the stub-era card allowed.
- **It is not a substitute for the structural questions**, and the run shows why in the cleanest form: T4 got
  26 of 49 files and zero information about how any of them calls the function.

### 0.9 Retraction — the Stage B "finding of the run" was my apparatus (2026-10-14)

**What was recorded.** §0.5 P4: five runs at default concurrency returned 254 / 257 / 257 / 257 / 254 with
a "provably deterministic" judge, five with `--concurrency 1` returned 257; conclusion, *"the variance is
jevgrep's own request scheduling, not Jev"*. It went into the commit message, the comparison footnote, and
the verdict as "one defect worth reporting".

**How it came apart**, in the order the evidence arrived, each step run before the next was believed:

1. I wrote a **self-contained minimal judge** (40 lines, a pure function of the request) so that the author
   could reproduce. On it: **240 files, ten runs, all byte-identical, in both arms.** No effect at all.
2. The old judge ("roles") still reproduced it (254 ×3, 257 ×2, and one run that printed
   `discovery incomplete` with `Provider error: Network request failed (connection unavailable or reset)`,
   13 requests). That run named a **cause of mine**: the standard-library server's accept queue is 5 and
   the client keeps up to 32 connections open.
3. Raising the queue to 256 and then 1024 did **not** remove it — at 1024, **10 of 16** runs gave 254, with
   no provider error. So connection resets were a second, separate thing, and the silent 254 was not them.
4. The server log said exactly what the client had not sent: in the ten 254-runs the file stage never
   judged `research/notebooks/02_ind_{calculators,factory,library}.py` (judged 6 times in 16 runs, every
   other file 16). The same three files each time.
5. The **items stage** that precedes it lists those three files in all 16 runs — in a batch of **three**
   in ten runs and in a batch of **four**, with other files, in six. The client's batch composition varies
   from run to run (sizes 2–17 across a campaign). My judge decided each question by whether the keyword
   occurred **anywhere in the request**, so a batch of three with no keyword in it answered 0.0 to all
   three, and the same three files in a different batch got 1.0 from their neighbours.
6. The request tells the judge which file each question is about (`q<k>` names the path in its text). A
   judge that answers `q<k>` from `items[k]` alone gave **200 relevant files in 12 of 12 runs at default
   concurrency, one hash**, with batch sizes from 2 to 17 in the same runs.

**Verdict.** The pipeline is deterministic under a per-question judge. The effect was **a stand-in judge
that answered per request**, and the bytes it moved were mine. The serial arm (`--concurrency 1`) looked
clean for a mundane reason: serial execution batches the same way every time.

**What survives.** (1) The client does vary its batching between runs — real, benign, and only visible
because the apparatus was wrong. (2) A run that has a request failure **says so**: `discovery incomplete`,
the provider's message, and the count. That is better disclosure than I credited when I wrote P2/P6 about
the same tool. (3) Everything measured with **real Jev** in §0.8 is unaffected: it never used my judge.
(4) The stand-in's own claim to measure "their pipeline" needs a second condition: **the stand-in must
answer the question that was asked, about the thing it was asked about.** A stub that answers a request is
not a stub of a question-answering model.

**Why this was caught.** Not by suspicion. By building the reproducer the author would need: the first
self-contained version showed no effect, and an effect that disappears in the minimal case is a statement
about the harness. The report that was about to go out would have asserted a defect in someone else's
client that was in mine. Nothing was filed, and nothing was published on the claim.

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
| determinism | ✅ artifact byte-identical (fast tier) | ✅ with a per-question judge: 12 runs at default concurrency byte-identical (§0.9). **With real Jev** not byte-stable even serialised — model variance, §0.8 |
| declared partiality | ✅ limit/filter/scope/epistemic blocks | ✅ **strong**: exact omitted-byte count on truncation, `locations only`, `source omitted`, `relevant; role uncertain`, "Roles are estimates" |
| what it did **not** judge | ✅ (gate and reports name it) | ✖ 23 of 280 eligible files were never sent and the answer never says so |
| offline / no account | ✅ | ✖ a provider key is required and **2.3–3× the repository is uploaded per search** |
| install footprint | `pip install codmap` | **3 packages, 7.3 MB** — the lightest measured |
| MCP | ✅ 28 tools | ✖ CLI + an agent skill (`jg skill`) |
| languages | Python | Py (grammar) · Go (grammar) · Rust (grammar) · TS/JS (tsc) · text fallback |
| license | MIT | MIT |

## Hands-on measurements (target: bquant)

**Scope:** `sha256:300e0a01…`, 280 files, bquant@cb89a24, materialized staging; `--exclude manifest.json`
so the uploaded set is exactly our scope. **The first table was produced with a stand-in judge** (§0.2
Stage B) and measures **their pipeline, not Jev's relevance**; the second table is **real Jev** (Stage D,
§0.7–0.8) and is the only one that describes the tool as shipped. Stage C (an OpenAI-backed judge) was not
run: Stage D made it unnecessary, and a substitute judge would have measured a different tool.

**Stage B — stand-in judge (pipeline only)**

| Task | Answer shape | Cost (measured) | Latency | Deterministic? | Notes |
|---|---|---|---|---|---|
| T1 where defined | 257 files with roles + `Declaration locations` + source blocks, capped at 256 KB with the omitted count named | 631 req / 9 765 questions / **9.39 MiB uploaded** | 13.8 s serialised, 46.8 s cold at 32 | ✅ with a per-question judge (§0.9); the first reading here was an artifact of my stand-in | relevance **not measured** |
| T2 callers | `caller` is a per-file verdict; no edges, no call sites | same pipeline | — | as above | shape measured, content needs a judge |
| T3 impact | not expressible | — | — | — | the unit is files-to-read |
| T4 sig-change | **✖ structurally**: `Symbol.method@start-end` only | — | — | — | seven tools, still only codemap |
| T5 architecture | **✖ structurally**: no cycle/layer vocabulary in a full untruncated answer | — | — | — | — |
| upper bound (permissive judge) | 280 of 280 files "relevant" | 731 req / 12 364 questions / **12.27 MiB** | 25.5 s | — | the ceiling of exploration |
| warm cache, same question | byte-identical to the cold answer | **5 req**, 2.6 MB on disk | 11.6 s | ✅ | 99.2% of requests removed — **with the stub; not what Jev did, see below** |

**Stage D — real Jev through OpenRouter (the tool as shipped)**, truth = codemap, file level, frozen in §0.7

| Task | Returned | Found | Precision | Cost / latency | Notes |
|---|---|---|---|---|---|
| T1 where defined | 36 files | **2 / 2** at ranks 1 and 2 | 0.06 | $0.06–0.08, 65–75 s | the ambiguity (a method of the same name) is not mentioned |
| T2 who calls the class | 26–27 | **21 / 22** in all six runs | 0.78–0.81 | ≈ $0.037, 20–30 s (94–125 s serial) | misses `tests/unit/test_sample_data.py` |
| T3 blast radius | 48 | **25 / 29**: tests 19/19, scripts 2/2, examples 1/1, **docs 3/7** | 0.52 | ≈ $0.054, 33 s | the four missed are all documents |
| T4 signature change | 52 | **26 / 49**: tests 8/8, examples 9/9, research 6/6, **docs 2/24** | 0.50 | ≈ $0.026, 24 s | file recall only; **no argument shape anywhere** |
| T5 layers / cycles | 155–163 | not a file set | — | $0.10–0.15, 40–55 s (235–311 s serial) | a ranked file list, silently, no cycle or layer vocabulary |
| warm repeat of T1 | 36, same set and order | — | — | $0.037 vs $0.078 cold (**47%**), 52 s vs 75 s | **not** a replay: three files change between `source below` and `locations only` |

## Quality (on the covered part)

- **accuracy** — **measured with real Jev, five questions, one tree** (§0.8): code that uses a symbol is
  found almost completely (T2 21/22, tests/examples/scripts complete in T3–T4); **documents are the weak
  class** (3/7 and 2/24); precision 0.5–0.8 on the questions it can answer. A sample of the tool on this
  scope, not a ranking of judges.
- **determinism** — ✖ at the tail, ✅ at the head. Rank 1–2 of T1 never moved; the T5 tail flickers (37 of
  177 distinct files appear in some runs and not others). With the **stub** the variance was provably
  their scheduling — **retracted, §0.9**: with a per-question judge the pipeline was byte-identical in 12 of
  12 runs at default concurrency. With **real Jev** even serialised runs are not byte-identical, which is
  the model, and nothing here attributes any of it to the client.
- **cost** — **real Jev: $0.026–0.15 per cold search**, $1.14 for the whole seventeen-search campaign. The
  stub-era "631 requests / 9.39 MiB / 2.3× the repository" describes a permissive judge's walk and is
  **not** what Jev uploads; the real upload volume was not observable. Their own
  [#38](https://github.com/dzhng/jevgrep/issues/38) reports ~5M tokens / 65 s / ~$0.2 on 2.7k files.
- **speed** — 18–75 s cold at default concurrency, 94–311 s serialised (3–6× slower), 52 s warm.
- **setup friction** — lowest in the roster: three packages, 7 s, one `auth`. A provider key is the only
  real gate.
- **language coverage** — Py/Go/Rust grammars + TS/JS via tsc; text fallback elsewhere.
- **license** — MIT, same as ours.
- **interface** — CLI to stdout plus an installable agent skill; no MCP.
- **honesty of claims** — **high, and measurably so**: the credential-free pre-check makes zero socket
  calls, truncation names the omitted bytes, roles are labelled estimates, three kinds of partial answer
  are distinguished, `doctor` refuses a judge that answers a known question wrongly, and the README states
  the filters are not a guarantee. The gaps are the two things only a gateway can see — the uploaded set
  and the unvisited remainder.

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
- **What we did NOT check** (§0.6 plus what the runs added):
  - **Relevance quality beyond five questions on one tree.** Stage D measures the tool as shipped, but on
    one 280-file Python scope, one symbol of each kind and one seed per cell. It says nothing about other
    trees, languages or sizes, and nothing about whether an agent given this list does better — that is
    their headline metric and needs an agent in the loop.
  - **What was uploaded under real Jev.** No gateway of ours sat on that path, so the byte volume and the
    request count are unknown; only the provider's bill is.
  - **The mechanism behind S8.** Why source blocks move between runs of one question — model variance in
    the per-file stage, ordering, or a budget shared between files — is not read from their code.
  - **Whether documents are a design choice or a limit.** Docs recall of 3/7 and 2/24 is measured; whether
    it comes from the questions asked of a `.md` file, the preview a document yields, or Jev is not.
  - **Their SWE-bench results**, agent-level cost and task success, and their speed study — theirs, quoted
    as theirs, not re-run.
  - **Whether a batch's composition changes what *real Jev* answers about one file.** The client's batch
    sizes vary from run to run (2–17 items); a per-question stand-in is indifferent to that, a model that
    reads the whole request may not be. The T5 spread under real Jev (default 7, serial 3) is therefore
    **unattributed** — model, batching, or both — and §0.9 withdraws the scheduling reading.
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
the price of a key, cents per search, a source of context that moves between runs, and documents it largely
does not find. **Stage D changed the reading:** on the code-shaped questions it is *better* than this card's
own first prediction (T2 21/22 at precision 0.8, not a haystack) — which makes it the closest thing to a
competitor `pack` has met, not a curiosity.

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
- **No defect to report.** This bullet used to propose reporting a scheduling defect to the author. It is
  **withdrawn** (§0.9): the effect was my stand-in judge answering per request instead of per question, and
  with a per-question judge their pipeline returned the same 200 files, byte for byte, in 12 of 12 runs.
  Nothing was filed. What the investigation did find on their side is creditable: when requests *do* fail,
  the answer says so — `discovery incomplete` with the provider error and the count, on a run where my
  server reset 13 connections.
