"""Measure grafema's Python import graph on the R2 tree (R2-grafema).

Pre-registration: ``research/tools/grafema.md`` §0 — controls, predictions and the scoring rule are
fixed there.

    python research/bench/grafema.py truth --stage STAGE --out truth.json        # needs codemap
    python research/bench/grafema.py fixture --grafema BIN --work WORK --out fixture.json
    python research/bench/grafema.py run --grafema BIN --stage STAGE --work WORK --out run.json \\
        [--repeat 3]
    python research/bench/grafema.py score --truth truth.json --run run.json --stage STAGE \\
        --out results.json                                                      # needs networkx

``--grafema`` is the ``grafema`` CLI of an ``npm i grafema@VERSION`` prefix. ``fixture`` and ``run``
use the standard library only, so they run wherever grafema is installed. Every tree gets the same
config: ``include: ["**/*.py"]``. The quickstart's brace glob does not load the Python analyzer
(card §0.1), so ``run`` also probes ``analyze --quickstart`` once, on its own copy.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

PACKAGE = "bquant"
CONFIG = 'version: 0.4.1\nroot: ..\ninclude:\n  - "**/*.py"\nexclude:\n  - "**/.git/**"\n'
EDGES = ("MATCH (a:MODULE)-[:DEPENDS_ON]->(b:MODULE) RETURN a.file, b.file LIMIT 1000000")
MODULES = "MATCH (a:MODULE) RETURN a.file LIMIT 1000000"

# C3: one line per case; the comment names the case and the expected outcome (card §0.3).
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
        "from .m import x               # C3g: should be sub -> sub.m\n"
        "from .m2 import y              # C3h: should be sub -> sub.m2, not pkg.m2\n"
    ),
    "pkg/sub/m.py": "x = 5\n",
    "pkg/sub/m2.py": "y = 'right one'\n",
    "pkg/user.py": "from pkg.sub import x          # C3i: edge user -> sub\n",
}
CASES = {
    "C3a": ("pkg.a", "pkg.b", True), "C3b": ("pkg.a", "pkg.c", True),
    "C3c": ("pkg.a", "pkg.d", True), "C3d": ("pkg.a", "pkg.e", True),
    "C3e": ("pkg.a", "pkg.f", True), "C3f": ("pkg.a", "pkg", True),
    "C3g": ("pkg.sub", "pkg.sub.m", True), "C3h_right": ("pkg.sub", "pkg.sub.m2", True),
    "C3h_wrong": ("pkg.sub", "pkg.m2", False), "C3i": ("pkg.user", "pkg.sub", True),
}


def _module(path: str, package: str | None = None) -> str | None:
    p = path.replace("\\", "/")
    if not p.endswith(".py") or (package and not p.startswith(package + "/")):
        return None
    parts = p[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _g(binary: Path, args, cwd: Path, timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run([str(binary), *args], cwd=cwd, capture_output=True, text=True,
                          timeout=timeout)


def _cypher(binary: Path, tree: Path, q: str) -> list:
    r = _g(binary, ["query", "--cypher", q, "-j", "-l", "1000000"], tree)
    out = r.stdout[r.stdout.find("{"):] if "{" in r.stdout else ""
    try:
        return json.loads(out)["rows"]
    except (json.JSONDecodeError, KeyError):
        raise SystemExit(f"cypher failed: {(r.stdout + r.stderr)[-800:]}")


def _analyze(binary: Path, tree: Path, quickstart: bool = False) -> dict:
    if not quickstart:
        (tree / ".grafema").mkdir(exist_ok=True)
        (tree / ".grafema" / "config.yaml").write_text(CONFIG)
    t0 = time.monotonic()
    args = ["analyze", "--quickstart"] if quickstart else ["analyze", "--clear"]
    r = _g(binary, args + ["--log-file", str(tree.parent / f"{tree.name}.analyze.log")], tree)
    return {"rc": r.returncode, "seconds": round(time.monotonic() - t0, 1),
            "tail": (r.stdout + r.stderr)[-600:]}


def _graph(binary: Path, tree: Path, package: str | None) -> dict:
    mods = sorted({row[0] for row in _cypher(binary, tree, MODULES) if row[0]})
    edges = set()
    for a, b in _cypher(binary, tree, EDGES):
        ma, mb = _module(a or "", package), _module(b or "", package)
        if ma and mb and ma != mb:
            edges.add((ma, mb))
    return {"modules": mods, "edges": sorted(map(list, edges))}


def _stop(binary: Path, tree: Path) -> None:
    _g(binary, ["stop"], tree, timeout=120)


def fixture(a) -> None:
    binary, work = Path(a.grafema).resolve(), Path(a.work).resolve()
    root = work / "fixture"
    shutil.rmtree(root, ignore_errors=True)
    for rel, body in FIXTURE.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body)
    an = _analyze(binary, root)
    g = _graph(binary, root, None)
    _stop(binary, root)
    got = {tuple(e) for e in g["edges"]}
    checks = {k: {"edge": f"{s} -> {t}", "expected": exp, "present": (s, t) in got}
              for k, (s, t, exp) in CASES.items()}
    res = {"analyze": an, "edges": g["edges"], "checks": checks}
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    for k, c in checks.items():
        print(f"{k:10} {c['edge']:28} present={c['present']!s:5} expected={c['expected']}")


def run(a) -> None:
    binary, work, stage = Path(a.grafema).resolve(), Path(a.work).resolve(), Path(a.stage).resolve()
    work.mkdir(parents=True, exist_ok=True)
    runs = []
    for i in range(a.repeat):
        tree = work / f"tree{i}"
        shutil.rmtree(tree, ignore_errors=True)
        shutil.copytree(stage, tree)
        an = _analyze(binary, tree)
        g = _graph(binary, tree, PACKAGE)
        _stop(binary, tree)
        digest = hashlib.sha256(json.dumps(g["edges"]).encode()).hexdigest()
        runs.append({"analyze": an, "digest": digest, "n_edges": len(g["edges"]),
                     "n_modules": len(g["modules"]), "graph": g if i == 0 else None})
        print(f"run {i}: rc={an['rc']} {an['seconds']}s modules={len(g['modules'])} "
              f"edges={len(g['edges'])} {digest[:12]}")
    qs = work / "quickstart"
    shutil.rmtree(qs, ignore_errors=True)
    shutil.copytree(stage, qs)
    an = _analyze(binary, qs, quickstart=True)
    mods = len(_cypher(binary, qs, MODULES)) if an["rc"] in (0, 1) else None
    _stop(binary, qs)
    cfg = (qs / ".grafema" / "config.yaml")
    res = {"version": _g(binary, ["--version"], work).stdout.strip(), "runs": runs,
           "quickstart": {"analyze": an, "modules": mods,
                          "include": [ln.strip() for ln in cfg.read_text().splitlines()
                                      if "**/" in ln] if cfg.exists() else None}}
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(f"quickstart: rc={an['rc']} modules={mods}")


def truth(a) -> None:
    from codemap.store import load

    stage = Path(a.stage)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "g.json"
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
    packages = sorted(m for m in mods if (stage / m.replace(".", "/") / "__init__.py").exists())
    Path(a.out).write_text(json.dumps(
        {"modules": mods, "packages": packages,
         "edges": {k: sorted(v) for k, v in sorted(edges.items())}}, indent=1) + "\n")
    print(f"truth: {len(mods)} modules, {len(edges)} edges, {len(packages)} packages")


def _relative_in_init(stage: Path) -> set[tuple[str, str]]:
    """(package, target) pairs written as a relative import inside a package ``__init__.py``."""
    out = set()
    for p in (stage / PACKAGE).rglob("__init__.py"):
        pkg = _module(str(p.relative_to(stage)), PACKAGE)
        for n in ast.walk(ast.parse(p.read_text())):
            if isinstance(n, ast.ImportFrom) and n.level > 0:
                base = pkg.split(".")[: len(pkg.split(".")) - (n.level - 1)]
                tgt = ".".join(base + ([n.module] if n.module else []))
                out.add((pkg, tgt))
                for al in n.names:  # `from .x import sub` may name a submodule
                    out.add((pkg, f"{tgt}.{al.name}"))
    return out


def score(a) -> None:
    import networkx as nx

    t = json.loads(Path(a.truth).read_text())
    r = json.loads(Path(a.run).read_text())
    stage = Path(a.stage)
    tedges = {tuple(k.split()): set(v) for k, v in t["edges"].items()}
    packages = set(t["packages"])
    g = r["runs"][0]["graph"]
    ge = {tuple(e) for e in g["edges"]}
    tset = set(tedges)

    def cycles(es):
        return {frozenset(c) for c in nx.simple_cycles(nx.DiGraph(list(es)))}

    tc, gc = cycles(tset), cycles(ge)
    by_scope = Counter(s for v in tedges.values() for s in v)
    found_scope = Counter(s for e, v in tedges.items() if e in ge for s in v)
    only = {s: [e for e, v in tedges.items() if v == {s}] for s in ("function", "type_checking")}
    rel_init = _relative_in_init(stage)
    missed = sorted(tset - ge)
    cls = Counter()
    rows = []
    for e in missed:
        if e[0] in packages and e in rel_init:
            c = "init_relative"
        elif e[0] in packages:
            c = "init_other"
        elif e[1] in packages:
            c = "into_package"
        else:
            c = "other"
        cls[c] += 1
        rows.append([*e, c, sorted(tedges[e])])
    res = {
        "version": r["version"],
        "determinism": {"runs": len(r["runs"]),
                        "distinct_digests": len({x["digest"] for x in r["runs"]})},
        "analyze": [x["analyze"] for x in r["runs"]],
        "modules": {"bquant_modules": len([m for m in g["modules"] if _module(m, PACKAGE)]),
                    "truth_modules": len(t["modules"]), "all_module_nodes": len(g["modules"])},
        "edges": {"grafema": len(ge), "truth": len(tset), "true": len(ge & tset),
                  "precision": round(len(ge & tset) / len(ge), 4) if ge else None,
                  "recall": round(len(ge & tset) / len(tset), 4),
                  "false": sorted(map(list, ge - tset))},
        "scopes": {"truth": dict(by_scope), "found": dict(found_scope),
                   "found_only_function": len([e for e in only["function"] if e in ge]),
                   "only_function": len(only["function"]),
                   "found_only_type_checking": len([e for e in only["type_checking"] if e in ge])},
        "init": {"truth_from_package": len([e for e in tset if e[0] in packages]),
                 "found_from_package": len([e for e in tset & ge if e[0] in packages])},
        "cycles": {"truth": len(tc), "grafema": len(gc), "hit": len(tc & gc),
                   "grafema_false": len(gc - tc)},
        "missed": {"by_class": dict(cls), "rows": rows},
        "quickstart": r["quickstart"],
    }
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    e, c = res["edges"], res["cycles"]
    print(f"edges {e['grafema']} (true {e['true']}, p={e['precision']}, r={e['recall']}); "
          f"cycles hit {c['hit']}/{c['truth']} (+{c['grafema_false']} false); "
          f"init {res['init']}; scopes {res['scopes']['found']}; missed {dict(cls)}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("truth")
    s.add_argument("--stage", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("fixture")
    for f in ("--grafema", "--work", "--out"):
        s.add_argument(f, required=True)
    s = sub.add_parser("run")
    for f in ("--grafema", "--stage", "--work", "--out"):
        s.add_argument(f, required=True)
    s.add_argument("--repeat", type=int, default=3)
    s = sub.add_parser("score")
    for f in ("--truth", "--run", "--stage", "--out"):
        s.add_argument(f, required=True)
    a = p.parse_args()
    {"truth": truth, "fixture": fixture, "run": run, "score": score}[a.cmd](a)


if __name__ == "__main__":
    main()
