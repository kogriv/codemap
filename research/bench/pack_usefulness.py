#!/usr/bin/env python3
"""pack usefulness, V2 + V3: does a seeded `pack` point at the files a real change touched?

R1-C61. The ground truth is **git**, not codemap's graph: for a commit that modified a
package file, the other files the same commit changed are the files a person working on
that change actually needed. The graph is built on the commit's **parent**, so no method
can see the change itself. Every method gets the same seed file and returns a ranked list
of files; we score recall@K against the co-changed set.

Methods (each excludes the seed file itself):
  pack          `build_pack(seeds=(seed_file,))`, items in rank order → files
  pack_global   `build_pack()` with no seed → files (the "importance only" baseline)
  impact        `impact(<seed module>, depth=2)` → files, by distance then path
  impact+pack   round-robin of impact and pack, impact first, duplicates dropped
  grep          files mentioning any top-level def/class name of the seed file or its
                dotted module path, ranked by match count (desc), then path
  random        the candidate files shuffled with a per-commit seed

V3 (R1-C66, research/pack_direction.md) adds four shapes of a seeded pack that also look
at who *uses* the seed (see V3_METHODS), a held-out second repository (`--package`,
`--roots`), paired bootstrap intervals in `report`, and `repro` (V2 still reproduces).

Selection rule (fixed before the run; `select` prints the list and its hash):
  non-merge commits reachable from the given ref; at least one **modified** `.py` under
  `bquant/`; between 2 and 15 modified-or-deleted `.py` files under the code roots
  (bquant/ tests/ examples/ scripts/ research/). The seed is the modified package file with
  the most changed lines (ties → path). Truth = the other modified-or-deleted `.py` files in
  the code roots. Added and renamed files are excluded (the parent has no such file) and
  counted, as are changed `.md` files (a pack can never hold a document — declared).

Usage:
  pack_usefulness.py select --repo ../bquant [--ref HEAD]
  pack_usefulness.py run    --repo ../bquant --out results.json [--ref HEAD] [--only N]
  pack_usefulness.py run    --repo ../codemap --package codemap --roots tests,research --out …
  pack_usefulness.py report --results results.json
  pack_usefulness.py repro  --old v2_results.json --new results.json
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import random
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from io import BytesIO
from pathlib import Path

# The tree under measurement. V2 fixed these for bquant; V3 (R1-C66) adds a held-out
# second repository, so they are set once from the command line (`_configure`).
ROOTS = ("bquant", "tests", "examples", "scripts", "research")
PACKAGE = ROOTS[0]
CONSUMERS = ROOTS[1:]
V2_METHODS = ("pack", "pack_global", "impact", "impact+pack", "grep", "random")
# V3 (R1-C66): a seeded pack that also looks at who *uses* the seed. Four shapes, fixed
# before the run (research/pack_direction.md §2):
#   pack_rev     PPR on the reversed usage graph, cut to what reaches the seed
#   pack_both    round-robin of pack_rev and pack, pack_rev first
#   pack_bidir   PPR on the symmetric graph, cut to seed ∪ ancestors ∪ descendants
#   pack_sym     PPR on the symmetric graph, cut to the seed's weak component
V3_METHODS = ("pack_rev", "pack_both", "pack_bidir", "pack_sym")
METHODS = V2_METHODS + V3_METHODS
KS = (5, 10, 20)


def _configure(package: str, roots: str | None) -> None:
    """Point the harness at another tree. With no arguments it is V2's bquant layout."""
    global ROOTS, PACKAGE, CONSUMERS
    rest = tuple(r for r in (roots.split(",") if roots else ROOTS[1:]) if r and r != package)
    PACKAGE, ROOTS, CONSUMERS = package, (package, *rest), rest


def _git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], check=True,
                          capture_output=True, text=True).stdout


def _in_roots(path: str) -> bool:
    return path.split("/", 1)[0] in ROOTS


# -- selection -------------------------------------------------------------------------

