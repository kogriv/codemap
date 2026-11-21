"""R1-C112: each tool's `impact` answer at depth 2 for the R2 targets, scored against rust-analyzer (D7, E13).

    python research/tools/_rust/adapter_impact.py <tools.json> > impact.json

`tools.json` names the binaries and indexed copies of the clean tree:
    {"codegraph": [bin, checkout], "gitnexus": [bin, alias, GITNEXUS_HOME], "roam": [bin, checkout]}

Each tool is asked once per target with its product command at depth 2, tests included where the tool has the
switch: `codegraph impact NAME --file F -d 2`, `gitnexus impact NAME -f F --depth 2 --include-tests`,
`roam impact QUALIFIED --depth 2`. An answer is reduced to the set of (file, function name) it lists; the truth is
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
from truth_ra import DECLS  # noqa: E402

# roam takes a qualified name; the others a bare name and the declaring file.
ROAM_NAME = {"grep_searcher::Sink::matched": "Sink::matched", "grep_matcher::Matcher::find_at": "Matcher::find_at",
             "grep_searcher::Searcher::search_path": "Searcher::search_path", "grep_cli::escape": "escape",
             "ignore::ParallelVisitor::visit": "ParallelVisitor::visit"}


def short(name: str) -> str:
    return re.split(r"[<(]", name.split("::")[-1].split(".")[-1])[0].strip()


def truth_sets() -> dict[str, set[tuple[str, str]]]:
    t = json.loads((HERE / "truth_ra.json").read_text())
    out = {}
    for sym, v in t["r2"].items():
        if v.get("kind") == "macro":
            continue
        ids = {c["caller"] for c in v["callers"]} | {x for xs in t["r3"].get(sym, {}).values() for x in xs}
        # id: "file::detail::name@line"
        out[sym] = {(i.split("::", 1)[0], short(i.rsplit("::", 1)[1].rsplit("@", 1)[0])) for i in ids}
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


def main(argv):
    cfg = json.loads(Path(argv[1]).read_text())
    truth = truth_sets()
    res = {"truth": {s: sorted(map(list, v)) for s, v in truth.items()}, "tools": {}}
    for tool in ("codegraph", "gitnexus", "roam"):
        if tool not in cfg:
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
            else:
                b, root = cfg[tool]
                d = run_json([b, "--json", "--detail", "--budget", "0", "impact", ROAM_NAME[sym], "--depth", "2",
                              "--max-callers", "1000"], cwd=root)
                got = walk({k: v for k, v in d.items() if k not in ("affected_file_list", "_meta")}, set())
            got.discard((path, short(name)))
            tp = len(got & tset)
            per[sym] = {"tool": len(got), "truth": len(tset), "tp": tp,
                        "precision": round(tp / len(got), 3) if got else None,
                        "recall": round(tp / len(tset), 3) if tset else None,
                        "missed": sorted(f"{f} {n}" for f, n in tset - got)[:8],
                        "extra": sorted(f"{f} {n}" for f, n in got - tset)[:8]}
            if "_error" in d:
                per[sym]["error"] = d["_error"]
        res["tools"][tool] = per
    json.dump(res, sys.stdout, indent=1, sort_keys=True)
    print()


if __name__ == "__main__":
    main(sys.argv)
