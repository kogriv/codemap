"""Measure import-linter / grimp on the R2 tree and probe its gate (R2-import-linter).

Pre-registration: ``research/tools/import-linter.md`` §0.

    python research/bench/import_linter.py graph --stage STAGE --out run.json [--repeat 3]   # needs grimp
    python research/bench/import_linter.py score --truth truth.json --run run.json --out results.json  # networkx

``graph`` builds grimp's graph of ``bquant`` in a fresh interpreter per run, with no cache, and dumps
module -> module direct imports with the line numbers grimp records. The truth file is the one written by
``research/bench/graphify.py truth`` on the same tree (codemap's module imports, split by scope).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

PACKAGE = "bquant"
DUMP = r"""
import json, sys, grimp
g = grimp.build_graph(sys.argv[1], cache_dir=None, exclude_type_checking_imports=(sys.argv[2] == "1"))
mods = sorted(g.modules)
edges = {}
for m in mods:
    for t in sorted(g.find_modules_directly_imported_by(m)):
        if t != m:
            det = g.get_import_details(importer=m, imported=t)
            edges[f"{m} {t}"] = sorted({d["line_number"] for d in det})
print(json.dumps({"modules": mods, "edges": edges, "grimp": grimp.__version__ if hasattr(grimp, "__version__") else None}))
"""


def graph(a) -> None:
    stage = Path(a.stage).resolve()
    runs = []
    for i in range(a.repeat):
        t0 = time.time()
        r = subprocess.run([sys.executable, "-c", DUMP, PACKAGE, "0"], cwd=stage, capture_output=True,
                           text=True, timeout=1800)
        if r.returncode:
            raise SystemExit(r.stderr[-1500:])
        d = json.loads(r.stdout)
        digest = hashlib.sha256(json.dumps(d["edges"], sort_keys=True).encode()).hexdigest()
        runs.append({"seconds": round(time.time() - t0, 2), "digest": digest, "n_edges": len(d["edges"]),
                     "n_modules": len(d["modules"]), "graph": d if i == 0 else None})
        print(f"run {i}: {runs[-1]['seconds']}s modules={len(d['modules'])} edges={len(d['edges'])} {digest[:12]}")
    r = subprocess.run([sys.executable, "-c", DUMP, PACKAGE, "1"], cwd=stage, capture_output=True, text=True)
    no_tc = json.loads(r.stdout)
    Path(a.out).write_text(json.dumps({"runs": runs, "exclude_type_checking": no_tc}, indent=1, sort_keys=True) + "\n")


def score(a) -> None:
    import networkx as nx

    t = json.loads(Path(a.truth).read_text())
    r = json.loads(Path(a.run).read_text())
    tedges = {tuple(k.split()): set(v) for k, v in t["edges"].items()}
    tset = set(tedges)
    g = r["runs"][0]["graph"]
    ge = {tuple(k.split()) for k in g["edges"]}
    ge_notc = {tuple(k.split()) for k in r["exclude_type_checking"]["edges"]}

    def cycles(es):
        return {frozenset(c) for c in nx.simple_cycles(nx.DiGraph(list(es)))}

    tc, gc = cycles(tset), cycles(ge)
    by_scope = Counter(s for v in tedges.values() for s in v)
    found_scope = Counter(s for e, v in tedges.items() if e in ge for s in v)
    res = {
        "determinism": {"runs": len(r["runs"]), "distinct": len({x["digest"] for x in r["runs"]}),
                        "seconds": [x["seconds"] for x in r["runs"]]},
        "modules": {"grimp": len(g["modules"]), "truth": len(t["modules"]),
                    "missing": sorted(set(t["modules"]) - set(g["modules"])),
                    "extra": sorted(set(g["modules"]) - set(t["modules"]))},
        "edges": {"grimp": len(ge), "truth": len(tset), "true": len(ge & tset),
                  "precision": round(len(ge & tset) / len(ge), 4) if ge else None,
                  "recall": round(len(ge & tset) / len(tset), 4),
                  "false": sorted(map(list, ge - tset)), "missed": sorted(map(list, tset - ge))},
        "scopes": {"truth": dict(by_scope), "found": dict(found_scope)},
        "cycles": {"truth": len(tc), "grimp": len(gc), "hit": len(tc & gc), "false": len(gc - tc)},
        "exclude_type_checking": {"edges": len(ge_notc), "dropped": sorted(map(list, ge - ge_notc))},
    }
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    e, c = res["edges"], res["cycles"]
    print(f"edges {e['grimp']} (true {e['true']}, p={e['precision']}, r={e['recall']}); cycles {c['hit']}/{c['truth']} "
          f"(+{c['false']}); scopes {res['scopes']['found']}; determinism {res['determinism']}; "
          f"false {e['false'][:6]}; missed {e['missed'][:6]}; tc-dropped {res['exclude_type_checking']['dropped']}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("graph")
    s.add_argument("--stage", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--repeat", type=int, default=3)
    s = sub.add_parser("score")
    for f in ("--truth", "--run", "--out"):
        s.add_argument(f, required=True)
    a = p.parse_args()
    {"graph": graph, "score": score}[a.cmd](a)


if __name__ == "__main__":
    main()
