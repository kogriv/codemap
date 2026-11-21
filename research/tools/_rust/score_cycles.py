"""R1-C112: score module-cycle answers at the file level against cargo-modules (recipe_rust.md D7, E12).

    python research/tools/_rust/score_cycles.py <planted checkout> <modules.json> <plants.json> name=components.json ...

Truth: the `uses` edges of `truth_modules.py` on the planted copy, each end folded to its file module (score.py's
`file_modules`), then strongly connected components of size ≥ 2, as sets of files. A tool's answer is a list of
file sets (its components or its cycles; cycles sharing a file are merged into one component here, so a tool that
lists every elementary cycle is not penalised for listing many). Reported per truth component: matched exactly,
covered by a larger tool component, partly found, or missed; plus tool components that match no truth component,
and whether the planted pair lands in one tool component.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from score import file_modules  # noqa: E402


def sccs(edges: set[tuple[str, str]]) -> list[frozenset[str]]:
    g: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        g[a].add(b)
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    out: list[frozenset[str]] = []
    sys.setrecursionlimit(10000)

    def visit(v: str) -> None:
        index[v] = low[v] = len(index)
        stack.append(v)
        on.add(v)
        for w in g[v]:
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = set()
            while True:
                w = stack.pop()
                on.discard(w)
                comp.add(w)
                if w == v:
                    break
            if len(comp) > 1:
                out.append(frozenset(comp))

    for v in list(g):
        if v not in index:
            visit(v)
    return out


def merge(sets: list[set[str]]) -> list[frozenset[str]]:
    comps: list[set[str]] = []
    for s in sets:
        s = set(s)
        for c in [c for c in comps if c & s]:
            s |= c
            comps.remove(c)
        comps.append(s)
    return [frozenset(c) for c in comps if len(c) > 1]


def main(argv):
    root = Path(argv[1]).resolve()
    mods = json.loads(Path(argv[2]).read_text())
    plants = json.loads(Path(argv[3]).read_text())
    fm = file_modules(root)
    mod_file = {m: f for f, m in fm.items()}
    known = set(mod_file)

    def fold(m: str) -> str | None:
        parts = m.split("::")
        for i in range(len(parts), 0, -1):
            if "::".join(parts[:i]) in known:
                return mod_file["::".join(parts[:i])]
        return None

    edges = set()
    for e in mods["edges"]:
        a, b = (fold(x) for x in e.split(" -> "))
        if a and b and a != b:
            edges.add((a, b))
    truth = sccs(edges)
    res = {"truth_components": [sorted(c) for c in sorted(truth, key=sorted)], "tools": {}}
    pair = set(plants["cycle_files"])
    for spec in argv[4:]:
        name, path = spec.split("=", 1)
        comps = merge([set(x) for x in json.loads(Path(path).read_text())])
        per = {}
        for t in truth:
            key = " + ".join(sorted(t))
            if t in comps:
                per[key] = "exact"
            elif any(t < c for c in comps):
                per[key] = "covered by a larger component"
            elif any(t & c for c in comps):
                per[key] = f"partly: {max(len(t & c) for c in comps)} of {len(t)} files"
            else:
                per[key] = "missed"
        extra = [sorted(c) for c in comps if not any(c & t for t in truth)]
        res["tools"][name] = {"components": len(comps), "per_truth_component": per, "unmatched_components": extra,
                              "planted_pair_in_one_component": any(pair <= c for c in comps)}
    json.dump(res, sys.stdout, indent=1, sort_keys=True)
    print()


if __name__ == "__main__":
    main(sys.argv)
