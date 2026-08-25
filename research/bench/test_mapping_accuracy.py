#!/usr/bin/env python3
"""`tests_for` accuracy against coverage.py ground truth (R1-C24 / design D6).

Unlike the call-graph bench, which needs a hand-labeled oracle because no sound
Python call-graph tool runs on 3.12, this question **has** a real oracle: run the
suite under coverage.py with per-test contexts and you know exactly which tests
executed which lines. Mapping those lines back through the graph's own
``symbol_at`` gives, per symbol, the set of tests that truly exercise it.

That oracle is what set the design's one open number — the distance cutoff — and
what overturned the design's declared success metric (see
``gaps/test_mapping_2026-08-25.md`` §6).

Read the numbers with their denominators:

  precision      of the returned band against the executed-set. The number that
                 matters, and the one the cutoff was chosen on.
  hit rate       share of answers containing >=1 genuinely covering test. This is
                 the claim the feature actually makes.
  recall         against the executed-set. Published because a reader would assume
                 it, NOT as a target: for a central symbol the executed-set is most
                 of the suite, and returning most of the suite is not an answer.
  answered       share of exercised symbols that get any confident answer. The rest
                 are reported `unknown` — never "untested".

Usage:
  # 1. run the suite under coverage with per-test contexts
  COVERAGE_RCFILE=<rc> COVERAGE_FILE=/tmp/.coverage python -m coverage run -m pytest -q
  #    where <rc> contains:  [run]\nsource = codemap\ndynamic_context = test_function
  # 2. build a repo-scoped graph
  codemap build codemap --consumer tests --mode full --deep -o /tmp/g.json
  # 3. score
  python research/bench/test_mapping_accuracy.py /tmp/.coverage /tmp/g.json

Needs `coverage` (not a codemap dependency — a measurement tool).
"""

from __future__ import annotations

import collections
import statistics
import sys
from pathlib import Path

from codemap import store
from codemap.query import Query

MAX_HOP = 6


def truth_from_coverage(covfile: str, q: Query, repo_root: Path) -> dict[str, set[str]]:
    """symbol id -> the set of tests coverage.py saw execute one of its lines."""
    import coverage

    data = coverage.CoverageData(covfile)
    data.read()
    truth: dict[str, set[str]] = {}
    prefix = str(repo_root).rstrip("/") + "/"
    for f in data.measured_files():
        rel = f[len(prefix):] if f.startswith(prefix) else f
        for line, contexts in data.contexts_by_lineno(f).items():
            sym = q.symbol_at(rel, line)
            if not sym:
                continue
            for ctx in contexts:
                if ctx:
                    # coverage's dynamic context is `test_module.test_func[|phase]`
                    truth.setdefault(sym, set()).add("tests." + ctx.split("|")[0])
    return truth


def score(q: Query, truth: dict[str, set[str]], target: str) -> None:
    core = [i for i, n in q.graph.nodes.items()
            if i.startswith(target) and n.kind in ("function", "class")]
    covered = [s for s in core if truth.get(s)]
    tier = (q.graph.provenance or {}).get("tier", "?")
    print(f"target={target} tier={tier} | core symbols={len(core)} | "
          f"exercised (per coverage.py)={len(covered)}")

    # -- the cliff: precision by how far back the nearest band was --------------
    by_hop: dict[int, list[float]] = collections.defaultdict(list)
    sizes: dict[int, list[int]] = collections.defaultdict(list)
    silent = 0
    for s in covered:
        r = q.tests_for(s, depth=MAX_HOP, cap=10 ** 6)
        if not r["distance"]:
            silent += 1
            continue
        pred = {t["id"] for t in r["tests"]}
        by_hop[r["distance"]].append(len(pred & truth[s]) / len(pred))
        sizes[r["distance"]].append(len(pred))

    print(f"\n{'nearest hop':>12}{'symbols':>9}{'median prec':>13}"
          f"{'mean prec':>11}{'median size':>13}")
    for hop in sorted(by_hop):
        ps = by_hop[hop]
        print(f"{hop:>12}{len(ps):>9}{statistics.median(ps):>13.2f}"
              f"{statistics.mean(ps):>11.2f}{statistics.median(sizes[hop]):>13.0f}")
    print(f"  (no test within {MAX_HOP} hops: {silent}/{len(covered)} — reported "
          f"`unknown`, never 'untested')")

    # -- the shipped default ----------------------------------------------------
    ps, szs, hits, answered = [], [], 0, 0
    recalls = []
    for s in covered:
        r = q.tests_for(s)                      # shipped defaults
        if not r["distance"]:
            continue
        answered += 1
        pred = {t["id"] for t in r["tests"]}
        p = len(pred & truth[s]) / len(pred)
        ps.append(p)
        szs.append(len(pred))
        recalls.append(len(pred & truth[s]) / len(truth[s]))
        hits += p > 0
    print(f"\nat the shipped cutoff:")
    print(f"  answered            {answered}/{len(covered)} "
          f"({100 * answered / len(covered):.0f}% of exercised symbols)")
    print(f"  median precision    {statistics.median(ps):.2f}  "
          f"(mean {statistics.mean(ps):.2f})")
    print(f"  hit rate            {hits}/{answered} "
          f"({100 * hits / answered:.0f}% contain >=1 genuinely covering test)")
    print(f"  median recall       {statistics.median(recalls):.2f}  "
          f"— see the module docstring before reading this as a failure")
    print(f"  median tests shown  {statistics.median(szs):.0f}")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    covfile, graph_path = sys.argv[1], sys.argv[2]
    q = Query(store.load(graph_path))
    repo_root = Path(sys.argv[3]) if len(sys.argv) > 3 else Path.cwd()
    truth = truth_from_coverage(covfile, q, repo_root)
    if not truth:
        print("no coverage contexts mapped to symbols — was the run made with "
              "`dynamic_context = test_function`, and is the graph of the same tree?")
        return 1
    score(q, truth, q.graph.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
