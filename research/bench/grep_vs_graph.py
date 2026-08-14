#!/usr/bin/env python3
"""grep-vs-graph: the cost of "what breaks if I change this signature?" (R1-C13, part b).

Reproduces, on codemap's own ops, the finding from the 936-run apache/superset
study: a resolved call-graph is far cheaper than grep for impact questions, and
NO cheaper for "where is X defined". The unit is **candidates an agent must
inspect** to answer the question.

Two questions per target symbol:

  BREAKAGE ("what call-sites break if I change the signature of X?")
    graph  : call_contract(X) → the resolved caller set. Every hit is a real
             call-site (a lower bound — the static ceiling can miss dynamic ones).
    grep   : `git grep '\\bX\\b'` (naive) and `'\\bX('` (call-ish) → every textual
             mention: defs, docstrings, comments, string args, and — crucially —
             every *other* symbol that happens to share the name. grep cannot tell
             a call from a mention, nor which receiver's method is meant.

  WHERE-DEFINED ("where is X defined?")
    graph  : 1 — the def node.
    grep   : `git grep 'def X|class X'` → usually ~1. The honest NULL result:
             grep is already good at this, so the graph earns no advantage.

The gap between the two questions is the point: the graph's leverage is precision
on *relationships*, not on *locations*.

Targets are auto-picked from the graph (no cherry-picking): symbols with ≥2
resolved callers, bucketed by how many definitions share the short name —
'unique' (grep is only mildly noisy) vs 'polymorphic' (grep cannot disambiguate
the receiver, and the graph's deep type-resolution decisively wins).

Usage:
  python research/bench/grep_vs_graph.py --graph graph.json --repo /path/to/bquant
  python research/bench/grep_vs_graph.py --build ./codemap --repo .        # dogfood
  python research/bench/grep_vs_graph.py ... --json
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from codemap import store  # noqa: E402
from codemap.extract import extract  # noqa: E402
from codemap.query import Query  # noqa: E402


def _grep_count(repo: Path, pattern: str) -> int:
    """Lines matching an extended-regex across tracked *.py files (deterministic)."""
    r = subprocess.run(
        ["git", "-C", str(repo), "grep", "-I", "-nE", pattern, "--", "*.py"],
        capture_output=True, text=True,
    )
    if r.returncode not in (0, 1):  # 1 = no matches (fine); >1 = real error
        raise RuntimeError(f"git grep failed ({r.returncode}): {r.stderr.strip()}")
    return sum(1 for ln in r.stdout.splitlines() if ln.strip())


def _short(node_id: str) -> str:
    return node_id.rsplit(".", 1)[-1]


def _auto_targets(q: Query, *, min_callers: int, per_bucket: int) -> list[dict]:
    """Pick representative targets: ≥min_callers resolved callers, split unique/poly."""
    name_defs = collections.Counter(
        _short(n.id) for n in q.graph.nodes.values()
        if n.kind in ("function", "class")
    )
    scored = []
    for n in q.graph.nodes.values():
        if n.kind != "function":
            continue
        cc = q.call_contract(n.id)
        callers = {r["caller"] for r in cc}
        if len(callers) < min_callers:
            continue
        short = _short(n.id)
        scored.append({
            "id": n.id, "short": short,
            "callers": len(callers),
            "callsites": sum(r["callsites"] for r in cc),
            "namesakes": name_defs[short],  # defs sharing this short name
        })
    unique = sorted((s for s in scored if s["namesakes"] == 1),
                    key=lambda s: -s["callers"])[:per_bucket]
    # polymorphic: rank by how many definitions share the name (the receiver-
    # ambiguity grep can't resolve), then by caller count. This surfaces domain
    # methods (calculate/validate/…) — the regime where the graph decisively wins
    # — rather than just the highest-traffic methods.
    poly = sorted((s for s in scored if s["namesakes"] >= 2),
                  key=lambda s: (-s["namesakes"], -s["callers"]))[:per_bucket]
    for s in unique:
        s["bucket"] = "unique"
    for s in poly:
        s["bucket"] = "polymorphic"
    return unique + poly


def measure(q: Query, repo: Path, targets: list[dict]) -> list[dict]:
    rows = []
    for t in targets:
        name = t["short"]
        grep_word = _grep_count(repo, rf"\b{name}\b")
        grep_call = _grep_count(repo, rf"\b{name}\(")
        grep_def = _grep_count(repo, rf"(def|class) {name}\b")
        graph_sites = t["callsites"]        # real call-sites into THIS exact symbol
        graph_defs = t["namesakes"]         # real defs sharing this short name
        rows.append({
            **t,
            "grep_word": grep_word, "grep_call": grep_call, "grep_def": grep_def,
            # BREAKAGE: the graph hands you exactly the call-sites; grep hands you
            # every mention. reduction = grep candidates ÷ graph candidates.
            "breakage_graph": graph_sites,
            "breakage_reduction_word": round(grep_word / graph_sites, 1) if graph_sites else None,
            "breakage_reduction_call": round(grep_call / graph_sites, 1) if graph_sites else None,
            # grep's precision AS A CALL-FINDER: fraction of its hits that are real
            # call-sites. Low → the agent wastes reads rejecting mentions.
            "grep_call_precision": round(graph_sites / grep_word, 3) if grep_word else None,
            # grep's precision AS A DEFINITION-FINDER: `def NAME` is already precise,
            # so this is ≈1 — which is exactly why the graph earns NO edge on
            # "where is X defined". The honest null result.
            "grep_def_precision": round(graph_defs / grep_def, 3) if grep_def else None,
        })
    return rows


def _fmt(res: dict) -> str:
    out = ["grep-vs-graph — candidates to inspect (lower = cheaper)\n"]
    out.append(f"repo: {res['repo']}   graph: {res['graph']}   "
               f"targets: {len(res['rows'])}\n")
    out.append(f"{'symbol':34} {'bkt':11} {'sites':>5} {'grepW':>6} "
               f"{'redW':>5} {'redC':>5} {'callP':>6} {'defP':>5}")
    out.append("-" * 88)
    for r in res["rows"]:
        out.append(f"{r['short']:34.34} {r['bucket']:11} {r['breakage_graph']:>5} "
                   f"{r['grep_word']:>6} "
                   f"{str(r['breakage_reduction_word']):>5} "
                   f"{str(r['breakage_reduction_call']):>5} "
                   f"{str(r['grep_call_precision']):>6} {str(r['grep_def_precision']):>5}")
    out.append("-" * 88)
    for bucket in ("unique", "polymorphic"):
        brows = [r for r in res["rows"] if r["bucket"] == bucket]
        if not brows:
            continue
        gw = sum(r["grep_word"] for r in brows)
        gs = sum(r["breakage_graph"] for r in brows)
        gd = sum(r["grep_def"] for r in brows)
        gdefs = sum(r["namesakes"] for r in brows)
        out.append(f"{'  ' + bucket + ' breakage (grep÷graph)':34} {'':11} {gs:>5} {gw:>6} "
                   f"{round(gw / gs, 1) if gs else 'n/a':>5}")
        out.append(f"{'  ' + bucket + ' def-find precision':34} {'':24} "
                   f"grep_def={gd} vs real_defs={gdefs} → {round(gdefs / gd, 2) if gd else 'n/a'}")
    out.append("\nsites = real call-sites into the exact symbol (graph).  grepW = `\\bNAME\\b` lines.")
    out.append("redW/redC = grepW / grepC ÷ graph sites — grep's cost multiplier for BREAKAGE.")
    out.append("callP = grep's precision as a call-finder (real sites ÷ grep hits) — low = wasteful.")
    out.append("defP  = grep's precision as a def-finder (real defs ÷ `def NAME` hits) — ≈1 = no graph edge.")
    out.append("\nBREAKAGE: graph wins, hugely on polymorphic names grep can't disambiguate by receiver.")
    out.append("WHERE-DEFINED: grep's `def NAME` is already precise → the graph earns no advantage.")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", help="prebuilt graph.json")
    ap.add_argument("--build", help="package dir to extract fresh (deep) instead of --graph")
    ap.add_argument("--repo", required=True, help="git repo root to grep (the graph's source tree)")
    ap.add_argument("--min-callers", type=int, default=3)
    ap.add_argument("--per-bucket", type=int, default=5)
    ap.add_argument("--targets", help="comma-separated short names to force instead of auto-pick")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.build:
        q = Query(extract(args.build, deep=True))
    elif args.graph:
        q = Query(store.load(args.graph))
    else:
        ap.error("need --graph or --build")

    repo = Path(args.repo).resolve()
    if args.targets:
        wanted = {s.strip() for s in args.targets.split(",")}
        targets = []
        for n in q.graph.nodes.values():
            if n.kind == "function" and _short(n.id) in wanted:
                cc = q.call_contract(n.id)
                targets.append({"id": n.id, "short": _short(n.id),
                                "callers": len({r["caller"] for r in cc}),
                                "callsites": sum(r["callsites"] for r in cc),
                                "namesakes": 0, "bucket": "forced"})
    else:
        targets = _auto_targets(q, min_callers=args.min_callers, per_bucket=args.per_bucket)

    rows = measure(q, repo, targets)
    res = {"repo": str(repo), "graph": args.graph or f"build:{args.build}", "rows": rows}
    print(json.dumps(res, indent=2) if args.json else _fmt(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
