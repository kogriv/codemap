# cocoindex-code (`ccc`)

**Verdict:** wrap (opt-in semantic-search adapter) + learn (incremental engine)  ·  **Feeds:** R1-C16 (router/adapter — first MIT/Apache semantic-search candidate), R1-C6 (relevance)  ·  **Card status:** hands-on

**Scope:** `sha256:300e0a010e351d0a91a7e006c3cc18047d7d400c94a525ddbe727f796a5e47d2` (R2 benchmark `bquant.scope.json` — 280 files, 207 .py / 73 .md, bquant@cb89a24) · run mode: materialized (`/tmp/ccc_stage`, scope_id verified == canonical). *Caveat:* `ccc`'s default include set spans 56 extensions and also picked up the harness's own `manifest.json` at the staging root (1 extra file, 90 json chunks) — it indexes by its own include/exclude, not the scope spec.

## Disambiguation (matters)
Two projects, same authors, one built on the other:
- **CocoIndex** — a general **incremental ETL / data-transformation framework** (Rust core + Python DSL), database-agnostic (Postgres+pgvector, LanceDB, Kuzu, Qdrant, … as *targets*). Its published quickstarts commonly stand up Postgres+pgvector. `github.com/cocoindex-io/cocoindex`, Apache-2.0.
- **cocoindex-code / `ccc`** — the **semantic code-search CLI**, a separate package built *on* CocoIndex, specialized for repos, with its own **embedded store (no DB service)**. **This card is about `ccc`.**

## Identity
- Repo / site: `github.com/cocoindex-io/cocoindex-code` (framework: `github.com/cocoindex-io/cocoindex`)
- License: **Apache-2.0** (SPDX) — codemap-compatible, unlike GitNexus's PolyForm-NC.
- Version tested: **cocoindex-code 0.2.41** on **cocoindex 1.0.20** (latest at time of test).
- Stack / language: **Python** (CLI) on the **Rust CocoIndex engine**; **tree-sitter** chunking; **SentenceTransformers** embeddings (`Snowflake/snowflake-arctic-embed-xs` — the *same* model GitNexus defaults to). Installed into a Python 3.14 `uv` tool venv.
- Install (exact): `uv tool install 'cocoindex-code[full]'` (the `[full]` extra pulls torch + sentence-transformers, ~1 GB). · reproduced? **yes** — needed `UV_HTTP_TIMEOUT=180` (the `scipy` wheel timed out at the 30 s default) and a **direct, proxy-free** network env (its HF model fetch fails behind a SOCKS proxy without `httpx[socks]`).

## What it is
A **semantic (vector) code-search** tool: tree-sitter chunks source into semantic units (functions/classes/blocks), embeds each chunk locally, and answers a natural-language query by embedding it and returning the nearest chunks (file + line range + score). Interfaces: **CLI** (`init`/`index`/`search`/`grep`/`status`/`mcp`) + **MCP server** (`ccc mcp`, stdio) + an installable agent **skill**. Runs **fully local/offline, no database service, no API key** — the index is an **embedded LMDB + SQLite** store (default under the global `~/.cocoindex_code/` + a project `.cocoindex_code/`). Embeddings run on **CPU/CUDA/MPS**. Source-only (it parses, never builds/runs the target). Also ships a non-semantic **`grep`** — tree-sitter *structural* search by example, no index/daemon needed.

**It produces a vector index only — no symbol graph, no call edges, no imports, no impact, no architecture.** That single fact frames the whole comparison.

## Coverage vs codemap

