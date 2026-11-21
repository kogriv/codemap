"""R1-C112: each tool's `impact` answer at depth 2 for the R2 targets, scored against rust-analyzer (D7, E13).

    python research/tools/_rust/adapter_impact.py <tools.json> > impact.json

`tools.json` names the binaries and indexed copies of the clean tree:
    {"codegraph": [bin, checkout], "gitnexus": [bin, alias, GITNEXUS_HOME], "roam": [bin, checkout],
     "ontoindex": [bin, repo name, HOME, checkout], "graphlens": [bin dir, checkout], "tree": clean checkout}

Each tool is asked once per target with its product command at depth 2, tests included where the tool has the
switch: `codegraph impact NAME --file F -d 2`, `gitnexus impact NAME -f F --depth 2 --include-tests`,
`roam impact QUALIFIED --depth 2`, `ontoindex impact NAME -u UID --depth 2 --include-tests` (it has no file switch:
the uid is looked up with Cypher at the declaration line), graphlens MCP `relations(symbol, file, depth=2)` over
stdio, its `callers` (it drops test call sites by design, so `recall_production` scores production callers only). An answer is reduced to the set of (file, function name) it lists; the truth is
rust-analyzer's depth-1 callers plus their callers (truth_ra.json R2 + R3), as (file, name). Names compare
without generic arguments and impl prefixes. The macro target is left out: the tools answer it under R2.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from truth_ra import DECLS, trait_scoped  # noqa: E402

# roam takes a qualified name; the others a bare name and the declaring file.
ROAM_NAME = {"grep_searcher::Sink::matched": "Sink::matched", "grep_matcher::Matcher::find_at": "Matcher::find_at",
             "grep_searcher::Searcher::search_path": "Searcher::search_path", "grep_cli::escape": "escape",
             "ignore::ParallelVisitor::visit": "ParallelVisitor::visit"}


TEST_NAMES: set[tuple[str, str]] = set()


def is_test(file: str, name: str) -> bool:
    """A truth caller in test code: under tests/, or a function rust-analyzer placed inside a `tests` module."""
    return bool(re.search(r"(^|/)(tests|benches|examples)/", file)) or (file, name) in TEST_NAMES


def short(name: str) -> str:
    return re.split(r"[<(]", name.split("::")[-1].split(".")[-1])[0].strip()


def truth_sets(tree: Path | None = None) -> dict[str, set[tuple[str, str]]]:
    """rust-analyzer's depth-2 callers as (file, name). With the clean tree given, callers after a file's first
    `#[cfg(test)]` are recorded in TEST_NAMES (test code)."""
    t = json.loads((HERE / "truth_ra.json").read_text())
    out = {}
    first_cfg: dict[str, int | None] = {}
    for sym, v in t["r2"].items():
        if v.get("kind") == "macro":
            continue
        ids = {c["caller"] for c in v["callers"]} | {x for xs in t["r3"].get(sym, {}).values() for x in xs}
        out[sym] = set()
        for i in ids:  # id: "file::detail::name@line"
            f, nm, ln = i.split("::", 1)[0], short(i.rsplit("::", 1)[1].rsplit("@", 1)[0]), int(i.rsplit("@", 1)[1])
            out[sym].add((f, nm))
            if tree is not None:
                if f not in first_cfg:
                    lines = (tree / f).read_text(encoding="utf-8").splitlines()
                    first_cfg[f] = next((k + 1 for k, x in enumerate(lines) if x.strip().startswith("#[cfg(test)]")),
                                        None)
                if first_cfg[f] is not None and ln > first_cfg[f]:
                    TEST_NAMES.add((f, nm))
    return out


def walk(obj, acc: set, file_keys=("filePath", "file", "file_path"), name_keys=("name",)):
    """Every dict below obj that carries a file and a name."""
    if isinstance(obj, dict):
        f = next((obj[k] for k in file_keys if isinstance(obj.get(k), str)), None)
        n = next((obj[k] for k in name_keys if isinstance(obj.get(k), str)), None)
        if f and n and obj.get("kind") != "file":  # a file node is a `use` line, not a caller
            acc.add((f, short(n)))
        for v in obj.values():
            walk(v, acc, file_keys, name_keys)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, acc, file_keys, name_keys)
    return acc


def run_json(args, env=None, cwd=None) -> dict:
    r = subprocess.run(args, capture_output=True, text=True, env={**os.environ, **(env or {})}, cwd=cwd, timeout=600)
    t = r.stdout
    return json.loads(t[t.index("{"):]) if "{" in t else {"_error": (r.stdout + r.stderr)[-300:]}


def graphlens_relations(bindir: str, root: str, name: str, path: str) -> dict:
    """One MCP session per call: initialize, then tools/call relations. Proxy variables are dropped: with a SOCKS
    proxy set and no `socksio`, the server dies at start while building its embedding client."""
    env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
    env["PATH"] = f"{bindir}:{env.get('PATH', '')}"
    p = subprocess.Popen([f"{bindir}/graphlens-mcp", "serve", "-r", root, "--no-watch"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
    try:
        def rpc(i, method, params, reply=True):
            msg = {"jsonrpc": "2.0", "method": method, "params": params} | ({"id": i} if reply else {})
            p.stdin.write(json.dumps(msg) + "\n")
            p.stdin.flush()
            while reply:
                m = json.loads(p.stdout.readline())
                if m.get("id") == i:
                    return m
        rpc(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                              "clientInfo": {"name": "lab", "version": "1"}})
        rpc(None, "notifications/initialized", {}, reply=False)
        r = rpc(2, "tools/call", {"name": "relations",
                                  "arguments": {"symbol": name, "file": path, "depth": 2, "limit": 1000}})
        return r["result"].get("structuredContent") or json.loads(r["result"]["content"][0]["text"])
    finally:
        p.kill()


def main(argv):
    cfg = json.loads(Path(argv[1]).read_text())
    truth = truth_sets(Path(cfg["tree"]) if cfg.get("tree") else None)
    res = {"truth": {s: sorted(map(list, v)) for s, v in truth.items()}, "tools": {}}
    for tool in ("codegraph", "gitnexus", "roam", "ontoindex", "graphlens"):
        if tool not in cfg or tool == "tree":
            continue
        per = {}
        for sym, tset in truth.items():
            _, path, _ = DECLS[sym]
            name = sym.split("::")[-1]
            if tool == "codegraph":
                b, root = cfg[tool]
                d = run_json([b, "impact", name, "--file", path, "-d", "2", "--path", root, "--json"],
                             env={"CODEGRAPH_TELEMETRY": "0"})
                defs = [x for x in d.get("definitions", []) if x["definition"]["filePath"] == path]
                got = walk([x.get("affected", []) for x in defs], set())
            elif tool == "gitnexus":
                b, alias, home = cfg[tool]
                d = run_json([b, "impact", name, "-f", path, "--depth", "2", "--include-tests", "-r", alias,
                              "-l", "1000"], env={"GITNEXUS_HOME": home})
                got = walk(d.get("byDepth", {}), set())
            elif tool == "graphlens":
                bindir, root = cfg[tool]
                d = graphlens_relations(bindir, root, name, path)
                resolved = (d.get("node") or {}).get("qualified_name")
                trait = DECLS[sym][2]
                if trait and resolved and not resolved.endswith(f"{trait}.{name}"):
                    # No node for a bodiless trait method: it answers for a same-named impl, without saying so.
                    per[sym] = {"error": f"resolved to {resolved}, not {trait}::{name}", "resolved": resolved}
                    continue
                got = {(str(Path(c["file_path"]).relative_to(Path(root).resolve())), short(c["name"]))
                       for c in d.get("callers", []) if c.get("file_path")}
            elif tool == "ontoindex":
                b, repo, home, root = cfg[tool]
                pat, _, trait = DECLS[sym]
                _, line, _ = trait_scoped(Path(root), pat, path, trait)
                q = (f"MATCH (n) WHERE n.name = '{name}' AND n.filePath = '{path}' "
                     "RETURN n.id AS id, n.startLine AS s LIMIT 100")
                rows = run_json([b, "cypher", "-r", repo, q], env={"HOME": home}).get("markdown", "")
                ids = [c.split("|")[1].strip() for c in rows.splitlines()[2:]
                       if abs(int(c.split("|")[2].strip() or -99) - line) <= 3]
                if len(ids) != 1:
                    per[sym] = {"error": f"{len(ids)} uid(s) at the declaration line"}
                    continue
                d = run_json([b, "impact", name, "-u", ids[0], "--depth", "2", "--include-tests", "-r", repo],
                             env={"HOME": home})
                got = walk(d.get("byDepth", {}), set())
            else:
                b, root = cfg[tool]
                d = run_json([b, "--json", "--detail", "--budget", "0", "impact", ROAM_NAME[sym], "--depth", "2",
                              "--max-callers", "1000"], cwd=root)
                got = walk({k: v for k, v in d.items() if k not in ("affected_file_list", "_meta")}, set())
            got.discard((path, short(name)))
            tp = len(got & tset)
            prod = {x for x in tset if not is_test(x[0], x[1])}
            per[sym] = {"tool": len(got), "truth": len(tset), "tp": tp,
                        "precision": round(tp / len(got), 3) if got else None,
                        "recall": round(tp / len(tset), 3) if tset else None,
                        "recall_production": round(len(got & prod) / len(prod), 3) if prod else None,
                        "missed": sorted(f"{f} {n}" for f, n in tset - got)[:8],
                        "extra": sorted(f"{f} {n}" for f, n in got - tset)[:8]}
            if "_error" in d:
                per[sym]["error"] = d["_error"]
        res["tools"][tool] = per
    json.dump(res, sys.stdout, indent=1, sort_keys=True)
    print()


if __name__ == "__main__":
    main(sys.argv)
