"""R1-C132, post hoc (not pre-registered): is each deep miss's target named at a call site in the caller's source,
and does the caller have a static edge to another function of that name (a base method instead of the override)?

    python misses_posthoc.py <work dir>
"""
import json, re, sys, collections
from pathlib import Path
work = Path(sys.argv[1])
PKG = {"more-itertools": "more_itertools", "click": "src/click", "rich": "rich", "markdown-it-py": "markdown_it", "jinja": "src/jinja2"}
print("| project | misses | named at a site in the caller | of them: the caller has a static edge to another function of that name | not named (variable, foreign code, protocol) |")
print("|---|---|---|---|---|")
for p, pk in PKG.items():
    x = json.loads((work / p / "cmp-deep.json").read_text())
    g = json.loads((work / p / "deep.json").read_text())
    nodes = {n["id"]: n for n in g["nodes"]}
    base = (work / p / "src" / pk).parent
    cache = {}
    static = collections.defaultdict(set)
    for e in g["edges"]:
        if e["type"] == "calls":
            static[e["source"]].add(e["target"].rsplit(".", 1)[-1])
    named = selfy = 0
    for f, t, via in x["misses"]:
        m = nodes.get(f)
        if not m or "file" not in m:
            continue
        src = cache.setdefault(m["file"], (base / m["file"]).read_text().splitlines())
        body = "\n".join(src[m["lineno"] - 1:m["endlineno"]])
        last = t.rsplit(".", 1)[-1]
        if last == "__init__":
            last = t.rsplit(".", 2)[-2]
        if re.search(r"\b" + re.escape(last) + r"\s*\(", body):
            named += 1
            if t.rsplit(".", 1)[-1] in static[f]:
                selfy += 1
    n = len(x["misses"])
    print(f"| {p} | {n} | {named} ({100*named/n:.0f}%) | {selfy} | {n-named} ({100*(n-named)/n:.0f}%) |")
