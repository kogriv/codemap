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
    """Caller rows, whatever the envelope — flat ``callers`` or per-definition groups."""
    if isinstance(js, list):
        return [r for r in js if isinstance(r, dict)]
    out = []
    for k, v in js.items():
        if k == "callers" and isinstance(v, list):
            out += [r for r in v if isinstance(r, dict) and "filePath" in r]
        elif isinstance(v, list):
            for d in v:
                if isinstance(d, dict) and isinstance(d.get("callers"), list):
                    out += d["callers"]
    return out


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


def run(a) -> None:
    prefix, work = Path(a.prefix).resolve(), Path(a.work).resolve()
    tree = work / "tree"
    shutil.copytree(a.stage, tree)
    version = json.loads((_sdk(prefix) / "package.json").read_text())["version"]
    tele = _run([_cli(prefix), "telemetry"]).stdout.strip().splitlines()
    status = _index(prefix, tree)
    cycles = [[p.replace(str(tree) + "/", "") for p in c] for c in _cycles(prefix, tree)]
    truth = [frozenset(c) for c in json.loads(Path(a.truth).read_text())["cycles"]]
    pair = frozenset({"bquant.core.config", "bquant.core.cache"})
    res = {
        "version": version, "telemetry": tele[-1] if tele else "",
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
    a = p.parse_args()
    {"run": run, "truth": truth}[a.cmd](a)


if __name__ == "__main__":
    main()
