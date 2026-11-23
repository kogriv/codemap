"""R1-C132: the tables of RESULTS.md from <work>/<project>/cmp-{fast,deep}.json, and the contradicted sites to read.

    python summarize.py <work dir>                 # tables (markdown)
    python summarize.py <work dir> --sites <proj>  # C5: each contradicted edge with its call-site lines (≤30, seed 132)
"""

from __future__ import annotations

import ast
import json
import random
import re
import sys
from pathlib import Path

PROJECTS = ("more-itertools", "click", "rich", "markdown-it-py", "jinja")
PKG = {"more-itertools": "more_itertools", "click": "src/click", "rich": "rich", "markdown-it-py": "markdown_it",
       "jinja": "src/jinja2"}


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "—"


def load(work: Path, p: str, tier: str):
    f = work / p / f"cmp-{tier}.json"
    return json.loads(f.read_text()) if f.is_file() else None


def tables(work: Path) -> str:
    out = []
    out.append("| project | functions | started (C4) | explicit pairs | fast recall | deep recall | "
               "deep recall, calls or references |")
    out.append("|---|---|---|---|---|---|---|")
    for p in PROJECTS:
        f, d = load(work, p, "fast"), load(work, p, "deep")
        if not d:
            out.append(f"| {p} | — | — | — | — | — | — |")
            continue
        e = d["recall"]["explicit"]
        out.append(f"| {p} | {d['functions']} | {pct(d['functions_started'], d['functions'])} | {e['pairs']} | "
                   f"{pct(f['recall']['explicit']['found'], e['pairs'])} | {pct(e['found'], e['pairs'])} | "
                   f"{pct(e['found_calls_or_references'], e['pairs'])} |")
    out.append("")
    out.append("**Deep recall by how the pair was reached** (found / pairs):")
    out.append("")
    out.append("| project | direct | nested | external | wrapper |")
    out.append("|---|---|---|---|---|")
    for p in PROJECTS:
        d = load(work, p, "deep")
        if not d:
            continue
        bv = d["recall"]["explicit"]["by_via"]
        out.append(f"| {p} | " + " | ".join(f"{bv[v]['found']}/{bv[v]['pairs']} ({pct(bv[v]['found'], bv[v]['pairs'])})"
                                            for v in ("direct", "nested", "external", "wrapper")) + " |")
    out.append("")
    out.append("**Runtime pairs outside the headline** (deep found / pairs): implicit dunders, properties, decorators.")
    out.append("")
    out.append("| project | implicit | property | decorator | init (behind a construction) |")
    out.append("|---|---|---|---|---|")
    for p in PROJECTS:
        d = load(work, p, "deep")
        if not d:
            continue
        r = d["recall"]
        out.append(f"| {p} | {r['implicit']['found']}/{r['implicit']['pairs']} | {r['property']['found']}/{r['property']['pairs']} | "
                   f"{r['decorator']['found']}/{r['decorator']['pairs']} | {d['categories'].get('init', 0)} |")
    for tier in ("fast", "deep"):
        out.append("")
        out.append(f"**Precision, {tier}** — decided = confirmed / (confirmed + contradicted); the rest is not judged.")
        out.append("")
        out.append("| project | calls edges | confirmed | contradicted | not judged | decided precision | "
                   "exact | inferred | heuristic |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for p in PROJECTS:
            x = load(work, p, tier)
            if not x:
                continue
            o = x["precision"]["outcomes"]
            conf, con = o.get("confirmed", 0), o.get("contradicted", 0)
            nj = x["calls_edges"] - conf - con
            bg = x["precision"]["by_grade"]

            def g(k):
                c = bg.get(k)
                if not c:
                    return "—"
                dec = c.get("confirmed", 0) + c.get("contradicted", 0)
                return f"{pct(c.get('confirmed', 0), dec)} of {dec}" if dec else f"0 decided of {sum(v for kk, v in c.items() if kk != 'decided')}"
            out.append(f"| {p} | {x['calls_edges']} | {conf} | {con} | {nj} ({pct(nj, x['calls_edges'])}) | "
                       f"{pct(conf, conf + con)} | {g('exact')} | {g('inferred')} | {g('heuristic')} |")
    out.append("")
    out.append("**Contradicted edges whose caller entered another function of the same name** (an override, a "
               "protocol's implementation, a definition for another platform) — counted by compare.py:")
    out.append("")
    out.append("| project | fast: same name / contradicted | deep: same name / contradicted |")
    out.append("|---|---|---|")
    for p in PROJECTS:
        f, d = load(work, p, "fast"), load(work, p, "deep")
        if not d:
            continue
        out.append(f"| {p} | {len(f.get('contradicted_same_name', []))}/{len(f['contradicted'])} | "
                   f"{len(d.get('contradicted_same_name', []))}/{len(d['contradicted'])} |")
    out.append("")
    out.append("**Deep precision, split by whether the fast graph has the edge too** (post hoc, not pre-registered):")
    out.append("")
    out.append("| project | in both: confirmed / contradicted | deep only: confirmed / contradicted | deep only: decided precision |")
    out.append("|---|---|---|---|")
    for p in PROJECTS:
        f, d = load(work, p, "fast"), load(work, p, "deep")
        if not d or "edge_outcomes" not in d:
            continue
        fast_edges = set(f["edge_outcomes"])
        both, only = {"confirmed": 0, "contradicted": 0}, {"confirmed": 0, "contradicted": 0}
        for e, o in d["edge_outcomes"].items():
            if o in both:
                (both if e in fast_edges else only)[o] += 1
        out.append(f"| {p} | {both['confirmed']} / {both['contradicted']} | {only['confirmed']} / {only['contradicted']} | "
                   f"{pct(only['confirmed'], only['confirmed'] + only['contradicted'])} |")
    out.append("")
    out.append("**`callers()` completeness** — callees whose every runtime caller is a static caller:")
    out.append("")
    out.append("| project | fast | deep |")
    out.append("|---|---|---|")
    for p in PROJECTS:
        f, d = load(work, p, "fast"), load(work, p, "deep")
        if not d:
            continue
        cf, cd = f["callers_complete"], d["callers_complete"]
        out.append(f"| {p} | {cf['complete']}/{cf['callees']} ({pct(cf['complete'], cf['callees'])}) | "
                   f"{cd['complete']}/{cd['callees']} ({pct(cd['complete'], cd['callees'])}) |")
    return "\n".join(out)


def sites(work: Path, p: str, tier: str = "deep", n: int = 30) -> str:
    x = load(work, p, tier)
    g = json.loads((work / p / f"{tier}.json").read_text())
    nodes = {m["id"]: m for m in g["nodes"]}
    base = (work / p / "src" / PKG[p]).parent
    lines_ran = {}
    for t in ("trace1.json", "trace2.json"):
        tr = json.loads((work / p / t).read_text())
        for f, ls in tr["lines"].items():
            lines_ran.setdefault(f, set()).update(ls)
    items = list(x["contradicted"])
    if len(items) > n:
        items = sorted(random.Random(132).sample(items, n))
    out = [f"# {p} {tier}: {len(x['contradicted'])} contradicted, {len(items)} shown"]
    same = {(f, t) for f, t, _ in x.get("contradicted_same_name", [])}
    for f, t, res in items:
        m = nodes[f]
        src = (base / m["file"]).read_text().splitlines()
        target = t.rsplit(".", 1)[-1]
        tag = "  SAME-NAME" if (f, t) in same else ""
        out.append(f"\n## {f} → {t}  [{res}]{tag}  ({m['file']}:{m['lineno']}-{m['endlineno']})")
        for i in range(m["lineno"], m["endlineno"] + 1):
            line = src[i - 1]
            if re.search(r"\b" + re.escape(target) + r"\s*\(", line):
                ran = "RAN" if i in lines_ran.get(m["file"], set()) else "   "
                out.append(f"  {ran} {i}: {line.strip()[:150]}")
    return "\n".join(out)


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    work = Path(argv[0])
    if len(argv) > 2 and argv[1] == "--sites":
        tier = argv[3] if len(argv) > 3 else "deep"
        print(sites(work, argv[2], tier))
    else:
        print(tables(work))
    return 0


if __name__ == "__main__":
    sys.exit(main())
