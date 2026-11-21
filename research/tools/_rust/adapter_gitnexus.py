"""R1-C111: GitNexus's answers on ripgrep, in score.py's shape.

    GITNEXUS_HOME=<isolated home> python research/tools/_rust/adapter_gitnexus.py <gitnexus bin> <repo alias>

Everything goes through `gitnexus cypher` (the same Cypher an agent gets from the MCP `cypher` tool; `context`
returns the same callers, without line numbers). GitNexus stores 0-based start lines: +1 here.
- R1: nodes named exactly so, except `Impl` blocks (an impl is not a definition of the name);
- R2: `CALLS` edges into the node declared at the target's declaration line; R3: once more for each caller;
- R4: `IMPORTS` edges between files;
- R5: names of nodes with an `IMPLEMENTS` edge to the trait.
A target with no node at its declaration line is reported in `notes` and left unanswered.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from truth_ra import DECLS, TRAITS  # noqa: E402


def cypher(binary, repo, q):
    r = subprocess.run([binary, "cypher", "-r", repo, "-l", "5000", q], capture_output=True, text=True, timeout=600)
    t = r.stdout
    if "{" not in t and t.strip().endswith("[]"):
        return []  # an empty result prints `[]`
    if "{" not in t:
        raise RuntimeError(f"cypher gave no JSON for {q!r}: {(r.stdout + r.stderr)[-500:]}")
    j = json.loads(t[t.index("{"):])
    if "error" in j:
        raise RuntimeError(f"{q}: {j['error']}")
    md = j.get("markdown", "")
    rows = []
    lines = md.splitlines()
    if len(lines) >= 2:
        heads = [h.strip() for h in lines[0].strip("|").split("|")]
        for line in lines[2:]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows.append(dict(zip(heads, cells)))
    return rows


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def main(argv):
    binary, repo = argv[1], argv[2]
    q = tomllib.loads((HERE / "questions.toml").read_text())
    ver = subprocess.run([binary, "--version"], capture_output=True, text=True).stdout.strip()
    out = {"tool": "gitnexus", "version": ver, "r1": {}, "r2": {}, "r3": {}, "r5": {}, "notes": {}}
    for r in q["r1"]:
        rows = cypher(binary, repo, f"MATCH (n) WHERE n.name = '{esc(r['name'])}' "
                                    "RETURN labels(n) AS l, n.filePath AS f, n.startLine AS s")
        out["r1"][r["name"]] = sorted({f"{x['f']}:{int(x['s']) + 1}" for x in rows if x["l"] != "Impl" and x["s"]})
        out["notes"][f"r1 {r['name']} impl nodes"] = sum(x["l"] == "Impl" for x in rows)

    def callers(node_id):
        rows = cypher(binary, repo, f"MATCH (a)-[r]->(b) WHERE b.id = '{esc(node_id)}' AND r.type = 'CALLS' "
                                    "RETURN a.id AS id, a.name AS n, a.filePath AS f, a.startLine AS s")
        return [{"id": x["id"], "file": x["f"], "name": x["n"], "line": int(x["s"]) + 1} for x in rows if x["s"]]

    for r in q["r2"]:
        _, path, _ = DECLS[r["symbol"]]
        name = r["symbol"].split("::")[-1]
        from truth_ra import trait_scoped  # noqa: PLC0415
        pat, path, trait = DECLS[r["symbol"]]
        _, line, _ = trait_scoped(Path(argv[3]).resolve(), pat, path, trait) if len(argv) > 3 else (None, None, None)
        rows = cypher(binary, repo, f"MATCH (n) WHERE n.name = '{esc(name)}' AND n.filePath = '{esc(path)}' "
                                    "RETURN n.id AS id, labels(n) AS l, n.startLine AS s")
        node = [x for x in rows if x["s"] and line is not None and abs(int(x["s"]) - line) <= 3]
        if len(node) != 1:
            out["notes"][r["symbol"]] = f"{len(node)} node(s) at the declaration line; candidates {rows}"
            continue
        cs = callers(node[0]["id"])
        out["r2"][r["symbol"]] = [{k: v for k, v in c.items() if k != "id"} for c in cs]
        if r["kind"] != "macro":
            seen, d2 = set(), []
            for c in cs + [x for c in cs for x in callers(c["id"])]:
                k = (c["file"], c["line"])
                if k not in seen:
                    seen.add(k)
                    d2.append({kk: v for kk, v in c.items() if kk != "id"})
            out["r3"][r["symbol"]] = d2
    for trait, (_, path) in TRAITS.items():
        name = trait.split("::")[-1]
        rows = cypher(binary, repo, f"MATCH (a)-[r]->(t) WHERE t.name = '{esc(name)}' AND t.filePath = '{esc(path)}' "
                                    "AND r.type = 'IMPLEMENTS' RETURN a.name AS n, labels(a) AS l")
        out["r5"][trait] = sorted(x["n"] for x in rows)
    rows = cypher(binary, repo, "MATCH (a)-[r]->(b) WHERE r.type = 'IMPORTS' RETURN a.filePath AS fa, b.filePath AS fb, "
                                "labels(a) AS la, labels(b) AS lb")
    out["r4"] = sorted({f"{x['fa']} -> {x['fb']}" for x in rows if x["fa"] and x["fb"] and x["fa"] != x["fb"]})
    out["notes"]["r4 endpoint labels"] = sorted({f"{x['la']}->{x['lb']}" for x in rows})
    json.dump(out, sys.stdout, indent=1, sort_keys=True)
    print()


if __name__ == "__main__":
    main(sys.argv)
