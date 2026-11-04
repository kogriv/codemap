"""Measure Graphify's Python code graph on the R2 tree (R2-graphify).

Pre-registration: ``research/tools/graphify.md`` §0. The controls, predictions and scoring rule are
fixed there.

    python research/bench/graphify.py truth --stage STAGE --out truth.json        # needs codemap
    python research/bench/graphify.py fixture --graphify BIN --work WORK --out fixture.json
    python research/bench/graphify.py run --graphify BIN --stage STAGE --work WORK --out run.json \\
        [--repeat 3]
    python research/bench/graphify.py score --truth truth.json --run run.json --stage STAGE \\
        --out results.json                                                      # needs networkx

``--graphify`` is the ``graphify`` CLI of a ``graphifyy==VERSION`` environment. Every extraction is
``graphify extract <tree> --code-only`` with ``GRAPHIFY_BACKEND=none`` and an empty ``HOME``, so no
model is reachable and nothing is read from an earlier run. ``fixture`` and ``run`` use the standard
library only.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

PACKAGE = "bquant"
IMPORT_RELS = ("imports", "imports_from", "re_exports")

# C3: the grafema card's fixture, kept identical so the two cards compare, plus C3j-C3l (card §0.3).
FIXTURE = {
    "pkg/__init__.py": "NAME = 1\n",
    "pkg/a.py": (
        "from typing import TYPE_CHECKING\n"
        "from pkg.b import f            # C3a: edge a -> b\n"
        "from .c import g               # C3b: edge a -> c\n"
        "from . import NAME             # C3f: edge a -> pkg\n"
        "try:\n"
        "    from .f import k           # C3e: edge a -> f\n"
        "except ImportError:\n"
        "    k = None\n"
        "if TYPE_CHECKING:\n"
        "    from .e import T           # C3d: edge a -> e\n\n\n"
        "def use() -> 'T':\n"
        "    from .d import h           # C3c: edge a -> d\n"
        "    return f() + g() + h() + NAME + (k or 0)\n"
    ),
    "pkg/b.py": "def f():\n    return 1\n",
    "pkg/c.py": "def g():\n    return 2\n",
    "pkg/d.py": "def h():\n    return 3\n",
    "pkg/e.py": "class T:\n    pass\n",
    "pkg/f.py": "k = 4\n",
    "pkg/m2.py": "y = 'one level up'\n",
    "pkg/sub/__init__.py": (
        "from .m import x               # C3g: sub -> sub.m\n"
        "from .m2 import y              # C3h: sub -> sub.m2, not pkg.m2\n"
    ),
    "pkg/sub/m.py": "x = 5\n",
    "pkg/sub/m2.py": "y = 'right one'\n",
    "pkg/user.py": "from pkg.sub import x          # C3i: edge user -> sub\n",
    "pkg/plain.py": "import pkg.b                   # C3j: edge plain -> b\n\n\ndef p():\n    return pkg.b.f()\n",
    "pkg/x.py": "from pkg.y import Y             # C3k: x -> y\n\n\nclass X:\n    pass\n",
    "pkg/y.py": (
        "class Y:\n    pass\n\n\n"
        "def make():\n    from pkg.x import X         # C3k: y -> x, the other half of a 2-cycle\n"
        "    return X()\n"
    ),
}
CASES = {
    "C3a": ("pkg.a", "pkg.b", True), "C3b": ("pkg.a", "pkg.c", True),
    "C3c": ("pkg.a", "pkg.d", True), "C3d": ("pkg.a", "pkg.e", True),
    "C3e": ("pkg.a", "pkg.f", True), "C3f": ("pkg.a", "pkg", True),
    "C3g": ("pkg.sub", "pkg.sub.m", True), "C3h_right": ("pkg.sub", "pkg.sub.m2", True),
    "C3h_wrong": ("pkg.sub", "pkg.m2", False), "C3i": ("pkg.user", "pkg.sub", True),
    "C3j": ("pkg.plain", "pkg.b", True),
    "C3k_xy": ("pkg.x", "pkg.y", True), "C3k_yx": ("pkg.y", "pkg.x", True),
    "C3a_reversed": ("pkg.b", "pkg.a", False),
}


def _module(path: str | None, package: str | None = None) -> str | None:
    if not isinstance(path, str):
        return None
    p = path.replace("\\", "/")
    if not p.endswith(".py") or (package and not p.startswith(package + "/")):
        return None
    m = p[:-3].replace("/", ".")
    return m[: -len(".__init__")] if m.endswith(".__init__") else m


def _env(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.endswith("_API_KEY") and k not in ("ANTHROPIC_BASE_URL", "OLLAMA_BASE_URL")}
    env.update(HOME=str(home), GRAPHIFY_BACKEND="none", PYTHONHASHSEED="0")
    return env


def _extract(binary: Path, tree: Path) -> dict:
    home = tree.parent / f"{tree.name}.home"
    shutil.rmtree(home, ignore_errors=True)
    home.mkdir()
    t0 = time.time()
    r = subprocess.run([str(binary), "extract", str(tree), "--code-only"], cwd=tree,
                       capture_output=True, text=True, env=_env(home), timeout=3600)
    # Keep machine paths out of committed results: the work directory becomes `<work>`.
    clean = lambda x: x.replace(str(tree.parent), "<work>")
    return {"rc": r.returncode, "seconds": round(time.time() - t0, 1),
            "stdout_tail": clean(r.stdout[-1500:]), "stderr_tail": clean(r.stderr[-1500:])}


def _edges(graph: dict, package: str | None) -> dict:
    """Module-level import edges, split by relation, plus calls file pairs, from graph.json."""
    nodes = {n["id"]: n for n in graph["nodes"]}
    links = graph.get("links", graph.get("edges", []))
    files = sorted({m for n in nodes.values() if (m := _module(n.get("source_file"), package))})
    imp: dict[str, set] = {}
    calls: set = set()
    tags: Counter = Counter()
    call_edges = []
    for e in links:
        s, t = nodes.get(e["source"], {}), nodes.get(e["target"], {})
        ms, mt = _module(s.get("source_file"), package), _module(t.get("source_file"), package)
        rel = e.get("relation")
        if rel in IMPORT_RELS and ms and mt and ms != mt:
            # `imports` may end on a symbol node (`from m import f` -> f, in f's defining file) or on a
            # file node (`import pkg.m`). Only file-ending edges are module dependencies (card §0.2).
            to_file = str(t.get("label", "")).endswith(".py")
            tag = rel if rel != "imports" else ("imports@file" if to_file else "imports@symbol")
            imp.setdefault(f"{ms} {mt}", set()).add(tag + (":type_only" if e.get("type_only") else ""))
        if rel in ("calls", "indirect_call") and ms and mt:
            tags[(rel, e.get("confidence"), "cross" if ms != mt else "same")] += 1
            call_edges.append([e["source"], e["target"], ms, mt, e.get("confidence"),
                               t.get("label"), e.get("source_location")])
            if ms != mt:
                calls.add(f"{ms} {mt}")
    return {"modules": files, "imports": {k: sorted(v) for k, v in sorted(imp.items())},
            "call_pairs": sorted(calls), "call_tags": {"|".join(map(str, k)): v for k, v in tags.items()},
            "call_edges": call_edges, "directed": graph.get("directed"),
            "multigraph": graph.get("multigraph"), "graph_meta": graph.get("graph")}


def fixture(a) -> None:
    binary, work = Path(a.graphify).resolve(), Path(a.work).resolve()
    root = work / "fixture"
    shutil.rmtree(root, ignore_errors=True)
    for rel, body in FIXTURE.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body)
    an = _extract(binary, root)
    g = json.loads((root / "graphify-out" / "graph.json").read_text())
    ed = _edges(g, None)
    got = {tuple(k.split()) for k in ed["imports"]}
    checks = {k: {"edge": f"{s} -> {t}", "expected": exp, "present": (s, t) in got,
                  "relations": ed["imports"].get(f"{s} {t}")}
              for k, (s, t, exp) in CASES.items()}
    res = {"extract": an, "edges": ed, "checks": checks}
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    for k, c in checks.items():
        print(f"{k:13} {c['edge']:28} present={c['present']!s:5} expected={c['expected']!s:5} {c['relations']}")


def run(a) -> None:
    binary, work, stage = Path(a.graphify).resolve(), Path(a.work).resolve(), Path(a.stage).resolve()
    work.mkdir(parents=True, exist_ok=True)
    runs = []
    for i in range(a.repeat):
        tree = work / f"tree{i}"
        shutil.rmtree(tree, ignore_errors=True)
        shutil.copytree(stage, tree)
        an = _extract(binary, tree)
        raw = (tree / "graphify-out" / "graph.json").read_bytes()
        g = json.loads(raw)
        ed = _edges(g, PACKAGE)
        links = g.get("links", [])
        strip = sorted(json.dumps({k: v for k, v in e.items()}, sort_keys=True) for e in links)
        runs.append({"extract": an, "bytes_digest": hashlib.sha256(raw).hexdigest(),
                     "links_digest": hashlib.sha256("\n".join(strip).encode()).hexdigest(),
                     "imports_digest": hashlib.sha256(json.dumps(ed["imports"]).encode()).hexdigest(),
                     "n_nodes": len(g["nodes"]), "n_links": len(links),
                     "edges": ed if i == 0 else None})
        print(f"run {i}: rc={an['rc']} {an['seconds']}s nodes={len(g['nodes'])} links={len(links)} "
              f"modules={len(ed['modules'])} imports={len(ed['imports'])} "
              f"bytes={runs[-1]['bytes_digest'][:12]} links={runs[-1]['links_digest'][:12]}")
    ver = subprocess.run([str(binary), "--version"], capture_output=True, text=True).stdout.strip()
    Path(a.out).write_text(json.dumps({"version": ver, "runs": runs}, indent=1, sort_keys=True) + "\n")


def truth(a) -> None:
    from codemap.store import load

    stage = Path(a.stage)
    out = Path(a.out).with_suffix(".codemap.json")
    r = subprocess.run([sys.executable, "-m", "codemap.cli", "build", str(stage / PACKAGE),
                        "-o", str(out)], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr[-600:])
    g = load(out)
    mods = sorted(i for i, n in g.nodes.items() if n.kind == "module")
    edges: dict[str, set] = {}
    for e in g.edges:
        if e.type == "imports" and e.source in mods and e.target in mods and e.source != e.target:
            edges.setdefault(f"{e.source} {e.target}", set()).add(e.extras.get("scope", "module"))

    def owner_module(nid: str) -> str | None:
        n = g.nodes.get(nid)
        while n is not None and n.kind != "module":
            nid = nid.rsplit(".", 1)[0] if "." in nid else ""
            n = g.nodes.get(nid)
        return nid if n is not None else None

    calls = sorted({f"{ms} {mt}" for e in g.edges if e.type == "calls"
                    for ms, mt in [(owner_module(e.source), owner_module(e.target))]
                    if ms and mt and ms != mt and ms.startswith(PACKAGE) and mt.startswith(PACKAGE)})
    packages = sorted(m for m in mods if (stage / m.replace(".", "/") / "__init__.py").exists())
    Path(a.out).write_text(json.dumps(
        {"modules": mods, "packages": packages, "call_pairs": calls,
         "edges": {k: sorted(v) for k, v in sorted(edges.items())}}, indent=1) + "\n")
    print(f"truth: {len(mods)} modules, {len(edges)} edges, {len(packages)} packages, "
          f"{len(calls)} codemap call file pairs")


def score(a) -> None:
    import networkx as nx

    t = json.loads(Path(a.truth).read_text())
    r = json.loads(Path(a.run).read_text())
    tedges = {tuple(k.split()): set(v) for k, v in t["edges"].items()}
    packages = set(t["packages"])
    ed = r["runs"][0]["edges"]
    allrel = {tuple(k.split()): set(v) for k, v in ed["imports"].items()}
    # Primary: module dependencies (imports_from, re_exports, imports ending on a file node).
    ge = {e for e, v in allrel.items() if any(not x.startswith("imports@symbol") for x in v)}
    gs = set(allrel) - ge          # reached only through an imported symbol's defining file
    gf = {e for e, v in allrel.items() if any(x.startswith("imports_from") for x in v)}
    tset = set(tedges)

    def cycles(es):
        return {frozenset(c) for c in nx.simple_cycles(nx.DiGraph(list(es)))}

    tc = cycles(tset)
    two = {c for c in tc if len(c) == 2}
    mutual_truth = {frozenset(e) for e in tset if (e[1], e[0]) in tset}
    mutual_found_both = {m for m in mutual_truth if all(e in ge for e in [tuple(m), tuple(m)[::-1]])}
    by_scope = Counter(s for v in tedges.values() for s in v)
    found_scope = Counter(s for e, v in tedges.items() if e in ge for s in v)
    missed = sorted(tset - ge)
    cls = Counter()
    rows = []
    for e in missed:
        if (e[1], e[0]) in tset and (e[1], e[0]) in ge:
            c = "reverse_of_found_mutual"
        elif e[0] in packages:
            c = "from_package_init"
        elif e[1] in packages:
            c = "into_package"
        else:
            c = "other"
        cls[c] += 1
        rows.append([*e, c, sorted(tedges[e])])
    tc_pairs = set(t["call_pairs"])
    gc_pairs = set(ed["call_pairs"])
    res = {
        "version": r["version"],
        "determinism": {"runs": len(r["runs"]),
                        "distinct_bytes": len({x["bytes_digest"] for x in r["runs"]}),
                        "distinct_links": len({x["links_digest"] for x in r["runs"]}),
                        "distinct_imports": len({x["imports_digest"] for x in r["runs"]})},
        "extract": [x["extract"] for x in r["runs"]],
        "graph": {"directed": ed["directed"], "multigraph": ed["multigraph"], "meta": ed["graph_meta"]},
        "modules": {"graphify": len(ed["modules"]), "truth": len(t["modules"]),
                    "missing": sorted(set(t["modules"]) - set(ed["modules"]))},
        "edges": {"graphify": len(ge), "truth": len(tset), "true": len(ge & tset),
                  "precision": round(len(ge & tset) / len(ge), 4) if ge else None,
                  "recall": round(len(ge & tset) / len(tset), 4),
                  "false": sorted(map(list, ge - tset)),
                  "symbol_only": {"n": len(gs), "true": len(gs & tset),
                                  "union_recall": round(len((ge | gs) & tset) / len(tset), 4)},
                  "imports_from_only": {"n": len(gf), "true": len(gf & tset),
                                        "recall": round(len(gf & tset) / len(tset), 4)}},
        "scopes": {"truth": dict(by_scope), "found": dict(found_scope)},
        "init": {"truth_from_package": len([e for e in tset if e[0] in packages]),
                 "found_from_package": len([e for e in tset & ge if e[0] in packages])},
        "cycles": {"truth": len(tc), "truth_two": len(two), "graphify_all": len(cycles(ge)),
                   "hit_all": len(tc & cycles(ge)), "hit_imports_from": len(tc & cycles(gf)),
                   "false_all": len(cycles(ge) - tc),
                   "truth_by_length": dict(Counter(len(c) for c in tc))},
        "mutual": {"truth_pairs": len(mutual_truth), "both_directions_found": len(mutual_found_both)},
        "missed": {"by_class": dict(cls), "rows": rows},
        "calls": {"codemap_pairs": len(tc_pairs), "graphify_pairs": len(gc_pairs),
                  "both": len(tc_pairs & gc_pairs),
                  "agreement": round(len(tc_pairs & gc_pairs) / len(gc_pairs), 4) if gc_pairs else None,
                  "coverage": round(len(tc_pairs & gc_pairs) / len(tc_pairs), 4) if tc_pairs else None,
                  "tags": ed["call_tags"],
                  "only_graphify_sample": sorted(gc_pairs - tc_pairs)[:40],
                  "only_codemap_sample": sorted(tc_pairs - gc_pairs)[:40]},
    }
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    e, c = res["edges"], res["cycles"]
    print(f"edges {e['graphify']} (true {e['true']}, p={e['precision']}, r={e['recall']}); "
          f"cycles hit {c['hit_all']}/{c['truth']} (+{c['false_all']} false), via imports_from "
          f"{c['hit_imports_from']}; mutual both {res['mutual']}; init {res['init']}; "
          f"scopes {res['scopes']['found']}; missed {dict(cls)}; determinism {res['determinism']}; "
          f"calls {res['calls']['agreement']}/{res['calls']['coverage']}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("truth")
    s.add_argument("--stage", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("fixture")
    for f in ("--graphify", "--work", "--out"):
        s.add_argument(f, required=True)
    s = sub.add_parser("run")
    for f in ("--graphify", "--stage", "--work", "--out"):
        s.add_argument(f, required=True)
    s.add_argument("--repeat", type=int, default=3)
    s = sub.add_parser("score")
    for f in ("--truth", "--run", "--stage", "--out"):
        s.add_argument(f, required=True)
    a = p.parse_args()
    {"truth": truth, "fixture": fixture, "run": run, "score": score}[a.cmd](a)


if __name__ == "__main__":
    main()
