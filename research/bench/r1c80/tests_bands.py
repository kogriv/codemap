"""R1-C80: `tests` answers against coverage.py truth, dumped per symbol so two codemap versions can be compared.

Design ``docs/design/tests_through_helpers.md`` (expectations E1–E6). Run once with codmap 0.0.27 and once with the
R1-C80 branch on the **same** graph and the **same** coverage data, then ``compare``.

    python tests_bands.py score COVERAGE GRAPH REPO_ROOT OUT.json [SYMBOL ...]
    python tests_bands.py compare BASE.json NEW.json

Differences from ``research/bench/test_mapping_accuracy.py`` (R1-C24 D6), on purpose:
- a coverage context is matched to a graph test by its **tail** (``test_mod.test_fn`` or ``test_mod.TestC.test_fn``),
  not by prepending ``tests.``: bquant's tests are nested (``tests/unit/test_x.py``), and coverage names the module
  the way pytest imported it, which need not carry the package path. An ambiguous or missing tail is counted, not
  guessed;
- every answer is written out, so E3 (old ⊆ new) and E6 (precision of the changed answers) are computed, not eyeballed.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from codemap import store
from codemap.query import Query


def test_index(q: Query) -> dict[str, list[str]]:
    by_tail: dict[str, list[str]] = defaultdict(list)
    for tid in q._test_ids:
        mod = q._module_of(tid)
        tail = tid[len(mod.id) + 1:]
        by_tail[mod.id.rsplit(".", 1)[-1] + "." + tail].append(tid)
    return by_tail


def truth_from_coverage(covfile: str, q: Query, repo_root: Path) -> tuple[dict[str, set[str]], dict]:
    import coverage

    data = coverage.CoverageData(covfile)
    data.read()
    idx = test_index(q)
    truth: dict[str, set[str]] = {}
    unmatched, ambiguous, matched = set(), set(), set()
    prefix = str(repo_root).rstrip("/") + "/"
    for f in data.measured_files():
        rel = f[len(prefix):] if f.startswith(prefix) else f
        for line, contexts in data.contexts_by_lineno(f).items():
            sym = q.symbol_at(rel, line)
            if not sym:
                continue
            for ctx in contexts:
                if not ctx:
                    continue
                name = ctx.split("|")[0]
                parts = name.split(".")
                cands = []
                for k in range(len(parts) - 1, 0, -1):          # longest tail that names a module + test
                    cands = idx.get(".".join(parts[-(k + 1):]) if k + 1 <= len(parts) else "", [])
                    if cands:
                        break
                if len(cands) == 1:
                    matched.add(name)
                    truth.setdefault(sym, set()).add(cands[0])
                elif cands:
                    ambiguous.add(name)
                else:
                    unmatched.add(name)
    return truth, {"contexts_matched": len(matched), "contexts_ambiguous": len(ambiguous),
                   "contexts_unmatched": len(unmatched), "unmatched_sample": sorted(unmatched)[:10]}


def score(covfile, graph, repo_root, out, symbols):
    q = Query(store.load(graph))
    import os
    if os.environ.get("R1C80_ABLATE_D1"):      # ablation: D0 edges kept, helpers cost a hop again
        q._test_helper_ids, q._test_parent, q._test_children = set(), {}, {}
    truth, mapping = truth_from_coverage(covfile, q, Path(repo_root))
    target = q.graph.target
    core = sorted(i for i, n in q.graph.nodes.items()
                  if i.startswith(target) and n.kind in ("function", "class") and q.root_of(i) == "core")
    covered = [s for s in core if truth.get(s)]
    per = {}
    for s in covered:
        r = q.tests_for(s, cap=10 ** 6)
        per[s] = {"distance": r["distance"], "tests": sorted(t["id"] for t in r["tests"]),
                  "next_band": r.get("next_band", "absent"), "truth": len(truth[s]),
                  "true_hits": len({t["id"] for t in r["tests"]} & truth[s])}
    named = {}
    from codemap.serve.session import Session
    session = Session(q.graph)
    for name in symbols:                       # resolved the way the CLI resolves it
        env = session.handle({"op": "tests", "args": {"symbol": name, "cap": 10 ** 6}})
        if not env.get("ok"):
            named[name] = {"error": env.get("error")}
            continue
        r = env["result"]
        s = r["symbol"]
        t_true = set(truth.get(s, ()))
        for k, v in truth.items():             # a module or class answers for its members
            if k.startswith(s + "."):
                t_true |= v
        named[s] = {"asked": name, "distance": r["distance"],
                    "tests": sorted(t["id"] for t in r["tests"]),
                    "next_band": r.get("next_band", "absent"), "truth": sorted(t_true),
                    "missed_true": sorted(t_true - {t["id"] for t in r["tests"]}),
                    "caveats": r["caveats"]}
    ans = [v for v in per.values() if v["distance"]]
    prec = [v["true_hits"] / len(v["tests"]) for v in ans]
    rec = [v["true_hits"] / v["truth"] for v in ans]
    summary = {"tier": (q.graph.provenance or {}).get("tier"), "core_symbols": len(core),
               "exercised": len(covered), "answered": len(ans),
               "median_precision": statistics.median(prec) if prec else None,
               "mean_precision": statistics.mean(prec) if prec else None,
               "hit_rate": sum(p > 0 for p in prec) / len(ans) if ans else None,
               "median_recall": statistics.median(rec) if rec else None,
               "median_shown": statistics.median(len(v["tests"]) for v in ans) if ans else None,
               "mapping": mapping}
    Path(out).write_text(json.dumps({"summary": summary, "named": named, "per_symbol": per},
                                    indent=1, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=1))
    for s, v in named.items():
        if "error" in v:
            print(f"{s}: {v['error']}")
            continue
        print(f"{s}: d={v['distance']} tests={len(v['tests'])} truth={len(v['truth'])} "
              f"missed={len(v['missed_true'])} next={v['next_band']}")


def compare(base_p, new_p):
    base, new = json.loads(Path(base_p).read_text()), json.loads(Path(new_p).read_text())
    b, n = base["per_symbol"], new["per_symbol"]
    changed, not_superset = [], []
    for s in sorted(set(b) & set(n)):
        if b[s]["tests"] != n[s]["tests"] or b[s]["distance"] != n[s]["distance"]:
            changed.append(s)
            if not set(b[s]["tests"]) <= set(n[s]["tests"]):
                not_superset.append(s)
    prec = [n[s]["true_hits"] / len(n[s]["tests"]) for s in changed if n[s]["tests"]]
    print(f"symbols compared {len(set(b) & set(n))}, answers changed {len(changed)}, "
          f"old not a subset of new {len(not_superset)}")
    if prec:
        print(f"changed answers: median precision {statistics.median(prec):.2f}, mean {statistics.mean(prec):.2f}, "
              f"min {min(prec):.2f}")
    for s in not_superset[:20]:
        print(f"  not superset: {s}: d {b[s]['distance']}→{n[s]['distance']}, "
              f"{len(b[s]['tests'])}→{len(n[s]['tests'])}")
    for k in ("answered", "median_precision", "hit_rate", "median_recall", "median_shown"):
        print(f"{k:18} base {base['summary'][k]}  new {new['summary'][k]}")


if __name__ == "__main__":
    if sys.argv[1] == "score":
        score(*sys.argv[2:6], sys.argv[6:])
    else:
        compare(sys.argv[2], sys.argv[3])
