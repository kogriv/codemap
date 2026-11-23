"""R1-C132: a static codemap graph against the runtime truth from ``r1c132_tracer``.

    python compare.py --graph deep.json --trace trace.json --src <dir holding the package> [--out result.json]

Recall: of the package-internal calls observed while the project's own tests ran, how many are `calls` edges.
Precision: of the `calls` edges, how many are confirmed, and how many are contradicted — every call site in the
caller naming the target ran, yet the target was never entered from that caller. Edges with a site that did not
run (`unexercised`, `partly_run`, `caller_not_run`), with no site naming the target (`no_site`), or whose target
is an attribute rather than a function or class (`attribute_target`) are not judged.

Definitions (fixed before the runs, docs in DESIGN.md):

- runtime pair ``(F, G)``: F, G graph nodes; categories —
  ``construct`` (``F → class``, flag 8), ``init`` (``F → C.__init__`` when the same F also constructs: the
  construction stands for it and the pair leaves the denominator), ``implicit`` (G is a dunder other than
  ``__init__``/``__new__``/``__call__`` — reached by an operator or protocol, not written as a call),
  ``property`` (G is not a function or class node), ``decorator`` (G applied as a decorator by module or class
  code at import — codemap's `decorated_by`), ``call`` (everything else);
- how it was reached: ``direct`` (flag 0), ``nested`` (1, through F's own nested function or lambda),
  ``external`` (4, through code outside the package), ``wrapper`` (2, through another function's nested
  function, e.g. a decorator's); a pair seen several ways takes the most direct;
- headline recall = explicit pairs (``call`` + ``construct``), every way of reaching.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ORDER = ("direct", "nested", "external", "wrapper")
EXPLICIT_DUNDERS = {"__init__", "__new__", "__call__"}


def via_name(v: int) -> str:
    if v & 2:
        return "wrapper"
    if v & 4:
        return "external"
    if v & 1:
        return "nested"
    return "direct"


def load_graph(path: str):
    g = json.loads(Path(path).read_text())
    nodes = {n["id"]: n for n in g["nodes"]}
    calls = {}
    refs = set()
    decorators = set()
    for e in g["edges"]:
        if e["type"] == "calls" and e["source"] in nodes and e["target"] in nodes:
            calls[(e["source"], e["target"])] = (e.get("extras") or {}).get("resolution")
        elif e["type"] == "references":
            refs.add((e["source"], e["target"]))
        elif e["type"] == "decorated_by":
            decorators.add(e["target"])
    return g, nodes, calls, refs, decorators


def runtime_pairs(trace: dict, nodes: dict, decorators: set = frozenset()):
    """(F, G) -> {"category", "via", "count"} plus counts of what could not be placed."""
    raw: dict = defaultdict(lambda: {"vias": set(), "count": 0, "construct": False})
    unmapped = Counter()
    for caller, callee, v, n in trace["edges"]:
        if caller not in nodes:
            unmapped["caller"] += 1
            continue
        if callee not in nodes:
            unmapped["callee"] += 1
            continue
        r = raw[(caller, callee)]
        r["vias"].add(via_name(v))
        r["count"] += n
        r["construct"] |= bool(v & 8)
    constructs = {(f, g) for (f, g), r in raw.items() if r["construct"]}
    constructing_callers = defaultdict(set)
    for f, g in constructs:
        constructing_callers[f].add(g)
    out = {}
    for (f, g), r in raw.items():
        name = g.rsplit(".", 1)[-1]
        kind = nodes[g]["kind"]
        if r["construct"]:
            cat = "construct"
        elif g in decorators and nodes[f]["kind"] in ("module", "class"):
            cat = "decorator"         # applied at import: codemap records it as `decorated_by`, not `calls`
        elif name == "__init__" and constructing_callers.get(f):
            cat = "init"
        elif name.startswith("__") and name.endswith("__") and name not in EXPLICIT_DUNDERS:
            cat = "implicit"
        elif kind not in ("function", "class"):
            cat = "property"
        else:
            cat = "call"
        via = min(r["vias"], key=ORDER.index)
        out[(f, g)] = {"category": cat, "via": via, "count": r["count"]}
    return out, unmapped


class Sites:
    """Call sites in a caller's own body, by the terminal name they call, and whether their lines ran."""

    def __init__(self, src: Path, nodes: dict, lines: dict):
        self.src, self.nodes, self.lines = src, nodes, {f: set(v) for f, v in lines.items()}
        self._trees: dict = {}
        self._own: dict = {}

    def _tree(self, file: str):
        if file not in self._trees:
            try:
                self._trees[file] = ast.parse((self.src / file).read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                self._trees[file] = None
        return self._trees[file]

    def _calls_of(self, fid: str):
        """Call nodes in F's span, minus those inside nested classes/functions that are graph nodes themselves."""
        if fid in self._own:
            return self._own[fid]
        n = self.nodes[fid]
        file, lo, hi = n.get("file"), n.get("lineno"), n.get("endlineno")
        out = []
        tree = self._tree(file) if file else None
        if tree is not None and lo and hi:
            inner_nodes = [(m["lineno"], m["endlineno"]) for mid, m in self.nodes.items()
                           if mid != fid and mid.startswith(fid + ".") and m.get("file") == file
                           and m["kind"] in ("function", "class") and m.get("lineno") and m.get("endlineno")]
            if n["kind"] == "module":
                inner_nodes = [(m["lineno"], m["endlineno"]) for m in self.nodes.values()
                               if m.get("file") == file and m["kind"] in ("function", "class")
                               and m.get("lineno") and m.get("endlineno")]
                lo, hi = 1, 10 ** 9
            for c in ast.walk(tree):
                if isinstance(c, ast.Call) and lo <= c.lineno <= hi \
                        and not any(a <= c.lineno <= b for a, b in inner_nodes):
                    f = c.func
                    name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
                    if name:
                        out.append((name, c.lineno, c.end_lineno or c.lineno))
        self._own[fid] = (file, out)
        return self._own[fid]

    def judge(self, f: str, g: str, started: set) -> str:
        target = g.rsplit(".", 1)[-1]
        file, calls = self._calls_of(f)
        cands = [(a, b) for name, a, b in calls if name == target]
        if not cands:
            return "no_site"
        ran = self.lines.get(file, set())
        hit = [any(x in ran for x in range(a, b + 1)) for a, b in cands]
        if all(hit):
            return "contradicted"     # every site naming the target ran, and the target was never entered from F
        if self.nodes[f]["kind"] == "function" and f not in started:
            return "caller_not_run"
        return "partly_run" if any(hit) else "unexercised"


def grades():
    try:
        from codemap.model import RESOLUTIONS
        return {v: row["confidence"] for (t, v), row in RESOLUTIONS.items() if t == "calls"}
    except Exception:  # noqa: BLE001 - outside the codemap checkout the grade column is empty
        return {}


def load_traces(paths) -> dict:
    """One trace, or the union of several runs of the same suite (C3)."""
    if isinstance(paths, (str, Path)):
        paths = [paths]
    edges, started, lines = Counter(), Counter(), defaultdict(set)
    for path in paths:
        t = json.loads(Path(path).read_text())
        for c, g, v, n in t["edges"]:
            edges[(c, g, v)] += n
        started.update(t["started"])
        for f, ls in t["lines"].items():
            lines[f].update(ls)
    return {"edges": [[c, g, v, n] for (c, g, v), n in sorted(edges.items())], "started": dict(started),
            "lines": {f: sorted(ls) for f, ls in lines.items()}}


def explicit_pairs(graph: str, trace_path) -> set:
    _, nodes, _, _, decorators = load_graph(graph)
    rt, _ = runtime_pairs(load_traces(trace_path), nodes, decorators)
    return {k for k, v in rt.items() if v["category"] in ("call", "construct")}


def compare(graph: str, trace_path, src: str) -> dict:
    g, nodes, calls, refs, decorators = load_graph(graph)
    trace = load_traces(trace_path)
    rt, unmapped = runtime_pairs(trace, nodes, decorators)
    started = set(trace["started"])
    grade = grades()

    def static_has(f, t, cat):
        return (f, t) in calls

    # ---- recall
    rec = {}
    for scope_name, cats in (("explicit", ("call", "construct")), ("implicit", ("implicit",)),
                             ("property", ("property",)), ("decorator", ("decorator",))):
        pairs = [(k, v) for k, v in rt.items() if v["category"] in cats]
        by_via = {}
        for via in ORDER:
            sub = [k for k, v in pairs if v["via"] == via]
            hit = [k for k in sub if static_has(*k, None)]
            by_via[via] = {"pairs": len(sub), "found": len(hit)}
        hit_all = [k for k, v in pairs if static_has(*k, v["category"])]
        hit_ref = [k for k, v in pairs if static_has(*k, None) or k in refs]
        rec[scope_name] = {"pairs": len(pairs), "found": len(hit_all),
                           "recall": round(len(hit_all) / len(pairs), 4) if pairs else None,
                           "found_calls_or_references": len(hit_ref), "by_via": by_via}
    # misses, for reading
    misses = sorted([f, t, v["via"]] for (f, t), v in rt.items()
                    if v["category"] in ("call", "construct") and (f, t) not in calls)

    # ---- precision
    sites = Sites(Path(src), nodes, trace["lines"])
    judged = Counter()
    by_res: dict = defaultdict(Counter)
    contradicted = []
    rt_keys = set(rt)
    for (f, t), res in calls.items():
        if (f, t) in rt_keys or (nodes[t]["kind"] == "class" and (f, t + ".__init__") in rt_keys):
            out = "confirmed"
        elif nodes[t]["kind"] not in ("function", "class"):
            out = "attribute_target"  # e.g. `self._key(x)` where _key holds a caller's function: not observable
        else:
            out = sites.judge(f, t, started)
        judged[out] += 1
        by_res[res or "unknown"][out] += 1
        if out == "contradicted":
            contradicted.append([f, t, res])

    def prec(c: Counter):
        d = c["confirmed"] + c["contradicted"]
        return round(c["confirmed"] / d, 4) if d else None
    by_grade: dict = defaultdict(Counter)
    for res, c in by_res.items():
        by_grade[grade.get(res, "unknown")].update(c)

    # ---- callers(): is the static caller set complete for each callee?
    static_callers = defaultdict(set)
    for f, t in calls:
        static_callers[t].add(f)
    rt_callers = defaultdict(set)
    for (f, t), v in rt.items():
        if v["category"] in ("call", "construct"):
            rt_callers[t].add(f)
    complete = sum(1 for t, fs in rt_callers.items() if fs <= static_callers[t])

    fn_nodes = [i for i, n in nodes.items() if n["kind"] == "function"]
    return {
        "graph": Path(graph).name,
        "tier": "deep" if any(r == "deep" for r in calls.values()) or g["provenance"].get("tier") == "deep" else "fast",
        "nodes": len(nodes), "functions": len(fn_nodes),
        "functions_started": len(started & set(fn_nodes)),
        "calls_edges": len(calls),
        "runtime_pairs": len(rt), "unmapped_runtime": dict(unmapped),
        "categories": dict(Counter(v["category"] for v in rt.values())),
        "recall": rec,
        "precision": {"outcomes": dict(judged), "decided": prec(judged),
                      "by_grade": {k: {**dict(c), "decided": prec(c)} for k, c in sorted(by_grade.items())},
                      "by_resolution": {k: {**dict(c), "decided": prec(c)} for k, c in sorted(by_res.items())}},
        "callers_complete": {"callees": len(rt_callers), "complete": complete,
                             "share": round(complete / len(rt_callers), 4) if rt_callers else None},
        "misses": misses,
        "contradicted": sorted(contradicted),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True)
    ap.add_argument("--trace", required=True, nargs="+", help="one trace, or several runs (their union)")
    ap.add_argument("--determinism", action="store_true",
                    help="C3: compare the explicit pairs of each --trace and print the difference")
    ap.add_argument("--src", required=True, help="directory holding the package directory (file paths are relative to it)")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if a.determinism:
        sets = [explicit_pairs(a.graph, tp) for tp in a.trace]
        union, inter = set().union(*sets), set.intersection(*sets)
        diff = union - inter
        print(json.dumps({"runs": [len(s) for s in sets], "union": len(union), "differ": len(diff),
                          "share": round(len(diff) / len(union), 4) if union else None,
                          "examples": sorted(diff)[:10]}))
        return 0
    r = compare(a.graph, a.trace, a.src)
    text = json.dumps(r, indent=1)
    if a.out:
        Path(a.out).write_text(text)
    short = {k: r[k] for k in ("tier", "functions", "functions_started", "calls_edges", "runtime_pairs", "categories")}
    print(json.dumps(short))
    print("recall", json.dumps({k: (v["found"], v["pairs"], v["recall"]) for k, v in r["recall"].items()}))
    print("precision", json.dumps(r["precision"]["outcomes"]), r["precision"]["decided"])
    print("callers_complete", json.dumps(r["callers_complete"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
