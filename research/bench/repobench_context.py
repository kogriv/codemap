"""R1-C93 — does codemap's rank put the definition a completion needs first? RepoBench, no model.

Pre-registration: ``research/repobench_context.md`` (c2f66d6). Two subcommands:

    run     --work DIR --codemap BIN --out results.jsonl [--jobs N]
    report  --results results.jsonl [--compare other.jsonl]

``run`` reads the pinned dataset revision through ``huggingface_hub`` (cache), clones repositories into
``DIR/repos`` and writes one JSON line per drawn row: its attrition stage, or its per-ranker gold position.
No code text is written out. Everything is seeded; the report is a pure function of the results file.
"""

from __future__ import annotations

import argparse
import ast
import collections
import json
import os
import random
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

DATASET = "tianyang/repobench_python_v1.1"
REVISION = "8a7cf0c8942cc1aa066bf261839650ac55a2ff79"
SPLITS = {"cross_file_first": 2, "cross_file_random": 1}  # split -> shards
SEED = 93
PER_SPLIT = 300
MAX_REPOS = 600
PER_REPO = 3
MAX_PY = 2000
BEFORE = "2024-01-01"
TAIL = 300
RANKERS = ("graph", "global", "random", "jaccard", "unused", "recency", "unused+graph")
WORD = re.compile(r"\w+")


# -- dataset -----------------------------------------------------------------------------------

def load_rows():
    from huggingface_hub import hf_hub_download, list_repo_files
    import pyarrow.parquet as pq
    files = list_repo_files(DATASET, repo_type="dataset", revision=REVISION)
    rows = []
    for split, n in SPLITS.items():
        shards = sorted(f for f in files if f.startswith(f"data/{split}-") and f.endswith(".parquet"))
        assert len(shards) == n, (split, shards)
        for s, f in enumerate(shards):
            t = pq.read_table(hf_hub_download(DATASET, f, repo_type="dataset", revision=REVISION))
            for i, r in enumerate(t.to_pylist()):
                rows.append({"split": split, "shard": s, "index": i, **r})
    return rows


def draw(rows, max_repos=MAX_REPOS):
    """Repository order and per-repository row picks, fixed before any eligibility check."""
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        by[r["repo_name"]][r["split"]].append(r)
    rng = random.Random(SEED)
    repos = sorted(by)
    rng.shuffle(repos)
    plan = []
    for name in repos[:max_repos]:
        picks = []
        for split in SPLITS:
            cand = by[name].get(split, [])
            picks += rng.sample(cand, min(PER_REPO, len(cand)))
        plan.append((name, picks))
    return plan


# -- per repository ----------------------------------------------------------------------------

def sh(args, cwd=None, timeout=900, env=None):
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def package_root(repo: Path, rel: str):
    """Topmost D such that D and every directory down to the file hold __init__.py (A3)."""
    parts = rel.split("/")[:-1]
    top = None
    for k in range(len(parts), 0, -1):
        if (repo.joinpath(*parts[:k]) / "__init__.py").is_file():
            top = k
        else:
            break
    return None if top is None else "/".join(parts[:top])


def module_of(rel_from_parent: str) -> str:
    mod = rel_from_parent[:-3].replace("/", ".")
    return mod[: -len(".__init__")] if mod.endswith(".__init__") else mod


def truncate(body: str, row):
    """Lines before next_line (cursor after the matched cropped_code tail), or None (A2)."""
    tail = row["cropped_code"][-TAIL:]
    nxt = row["next_line"]
    p = body.find(tail)
    if p < 0 or nxt not in body:
        return None
    lines = body.split("\n")
    k = body[: p + len(tail)].count("\n")
    for j in range(k, len(lines)):
        if lines[j] == nxt or lines[j].rstrip() == nxt.rstrip():
            return lines[:j]
    return None


def parses(text: str) -> bool:
    try:
        ast.parse(text)
        return True
    except (SyntaxError, ValueError):
        return False


def build(cm: str, pkg: Path, out: Path):
    env = {**os.environ, "PYTHONHASHSEED": "0"}
    rc, _, err = sh([cm, "build", str(pkg), "-o", str(out)], env=env)
    return rc, err.strip()[-200:]


