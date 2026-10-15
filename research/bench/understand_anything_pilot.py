"""Score the Understand-Anything LLM pilot (card §3): usage by agent, and the graph against truth.

    python research/bench/understand_anything_pilot.py --plugin PLUGIN --proj PROJ \\
        --stream run.jsonl --out pilot_results.json [--seconds N]

``--stream`` is the ``claude -p --output-format stream-json --verbose`` log of the run; ``--proj``
the slice repo the run wrote ``.ua/knowledge-graph.json`` into.

Usage is attributed by ``parent_tool_use_id``: events without one are the orchestrator, the rest
belong to the subagent dispatched by that tool call. Cost per agent is the run's
``total_cost_usd`` split in proportion to a token weight. The weight uses Sonnet-family price
*ratios* (input 1, 5-minute cache write 1.25, 1-hour cache write 2, cache read 0.1, output 5). That is
an assumption about ratios, not prices, and the split is labelled as such.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

W = {"input_tokens": 1.0, "cache_read_input_tokens": 0.1, "output_tokens": 5.0,
     "cw_5m": 1.25, "cw_1h": 2.0}


def _usage(stream: Path) -> dict:
    agents: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    names: dict[str, str] = {}
    seen: set = set()
    result = None
    for line in stream.read_text().splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result":
            result = ev
            continue
        if ev.get("type") != "assistant":
            continue
        msg = ev.get("message") or {}
        for block in msg.get("content") or []:
            if block.get("type") == "tool_use" and block.get("name") in ("Task", "Agent"):
                inp = block.get("input") or {}
                names[block["id"]] = (inp.get("subagent_type") or "?") + ": " + \
                    (inp.get("description") or "")[:60]
        key = msg.get("id")
        if not key or key in seen:
            continue
        seen.add(key)
        u = msg.get("usage") or {}
        who = ev.get("parent_tool_use_id") or "orchestrator"
        a = agents[who]
        a["messages"] += 1
        for k in ("input_tokens", "cache_read_input_tokens", "output_tokens"):
            a[k] += u.get(k) or 0
        cc = u.get("cache_creation") or {}
        a["cw_5m"] += cc.get("ephemeral_5m_input_tokens") or 0
        a["cw_1h"] += cc.get("ephemeral_1h_input_tokens") or 0
        if not cc:
            a["cw_5m"] += u.get("cache_creation_input_tokens") or 0
    total = (result or {}).get("total_cost_usd")
    weight = {k: sum(W[f] * v[f] for f in W) for k, v in agents.items()}
    wsum = sum(weight.values()) or 1
    rows = {}
    for k, v in agents.items():
        row = {f: int(v[f]) for f in ("messages", *W)}
        row["input_all"] = int(v["input_tokens"] + v["cache_read_input_tokens"] + v["cw_5m"] + v["cw_1h"])
        row["cost_share_usd"] = round(total * weight[k] / wsum, 4) if total is not None else None
        rows[names.get(k, k)] = row
    res = {k: (result or {}).get(k) for k in ("total_cost_usd", "num_turns", "duration_ms",
                                               "is_error", "subtype", "modelUsage")}
    return {"result": res, "agents": rows}


def _graph(proj: Path) -> dict:
    for d in (".ua", ".understand-anything"):
        g = proj / d / "knowledge-graph.json"
        if g.exists():
            return json.loads(g.read_text())
    return {}


def _file_of(node_id: str) -> str | None:
    # ids look like `file:<path>`, `function:<path>:<name>`, `class:<path>:<name>`
    parts = node_id.split(":")
    return parts[1] if len(parts) >= 2 and parts[1].endswith(".py") else None


def _import_truth(plugin: Path, proj: Path) -> set[tuple[str, str]]:
    skill = plugin / "skills" / "understand"
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        subprocess.run(["node", str(skill / "scan-project.mjs"), str(proj), str(t / "s.json")],
                       check=True, capture_output=True)
        s = json.loads((t / "s.json").read_text())
        files = [{k: f[k] for k in ("path", "language", "fileCategory")} for f in s["files"]]
        (t / "i.json").write_text(json.dumps({"projectRoot": str(proj), "files": files}))
        subprocess.run(["node", str(skill / "extract-import-map.mjs"), str(t / "i.json"),
                        str(t / "o.json")], check=True, capture_output=True)
        m = json.loads((t / "o.json").read_text())["importMap"]
    return {(a, b) for a, bs in m.items() for b in bs if a != b}


def _calls_truth(proj: Path) -> set[tuple[str, str]]:
    from codemap.store import load

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "g.json"
        r = subprocess.run([sys.executable, "-m", "codemap.cli", "build", str(proj / "bquant"),
                            "-o", str(out)], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(r.stderr[-600:])
        g = load(out)
    file_of = {i: n.file for i, n in g.nodes.items() if getattr(n, "file", None)}
    pairs = set()
    for e in g.edges:
        if e.type == "calls":
            a, b = file_of.get(e.source), file_of.get(e.target)
            if a and b and a != b:
                pairs.add((_rel(a), _rel(b)))
    return pairs


def _rel(path: str) -> str:
    p = path.replace("\\", "/")
    i = p.find("bquant/")
    return p[i:] if i >= 0 else p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for f in ("--plugin", "--proj", "--stream", "--out"):
        ap.add_argument(f, required=True)
    ap.add_argument("--seconds", type=int)
    a = ap.parse_args()
    proj = Path(a.proj).resolve()
    usage = _usage(Path(a.stream))
    g = _graph(proj)
    edges = g.get("edges") or []
    by_type: dict[str, int] = defaultdict(int)
    for e in edges:
        by_type[e.get("type")] += 1
    ua_imp = {(e["source"].removeprefix("file:"), e["target"].removeprefix("file:"))
              for e in edges if e.get("type") == "imports"}
    ua_calls = set()
    for e in edges:
        if e.get("type") == "calls":
            a_, b_ = _file_of(e["source"]), _file_of(e["target"])
            if a_ and b_ and a_ != b_:
                ua_calls.add((a_, b_))
    t_imp = _import_truth(Path(a.plugin).resolve(), proj)
    t_calls = _calls_truth(proj)
    out = {
        "wall_seconds": a.seconds,
        "usage": usage,
        "graph": {"present": bool(g), "nodes": len(g.get("nodes") or []), "edges": len(edges),
                  "edge_types": dict(by_type),
                  "node_types": dict(_count(n.get("type") for n in g.get("nodes") or [])),
                  "layers": len(g.get("layers") or []), "tour_steps": len(g.get("tour") or [])},
        "imports": {"ua": len(ua_imp), "truth": len(t_imp), "equal": ua_imp == t_imp,
                    "ua_only": sorted(map(list, ua_imp - t_imp)),
                    "truth_only": sorted(map(list, t_imp - ua_imp))},
        "calls": {"ua_pairs": len(ua_calls), "truth_pairs": len(t_calls),
                  "true": len(ua_calls & t_calls),
                  "precision": round(len(ua_calls & t_calls) / len(ua_calls), 4) if ua_calls else None,
                  "recall": round(len(ua_calls & t_calls) / len(t_calls), 4) if t_calls else None,
                  "false": sorted(map(list, ua_calls - t_calls)),
                  "missed": sorted(map(list, t_calls - ua_calls))},
    }
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({k: out[k] for k in ("graph", "imports")}, indent=1))
    print("calls", {k: v for k, v in out["calls"].items() if not isinstance(v, list)})
    print("cost", usage["result"].get("total_cost_usd"))


def _count(it):
    c: dict = defaultdict(int)
    for x in it:
        c[x] += 1
    return c


if __name__ == "__main__":
    main()
