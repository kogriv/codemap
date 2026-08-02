# R1.5 — Curated sources (field intake)

Processed from a hand-collected set of Telegram posts (channels **@ai_for_dev**, **DevHub**,
**@data_analysis_ml**, and curator notes) — a *bottom-up* complement to the top-down R1 survey. The raw
export is kept out of git (`assets/` is gitignored); this report is the cleaned artifact (personal data
stripped; tool-author handles and source channels kept as attribution; one private share-token dropped).

**Headline:** almost every item is squarely in codemap's own category — *"grep burns tokens → give the
agent a code **graph** over MCP."* That is strong validation of codemap's thesis **and** a warning that
the space is now crowded: differentiation (deterministic canonical graph + provenance + honesty) matters
more than presence. R1 mapped the categories and standards; this intake fills in the **live competitor
roster** R1 didn't enumerate, plus one hard benchmark and two new capability signals.

---

## 1. Direct peers — code graph for AI agents (codemap's category)

All NEW vs R1 (R1 named the *standards*; these are the *products*). Verdict is codemap's stance toward each.

| Tool | What it is | License | Verdict for codemap |
|---|---|---|---|
| **graphlens / graphlens-mcp** | typed code graph from source (Py/TS/Go/Rust/PHP), MCP; "who calls X" | MIT (alpha) | **learn / benchmark** — nearest twin (typed graph + MCP + impact). Its author's benchmark is our best evidence (§3). |
| **CodeGraph** (colbymchenry) | local semantic graph, symbols/relations/calls, MCP, `npx` | MIT | learn — same pitch; ships tool-call-reduction benchmarks (−92%). |
| **GitNexus** (abhigyanpatwari) | repo → knowledge graph (3D map) + CLI + MCP | PolyForm NC | learn — note the *non-commercial* license (codemap's MIT is a differentiator). |
| **OntoIndex** | GitNexus fork for 10k+ files; links files/functions/classes/calls/tests/docs; MCP/CLI/web | — | learn — provenance across tests/docs like codemap's roots. |
| **Understand-Anything** (Lum1104) | repo → graph; CC/Codex/Cursor/Copilot/Gemini | OSS | learn — visualization-first peer. |
| **rag_for_git** (mimfort) | hybrid index: **ParadeDB** (BM25+vector, RRF) + **Neo4j** call graph; single key **`path#fqn`** | OSS | learn — `path#fqn` = codemap's canonical id / SCIP descriptor idea, independently reinvented. |
| **cocoindex-code** (ccc) | semantic code search, local embeddings, no DB, ~70% token savings | Apache-2.0 | learn — embeddings peer; benchmarked vs CodeGraph & SocratiCode. |
| **Sentrux** | Rust static "code-health" sensor, 52 langs, MCP, `rules.toml`; measures health **before/after** an agent edit → agent asks "what did I break?" | OSS | **learn (strong)** — the before/after health-delta gate + `rules.toml` is exactly R1-C3 territory, plus an agent-loop pattern codemap could adopt. |
| **CodeSlicer** | traces real cross-layer connections so one edit doesn't break a neighbor scenario | — | learn — impact/blast-radius framed for the agent-breaks-things problem. |
| **Foglamp** | SaaS: interactive repo diagram (deps, integrations, DBs, custom agents) | SaaS | learn — the hosted/visual end; codemap is local/deterministic. |
| **Graphify** (Graphify-Labs) · **grafema.dev** · **ast-index** (defendend) · **SocratiCode** | more graph/AST-search-for-agents entrants | mixed | learn — roster; `grafema.dev` was singled out by the curator. |

## 2. Living docs from code (NEW capability signal)

| Source | Idea |
|---|---|
| **CodeWiki** (Google, codewiki.google) | living wiki auto-updated per commit; Gemini chat over the repo; class/sequence diagrams |
| **"нейростатьи"** (@ai_for_dev, habr 1061746) | docs that self-update from commits and **mark "unverified" whatever they can't confirm against code** |
| **Tutorial-Codebase-Knowledge** (The-Pocket) | walks a repo → generated tutorial w/ diagrams; tiny PocketFlow engine |

**Why it matters:** self-updating, honesty-marked documentation resonates directly with codemap's stance
(deterministic facts, approximations labeled). codemap already has the graph and the honesty discipline —
generating a living, "unverified"-marked doc/wiki from it is a natural, on-brand output. → new backlog
candidate **R1-C15**.

## 3. Hard evidence — grep vs graph vs LSP (the key artifact)

- **936-run benchmark on apache/superset (~400k LoC)** (@ai_for_dev, habr 1051504 / graphlens habr 1052776):
  varying only the context source (grep+read / structural graph / LSP / codegraph) across 3 models × 3 seeds
  × 26 tasks. Findings: for **"where is X defined"** all four are equally accurate — graph gives *no* edge,
  only ~3× cost difference. For **"what breaks if I change this signature"** grep collapses (accuracy 0.71,
  finishes only 83% of runs, **10–23× more expensive**); graph and LSP are cheap and accurate.
- **"Beyond grep"** (Augment Code, arstechnica 2026-07): semantics win on *large private* codebases the
  model hasn't memorized; on public OSS the model often already knows the layout.
- **"Refactor for money"** (habr 1065178): a 17k-line vibe-coded file — refactor to make *each future edit
  cheaper*, measured by re-running one prompt.

**Directly validates codemap's value prop** — its `impact` / `call_contract` are exactly the "what breaks"
queries where a graph is 10–23× cheaper than grep — and tells codemap where **not** to bother (plain
"where is X" needs no graph). → broadens **R1-C13** from a PyCG-only check into a grep-vs-graph harness bench.

## 4. Architecture-as-tests (reinforces R1-C3)

| Tool | Note |
|---|---|
| **ArchUnitPython** (LukasNiessen) | architecture rules **as pytest** — `have_no_cycles()`, layer direction, naming, file size; `pip install archunitpython` |
| **AACT** (Byndyusoft) | architecture-as-code: cover PlantUML arch with tests, autogenerate arch from source, test modular-monolith coupling |
| **Sentrux** (§1) | `rules.toml` forbids monster files / cycles; fails the agent loop |

Three independent Python-world implementations of "architecture violations should fail a test." Confirms
**R1-C3** (architecture contracts + `--check`) is a real, wanted capability — and gives concrete rule
vocabularies (cycles / layer direction / naming / file-size / coupling) to model.

## 5. Ranking & graph technique (reinforces R1-C6)

- **HippoRAG 2** (Ohio State, habr 1025812) — knowledge graph + **Personalized PageRank** for multi-hop
  retrieval. Second independent sighting of personalized PageRank (after aider) → strengthens **R1-C6**
  (relevance ranking).
- **LightRAG** (HKUDS), **LLM Graph Builder** (neo4j-labs), **awesome-ai-memory** (topoteretes) — hybrid
  graph+vector RAG and a memory-landscape map. Tangential (general KG, not code), useful reference.
- **Neo4j** recurs as the graph backend (rag_for_git, GitNexus) → validates codemap's deferred **M3.3 /
  Neo4j door** as the scale option, if/when needed.

## 6. Graph federation (NEW, deferred idea)

- **enox.dev** — a *federation protocol for knowledge graphs* + prototypes (shared by the curator; the
  private share-token is intentionally omitted). Interesting long-horizon direction: codemap graphs as
  **federatable** artifacts an agent consumes directly. Parked as a "door", not a near-term task.

## 7. Adjacent (ecosystem codemap feeds, not its core)

- **Review:** nitpicker (multi-LLM review, Rust), Serge (HF, OSS PR reviewer, rules-in-repo),
  Anthropic multi-agent code review. *(codemap can be the structural context these consume.)*
- **Bug-repro:** codex-bug-reproducer — *proves a bug with a failing test before fixing* — the same
  principle as bquant's #110 fix ("reproduce before fixing"); nice cross-validation of that discipline.
- **Harness / standards (reference):** Anthropic ["large-codebase best practices"](https://claude.com/blog/how-claude-code-works-in-large-codebases-best-practices-and-where-to-start)
  (harness = CLAUDE.md/AGENTS.md, hooks, skills, plugins, **LSP + MCP**), Anthropic
  ["effective harnesses for long-running agents"](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents),
  OpenAI harness-engineering / Codex-CLI internals (prompt caching, autocompaction, 32 KB instruction cap).
  codemap's role in this picture is explicit: **the structural/MCP leg of the harness**.
- **Agent plugins/context:** Superpowers, GSD, Cursor Team Kit, cursor.directory, claude-mem, RTK
  (token-saving Rust proxy), deja (index Claude transcripts), cq (Mozilla — agent knowledge sharing),
  Obsidian Hybrid Search / obsidian-skills, n8n-mcp. *(Out of codemap's scope; noted for context.)*

## 8. Out of scope (logged, not pursued)

Spec-to-code / traceability (SSC, SpecLoom, Doc2Spec, TLA+, Gherkin) · SQL viz (SQL Crack, actuallyexplain)
· Regex Vis · text-to-SQL ontology (Метана) · KOMPAS Guard (domain type-graph) · local coder models,
llm-from-scratch, IVF/HNSW, WITH-RECURSIVE-vs-graph · frontend kits (21st.dev, impeccable, taste-skill) ·
Malus (license-laundering). Interesting reading, but outside codemap's source-graph mission.

---

## What this intake changes

**Nothing about codemap's direction — it confirms it.** The field has converged on codemap's exact thesis,
which means:

1. **Validation is overwhelming** — dozens of independent "code graph over MCP beats grep" tools, plus a
   936-run benchmark quantifying *10–23× cheaper on impact queries*. codemap is on the right axis.
2. **The moat must be explicit** — in a crowd of graph-for-agent tools, codemap's distinct claims are the
   **deterministic, diffable, canonical `graph.json`**, **provenance** (core/tests/docs), **honesty**
   (labeled approximations, defs-only SCIP export), **MIT** (vs GitNexus's non-commercial), and
   **SCIP/interop**. This should be stated loudly (feeds R1-C14 positioning).
3. **Three concrete backlog effects** (folded into [../BACKLOG.md](../BACKLOG.md)):
   - **R1-C3** (architecture `--check`) — reinforced by ArchUnitPython / AACT / Sentrux; adopt their rule
     vocabulary; consider Sentrux's before/after health-delta agent loop.
   - **R1-C6** (relevance ranking) — reinforced by HippoRAG's personalized PageRank (2nd sighting).
   - **R1-C13** — broaden from PyCG-only into a **grep-vs-graph harness benchmark** (replicate the
     superset study on codemap's own ops).
   - **R1-C15 (NEW)** — *living documentation from the graph* (self-updating, "unverified"-marked), as
     CodeWiki / нейростатьи / Tutorial-Codebase-Knowledge do — on-brand with codemap's honesty stance.
   - **M3.3 / federation** — Neo4j recurs as the scale backend; enox.dev's graph-federation protocol is a
     parked long-horizon door.