| Capability | codemap | cocoindex-code |
|---|---|---|
| symbol lookup (T1) | ✅ exact (`where_defined`, resolves re-exports) | ◐ semantic (relevant spread) / ✅ via `grep` (exact, tree-sitter) |
| callers/callees (T2) | ✅ | ✖ (no call graph) |
| impact / blast-radius (T3) | ✅ | ✖ |
| signature-change surface (T4) | ✅ | ✖ |
| architecture / layers (T5) | ✅ | ✖ |
| **semantic / concept search** | ✖ | ✅ (local embeddings, RRF-style) |
| **incremental re-index** | ◐ (full re-extract; R1-C9 planned) | ✅ (content-hash delta — the engine's core value) |
| determinism | ✅ (diffable JSON) | ◐ answer deterministic; artifact = binary LMDB/SQLite |
| MCP | ✅ | ✅ (`ccc mcp`) |
| languages | Python (deep) | multi (tree-sitter breadth) |
| license | MIT | Apache-2.0 |

## Hands-on measurements (target: bquant, R2 scope)
Index build: **280 scope files → 6403 chunks** (python 5185, markdown 1128, json 90 — the stray `manifest.json`). **Cold CPU build: 559 s (~9.3 min)** on this 4-core box (model load + 6403 chunk embeds); **incremental re-index of unchanged content: ~1 s** (content-hash cache — measured; the CocoIndex thesis, proven). Index artifact **~40 MB** (SQLite ~20 MB + LMDB) for 4.3 MB of source — **~9× input** (codemap ~1.1×, GitNexus ~28×). **GPU unavailable:** `[full]` pulled **torch 2.13.0+cu130**, whose wheel is compiled for **sm_75+ only**; the box's **GTX 1080 Ti is sm_61 (Pascal)** → `cudaErrorNoKernelImageForDevice`. A *packaging* cutoff, not the hardware — and unlike GitNexus's onnxruntime CUDA-13 EP, which *did* run on sm_61 (different runtime, different arch policy). Embeds forced to CPU (`CUDA_VISIBLE_DEVICES=""`). *(This paragraph records the original 4-core/Pascal run; the GPU path was measured separately on an RTX 3070 — see the GPU follow-up at the end.)*

| Task | Correct? | Cost | Latency | Deterministic? | Notes |
|---|---|---|---|---|---|
| T1 where defined (`analyze_zones`) | ◐ semantic / ✅ grep | 1 query | sub-sec | ✅ | `search` returns a relevant spread (scores 0.69–0.71, low discrimination); the real def `pipeline.py:718` ranks **#5**, not #1. `ccc grep 'def analyze_zones'` pinpoints it exactly (pipeline.py:718 + analyzer.py:122). |
| T2 callers (`MACDZoneAnalyzer`) | ✖ N/A | — | — | — | `search "who calls MACDZoneAnalyzer"` → semantically-similar *docs/tests*, not a caller list. No call graph exists. |
| T3 impact (`MACDZoneAnalyzer`) | ✖ N/A | — | — | — | No graph → no blast-radius. |
| T4 sig-change (`analyze_zones`) | ✖ N/A | — | — | — | No call-site/contract model. |
| T5 architecture | ✖ N/A | — | — | — | No layers/coupling/cycles. |
| **(bonus) concept query** — "detect swing high/low pivot points within a zone" | ✅ | 1 query | sub-sec | ✅ | Top hit `strategies/swing/pivot_points.py:1-19` (0.72) + more pivot chunks + swing `__init__` + a swing test — **exactly right by concept, zero knowledge of names.** codemap cannot do this. |

## Quality (on the covered part)
- **accuracy** — semantic retrieval is genuinely on-target for *concept* queries; for *exact symbol* lookup it's fuzzy (def not top-ranked) — but `grep` covers exact lookup precisely.
- **determinism** — the *answer* is byte-identical across runs ✓ (CPU embeddings stable); the *artifact* is a binary LMDB/SQLite blob, not `git diff`-able ◐.
- **cost** — install heavy (~1 GB torch + sentence-transformers); the on-disk index for 280 files is modest (embedded store). Query cost = 1 embedding, sub-second.
- **speed** — cold CPU build **~9 min** (559 s, 6403 chunks, 4 cores); **incremental ~1 s** (content-hash — its headline). GPU cuts the cold build **~4.5×** — measured 2026-08-22 on an RTX 3070 (48 s vs 216 s, same box, same scope); see the GPU follow-up.
- **setup friction** — moderate: no DB and no API key (a real advantage over the parent framework), but the `[full]` install is large, needs a proxy-free path for the HF model, and **its bundled torch drops pre-Turing GPUs** (Pascal fails) — CPU-only in practice on older cards.
- **language coverage** — multi (tree-sitter) vs codemap's Python-deep.
- **license** — **Apache-2.0** — the key enabler: unlike GitNexus (PolyForm-NC), `ccc` is legally wrappable/adaptable by codemap.
- **interface** — CLI + MCP + agent skill; `--json` on search; `grep` needs no index.
- **honesty-of-claims** — high: "no database required" is true; the tool surfaces per-result scores; PyTorch itself emitted the clear sm_61 incompatibility warning.

## Разбор
- **What we'd take** (with where from):
  - **A local, Apache-2.0 semantic layer is the missing complement to codemap's structural graph** — the exact "fuzzy concept → candidate files" leg codemap deliberately lacks. `ccc` is the concrete MIT/Apache tool to sit behind the R1-C16 router as the **semantic-search capability** (where GitNexus could only be *routed*, not *adapted*, due to its NC license).
  - **Content-hash incremental re-index** (re-index of unchanged content ≈ 1 s). This is the substrate idea behind codemap's deferred **R1-C9** (Merkle/incremental) — `ccc` is a working proof that delta-embedding keeps a code index fresh cheaply.
  - **`grep` = tree-sitter structural search with no index/daemon** — a clean pattern for on-brand exact lookup without standing anything up.
- **What we'd do differently and why** (mandatory):
  - **Keep our answer a diffable artifact.** `ccc`'s index is a binary LMDB/SQLite blob; codemap's whole thesis is a graph you can `git diff` and review in a PR. The *why*: an index you can't diff can't be trusted fresh-and-reviewed.
  - **Don't conflate concept-search with symbol-lookup.** `ccc search` for an exact name returns a fuzzy spread, not the definition; codemap answers "where is X defined" precisely (and resolves re-exports, which grep can't). Semantic retrieval belongs *next to* exact structure, not in place of it — so we wrap it as an **opt-in** capability, not the default answer to a symbol query.
