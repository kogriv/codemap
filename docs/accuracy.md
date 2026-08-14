# Accuracy & the honest ceiling

codemap's call-graph is a **static lower bound**, and it says so — every call-graph answer that can be
incomplete carries an `epistemic: partial` label (R1-C13) and the prose caveat "a call resolution can miss
dynamic edges". This page backs that honesty with numbers: how accurate the call graph actually is, where
the ceiling is and why, and what the graph buys you over `grep`.

Two things are measured here, both reproducible:

- **(a) Call-graph accuracy** — against a hand-labeled ground truth, plus the intrinsic resolution rate on a
  real package. *Are the edges right, and how many of the true edges do we get?*
- **(b) grep-vs-graph value** — the cost of answering "what breaks if I change this?" with the graph vs with
  `grep`. *Is the graph worth building?*

> **TL;DR.** On statically-decidable calls the deep tier is sound (100% precision, 100% recall on the
> labeled suite) and it *marks* what it cannot resolve. Overall recall against *all* true edges is ~60% on
> the suite and ~26% of raw call-sites resolve to internal targets on a real package — the rest are calls
> into third-party libraries (~46%) or genuinely undecidable dynamic dispatch (~28%). That gap is the price
> of Python's dynamism, not a bug, and it is the same ceiling every sound static tool hits (~99% precision /
> ~70% recall in the PyCG literature). For impact questions the graph is **~2× cheaper than grep on unique
> names and tens of × on polymorphic ones**; for "where is X defined" it is **no cheaper** — grep already
> nails that.

---

## (a) Call-graph accuracy

### Why not PyCG as the oracle

The natural oracle is [PyCG](../research/tools/pycg.md) — the academic reference for Python call graphs. It
**does not run on Python 3.12**: its import-hook machinery collides with the modern stdlib and fails even on
a 3-line file (three layered breakages, the last structural — see the card). Rather than treat a *second
imperfect static tool* as ground truth, we measure against a **hand-labeled micro-suite we own**
([`research/bench/callgraph_truth/`](../research/bench/callgraph_truth/)) whose true edges are known by
construction. This is more honest than a cross-check: the labels are auditable and the undecidable cases are
marked, so the ceiling is explicit.

We still cite PyCG's **published ceiling** as the field's reference point: **~99.2% precision / ~69.9%
recall** on its own benchmark (Salis et al., ICSE 2021). ~70% recall is not a PyCG weakness — it is the
practical limit of *sound* static analysis on a dynamic language.

### The micro-suite result

10 cases span the spectrum from trivially-decidable to provably-undecidable. Metrics per tier
(`fast` = stdlib-ast resolver, `deep` = jedi type inference):

| Tier | Precision | Recall (decidable) | Recall (all true) | Phantom edges |
|---|---|---|---|---|
| fast | 87.5% | 100% | 53.8% | 1 |
| **deep** | **100%** | **100%** | **60.0%** | 1 |

Reading it:

- **Precision (deep) = 100%** — every emitted edge is a real call. No invented edges.
- **Recall on decidable edges = 100%** — the deep tier misses *none* of the statically-resolvable calls.
  This is the "no bugs" metric.
- **Recall on all true edges = 60%** — the honest number. The missing 40% are edges no sound analyzer can
  resolve: a function passed as a parameter and called via it (higher-order), `getattr(obj, name)()`
  (dynamic dispatch), and value-flow through a string-keyed registry. The suite labels these as `ceiling`,
  so the gap is visible, not hidden.
- **Phantom edges** — edges whose *target is not a graph node*, surfaced as a soundness signal rather than
  swept up:
  - **fast tier, inheritance** — `self.<inherited_method>()` is over-approximated to a same-class id that
    doesn't exist (the fast resolver doesn't walk the MRO). The deep tier resolves the real base-class
    method. This is why fast precision is 87.5%, not 100%. *(follow-up: R1-C13-f1.)*
  - **deep tier, closure** — a call to a nested inner function emits an edge to the closure's
    (unmaterialized) id. The relationship is real; only its target id is not a node. *(follow-up: R1-C13-f2.)*

Both findings are the suite doing its job: an accuracy benchmark that only ever prints 100% isn't measuring
anything. Run it yourself:

```bash
python research/bench/callgraph_accuracy.py            # human table
python research/bench/callgraph_accuracy.py --check    # assert the invariants (also in CI)
```

### Intrinsic resolution rate on a real package

The micro-suite proves correctness on hard cases; the intrinsic rate shows the *shape of the tail* on real
code. Aggregated over the **bquant** deep graph (`bquant@cb89a24`, the canonical benchmark scope), across
6 323 call-sites in 833 functions:

| Outcome | Share | Meaning |
|---|---|---|
| resolved (internal) | **25.7%** | edge into the analyzed package — the call graph you query |
| external | **46.1%** | resolved to a third-party library (pandas, numpy, …) — correctly *not* an internal edge |
| unresolved | **28.2%** | local-variable / dynamic call the static tiers can't type — the ceiling tail |
| dynamic | 0.0% | — |

So of the call-sites that *could* be internal (resolved + unresolved = 3 407), the deep tier resolves
**~48%**. That is the real-world echo of the suite's 60% — and exactly why the graph is labeled a lower
bound. Reproduce:

```bash
python - <<'PY'
import json, collections
g = json.load(open("graph.json"))  # a bquant deep graph
agg = collections.Counter()
for n in g["nodes"]:
    for k, v in (n.get("extras", {}).get("calls") or {}).items():
        agg[k] += v
print(dict(agg))
PY
```

---

## (b) grep-vs-graph — is the graph worth it?

The benchmark reproduces, on codemap's ops, the finding from the 936-run apache/superset study: a resolved
call-graph is far cheaper than `grep` for **impact** questions and no cheaper for **location** questions. The
unit is *candidates an agent must inspect*. Measured on **bquant** (`bquant@cb89a24`); auto-picked targets,
no cherry-picking:

| Task | Symbol kind | grep candidates | graph candidates | grep cost multiplier |
|---|---|---|---|---|
| **"what breaks if I change the signature?"** | unique name | 2 188 | 198 | **~11×** |
| | polymorphic name | 1 015 | 27 | **~38×** (tens of ×; `calculate`: 5 real sites vs 278 grep lines = 56×) |
| **"where is X defined?"** | any | ≈ real defs | = real defs | **~1×** (no advantage) |

Why the split:

- **Impact** — `grep` cannot tell a *call* from a *mention*, nor *which* receiver's method a name refers to.
  For `BaseIndicator.calculate`, `grep '\bcalculate\b'` returns 278 lines across the 36 classes that define a
  `calculate`; the graph's deep type-resolution returns the **5** that actually call *this* one. grep's
  precision as a call-finder is **0.02–0.5**; most reads are wasted rejecting noise. (Even a *unique* name
  can be grep-hostile: `log` matches 1 698 lines — a common English word — for 30 real call-sites, 56×.)
- **Location** — `grep 'def NAME'` is already precise (**~1.0**): a definition line is unambiguous. The graph
  knows nothing grep doesn't, so it earns **no** advantage. Stating this null result is what keeps the impact
  claim credible.

The graph's leverage is on **relationships, not locations**. Reproduce (any git repo + its graph):

```bash
python research/bench/grep_vs_graph.py --graph graph.json --repo /path/to/bquant
python research/bench/grep_vs_graph.py --build ./codemap --repo .    # dogfood on codemap itself
```

---

## What this means for trust

- Believe a **present** edge: deep-tier precision is 100% on the labeled suite — codemap does not invent
  calls. (The two phantom-target cases are labeled soundness follow-ups, not silent errors.)
- Treat an **absent** edge as *"not proven"*, never *"proven absent"*: recall against all true edges is
  ~60%. That is why `impact`, `callers`, `callees`, `flows` and `call_contract` all carry
  `epistemic: partial`.
- Use the graph where it wins — **impact / blast-radius / signature-change** — and don't bother reaching for
  it to *locate* a well-named symbol; `grep` is fine there.

_Harnesses: [`research/bench/callgraph_accuracy.py`](../research/bench/callgraph_accuracy.py),
[`research/bench/grep_vs_graph.py`](../research/bench/grep_vs_graph.py). Both are guarded in CI
(`tests/test_r1c13_*.py`). Deterministic — re-run to refresh._