def select(repo: str, ref: str = "HEAD") -> list[dict]:
    """Every commit the rule admits, oldest first. Pure function of the repository."""
    out = []
    hashes = _git(repo, "rev-list", "--no-merges", "--reverse", ref).split()
    for h in hashes:
        status = _git(repo, "show", "--format=", "--name-status", "-M", h).splitlines()
        numstat = _git(repo, "show", "--format=", "--numstat", "-M", h).splitlines()
        lines_changed = {}
        for row in numstat:
            parts = row.split("\t")
            if len(parts) == 3 and parts[0] != "-":
                lines_changed[parts[2]] = int(parts[0]) + int(parts[1])
        mod_pkg, truth_py, added, renamed, md = [], [], [], [], []
        for row in status:
            parts = row.split("\t")
            st, path = parts[0][0], parts[-1]
            if st == "R":
                renamed.append(path)
                continue
            if path.endswith(".md"):
                md.append(path)
                continue
            if not (path.endswith(".py") and _in_roots(path)):
                continue
            if st == "A":
                added.append(path)
            elif st in "MD":
                truth_py.append(path)
                if st == "M" and path.startswith(PACKAGE + "/"):
                    mod_pkg.append(path)
        if not mod_pkg or not 2 <= len(truth_py) <= 15:
            continue
        seed = sorted(mod_pkg, key=lambda p: (-lines_changed.get(p, 0), p))[0]
        out.append({"commit": h, "parent": _git(repo, "rev-parse", f"{h}^").strip(),
                    "seed": seed, "truth": sorted(p for p in truth_py if p != seed),
                    "excluded": {"added_py": len(added), "renamed": len(renamed),
                                 "md": len(md)}})
    return out


def selection_hash(sel: list[dict]) -> str:
    return hashlib.sha256("\n".join(c["commit"] for c in sel).encode()).hexdigest()


# -- one commit ------------------------------------------------------------------------

def _extract(repo: str, rev: str, dest: Path) -> None:
    present = set(_git(repo, "ls-tree", "--name-only", rev).split())  # an early parent may lack a root
    data = subprocess.run(["git", "-C", repo, "archive", rev, *[r for r in ROOTS if r in present]],
                          check=True, capture_output=True).stdout
    with tarfile.open(fileobj=BytesIO(data)) as tf:
        tf.extractall(dest, filter="data")


def _build(tree: Path, out: Path) -> tuple[bool, str]:
    args = [sys.executable, "-m", "codemap.cli", "build", str(tree / PACKAGE), "-o", str(out)]
    for c in CONSUMERS:
        if (tree / c).is_dir():
            args += ["--consumer", str(tree / c)]
    r = subprocess.run(args, capture_output=True, text=True)
    return r.returncode == 0, r.stderr[-400:]


def _files_in_order(ids, graph) -> list[str]:
    seen, out = set(), []
    for i in ids:
        n = graph.nodes.get(i)
        f = n.file if n else None
        if f and f not in seen:
            seen.add(f)
            out.append(f)
    return out


def _grep(tree: Path, seed: str, candidates: list[str]) -> list[str]:
    try:
        mod = ast.parse((tree / seed).read_text(encoding="utf-8", errors="replace"))
        names = sorted({n.name for n in mod.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))})
    except SyntaxError:
        names = []
    dotted = seed[:-3].replace("/", ".").removesuffix(".__init__")
    pats = [re.compile(rf"\b{re.escape(n)}\b") for n in names] + [re.compile(re.escape(dotted))]
    scored = []
    for f in candidates:
        text = (tree / f).read_text(encoding="utf-8", errors="replace")
        hits = sum(len(p.findall(text)) for p in pats)
        if hits:
            scored.append((-hits, f))
    return [f for _, f in sorted(scored)]


def _round_robin(a: list[str], b: list[str]) -> list[str]:
    out, seen = [], set()
    for i in range(max(len(a), len(b))):
        for lst in (a, b):
            if i < len(lst) and lst[i] not in seen:
                seen.add(lst[i])
                out.append(lst[i])
    return out


