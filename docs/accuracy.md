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
> labeled suite) and it *marks* what it cannot resolve. Overall recall against *all* true edges is ~67% on
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

11 cases span the spectrum from trivially-decidable to provably-undecidable. Metrics per tier
(`fast` = stdlib-ast resolver, `deep` = jedi type inference):

| Tier | Precision | Recall (decidable) | Recall (all true) | Phantom edges |
|---|---|---|---|---|
| fast | 100% | 100% | 64.7% | 0 |
| **deep** | **100%** | **100%** | **66.7%** | 0 |

Reading it:

- **Precision (deep) = 100%** — every emitted edge is a real call. No invented edges.
- **Recall on decidable edges = 100%** — the deep tier misses *none* of the statically-resolvable calls.
  This is the "no bugs" metric.
- **Recall on all true edges = 67%** — the honest number. The missing third are edges no sound analyzer can
  resolve: a function passed as a parameter and called via it (higher-order), `getattr(obj, name)()`
  (dynamic dispatch), and value-flow through a string-keyed registry. The suite labels these as `ceiling`,
  so the gap is visible, not hidden.
- **The two tiers are close on this suite, and that is recent.** `c11_local_import` — a callee imported
  *inside* the calling function — was a deep-only edge until R1-C30: jedi resolved it, the default fast
  resolver did not, which read as a capability difference and was really a missing map (issue #11). The
  case also carries a sibling function that calls the same bare name without importing it, so the cheap way
  to win the recall — merging the local import into the module map — shows up as a precision loss instead.
- **Phantom edges = 0** — no `calls` edge points at a non-node on either tier. This did *not* start clean:
  the first run of this suite surfaced two soundness warts, both since fixed —
  - **fast tier, inheritance (R1-C13-f1)** — `self.<inherited_method>()` was over-approximated to a
    same-class id that doesn't exist (the fast resolver ignored the MRO). Fixed: `_class_members` now maps
    each inherited member to the *base class that defines it*, so the edge lands on the real method. Fast
    precision went 87.5% → 100%.
  - **closure (R1-C13-f2)** — a call to a nested inner function emitted an edge to the closure's
    unmaterialized id. Fixed by a general guard: an internal edge whose target is not a graph node is
    downgraded to *unresolved* rather than emitted, so the graph never points at nothing (this also removed
    40 latent phantom edges on the bquant graph — locals that `jedi` typed to their own scope-path).

An accuracy benchmark that only ever prints 100% isn't measuring anything; this one found real bugs on its
first run, and now guards against their return in CI. Run it yourself:

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
| resolved (internal) | **25.3%** | edge into the analyzed package — the call graph you query |
| external | **46.1%** | resolved to a third-party library (pandas, numpy, …) — correctly *not* an internal edge |
| unresolved | **28.6%** | local-variable / dynamic call the static tiers can't type — the ceiling tail |
| dynamic | 0.0% | — |

So of the call-sites that *could* be internal (resolved + unresolved = 3 407), the deep tier resolves
**~47%**. That is the real-world echo of the suite's 60% — and exactly why the graph is labeled a lower
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

## (c) A limit is partiality too — and it is declared

The two sections above are about how well calls **resolve**. A second, independent thing can make an
answer a lower bound: a **result limit**. It is not an accuracy problem at all — the graph knew the
whole answer — which is exactly why it slipped past the machinery built for accuracy.

Found by measuring someone else's tool and then asking the same question of our own
([R2 / CodeGraph](../research/tools/codegraph.md); post
[*Two empty columns*](../research/blog/06-two-empty-columns.md)). `search "zone"` on a 5 113-node graph
returned **50 of 1 259 matches** under an envelope that read, in full, `{"ok": true}` — in the one op
whose entire job is to tell a cold agent what exists.

The rule now:

> **Whenever an op accepts a limit, the envelope carries a `limit` block — always, including when
> nothing was cut.**

```json
{"ok": true,
 "result": ["…"],
 "limit": {"applied": 50, "returned": 50, "total": 1259, "truncated": true}}
```

- **Always**, not only on truncation: an absent field forces a machine consumer to distinguish
  *"nothing was cut"* from *"this build does not report cuts"*, and it cannot.
- `total: null` is a legitimate answer and is **never** an omission. `semantic` is the honest case —
  the retrieval adapter applies the limit itself, so when it hands back a full page the pre-limit total
  was never observed. The block says so (`total: null`, `truncated: null`, plus a `note`), and a caller
  that sees it can widen the limit instead of trusting a number nobody counted.
- **Orthogonal to `epistemic`.** An answer can be resolution-partial *and* limit-truncated; the two
  say different things, and collapsing them loses which one bit.
- Ops bounded by something that is *not* a slice of a computed list — `pack`'s token budget, `impact`'s
  and `flows`' depth — are exempt **in writing** (`_UNLIMITED_BY_DESIGN`), with the reason, so the guard
  test can tell a deliberate exemption from a forgotten one.

Surfaces: `search`, `semantic`, `tests`, `covers`, and the MCP transport caps on `impact` /
`call_contract`. The CLI prints a one-line footer on truncation only — a person re-reads the command
they just typed; a machine consumer cannot. Enforced by
[`tests/test_r1c28_limit_envelope.py`](../tests/test_r1c28_limit_envelope.py), whose last test reads the
ops' own source and fails when a new op learns a limit without declaring it. Gap:
[`gaps/limit_truncation_2026-08-28.md`](../gaps/limit_truncation_2026-08-28.md).

---

## What this means for trust

- Believe a **present** edge: precision is 100% on the labeled suite (both tiers) — codemap does not invent
  calls, and no edge points at a non-node (the two phantom cases the suite first surfaced are fixed and
  guarded in CI).
- Treat an **absent** edge as *"not proven"*, never *"proven absent"*: recall against all true edges is
  ~60%. That is why `impact`, `callers`, `callees`, `flows` and `call_contract` all carry
  `epistemic: partial`.
- Use the graph where it wins — **impact / blast-radius / signature-change** — and don't bother reaching for
  it to *locate* a well-named symbol; `grep` is fine there.
- Read the **`limit` block** before concluding a list is complete. `epistemic: partial` says the resolution
  was a lower bound; `limit.truncated` says the delivery was. An answer can be either, both, or neither.

_Harnesses: [`research/bench/callgraph_accuracy.py`](../research/bench/callgraph_accuracy.py),
[`research/bench/grep_vs_graph.py`](../research/bench/grep_vs_graph.py). Both are guarded in CI
(`tests/test_r1c13_*.py`). Deterministic — re-run to refresh._
