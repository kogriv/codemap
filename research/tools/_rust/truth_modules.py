"""R1-C111 truth for R4: module → module `use` edges across the workspace, from cargo-modules (D3).

    python research/tools/_rust/truth_modules.py <ripgrep checkout> > truth_modules.json

For each workspace package (its lib, and the ripgrep binary) `cargo-modules dependencies --no-sysroot` prints a
DOT graph of items with "owns" and "uses" edges. An edge's ends are mapped to their enclosing module (the
longest prefix that is a module or crate node in any package's graph), so uses of another workspace crate's
items land on that crate's module. Kept: `uses` edges whose two modules differ and both belong to workspace
crates. Crate names use underscores (`grep_searcher`).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

EDGE = re.compile(r'^\s*"([^"]+)" -> "([^"]+)" \[label="(owns|uses)"')
NODE = re.compile(r'^\s*"([^"]+)" \[label="[^"]*"[^\]]*\]; // "([^"]+)" node')


def packages(root: Path) -> list[tuple[str, str]]:
    meta = json.loads(subprocess.run(["cargo", "metadata", "--no-deps", "--format-version", "1"], cwd=root,
                                     capture_output=True, text=True, check=True).stdout)
    out = []
    for p in meta["packages"]:
        kinds = {k for t in p["targets"] for k in t["kind"]}
        if "lib" in kinds:
            out.append((p["name"], "--lib"))
        if p["name"] == "ripgrep":
            out.append((p["name"], "--bin=rg"))
    return sorted(out)


def main(argv):
    root = Path(argv[1]).resolve()
    modules: set[str] = set()
    raw_edges: set[tuple[str, str]] = set()
    pkgs = packages(root)
    # Workspace crates only; an external crate (serde_json) also appears as a "crate" node.
    crates: set[str] = {("rg" if n == "ripgrep" else n.replace("-", "_")) for n, _ in pkgs}
    for name, target in pkgs:
        args = ["cargo-modules", "dependencies", "--package", name, "--no-sysroot"]
        args += [target] if target == "--lib" else ["--bin", target.split("=")[1]]
        dot = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=600).stdout
        if not dot.strip():
            raise SystemExit(f"cargo-modules printed nothing for {name} {target}")
        for line in dot.splitlines():
            m = NODE.match(line)
            if m and m.group(2) in ("mod", "crate"):
                modules.add(m.group(1))
            e = EDGE.match(line)
            if e and e.group(3) == "uses":
                raw_edges.add((e.group(1), e.group(2)))

    def module_of(path: str) -> str | None:
        parts = path.split("::")
        for i in range(len(parts), 0, -1):
            cand = "::".join(parts[:i])
            if cand in modules:
                return cand
        return None

    edges = set()
    for a, b in raw_edges:
        ma, mb = module_of(a), module_of(b)
        if ma and mb and ma != mb and ma.split("::")[0] in crates and mb.split("::")[0] in crates:
            edges.add((ma, mb))
    json.dump({"crates": sorted(crates), "modules": sorted(modules),
               "edges": sorted(f"{a} -> {b}" for a, b in edges)}, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main(sys.argv)
