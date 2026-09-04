"""Union of N deep samples of one tree (R1-C45, design D7).

A deep build is one sample of a slightly fuzzy function (R1-C42): jedi's per-script
execution budget makes an inference that ran out of it indistinguishable from "nothing
to find", and which inference runs out differs between processes. Measured on an
88-module tree, a real ``accesses`` edge was present in 126 of 168 full builds — so one
build misses such an edge about one time in four, and the standard remedy, "build
again", was advice that never said how many times.

``merge_samples`` takes N graphs built from the **same structural base** and returns one
graph holding every edge any run produced. What is merged, and by which key, is decided
per edge class, because the two jedi passes resolve in opposite orders:

- ``calls`` produced by the behavioural pass (``resolution`` in :data:`BEHAVIOR_CALL_RES`)
  is resolved **jedi first, fast fallback** (R1-C26 D2). The same call site can come out
  ``deep`` in one run and ``imported``/``self``/``module`` in another, and the deep run may
  also carry more ``callsites`` and extra method edges. Its identity is
  ``(source, target, via)`` — unique within one build, verified on 2807 edges — and the
  ``deep`` variant wins whole.
- ``accesses`` is resolved **form first**: ``construct``/``self``/``class`` by syntax, jedi
  only for a local or expression receiver. The label is a property of the site, a
  ``construct`` write and a ``deep`` write of one field are two sites, and the only thing
  that varies between runs is presence (4649 keys × 8 runs, no label ever swapped). Its
  identity is the full key.
- Everything else is resolved without jedi and is expected identical across runs
  (measured 0 of 13 674 unstable). It is unioned by full key too, and anything that does
  vary is counted as unstable like the rest — a deterministic pass that turns out not
  to be is a finding, not something to hide behind an assert.

The consumer's proposal — merge by ``(type, source, target)``, deeper wins — does not
survive the data: inside a *single* build 96 such triples carry two records (a read and
a write of one attribute; a name as annotation and as value; the ``construct``/``deep``
pair above). Measurement: ``gaps/deep_tier_union_by_repeat_2026-09-04.md``.

An edge seen in fewer than N runs carries ``extras.seen: k``; nothing is written when
``k == N``, so a single-sample build's edges are byte-identical to what they were. Node
counters (``calls`` / ``attr_access``) count *sites*, which dedupe into edges — the
measured node had three counter variants behind one flapping edge — so per node the
variant with the fewest ``unresolved`` is kept (tie: most ``resolved``, tie: first run).

**Every sample is a fresh process.** The share above was measured across processes —
the consumer's 175 builds and the eight here. Repeating the behavioural layer *inside*
one process was measured too, on the same tree: eight passes gave two distinct
artifacts in streaks (pass 1 | passes 2–6 | passes 7–8), so consecutive passes are
correlated in a way separate processes were not seen to be, and whether they are
independent samples at all is not established. ``griffe_extractor.collect_samples``
therefore spawns one interpreter per sample — the regime whose share is known — and runs them
concurrently; the consumer measured 8 parallel builds against sequential ones and found
the same share (10 of 12 vs 11 of 12).
"""

from __future__ import annotations

import copy
import json

from codemap.model import Edge, Graph

#: Behavioral ``calls`` resolutions — the class whose ``resolution`` is a *quality* of the
#: run rather than an identity of the edge. The incremental splice keys on the same set
#: (``incremental.py`` imports it from here): what is spliced and what is unstable turned
#: out to be one list, twice.
BEHAVIOR_CALL_RES = frozenset({"module", "self", "imported", "deep"})

#: Node-extras counters that count sites and may differ between runs of one tree.
_SITE_COUNTERS = ("calls", "attr_access")


def _identity(e: Edge) -> tuple:
    """The key two runs' edges are matched on (see module docstring)."""
    if e.type == "calls" and e.extras.get("resolution") in BEHAVIOR_CALL_RES:
        return ("calls:behavioral", e.source, e.target, e.extras.get("via"))
    return (e.type, e.source, e.target,
            json.dumps(e.extras, sort_keys=True, ensure_ascii=False))


def _deeper(new: Edge, current: Edge) -> bool:
    return (new.extras.get("resolution") == "deep"
            and current.extras.get("resolution") != "deep")


def _better_counter(a: dict | None, b: dict | None) -> dict | None:
    """The counter variant that resolved more sites (``None`` never beats a value)."""
    if a is None:
        return b
    if b is None:
        return a
    ka = (-a.get("unresolved", 0), a.get("resolved", 0))
    kb = (-b.get("unresolved", 0), b.get("resolved", 0))
    return b if kb > ka else a


def merge_samples(samples: list[Graph]) -> tuple[Graph, dict]:
    """Union ``samples`` into one graph; return it with ``{"runs": N, "unstable": K}``.

    A single sample is returned **untouched** with ``{"runs": 1}`` — no ``unstable`` key,
    because instability is not measurable from one run, and an absent value must mean
    *unmeasured*, not zero (R1-C28). Every sample must come from the same structural
    base (same nodes); the first one's nodes and provenance are the merged graph's.
    """
    if not samples:
        raise ValueError("merge_samples needs at least one sample")
    if len(samples) == 1:
        return samples[0], {"runs": 1}
    runs = len(samples)
    base = samples[0]
    # identity -> [runs seen in, chosen edge]
    chosen: dict[tuple, list] = {}
    for g in samples:
        seen_this_run: set[tuple] = set()
        for e in g.edges:
            key = _identity(e)
            entry = chosen.get(key)
            if entry is None:
                chosen[key] = [1, e]
            else:
                if key not in seen_this_run:
                    entry[0] += 1
                if _deeper(e, entry[1]):
                    entry[1] = e
            seen_this_run.add(key)

    merged = Graph(target=base.target)
    merged.provenance = copy.deepcopy(base.provenance)
    for nid in base.nodes:
        node = copy.deepcopy(base.nodes[nid])
        for key in _SITE_COUNTERS:
            best = None
            for g in samples:
                other = g.nodes.get(nid)
                best = _better_counter(best, other.extras.get(key) if other else None)
            if best is not None:
                node.extras[key] = copy.deepcopy(best)
        merged.add_node(node)

    unstable = 0
    for count, edge in chosen.values():
        e = copy.deepcopy(edge)
        if count < runs:
            e.extras["seen"] = count
            unstable += 1
        merged.add_edge(e)
    return merged, {"runs": runs, "unstable": unstable}

