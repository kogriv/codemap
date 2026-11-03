"""R1-C61 V4 pilot: does an agent with codemap's `pack` locate a change better than without it?

A model is in the loop, so the numbers are not reproducible without the same model, harness and
seeds. That is stated in the report, and it is why this is a pilot that estimates cost and spread for
the owner's decision on a full run. It makes no usefulness claim. Design: research/pack_agent_pilot.md.

  select  --repo R                    the 20 pilot tasks (V2's selection, leak-filtered, seeded sample)
  prepare --repo R --work W           per task: the parent tree (git archive) + a repo-scoped graph
  run     --work W --out O [--codemap BIN] [--budget USD]
                                      2 arms x 2 repeats per task, headless `claude`, isolated
  report  --out O                     recall / precision / cost / turns per arm, spread between repeats

Protocol v2 (pilot 2, research/pack_agent_pilot.md §4): `context --work W --codemap BIN` computes, per task,
a `pack` over seeds taken from the message and a grep listing over the same names cut to the same length;
`run --protocol v2` gives each arm its context in the prompt and no MCP at all.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2_REF = "40839156608c6324d41290b17fb9f8d8322f4f59"   # V2's pinned bquant ref (pack_usefulness.md §1)
ROOTS = "tests,examples,scripts,research"
N_TASKS, SEED, REPEATS = 20, 61, 2
MODEL, MAX_TURNS = "sonnet", 40
ARMS = ("baseline", "pack")
BASE_TOOLS = ["Read", "Grep", "Glob"]

PROMPT = """You are in a checkout of the `bquant` Python repository, at the state just before one commit.
That commit is described by this message:

<<<
{message}
>>>

Without editing anything, identify every Python file (a path relative to the repository root) that this
commit modifies or deletes. Investigate the code as you see fit. End your reply with one line that is
only a JSON list of paths, for example: ["bquant/core/config.py", "tests/unit/test_config.py"]"""
PACK_NOTE = """