- **What the author knows that we didn't** (the most valuable part):
  - **A DB-free embedded store makes local semantic search genuinely zero-infra.** The parent CocoIndex framework leans on Postgres+pgvector; `ccc` ships LMDB+SQLite so `pipx install → index → search` needs no service. That "provisions nothing" ergonomic is exactly codemap's own value applied to the retrieval half.
  - **Incremental delta-embedding as a first-class engine property**, not a bolt-on — the right shape for R1-C9.
- **What we did NOT check** (honest boundary):
  - ~~**GPU-accelerated embedding**~~ — **closed 2026-08-22 on an RTX 3070**, see the GPU follow-up below. The Pascal-supporting `cu121/cu126` torch swap remains untried and is now moot for us.
  - **Retrieval quality at scale** (precision/recall over a labelled query set) — only spot-checked relevance on a handful of queries.
  - **MCP transport** end-to-end (measured the CLI, same index) and the **agent skill** flow.
  - **Multi-language** behavior (Python/Markdown only, on the shared scope) and the **RRF/BM25 fusion** internals.
  - The **parent framework** (CocoIndex ETL) as an adapter target — only `ccc` was run.

## Verdict & backlog effect
**wrap (opt-in semantic-search adapter) + learn (incremental engine).** `ccc` is the **first license-clean (Apache-2.0) semantic-search tool** fit to sit behind codemap's R1-C16 router/adapter — it fills the fuzzy-retrieval gap GitNexus surfaced, without GitNexus's NC blocker. It confirms **R1-C16** (semantic search is a wrap-not-build capability, and here's the tool to wrap) and feeds **R1-C9** (content-hash incremental is real and cheap) and **R1-C6** (relevance/retrieval). It does **none** of codemap's structural work (T2–T5 N/A) — which is precisely why the two compose rather than compete.

## Follow-up: the GPU path, measured (2026-08-22)

The R2 pass left GPU embedding open because `[full]` pulls **torch 2.13.0+cu130**, whose wheel
ships no Pascal cubin — the original box's GTX 1080 Ti (sm_61) died on
`cudaErrorNoKernelImageForDevice`. Re-run on a second machine with an **RTX 3070 (sm_86)**;
identical tool versions (**cocoindex-code 0.2.41 / cocoindex 1.0.20 / torch 2.13.0+cu130**) and
the **same canonical scope** (`sha256:300e0a01…5e47d2`, 280 files, `bquant@cb89a24`,
materialized), so only the hardware differs.

**The packaging cutoff, verified directly.** `torch.cuda.get_arch_list()` returns
`['sm_75','sm_80','sm_86','sm_90','sm_100','sm_120']` — sm_61 is absent from the wheel, sm_86 is
present. That is the whole story: not a hardware limit, a build-target list. A 4096³ matmul runs
in 0.026 s/iter on the 3070, so the kernels are real.

**Cold-build cost, same box, same scope, daemon restarted between arms:**

| device | wall | chunks | GPU peak |
|---|---|---|---|
| `cpu`  | **216 s** | 6403 | 0 % |
| `cuda` | **48 s**  | 6403 | 69 % |

**≈4.5× from the GPU.** The 0 % reading in the CPU arm is what makes the attribution honest —
an earlier apparent "GPU load" turned out to be the machine's console user, not the run.

**Two measurement traps worth recording**, both of which produce plausible-looking wrong numbers:
1. **`ccc` runs a background daemon** (`~/.cocoindex_code/daemon.pid`) that loads the model once
   and serves every subsequent `ccc index`. Changing `COCOINDEX_CODE_DEVICE` — or setting
   `CUDA_VISIBLE_DEVICES=""` — has **no effect** on an already-running daemon: three "different"
   configurations all returned ~34 s because they hit the same warm process. **The daemon must be
   killed between device arms**, and the device set in `~/.cocoindex_code/global_settings.yml`
   (`embedding.device`), not only in the environment.
2. **Device defaults to auto-detect** (`device: null`), and sentence-transformers then picks CUDA
   when it is available. So the out-of-the-box path is already GPU on a supported card — the
   CPU number above only appears if you pin `device: cpu` deliberately.

**Cross-machine note:** the recorded 559 s baseline was a 4-core box; this box is 12c/24t but
~30 % slower per core, so its CPU arm lands at 216 s. Against that baseline the end-to-end gain
here is ~11.6×, of which ~2.6× is cores and ~4.5× is the GPU. Quote the same-box pair, not the
cross-machine ratio.
