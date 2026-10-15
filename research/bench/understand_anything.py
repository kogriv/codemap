"""Measure Understand-Anything's deterministic layer on the R2 tree (R2-understand-anything).

Pre-registration: ``research/tools/understand-anything.md`` §0 — controls, predictions and the
scoring rule are fixed there. No LLM is called: only the scripts the ``/understand`` skill ships.

    python research/bench/understand_anything.py run --plugin PLUGIN --stage STAGE \\
        --work WORK --out results.json [--repeat 4]

``--plugin`` is the ``understand-anything-plugin`` directory of a checkout whose core is built
(``pnpm --filter @understand-anything/core build``); ``--stage`` a staging tree from
``research/tools/_scope/materialize.py``. Every run indexes its own copy of the stage.

    python research/bench/understand_anything.py fixture --plugin PLUGIN --work WORK

runs control C3 on a three-file package written here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

PACKAGE = "bquant"
SYMBOLS = ("analyze_zones", "MACDZoneAnalyzer")

# C3: a top-level relative import (edge expected), a function-local one (none expected), and
# `from . import NAME` with NAME defined in the package `__init__` (none expected, P4's mechanism).
FIXTURE = {
    "pkg/__init__.py": "NAME = 1\n",
    "pkg/a.py": "from .b import f\nfrom . import NAME\n\n\ndef use():\n"
                "    from .c import g\n    return f() + g() + NAME\n",
    "pkg/b.py": "def f():\n    return 1\n",
    "pkg/c.py": "def g():\n    return 2\n",
}


def _skill(plugin: Path) -> Path:
    return plugin / "skills" / "understand"


def _node(script: Path, *args) -> None:
    r = subprocess.run(["node", str(script), *map(str, args)], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"{script.name} failed: {r.stderr[-800:]}")


def _scan_and_map(plugin: Path, root: Path, tmp: Path) -> tuple[dict, dict]:
    scan, inp, out = tmp / "scan.json", tmp / "imp-in.json", tmp / "imp-out.json"
    _node(_skill(plugin) / "scan-project.mjs", root, scan)
    s = json.loads(scan.read_text())
    files = [{k: f[k] for k in ("path", "language", "fileCategory")} for f in s["files"]]
    inp.write_text(json.dumps({"projectRoot": str(root), "files": files}))
    _node(_skill(plugin) / "extract-import-map.mjs", inp, out)
    return s, json.loads(out.read_text())


def _module(path: str) -> str | None:
    p = path.replace("\\", "/")
    if not p.startswith(PACKAGE + "/") or not p.endswith(".py"):
        return None
    parts = p[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _ua_edges(import_map: dict) -> set[tuple[str, str]]:
    out = set()
    for src, targets in import_map.items():
        a = _module(src)
        for t in targets:
            b = _module(t)
            if a and b and a != b:
                out.add((a, b))
    return out


def _truth(stage: Path) -> dict:
    from codemap.store import load

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "g.json"
        r = subprocess.run([sys.executable, "-m", "codemap.cli", "build", str(stage / PACKAGE),
                            "-o", str(out)], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(r.stderr[-600:])
        g = load(out)
    mods = {i for i, n in g.nodes.items() if n.kind == "module"}
    edges: dict[tuple[str, str], set[str]] = {}
    for e in g.edges:
        if e.type == "imports" and e.source in mods and e.target in mods and e.source != e.target:
            edges.setdefault((e.source, e.target), set()).add(e.extras.get("scope", "module"))
    return {"modules": mods, "edges": edges}


def _cycles(edges) -> list[frozenset]:
    import networkx as nx

    return [frozenset(c) for c in nx.simple_cycles(nx.DiGraph(list(edges)))]


def _structure(plugin: Path, root: Path, scan: dict, tmp: Path) -> dict:
    batch = [f for f in scan["files"] if f["path"].startswith(PACKAGE + "/")
             and f["path"].endswith(".py")]
    inp, out = tmp / "st-in.json", tmp / "st-out.json"
    inp.write_text(json.dumps({"projectRoot": str(root), "batchFiles": batch, "batchImportData": {}}))
    _node(_skill(plugin) / "extract-structure.mjs", inp, out)
    res = json.loads(out.read_text())
    hits: dict[str, list] = {s: [] for s in SYMBOLS}
    counts: Counter = Counter()
    for r in res.get("results", []):
        path = r.get("path") or r.get("filePath")
        st = r.get("structure") or r.get("structural") or r
        for fn in st.get("functions", []) or []:
            counts["function"] += 1
            if fn.get("name") in hits:
                hits[fn["name"]].append([path, "function", fn.get("lineRange") or fn.get("line")])
        for cl in st.get("classes", []) or []:
            counts["class"] += 1
            if cl.get("name") in hits:
                hits[cl["name"]].append([path, "class", cl.get("lineRange") or cl.get("line")])
            for m in cl.get("methods", []) or []:
                counts["method"] += 1
                name = m if isinstance(m, str) else m.get("name")
                if name in hits:
                    hits[name].append([path, f"method of {cl.get('name')}", None])
    return {"files_analyzed": res.get("filesAnalyzed"), "files_skipped": res.get("filesSkipped"),
            "counts": dict(counts), "symbols": hits,
            "result_keys": sorted(res["results"][0]) if res.get("results") else None}


def run(a) -> None:
    plugin, work, stage = Path(a.plugin).resolve(), Path(a.work).resolve(), Path(a.stage).resolve()
    work.mkdir(parents=True, exist_ok=True)
    digests, import_map, scan = [], None, None
    for i in range(a.repeat):
        tree, tmp = work / f"tree{i}", work / f"tmp{i}"
        shutil.rmtree(tree, ignore_errors=True)
        shutil.copytree(stage, tree)
        tmp.mkdir(exist_ok=True)
        scan, m = _scan_and_map(plugin, tree, tmp)
        digests.append(hashlib.sha256(json.dumps(m["importMap"], sort_keys=True).encode())
                       .hexdigest())
        import_map = import_map or m
    truth = _truth(stage)
    t_edges = truth["edges"]
    ua = _ua_edges(import_map["importMap"])
    by_scope = Counter(s for scopes in t_edges.values() for s in scopes)
    found = Counter(s for e, scopes in t_edges.items() if e in ua for s in scopes)
    only = {"module": [], "function": [], "type_checking": []}
    for e, scopes in t_edges.items():
        if len(scopes) == 1:
            only[next(iter(scopes))].append(e)
    t_cycles = set(_cycles(t_edges))
    ua_cycles = _cycles(ua)
    rel = [(s, "bquant.analysis") for s in (
        "bquant.analysis.zones", "bquant.analysis.zones.sequence_analysis",
        "bquant.analysis.zones.zone_features", "bquant.analysis.technical",
        "bquant.analysis.timeseries", "bquant.analysis.candlestick", "bquant.analysis.statistical",
        "bquant.analysis.statistical.hypothesis_testing", "bquant.analysis.chart",
        "bquant.analysis.statistical.regression")]
    res = {
        "scan": {"totalFiles": scan.get("totalFiles"), "filteredByIgnore": scan.get("filteredByIgnore"),
                 "languages": dict(Counter(f["language"] for f in scan["files"]))},
        "import_map_stats": import_map.get("stats"),
        "determinism": {"runs": a.repeat, "distinct_digests": len(set(digests)), "digest": digests[0]},
        "truth": {"modules": len(truth["modules"]), "edges": len(t_edges),
                  "edge_scopes": dict(by_scope), "cycles": len(t_cycles),
                  "cycles_module_only": len(_cycles([e for e, s in t_edges.items() if "module" in s])),
                  "cycles_module_tc": len(_cycles([e for e, s in t_edges.items()
                                                   if s & {"module", "type_checking"}]))},
        "ua": {"edges": len(ua), "in_truth": len(ua & set(t_edges)),
               "precision": round(len(ua & set(t_edges)) / len(ua), 4) if ua else None,
               "false_edges": sorted(map(list, ua - set(t_edges))),
               "found_by_scope": dict(found),
               "found_only_function": sorted(map(list, set(only["function"]) & ua)),
               "found_only_type_checking": sorted(map(list, set(only["type_checking"]) & ua)),
               "missed_module": sorted(map(list, {e for e, s in t_edges.items()
                                                  if "module" in s} - ua)),
               "cycles": len(ua_cycles),
               "cycles_in_truth": sum(1 for c in ua_cycles if c in t_cycles),
               "relative_bare_into_analysis": {f"{s}": (s, t) in ua for s, t in rel}},
        "structure": _structure(plugin, work / "tree0", scan, work / "tmp0"),
    }
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    u, t = res["ua"], res["truth"]
    print(f"truth {t['edges']} edges {t['edge_scopes']}, {t['cycles']} cycles "
          f"(module-only {t['cycles_module_only']}, +tc {t['cycles_module_tc']})")
    print(f"UA {u['edges']} edges, precision {u['precision']}, found {u['found_by_scope']}, "
          f"{u['cycles']} cycles; digests {res['determinism']['distinct_digests']}/{a.repeat}")


def fixture(a) -> None:
    plugin, work = Path(a.plugin).resolve(), Path(a.work).resolve()
    root = work / "fixture"
    shutil.rmtree(root, ignore_errors=True)
    for rel, body in FIXTURE.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body)
    tmp = work / "fixture-tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    _, m = _scan_and_map(plugin, root, tmp)
    got = sorted(m["importMap"].get("pkg/a.py", []))
    checks = {"top-level `from .b import f` -> pkg/b.py": "pkg/b.py" in got,
              "function-local `from .c import g` -> no pkg/c.py": "pkg/c.py" not in got,
              "`from . import NAME` -> no pkg/__init__.py": "pkg/__init__.py" not in got}
    print(json.dumps({"pkg/a.py": got, "checks": checks}, indent=1))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    for f in ("--plugin", "--stage", "--work", "--out"):
        r.add_argument(f, required=True)
    r.add_argument("--repeat", type=int, default=4)
    f = sub.add_parser("fixture")
    f.add_argument("--plugin", required=True)
    f.add_argument("--work", required=True)
    a = p.parse_args()
    {"run": run, "fixture": fixture}[a.cmd](a)


if __name__ == "__main__":
    main()