A code-graph tool is available: `mcp__codemap__pack` returns the parts of the package most relevant to
given seed symbols or files, ranked, within a token budget."""


def _v2():
    spec = importlib.util.spec_from_file_location("pack_usefulness", HERE / "pack_usefulness.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._configure("bquant", ROOTS)
    return mod


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def _leaks(message: str, truth: list[str]) -> bool:
    """A message naming a file of its own answer (path or module stem) gives the task away."""
    low = message.lower()
    for path in truth:
        stem = Path(path).stem
        if path.lower() in low or (len(stem) > 3 and re.search(rf"\b{re.escape(stem.lower())}\b", low)):
            return True
    return False


def select(repo: str) -> list[dict]:
    v2 = _v2()
    out = []
    for c in v2.select(repo, V2_REF):
        truth = sorted({c["seed"], *c["truth"]})
        msg = _git(repo, "log", "-1", "--format=%B", c["commit"]).strip()
        if _leaks(msg, truth):
            continue
        out.append({"sha": c["commit"], "parent": c["parent"], "message": msg, "truth": truth})
    rng = random.Random(SEED)
    return sorted(rng.sample(out, N_TASKS), key=lambda t: t["sha"])


def prepare(repo: str, work: Path, codemap: str) -> None:
    tasks = select(repo)
    work.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(tasks):
        d = work / f"t{i:02d}"
        tree = d / "repo"
        shutil.rmtree(d, ignore_errors=True)
        tree.mkdir(parents=True)
        arch = subprocess.run(["git", "-C", repo, "archive", t["parent"]], capture_output=True, check=True)
        subprocess.run(["tar", "x", "-C", str(tree)], input=arch.stdout, check=True)
        cons = [x for r in ROOTS.split(",") if (tree / r).is_dir() for x in ("--consumer", r)]
        rc = subprocess.run([codemap, "build", "bquant", *cons, "-o", str(d / "graph.json")],
                            cwd=tree, capture_output=True, text=True).returncode
        t["graph_ok"] = rc == 0 and (d / "graph.json").exists()
        print(f"t{i:02d} {t['sha'][:8]} truth={len(t['truth'])} graph_ok={t['graph_ok']}", flush=True)
    (work / "tasks.json").write_text(json.dumps(tasks, indent=1))


SEED_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
MAX_SEEDS, PACK_BUDGET = 8, 2000
ARMS_V2 = ("grep_ctx", "pack_ctx")
CONTEXT_HEAD = ("\n\nContext gathered automatically from the names in the message (seeds: {seeds}):\n<<<\n"
                "{context}\n>>>")


def seeds_for(message: str, graph: dict) -> list[str]:
    """Words of the message (4+ chars) that are the short name of a node of the graph, in order, at most 8."""
    names = {n["id"].rsplit(".", 1)[-1] for n in graph["nodes"]
             if n.get("kind") in ("function", "class", "module", "attribute")}
    out = []
    for w in SEED_RE.findall(message):
        if w in names and w not in out:
            out.append(w)
    return out[:MAX_SEEDS]


def grep_context(tree: Path, seeds: list[str], limit: int) -> str:
    """Files under the tree matching each seed as a word, ranked by total hits, cut to `limit` characters."""
    hits: dict[str, int] = {}
    for sd in seeds:
        p = subprocess.run(["grep", "-rcw", "--include=*.py", sd, "."], cwd=tree, capture_output=True, text=True)
        for line in p.stdout.splitlines():
            path, _, n = line.rpartition(":")
            if n.isdigit() and int(n) > 0:
                hits[path.lstrip("./")] = hits.get(path.lstrip("./"), 0) + int(n)
    lines, size = [], 0
    for path, n in sorted(hits.items(), key=lambda x: (-x[1], x[0])):
        row = f"- {path} ({n} matches)"
        if size + len(row) + 1 > limit:
            break
        lines.append(row)
        size += len(row) + 1
    return "\n".join(lines) or "(no matches)"


def context(work: Path, codemap: str) -> None:
    tasks = json.loads((work / "tasks.json").read_text())
    for i, t in enumerate(tasks):
        d = work / f"t{i:02d}"
        g = json.loads((d / "graph.json").read_text())
        seeds = seeds_for(t["message"], g)
        if seeds:
            p = subprocess.run([codemap, "pack", "--graph", str(d / "graph.json"), "--budget", str(PACK_BUDGET),
                                *[x for sd in seeds for x in ("--seed", sd)]],
                               cwd=d / "repo", capture_output=True, text=True)
            pack_md = p.stdout.strip() if p.returncode == 0 else f"(pack refused: {p.stdout.strip()[:300]})"
        else:
            pack_md = "(no name in the message is a symbol of the graph)"
        grep_md = grep_context(d / "repo", seeds, max(len(pack_md), 200)) if seeds else \
            "(no name in the message is a symbol of the graph)"
        (d / "context_pack.md").write_text(pack_md)
        (d / "context_grep.md").write_text(grep_md)
        (d / "seeds.json").write_text(json.dumps(seeds))
        print(f"t{i:02d} seeds={len(seeds)} pack_chars={len(pack_md)} grep_chars={len(grep_md)}", flush=True)


def _final_list(text: str) -> list[str] | None:
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip().strip("`")
        if line.startswith("[") and line.endswith("]"):
            try:
                val = json.loads(line)
                return [str(x).lstrip("./") for x in val] if isinstance(val, list) else None
            except ValueError:
                return None
    return None


def run(work: Path, out: Path, codemap: str, budget: float, protocol: str = "v1") -> None:
    tasks = json.loads((work / "tasks.json").read_text())
    done = {}
    if out.exists():
        for line in out.read_text().splitlines():
            r = json.loads(line)
            done[(r["task"], r["arm"], r["rep"])] = r
    arms = ARMS if protocol == "v1" else ARMS_V2
    plan = [(i, arm, rep) for i in range(len(tasks)) for arm in arms for rep in range(REPEATS)]
    random.Random(SEED).shuffle(plan)                    # arms interleaved, order fixed
    spent = sum(r.get("cost") or 0 for r in done.values())
    empty = work / "empty_mcp.json"
    empty.write_text('{"mcpServers":{}}')
    for i, arm, rep in plan:
        if (i, arm, rep) in done:
            continue
        if spent >= budget:
            print(f"budget {budget} reached at {spent:.2f}; stopping", flush=True)
            break
        t, d = tasks[i], work / f"t{i:02d}"
        tree = d / f"run-{arm}-{rep}"
        shutil.rmtree(tree, ignore_errors=True)
        shutil.copytree(d / "repo", tree)
        prompt = PROMPT.format(message=t["message"])
        tools = list(BASE_TOOLS)
        if arm in ARMS_V2:
            ctx = (d / ("context_pack.md" if arm == "pack_ctx" else "context_grep.md")).read_text()
            seeds = ", ".join(json.loads((d / "seeds.json").read_text())) or "none"
            prompt += CONTEXT_HEAD.format(seeds=seeds, context=ctx)
            cfg = empty
        elif arm == "pack":
            cfg = d / "mcp_pack.json"
            cfg.write_text(json.dumps({"mcpServers": {"codemap": {
                "command": codemap, "args": ["serve", "--mcp", "--graph", str(d / "graph.json"),
                                             "--source-root", str(tree)]}}}))
            prompt += PACK_NOTE
            tools.append("mcp__codemap__pack")
        else:
            cfg = empty
        cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--model", MODEL,
               "--max-turns", str(MAX_TURNS), "--no-session-persistence", "--setting-sources", "local",
               "--strict-mcp-config", "--mcp-config", str(cfg), "--allowedTools", *tools,
               "--disallowedTools", "Edit", "Write", "NotebookEdit", "Bash"]
        t0 = time.time()
        p = subprocess.run(cmd, cwd=tree, capture_output=True, text=True, timeout=1800)
        j, tool_calls = {"is_error": True, "result": (p.stdout + p.stderr)[-2000:]}, {}
        for line in p.stdout.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "assistant":
                for block in (ev.get("message") or {}).get("content") or []:
                    if block.get("type") == "tool_use":
                        tool_calls[block["name"]] = tool_calls.get(block["name"], 0) + 1
            elif ev.get("type") == "result":
                j = ev
        named = _final_list(j.get("result", ""))
        truth = set(t["truth"])
        hit = len(truth & set(named or []))
        rec = {"task": i, "sha": t["sha"], "arm": arm, "rep": rep, "protocol": protocol, "named": named,
               "truth": sorted(truth), "hits": hit,
               "recall": hit / len(truth), "precision": (hit / len(named)) if named else None,
               "cost": j.get("total_cost_usd"), "turns": j.get("num_turns"),
               "error": bool(j.get("is_error")) or named is None,
               "subtype": j.get("subtype"), "seconds": round(time.time() - t0, 1),
               "tool_calls": tool_calls,
               "usage": j.get("usage")}
        spent += rec["cost"] or 0
        with out.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"t{i:02d} {arm:8s} r{rep} recall={rec['recall']:.2f} named={len(named or [])} "
              f"cost={rec['cost']} turns={rec['turns']} err={rec['error']} spent={spent:.2f}", flush=True)
        shutil.rmtree(tree, ignore_errors=True)


def report(out: Path) -> str:
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    arms = ARMS_V2 if any(r.get("protocol") == "v2" for r in rows) else ARMS
    lines = ["arm       runs  errors  recall(mean)  precision(mean)  cost/run  turns(mean)"]
    for arm in arms:
        r = [x for x in rows if x["arm"] == arm]
        ok = [x for x in r if not x["error"]]
        mean = lambda xs: sum(xs) / len(xs) if xs else float("nan")
        lines.append(f"{arm:8s}  {len(r):4d}  {len(r) - len(ok):6d}  {mean([x['recall'] for x in r]):12.3f}  "
                     f"{mean([x['precision'] for x in ok if x['precision'] is not None]):15.3f}  "
                     f"{mean([x['cost'] or 0 for x in r]):8.3f}  {mean([x['turns'] or 0 for x in r]):11.1f}")
    by = {}
    for x in rows:
        by.setdefault((x["task"], x["arm"]), []).append(x["recall"])
    diffs = [abs(v[0] - v[1]) for v in by.values() if len(v) == 2]
    lines.append(f"repeat spread: mean |recall(rep0) - recall(rep1)| over {len(diffs)} task-arm pairs = "
                 f"{(sum(diffs) / len(diffs)) if diffs else float('nan'):.3f}")
    paired = []
    for i in {x["task"] for x in rows}:
        a = [x["recall"] for x in rows if x["task"] == i and x["arm"] == arms[0]]
        b = [x["recall"] for x in rows if x["task"] == i and x["arm"] == arms[1]]
        if a and b:
            paired.append(sum(b) / len(b) - sum(a) / len(a))
    if paired:
        m = sum(paired) / len(paired)
        sd = (sum((d - m) ** 2 for d in paired) / max(len(paired) - 1, 1)) ** 0.5
        lines.append(f"per-task paired difference ({arms[1]} - {arms[0]}): mean {m:+.3f}, sd {sd:.3f}, n {len(paired)}")
        lines.append(f"tasks needed to see a 0.05 difference at ~95% (2 sd/sqrt(n) < 0.05): "
                     f"{int((2 * sd / 0.05) ** 2) + 1}")
    pk = [x for x in rows if x["arm"] == "pack"]
    used = [x for x in pk if (x.get("tool_calls") or {}).get("mcp__codemap__pack")]
    lines.append(f"pack arm runs that called pack: {len(used)} of {len(pk)}")
    lines.append(f"total spent: ${sum(x['cost'] or 0 for x in rows):.2f}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select"); s.add_argument("--repo", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--repo", required=True); p.add_argument("--work", required=True)
    p.add_argument("--codemap", default="codemap")
    r = sub.add_parser("run"); r.add_argument("--work", required=True); r.add_argument("--out", required=True)
    r.add_argument("--codemap", default="codemap"); r.add_argument("--budget", type=float, default=50.0)
    r.add_argument("--protocol", choices=("v1", "v2"), default="v1")
    c = sub.add_parser("context"); c.add_argument("--work", required=True); c.add_argument("--codemap", default="codemap")
    q = sub.add_parser("report"); q.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "select":
        tasks = select(a.repo)
        print(json.dumps([{k: v for k, v in t.items() if k != "message"} | {"message_head": t["message"][:80]}
                          for t in tasks], indent=1))
    elif a.cmd == "prepare":
        prepare(a.repo, Path(a.work), a.codemap)
    elif a.cmd == "run":
        run(Path(a.work), Path(a.out), a.codemap, a.budget, a.protocol)
    elif a.cmd == "context":
        context(Path(a.work), a.codemap)
    else:
        print(report(Path(a.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
