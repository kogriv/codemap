"""R1-C111: CodeGraph's answers on ripgrep, in score.py's shape — through its CLI, as an agent would see them.

    CODEGRAPH_TELEMETRY=0 python research/tools/_rust/adapter_codegraph.py <codegraph bin> <indexed checkout>

R1 `query <name> --json` (exact name kept); R2 `callers <name> --file <decl file> --json`, the definition at the
declaration line; R3 `callers` again for each R2 caller; R5 `implementations <trait> --file … --json`; R4 the
`imports` edges of its index (`.codegraph/codegraph.db`), mapped from item to defining file — the CLI has no
import-graph listing beyond `cycles`.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from truth_ra import DECLS, TRAITS, find_decl, trait_scoped  # noqa: E402

NOTES: dict = {}
ENV = {**os.environ, "CODEGRAPH_TELEMETRY": "0", "NO_COLOR": "1"}


def cg(binary, root, *args):
    r = subprocess.run([binary, *args, "--path", str(root), "--json"], capture_output=True, text=True, env=ENV,
                       timeout=600)
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {"_error": (r.stdout + r.stderr)[-400:]}


def callers_of(binary, root, name, file, line):
    d = cg(binary, root, "callers", name, "--file", file, "--limit", "1000")
    for block in d.get("definitions", []) if isinstance(d, dict) else []:
        df = block["definition"]
        if df["filePath"] == file and abs(df["startLine"] - (line + 1)) <= 3:
            # File nodes in the list are `use` lines, not calls: kept out, counted in the notes.
            NOTES["file_callers"] = NOTES.get("file_callers", 0) + sum(c.get("kind") == "file" for c in block["callers"])
            return [{"file": c["filePath"], "name": c["name"], "line": c["startLine"]} for c in block["callers"]
                    if c.get("kind") != "file"]
    return None


def main(argv):
    binary, root = argv[1], Path(argv[2]).resolve()
    q = tomllib.loads((HERE / "questions.toml").read_text())
    ver = subprocess.run([binary, "--version"], capture_output=True, text=True, env=ENV).stdout.strip()
    out = {"tool": "codegraph", "version": ver, "r1": {}, "r2": {}, "r3": {}, "r5": {}, "notes": {}}
    for r in q["r1"]:
        d = cg(binary, root, "query", r["name"], "--limit", "200")
        out["r1"][r["name"]] = sorted({f"{x['node']['filePath']}:{x['node']['startLine']}" for x in d
                                       if isinstance(x, dict) and x["node"]["name"] == r["name"]
                                       and x["node"]["kind"] not in ("file", "import")})
    for r in q["r2"]:
        pat, path, trait = DECLS[r["symbol"]]
        f, line, _ = trait_scoped(root, pat, path, trait)
        name = r["symbol"].split("::")[-1]
        cs = callers_of(binary, root, name, path, line)
        if cs is None:
            out["notes"][r["symbol"]] = "no definition at the declaration line among `callers` targets"
            continue
        out["r2"][r["symbol"]] = cs
        if r["kind"] != "macro":
            d2 = list(cs)
            for c in cs:
                more = callers_of(binary, root, c["name"], c["file"], c["line"] - 1) or []
                d2 += more
            seen, uniq = set(), []
            for c in d2:
                k = (c["file"], c["line"])
                if k not in seen:
                    seen.add(k)
                    uniq.append(c)
            out["r3"][r["symbol"]] = uniq
    for trait, (pat, path) in TRAITS.items():
        name = trait.split("::")[-1]
        d = cg(binary, root, "implementations", name, "--file", path)
        types = []
        if isinstance(d, dict):
            for block in d.get("definitions", [d]):
                for x in block.get("implementations", []) or block.get("implementors", []) or []:
                    types.append(x.get("name") or x.get("qualifiedName"))
        out["r5"][trait] = types
        out["notes"][f"r5 raw keys {name}"] = sorted(d.keys()) if isinstance(d, dict) else str(type(d))
    db = sqlite3.connect(root / ".codegraph" / "codegraph.db")
    rows = db.execute("select s.file_path, t.file_path from edges e join nodes s on s.id=e.source "
                      "join nodes t on t.id=e.target where e.kind='imports'").fetchall()
    out["notes"].update(NOTES)
    out["r4"] = sorted({f"{a} -> {b}" for a, b in rows if a != b})
    json.dump(out, sys.stdout, indent=1, sort_keys=True)
    print()


if __name__ == "__main__":
    main(sys.argv)