def enclosing(graph, file_rel: str, line: int, module_id: str) -> str:
    best = None
    for n in graph.nodes.values():
        if n.file == file_rel and n.kind in ("function", "class") and n.lineno and n.endlineno \
                and n.lineno <= line <= n.endlineno:
            if best is None or n.lineno > best.lineno:
                best = n
    return best.id if best else module_id


def cand_node(graph, c, parent_rel: str, pkg_rel: str):
    path = c["path"]
    if not (path == pkg_rel or path.startswith(pkg_rel + "/")) or not path.endswith(".py"):
        return None
    mod = module_of(path[len(parent_rel) + 1:] if parent_rel else path)
    for nid in (f"{mod}.{c['identifier']}", mod if mod.rsplit(".", 1)[-1] == c["identifier"] else None):
        if nid and nid in graph.nodes:
            return nid
    return None


def gold_position(scores, gold, key):
    """1-based position of gold after sorting by score desc, ties by the row's seeded shuffle."""
    rng = random.Random(key)
    order = list(range(len(scores)))
    rng.shuffle(order)
    order.sort(key=lambda i: -scores[i])  # stable: the shuffle breaks ties
    return order.index(gold) + 1


def lexical(row):
    code = row["cropped_code"]
    toks = set(WORD.findall(code))
    out = {"jaccard": [], "unused": [], "recency": []}
    for c in row["context"]:
        st = set(WORD.findall(c["snippet"]))
        out["jaccard"].append(len(toks & st) / len(toks | st) if toks | st else 0.0)
        last = -1
        for m in re.finditer(rf"\b{re.escape(c['identifier'])}\b", code):
            last = m.start()
        out["unused"].append(1.0 if last < 0 else 0.0)
        out["recency"].append(float(last))
    return out


def score_graph(graph, seed, module_id):
    from codemap.query import Query
    q = Query(graph)
    local = q.rank(seeds=[seed], direction="both")
    glob = q.rank()
    inside = {nid for nid in graph.nodes if nid == module_id or nid.startswith(module_id + ".")}
    return q, local, glob, inside


