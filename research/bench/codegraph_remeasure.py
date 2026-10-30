"""Re-measure CodeGraph's published figures on a newer release (R2-codegraph).

Pre-registration: ``research/codegraph_remeasure.md`` — the scoring rule for M1 is fixed there.

    python research/bench/codegraph_remeasure.py run --prefix CG --stage STAGE \\
        --work WORK --truth truth.json --out results.json

``--prefix`` is an ``npm i --prefix`` directory holding ``@colbymchenry/codegraph@VERSION``;
``--stage`` a staging tree from ``research/tools/_scope/materialize.py``. The stage is copied, never
indexed in place. Telemetry is switched off for every call (``DO_NOT_TRACK=1``).

    python research/bench/codegraph_remeasure.py truth --stage STAGE --out truth.json

builds the truth set once: every elementary cycle of the ``bquant`` import graph, all import scopes.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGE = "bquant"
SYMBOLS = ("MACDZoneAnalyzer", "ZoneInfo", "ZoneFeaturesAnalyzer", "analyze_zones", "get_logger")
ENV = {**os.environ, "DO_NOT_TRACK": "1"}

# The two-file repro, verbatim from the #1566 comment: settings.py imports nothing.
REPRO = {
    "settings.py": 'DEFAULTS = {"answer": "42"}\n\n\ndef read_setting(name):\n'
                   "    return DEFAULTS.get(name, None)\n",
    "cache.py": "from settings import read_setting\n\n\nclass LRUCache:\n"
                "    def __init__(self):\n        self._store = {}\n\n"
                "    def get(self, key):\n        return self._store.get(key)\n\n"
                "    def warm(self):\n"
                '        self._store["answer"] = read_setting("answer")\n',
}

NODE_CYCLES = r"""
const { CodeGraph } = require(process.argv[2]);
(async () => {
  const cg = await CodeGraph.open(process.argv[3]);
  const cycles = cg.findCircularDependencies();
  process.stdout.write(JSON.stringify(cycles));
  if (cg.close) cg.close();
})().catch(e => { console.error(e); process.exit(1); });
"""


def _cli(prefix: Path) -> Path:
    return prefix / "node_modules" / ".bin" / "codegraph"


def _sdk(prefix: Path) -> Path:
    return prefix / "node_modules" / "@colbymchenry" / "codegraph"


def _run(args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run([str(a) for a in args], capture_output=True, text=True, env=ENV, cwd=cwd)


def _index(prefix: Path, tree: Path) -> dict:
    r = _run([_cli(prefix), "init", "-y", tree])
    if r.returncode:
        raise SystemExit(f"init failed: {r.stderr[-600:]}")
    s = _run([_cli(prefix), "status", "--json", tree])
    return json.loads(s.stdout) if s.returncode == 0 else {"error": s.stderr[-400:]}


def _cycles(prefix: Path, tree: Path) -> list[list[str]]:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(NODE_CYCLES)
    try:
        r = _run(["node", f.name, _sdk(prefix), tree])
    finally:
        os.unlink(f.name)
    if r.returncode:
        raise SystemExit(f"cycles failed: {r.stderr[-600:]}")
    return json.loads(r.stdout)


def _module(path: str) -> str | None:
    """``bquant/core/config.py`` → ``bquant.core.config``; None outside the package."""
    p = path.replace("\\", "/")
    if not p.startswith(PACKAGE + "/") or not p.endswith(".py"):
        return None
    parts = p[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def score(reported: list[list[str]], truth: list[frozenset]) -> dict:
    tset = set(truth)
    hits, true_reported = set(), 0
    for cyc in reported:
        mods = [_module(p) for p in cyc]
        if None in mods:
            continue
        s = frozenset(mods)
        if s in tset:
            true_reported += 1
            hits.add(s)
    n = len(reported)
    return {"reported": n, "true_reported": true_reported, "truth": len(tset),
            "truth_hit": len(hits),
            "precision": round(true_reported / n, 4) if n else None,
            "recall": round(len(hits) / len(tset), 4) if tset else None}


def _callers(prefix: Path, tree: Path, sym: str, limit: int | None) -> dict:
    args = [_cli(prefix), "callers", sym, "--json", "-p", tree]
    if limit:
        args += ["--limit", str(limit)]
    r = _run(args)
    try:
        js = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": (r.stdout + r.stderr)[-400:]}
    rows = _rows(js)
    kinds: dict[str, int] = {}
    for row in rows:
        kinds[row.get("kind", "?")] = kinds.get(row.get("kind", "?"), 0) + 1
    top = {k: v for k, v in js.items() if not isinstance(v, list)} if isinstance(js, dict) else {}
    return {"rows": len(rows), "kinds": kinds, "keys": sorted(js) if isinstance(js, dict) else None,
            "scalars": top}


def _rows(js) -> list[dict]:
    """Caller rows, whatever the envelope.

    1.6.0 returns ``{symbol, callers}``. 1.6.2 returns the same top-level ``callers`` **and**
    repeats them per definition under ``definitions[].callers``; counting both doubles every row,
    so the top-level list wins whenever it exists.
    """
    if isinstance(js, list):
        return [r for r in js if isinstance(r, dict)]
    if isinstance(js.get("callers"), list):
        return [r for r in js["callers"] if isinstance(r, dict)]
    return [r for d in js.get("definitions") or [] if isinstance(d, dict)
            for r in d.get("callers") or [] if isinstance(r, dict)]


def _header(prefix: Path, tree: Path, sym: str) -> str:
    r = _run([_cli(prefix), "callers", sym, "-p", tree])
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    return lines[0].strip() if lines else ""


def _db_edges_into_get(tree: Path) -> dict:
    """M4 — ``calls`` edges from core/config.py into a ``get`` defined in core/cache.py."""
    db = tree / ".codegraph" / "codegraph.db"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cols = {t: [c[1] for c in con.execute(f"PRAGMA table_info({t})")]
            for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    q = """SELECT s.file_path, e.line, t.qualified_name FROM edges e
           JOIN nodes s ON s.id = e.source JOIN nodes t ON t.id = e.target
           WHERE e.kind = 'calls' AND t.name = 'get'
             AND t.file_path LIKE '%bquant/core/cache.py'
             AND s.file_path LIKE '%bquant/core/config.py'"""
    try:
        rows = [list(r) for r in con.execute(q)]
    except sqlite3.Error as e:
        return {"error": str(e), "schema": {k: cols[k] for k in ("nodes", "edges") if k in cols}}
    return {"edges": len(rows), "rows": sorted(rows, key=lambda r: (r[0], r[1] or 0))}


def _repro(prefix: Path, work: Path) -> list:
    d = work / "repro"
    d.mkdir(parents=True)
    for name, body in REPRO.items():
        (d / name).write_text(body)
    _index(prefix, d)
    return _cycles(prefix, d)


# #2566 (§8): `from <external> import name` against a same-named project symbol. The first three
# rows must bind on 1.6.2 (F1); the last two are negative controls (F2). `report.py → summary` is
# a project import every row must keep (F3).
ISSUE_2566 = {
    "scipy_vs_variable": ("from scipy import stats", "stats", "stats = summary([1, 2, 3])\n"),
    "scipy_vs_function": ("from scipy import stats", "stats",
                          "def stats():\n    return summary([1, 2, 3])\n"),
    "os_vs_variable": ("from os import path", "path", "path = summary([1, 2, 3])\n"),
    "control_import_as": ("import scipy.stats as stats", "stats", "stats = summary([1, 2, 3])\n"),
    "control_renamed": ("from scipy import stats", "stats", "result = summary([1, 2, 3])\n"),
}


def _file_edges(tree: Path) -> list[list]:
    db = tree / ".codegraph" / "codegraph.db"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    q = """SELECT s.file_path, t.file_path, t.kind, t.name, e.kind, e.metadata FROM edges e
           JOIN nodes s ON s.id = e.source JOIN nodes t ON t.id = e.target
           WHERE e.kind = 'imports' AND s.file_path != t.file_path"""
    try:
        rows = list(con.execute(q))
    except sqlite3.Error:  # no metadata column
        rows = [(*r, None) for r in con.execute(q.replace(", e.metadata", ""))]
    out = []
    for src, dst, kind, name, ekind, meta in rows:
        m = json.loads(meta) if meta else {}
        out.append([Path(src).name, Path(dst).name, f"{kind} {name}", m.get("resolvedBy")])
    return sorted(out)


def issue2566(a) -> None:
    prefix, work = Path(a.prefix).resolve(), Path(a.work).resolve()
    res = {"version": json.loads((_sdk(prefix) / "package.json").read_text())["version"]}
    for case, (imp, name, report_body) in ISSUE_2566.items():
        d = work / case
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        (d / "analysis.py").write_text(f"{imp}\n\n\ndef summary(values):\n"
                                       f"    return {name}.describe(values)\n")
        (d / "report.py").write_text(f"from analysis import summary\n\n{report_body}")
        _index(prefix, d)
        edges = _file_edges(d)
        res[case] = {
            "cycles": _cycles(prefix, d),
            "external_bound": [e for e in edges if e[0] == "analysis.py" and e[1] == "report.py"],
            "project_import_kept": any(e[0] == "report.py" and e[1] == "analysis.py" for e in edges),
        }
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    for case in ISSUE_2566:
        r = res[case]
        print(f"{res['version']} {case}: cycles={len(r['cycles'])} "
              f"bound={len(r['external_bound'])} project_import_kept={r['project_import_kept']}")


def run(a) -> None:
    prefix, work = Path(a.prefix).resolve(), Path(a.work).resolve()
    tree = work / "tree"
    shutil.copytree(a.stage, tree)
    version = json.loads((_sdk(prefix) / "package.json").read_text())["version"]
    tele = [ln.strip() for ln in _run([_cli(prefix), "telemetry"]).stdout.splitlines()
            if "disabled" in ln.lower() or "enabled" in ln.lower()]
    status = _index(prefix, tree)
    cycles = [[p.replace(str(tree) + "/", "") for p in c] for c in _cycles(prefix, tree)]
    truth = [frozenset(c) for c in json.loads(Path(a.truth).read_text())["cycles"]]
    pair = frozenset({"bquant.core.config", "bquant.core.cache"})
    res = {
        "version": version, "telemetry": tele,
        "status": status,
        "cycles": score(cycles, truth),
        "config_cache_cycle": any(frozenset(filter(None, map(_module, c))) == pair
                                  and len(c) == 2 for c in cycles),
        "cycles_outside_package": sum(1 for c in cycles if any(_module(p) is None for p in c)),
        "m4": _db_edges_into_get(tree),
        "callers": {s: {"default": _callers(prefix, tree, s, None),
                        "limit500": _callers(prefix, tree, s, 500),
                        "header": _header(prefix, tree, s)} for s in SYMBOLS},
        "repro": _repro(prefix, work),
        "raw_cycles": sorted(cycles),
    }
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    c = res["cycles"]
    print(f"{version}: {c['reported']} cycles, {c['true_reported']} true, "
          f"{c['truth_hit']}/{c['truth']} truth hit, p={c['precision']} r={c['recall']}")


def truth(a) -> None:
    import networkx as nx

    from codemap.store import load

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "g.json"
        r = subprocess.run([sys.executable, "-m", "codemap.cli", "build",
                            str(Path(a.stage) / PACKAGE), "-o", str(out)],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(r.stderr[-600:])
        g = load(out)
    mods = {i for i, n in g.nodes.items() if n.kind == "module"}
    dg = nx.DiGraph()
    for e in g.edges:
        if e.type == "imports" and e.source in mods and e.target in mods and e.source != e.target:
            dg.add_edge(e.source, e.target)
    cycles = sorted(sorted(c) for c in nx.simple_cycles(dg))
    sets = len({frozenset(c) for c in cycles})
    Path(a.out).write_text(json.dumps({"modules": len(mods), "import_edges": dg.number_of_edges(),
                                       "distinct_sets": sets, "cycles": cycles}, indent=1) + "\n")
    print(f"truth: {len(mods)} modules, {dg.number_of_edges()} edges, "
          f"{len(cycles)} cycles, {sets} distinct sets")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    for f in ("--prefix", "--stage", "--work", "--truth", "--out"):
        r.add_argument(f, required=True)
    t = sub.add_parser("truth")
    t.add_argument("--stage", required=True)
    t.add_argument("--out", required=True)
    i = sub.add_parser("issue2566")
    for f in ("--prefix", "--work", "--out"):
        i.add_argument(f, required=True)
    a = p.parse_args()
    {"run": run, "truth": truth, "issue2566": issue2566}[a.cmd](a)


if __name__ == "__main__":
    main()