def _ranked_ids(pr: dict, keep: set[str]) -> list[str]:
    """Rank desc, id tiebreak, rounded like `Query.rank` — the order `build_pack` uses."""
    r = {n: round(v, 8) for n, v in pr.items() if n in keep}
    return sorted(r, key=lambda n: (-r[n], n))


def _directional(q, seed_ids: list[str]) -> dict[str, list[str]]:
    """The V3 shapes, as ranked node ids. Built from the same rank graph and the same
    PageRank as `pack`, so the only thing that differs is the direction of the walk."""
    import networkx as nx
    from codemap.query import _pagerank
    g = q._rank_graph()
    seeds = [s for s in seed_ids if s in g]
    pers = {n: (1.0 if n in seeds else 0.0) for n in g}
    down = set(seeds).union(*(nx.descendants(g, s) for s in seeds))
    up = set(seeds).union(*(nx.ancestors(g, s) for s in seeds))
    sym = nx.DiGraph(g)
    sym.add_edges_from((b, a) for a, b in g.edges)
    weak = set().union(*(nx.node_connected_component(g.to_undirected(as_view=True), s)
                         for s in seeds))
    pr_sym = _pagerank(sym, pers)
    return {"pack_rev": _ranked_ids(_pagerank(g.reverse(copy=True), pers), up),
            "pack_bidir": _ranked_ids(pr_sym, up | down),
            "pack_sym": _ranked_ids(pr_sym, weak)}


def evaluate(repo: str, c: dict, work: Path) -> dict:
    from codemap.query import Query
    from codemap.serve.pack import build_pack
    from codemap.store import load

    tree = work / c["parent"][:12]
    tree.mkdir(parents=True, exist_ok=True)
    _extract(repo, c["parent"], tree)
    gpath = work / f"{c['parent'][:12]}.json"
    t0 = time.monotonic()
    ok, err = _build(tree, gpath)
    rec = {"commit": c["commit"], "seed": c["seed"], "truth": c["truth"],
           "excluded": c["excluded"], "build_s": round(time.monotonic() - t0, 1)}
    if not ok:
        rec["status"] = "build_failed"
        rec["error"] = err
        return rec
    graph = load(gpath)
    q = Query(graph)
    seed = c["seed"]
    candidates = sorted(str(p.relative_to(tree)) for r in ROOTS if (tree / r).is_dir()
                        for p in (tree / r).rglob("*.py"))
    candidates = [f for f in candidates if f != seed]
    rec["candidates"] = len(candidates)
    rec["truth_in_parent"] = [t for t in c["truth"] if (tree / t).is_file()]

    p = build_pack(q, budget=10 ** 9, seeds=(seed,))
    if "error" in p:
        rec["status"] = "seed_unresolved"
        rec["seeds"] = p["seeds"]
        return rec
    lists = {}
    lists["pack"] = [f for f in _files_in_order([i["id"] for i in p["items"]], graph) if f != seed]
    pg = build_pack(q, budget=10 ** 9)
    lists["pack_global"] = [f for f in _files_in_order([i["id"] for i in pg["items"]], graph)
                            if f != seed]
    mod_ids = [nid for nid, n in graph.nodes.items() if n.kind == "module" and n.file == seed]
    refs = []
    for mid in mod_ids:
        refs += q.impact(mid, depth=2)["refs"]
    refs.sort(key=lambda r: (r["distance"], graph.nodes[r["source"]].file or "", r["source"]))
    lists["impact"] = [f for f in _files_in_order([r["source"] for r in refs], graph) if f != seed]
    lists["impact+pack"] = _round_robin(lists["impact"], lists["pack"])
    lists["grep"] = _grep(tree, seed, candidates)
    rnd = list(candidates)
    random.Random(int(c["commit"][:16], 16)).shuffle(rnd)
    lists["random"] = rnd
    seed_ids = p["seeds"]["requested"][0]["matched"]
    for m, ids in _directional(q, seed_ids).items():
        lists[m] = [f for f in _files_in_order(ids, graph) if f != seed]
    lists["pack_both"] = _round_robin(lists["pack_rev"], lists["pack"])

    truth = set(rec["truth_in_parent"])
    rec["status"] = "ok"
    rec["unreachable_from_seeds"] = p["unreachable_from_seeds"]
    rec["scores"] = {}
    for m in METHODS:
        lst = lists[m]
        rec["scores"][m] = {"returned": len(lst),
                            **{f"recall@{k}": (round(len(truth & set(lst[:k])) / len(truth), 4)
                                               if truth else None) for k in KS},
                            "first_hit_rank": next((i + 1 for i, f in enumerate(lst) if f in truth),
                                                   None)}
    tests_truth = {t for t in truth if t.startswith("tests/")}
    rec["tests_truth"] = len(tests_truth)
    rec["tests_recall@10"] = {m: (round(len(tests_truth & set(lists[m][:10])) / len(tests_truth), 4)
                                  if tests_truth else None) for m in METHODS}
    rec["top10"] = {m: lists[m][:10] for m in METHODS}
    return rec