def run_repo(job):
    name, picks, work, cm = job
    repo = Path(work) / "repos" / name.replace("/", "__")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    base = {"repo": name}
    recs = [dict(base, split=r["split"], shard=r["shard"], index=r["index"]) for r in picks]

    def drop(stage, **kw):
        return [dict(r, stage=stage, **kw) for r in recs]

    if not (repo / ".git").is_dir():
        rc, _, err = sh(["git", "clone", "-q", "--filter=blob:none", f"https://github.com/{name}.git",
                         str(repo)], env=env)
        if rc:
            return drop("A1", why=(err.strip().splitlines() or ["?"])[-1][:80])
    rc, commit, _ = sh(["git", "rev-list", "-1", f"--before={BEFORE}", "HEAD"], cwd=repo)
    commit = commit.strip()
    if not commit:
        return drop("A1", why="no commit before " + BEFORE)
    sh(["git", "checkout", "-q", "-f", commit], cwd=repo)
    sh(["git", "clean", "-qfdx"], cwd=repo)
    rc, ls, _ = sh(["git", "ls-files", "*.py"], cwd=repo)
    if len(ls.split()) > MAX_PY:
        return drop("size", py_files=len(ls.split()))
    base["commit"] = commit
    from codemap import store
    out = []
    untrunc = {}  # pkg -> graph built on the untouched tree (C1)
    for rec, row in zip(recs, picks):
        rec["commit"] = commit
        key = f"{row['split']}:{row['shard']}:{row['index']}"
        f = repo / row["file_path"]
        body = f.read_text(errors="replace") if f.is_file() else ""
        kept = truncate(body, row) if body else None
        if kept is None:
            out.append(dict(rec, stage="A2"))
            continue
        pkg_rel = package_root(repo, row["file_path"])
        if pkg_rel is None:
            out.append(dict(rec, stage="A3"))
            continue
        ctx = row["context"]
        if len(ctx) < 2:
            out.append(dict(rec, stage="A4"))
            continue
        text = "\n".join(kept) + "\n"
        filled = False
        if not parses(text):
            indent = row["next_line"][: len(row["next_line"]) - len(row["next_line"].lstrip())]
            text += indent + "pass\n"
            filled = True
            if not parses(text):
                out.append(dict(rec, stage="A5"))
                continue
        parent_rel = pkg_rel.rsplit("/", 1)[0] if "/" in pkg_rel else ""
        file_rel = row["file_path"][len(parent_rel) + 1:] if parent_rel else row["file_path"]
        module_id = module_of(file_rel)
        last_line = len(kept)
        gpath = Path(work) / "graphs" / f"{key.replace(':', '_')}.json"
        gpath.parent.mkdir(exist_ok=True)
        try:
            f.write_text(text)
            rc, err = build(cm, repo / pkg_rel, gpath)
        finally:
            sh(["git", "checkout", "-q", "--", row["file_path"]], cwd=repo)
        if rc:
            out.append(dict(rec, stage="A6", why=err))
            continue
        graph = store.load(gpath)
        seed = enclosing(graph, file_rel, last_line, module_id)
        q, local, glob, inside = score_graph(graph, seed, module_id)
        nodes = [cand_node(graph, c, parent_rel, pkg_rel) for c in ctx]
        gold = row["gold_snippet_index"]
        lex = lexical(row)
        scores = {
            "graph": [local.get(n, -1.0) if n else -1.0 for n in nodes],
            "global": [glob.get(n, -1.0) if n else -1.0 for n in nodes],
            "random": [0.0] * len(ctx),
            **lex,
        }
        scores["unused+graph"] = [u * 2.0 + (g if g >= 0 else -1.0) / 2.0
                                  for u, g in zip(lex["unused"], scores["graph"])]
        pos = {k: gold_position(v, gold, key) for k, v in scores.items()}
        # pack's own question: gold among all nodes outside the truncated module.
        gnode = nodes[gold]
        allpos = None
        if gnode:
            order = sorted((n for n in local if n not in inside), key=lambda n: (-local[n], n))
            allpos = order.index(gnode) + 1 if gnode in order else None
        # C1: the same row on the untruncated tree.
        if pkg_rel not in untrunc:
            up = Path(work) / "graphs" / f"{name.replace('/', '__')}__{pkg_rel.replace('/', '_')}.full.json"
            rc, _ = build(cm, repo / pkg_rel, up)
            untrunc[pkg_rel] = store.load(up) if rc == 0 else None
        c1 = None
        ug = untrunc[pkg_rel]
        if ug is not None:
            useed = enclosing(ug, file_rel, last_line + 1, module_id)
            from codemap.query import Query
            ul = Query(ug).rank(seeds=[useed], direction="both")
            unodes = [cand_node(ug, c, parent_rel, pkg_rel) for c in ctx]
            c1 = gold_position([ul.get(n, -1.0) if n else -1.0 for n in unodes], gold, key)
        gpath.unlink()
        out.append(dict(rec, stage="ok", k=len(ctx), pass_filled=filled, seed_kind=graph.nodes[seed].kind if seed in graph.nodes else "missing",
                        gold_has_node=gnode is not None, seed_effective=local != glob, pos=pos, all_nodes_pos=allpos,
                        n_nodes=len(graph.nodes), c1_pos=c1))
    return out


def cmd_run(a):
    rows = load_rows()
    plan = draw(rows, a.max_repos)
    work = Path(a.work)
    (work / "repos").mkdir(parents=True, exist_ok=True)
    done = {s: 0 for s in SPLITS}
    results = []
    batch = max(a.jobs * 2, 8)
    i = 0
    with ProcessPoolExecutor(a.jobs) as ex:
        while i < len(plan) and min(done.values()) < PER_SPLIT:
            chunk = plan[i:i + batch]
            for order, recs in zip(range(i, i + len(chunk)),
                                   ex.map(run_repo, [(n, p, str(work), a.codemap) for n, p in chunk])):
                for r in recs:
                    r["repo_order"] = order
                    results.append(r)
                    if r["stage"] == "ok":
                        done[r["split"]] += 1
            i += len(chunk)
            print(f"[run] repos {i}, eligible {done}", file=sys.stderr, flush=True)
    results.sort(key=lambda r: (r["repo_order"], r["split"], r["shard"], r["index"]))
    with open(a.out, "w") as fh:
        for r in results:
            fh.write(json.dumps(r, sort_keys=True) + "\n")


# -- report ------------------------------------------------------------------------------------

