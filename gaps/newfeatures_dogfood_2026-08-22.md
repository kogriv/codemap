# Dogfood — new features on a real task (2026-08-22)

First real practical use of codemap: **scope the removal of the deprecated, MACD-
hardcoded `MACDZoneAnalyzer`** from bquant (the universal pipeline superseded it, but
the archaic class still lingers). Along the way, exercise the Tier-1/2 features shipped
this week — impact, semantic search, dead-code confidence, complexity, context pack —
on a fresh repo-scoped **deep** graph of bquant (core + tests + examples + scripts +
research + docs; 2886 nodes / 7861 edges). Verdict up front: **the features hold up;
the findings are mostly confirmations plus a few sharp edges worth logging.**

## The task: MACDZoneAnalyzer removal blast-radius

`codemap report impact --symbol MACDZoneAnalyzer` → **31 code references** (core 2,
docs 7, examples 1, scripts 2, tests 19), Risk HIGH. Reconciled against `grep -rl`
(44 files):

| bucket | count | codemap right? |
|---|---|---|
| real code references | 31 | ✅ found all |
| `docs/_build/html/*` generated | 3 | ✅ correctly ignored (build artifacts) |
| prose-only doc mentions (no import) | 5 | ➖ not code-refs (see F-DOG-1) |
| `tests/*.md` docs | 2 | ➖ outside the `--docs docs` root |
| `from … import` **inside `nb.log("""…""")`** | 3 | ✅ correctly ignored (string, not code) |

**Key positive:** codemap's AST impact is *precise where grep over-counts* — it did
not false-positive on example code living inside log-strings or on prose mentions,
which grep flags. This is the "graph beats grep" thesis demonstrated on a real removal.
The core is a **clean cut** (class + 2 sibling helpers `analyze_macd_zones` /
`create_macd_analyzer` + the `__init__` re-export; the universal pipeline does **not**
depend on it — it delegates *into* the pipeline). The bulk of the work is 19 tests that
use `MACDZoneAnalyzer` as a convenient zone-producer, to be rewritten onto `analyze_zones()`.

## Findings

- **F-DOG-1 (impact, minor) — removal needs a prose/doc sweep codemap doesn't give.**
  For a *deletion* (not a refactor), prose doc mentions + `.md` outside `docs/` are real
  edit sites, but they aren't code references, so `impact` (correctly) omits them.
  codemap's own disclaimer already says "pair with grep before deleting" — accurate. A
  candidate capability: an opt-in *textual-mention* sweep (or accepting `.md` from any
  root as doc-scan input) so the removal checklist is one tool. Low priority; the
  precise/loose split is on-brand.

- **F-DOG-2 (semantic, positive + minor) — concept search cross-confirms the map.**
  `codemap semantic "deprecated macd zone analyzer class"` → top hit `MACDZoneAnalyzer`
  (0.765) + its doc, backward-compat test, and `analyze_macd_zones` — the same cluster
  the exact impact found, via a different modality. Minor: a hit landing in a `docs/*.md`
  file resolves to `unresolved` (a `doc` node isn't a def, so `symbol_at` returns None).
  Could resolve doc-file hits to the doc node. Small.

- **F-DOG-3 (dead-code, positive) — repo-scope + deep tier crushes false positives.**
  On the core-only codemap graph, `report dead-code` shows 42 "high" candidates (all
  argparse/dict-wired FPs). On the **repo-scoped deep** bquant graph it's **5 high** —
  cross-root references + deep call resolution eliminate the rest. R1-C8's confidence +
  the richer graph together make the report genuinely actionable. (No low/medium tier
  appeared here — the 5 truly have zero inbound edges.)

- **F-DOG-4 (complexity, positive) — hotspots match known pain.** Top complexity:
  `ZoneVisualizer._create_plotly_zones_on_price` (CC 66), `extract_zone_features`
  (CC 59, MI 9.2), several more ZoneVisualizer methods — the viz layer is the real
  complexity center, matching lived experience. The MI axis (9–29 on these) reads right.

- **F-DOG-5 (pack, positive) — ranking + budget behave.** Global pack tops out at
  `logging_config` / `config` / `exceptions` (the most-depended-upon); seeding on
  `analyze_zones` swaps the top for the zone subsystem. Budget respected; hubs before
  leaves. Deterministic.

- **F-DOG-6 (MCP channel, process) — dogfooding the MCP surface needs a fresh graph.**
  The `serve --mcp` server reads a committed `graph.json` that goes stale; testing the
  new tools (`pack`, `semantic_search`, graded `dead-code`) as an *agent* requires
  rebuilding that graph and restarting the server. Friction worth noting — a `--build`
  option on `serve`, or an auto-refresh, would smooth agent dogfooding. (Deferred; the
  M18 freshness signal already tells a caller the map is old.)

## Net

Features work as designed; no correctness surprises. The one genuinely useful product
signal is **F-DOG-1**: codemap answers "what *code* breaks" precisely, and a removal
also needs a "what *prose* mentions it" sweep — today that's grep. Everything else is
confirmation that the week's Tier-1/2 work is sound on a real target. The MACD removal
itself is a real breaking change (v3.0.0) whose scope is now mapped; execution is a
separate decision.