# -- report ----------------------------------------------------------------------------

def paired_ci(results: list[dict], a: str, b: str, *, k: int = 10, n: int = 10_000,
              seed: int = 0) -> tuple[float, float, float]:
    """Mean of recall@k(a) − recall@k(b) over scored commits, with a 95 % percentile
    bootstrap interval resampling commits (paired). V2 had no interval and said so."""
    ok = [r for r in results if r["status"] == "ok" and r["truth_in_parent"]]
    d = [r["scores"][a][f"recall@{k}"] - r["scores"][b][f"recall@{k}"] for r in ok]
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(n))
    return sum(d) / len(d), means[int(0.025 * n)], means[int(0.975 * n) - 1]


V3_PAIRS = (("pack_rev", "pack"), ("pack_both", "pack"), ("pack_bidir", "pack"),
            ("pack_sym", "pack"), ("pack_bidir", "pack_sym"))


def report(results: list[dict]) -> str:
    ok = [r for r in results if r["status"] == "ok" and r["truth_in_parent"]]
    methods = [m for m in METHODS if ok and m in ok[0]["scores"]]
    lines = [f"commits: {len(results)} · scored: {len(ok)} · "
             f"build_failed: {sum(r['status'] == 'build_failed' for r in results)} · "
             f"seed_unresolved: {sum(r['status'] == 'seed_unresolved' for r in results)} · "
             f"no truth in parent: {sum(r['status'] == 'ok' and not r['truth_in_parent'] for r in results)}",
             "", "| method | " + " | ".join(f"recall@{k}" for k in KS) + " | hit@10 | tests recall@10 |",
             "|---|" + "---|" * (len(KS) + 2)]
    for m in methods:
        means = [sum(r["scores"][m][f"recall@{k}"] for r in ok) / len(ok) for k in KS]
        hit10 = sum(1 for r in ok if (r["scores"][m]["first_hit_rank"] or 99) <= 10) / len(ok)
        tr = [r["tests_recall@10"][m] for r in ok if r["tests_recall@10"][m] is not None]
        lines.append(f"| {m} | " + " | ".join(f"{x:.3f}" for x in means)
                     + f" | {hit10:.3f} | {(sum(tr) / len(tr) if tr else float('nan')):.3f} (n={len(tr)}) |")
    lines.append("")
    for a, b in (("pack", "grep"), ("pack", "impact"), ("pack", "pack_global"),
                 ("impact+pack", "impact")):
        w = sum(1 for r in ok if r["scores"][a]["recall@10"] > r["scores"][b]["recall@10"])
        l = sum(1 for r in ok if r["scores"][a]["recall@10"] < r["scores"][b]["recall@10"])
        lines.append(f"{a} vs {b} at recall@10: {a} better on {w}, worse on {l}, tied on {len(ok) - w - l}")
    if "pack_rev" in methods:
        best = max(V3_METHODS, key=lambda m: (sum(r["scores"][m]["recall@10"] for r in ok),
                                              -V3_METHODS.index(m)))
        lines += ["", f"best V3 shape by mean recall@10 (ties → listed order): {best}",
                  "", "paired recall@10 difference, mean [95 % bootstrap CI, commits resampled]:"]
        for a, b in (*V3_PAIRS, (best, "grep"), (best, "impact+pack"), (best, "impact"),
                     ("impact+pack", "grep")):
            mean, lo, hi = paired_ci(results, a, b)
            lines.append(f"  {a} − {b}: {mean:+.3f} [{lo:+.3f}, {hi:+.3f}]")
        mean, lo, hi = paired_ci(results, best, "pack", k=5)
        lines.append(f"  {best} − pack at recall@5: {mean:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    return "\n".join(lines)


def repro(old: list[dict], new: list[dict]) -> list[str]:
    """Control C6: V2's six methods score byte-identically on a re-run. Returns the
    commits where any V2 field differs (empty = reproduced)."""
    by = {r["commit"]: r for r in old}
    bad = []
    for r in new:
        o = by.get(r["commit"])
        if o is None or o["status"] != r["status"]:
            bad.append(r["commit"])
            continue
        if r["status"] != "ok":
            continue
        if any(o["scores"][m] != r["scores"][m] or o["top10"][m] != r["top10"][m]
               or o["tests_recall@10"][m] != r["tests_recall@10"][m] for m in V2_METHODS):
            bad.append(r["commit"])
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select"); s.add_argument("--repo", required=True); s.add_argument("--ref", default="HEAD")
    s.add_argument("--json", action="store_true")
    r = sub.add_parser("run"); r.add_argument("--repo", required=True); r.add_argument("--ref", default="HEAD")
    r.add_argument("--out", required=True); r.add_argument("--only", type=int)
    r.add_argument("--work", help="scratch directory (default: a temp dir)")
    for sp in (s, r):
        sp.add_argument("--package", default="bquant", help="the package root (V2: bquant)")
        sp.add_argument("--roots", help="comma-separated consumer roots (V2: tests,examples,scripts,research)")
    p = sub.add_parser("report"); p.add_argument("--results", required=True)
    c6 = sub.add_parser("repro", help="control C6: V2 methods reproduce byte-identically")
    c6.add_argument("--old", required=True); c6.add_argument("--new", required=True)
    a = ap.parse_args(argv)
    if a.cmd in ("select", "run"):
        _configure(a.package, a.roots)
    if a.cmd == "select":
        sel = select(a.repo, a.ref)
        if a.json:
            print(json.dumps(sel, indent=1))
        else:
            for c in sel:
                print(c["commit"][:12], c["seed"], len(c["truth"]))
        print(f"# {len(sel)} commits · selection sha256 {selection_hash(sel)}", file=sys.stderr)
        return 0
    if a.cmd == "run":
        sel = select(a.repo, a.ref)
        if a.only:
            sel = sel[: a.only]
        work = Path(a.work) if a.work else Path(tempfile.mkdtemp(prefix="packuse-"))
        results = []
        for i, c in enumerate(sel, 1):
            results.append(evaluate(a.repo, c, work))
            print(f"[{i}/{len(sel)}] {c['commit'][:12]} {results[-1]['status']} "
                  f"{results[-1].get('build_s')}s", file=sys.stderr, flush=True)
            Path(a.out).write_text(json.dumps({"selection_sha256": selection_hash(sel),
                                               "package": PACKAGE, "roots": list(ROOTS),
                                               "results": results}, indent=1))
        return 0
    if a.cmd == "repro":
        old = json.loads(Path(a.old).read_text())["results"]
        new = json.loads(Path(a.new).read_text())["results"]
        bad = repro(old, new)
        print(f"C6: {len(new) - len(bad)} / {len(new)} commits reproduce V2 byte-identically"
              + (f"; differ: {', '.join(b[:12] for b in bad)}" if bad else ""))
        return 1 if bad else 0
    data = json.loads(Path(a.results).read_text())
    print(report(data["results"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