def selected(results):
    """Per split, eligible rows in repository order up to PER_SPLIT; the drawn rows of those repos."""
    sel, drawn = {}, {}
    for split in SPLITS:
        rs = [r for r in results if r["split"] == split]
        ok, cut = [], None
        for r in rs:
            if r["stage"] == "ok" and len(ok) < PER_SPLIT:
                ok.append(r)
                cut = r["repo_order"]
        sel[split] = ok
        drawn[split] = [r for r in rs if cut is not None and r["repo_order"] <= cut]
    return sel, drawn


def boot(rows, stat, n=10000):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["repo"]].append(r)
    groups = list(by.values())
    rng = random.Random(SEED)
    vals = []
    for _ in range(n):
        pick = [x for _ in groups for x in rng.choice(groups)]
        vals.append(stat(pick))
    vals.sort()
    return vals[int(0.025 * n)], vals[int(0.975 * n) - 1]


def acc(rows, ranker, k=1):
    return sum(r["pos"][ranker] <= k for r in rows) / len(rows) if rows else float("nan")


def cmd_report(a):
    results = [json.loads(x) for x in open(a.results)]
    if a.compare:
        other = [json.loads(x) for x in open(a.compare)]
        strip = lambda rs: [{k: v for k, v in r.items()} for r in rs]  # noqa: E731
        print("C2 identical:", strip(results) == strip(other))
    sel, drawn = selected(results)
    for split in SPLITS:
        rows, d = sel[split], drawn[split]
        print(f"\n## {split}: {len(rows)} eligible of {len(d)} drawn "
              f"({len(rows) / max(len(d), 1):.0%}), repos {len({r['repo'] for r in rows})}")
        att = collections.Counter(r["stage"] for r in d)
        print("attrition:", dict(sorted(att.items())))
        print(f"gold has a node: {sum(r['gold_has_node'] for r in rows)}/{len(rows)}; "
              f"pass-filled: {sum(r['pass_filled'] for r in rows)}; "
              f"seed module-level: {sum(r['seed_kind'] == 'module' for r in rows)}; "
              f"seed had no effect (rank fell back to global): {sum(not r['seed_effective'] for r in rows)}; "
              f"mean candidates: {sum(r['k'] for r in rows) / max(len(rows), 1):.1f}")
        print(f"random expected acc@1: {sum(1 / r['k'] for r in rows) / max(len(rows), 1):.3f}")
        print("| ranker | acc@1 [95%] | acc@3 | graph − ranker, acc@1 [95%] |")
        print("|---|---|---|---|")
        for rk in RANKERS:
            lo, hi = boot(rows, lambda p, rk=rk: acc(p, rk))
            dlo, dhi = boot(rows, lambda p, rk=rk: acc(p, "graph") - acc(p, rk))
            print(f"| {rk} | {acc(rows, rk):.3f} [{lo:.3f}, {hi:.3f}] | {acc(rows, rk, 3):.3f} | "
                  f"{acc(rows, 'graph') - acc(rows, rk):+.3f} [{dlo:+.3f}, {dhi:+.3f}] |")
        ug = [r for r in rows if r["c1_pos"] is not None]
        lo, hi = boot(ug, lambda p: sum(r["c1_pos"] == 1 for r in p) / len(p) - acc(p, "graph"))
        print(f"C1 untruncated graph acc@1: {sum(r['c1_pos'] == 1 for r in ug) / max(len(ug), 1):.3f} "
              f"vs truncated {acc(ug, 'graph'):.3f} on {len(ug)} rows; Δ [{lo:+.3f}, {hi:+.3f}]")
        lo, hi = boot(rows, lambda p: acc(p, "unused+graph") - acc(p, "unused"))
        print(f"P8 unused+graph − unused: {acc(rows, 'unused+graph') - acc(rows, 'unused'):+.3f} "
              f"[{lo:+.3f}, {hi:+.3f}]")
        ap = [r["all_nodes_pos"] for r in rows]
        print(f"all nodes: recall@10 {sum(1 for x in ap if x and x <= 10) / len(ap):.3f}, "
              f"recall@20 {sum(1 for x in ap if x and x <= 20) / len(ap):.3f}")


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--work", required=True)
    r.add_argument("--codemap", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--jobs", type=int, default=4)
    r.add_argument("--max-repos", type=int, default=MAX_REPOS, help="smoke runs only")
    s = sub.add_parser("report")
    s.add_argument("--results", required=True)
    s.add_argument("--compare")
    a = p.parse_args(argv)
    {"run": cmd_run, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
