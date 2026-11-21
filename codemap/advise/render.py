"""Markdown for ``codemap advise`` and the generated inventory ``research/matrix.md`` (design D2, D3)."""

from __future__ import annotations

from codemap.advise import STATUSES, Catalog, need_answer, news, overview, recipes, tool_answer

_MARK = {"measured": "measured", "probed": "probed", "read": "read only", "rejected": "rejected"}
_COV = {"covered": "✅ covered", "partial": "◐ partial", "none": "— not covered"}


def _catalog_line(h: dict) -> str:
    src = h["source"]
    s = "packaged" if set(src.values()) == {"packaged"} else ", ".join(f"{k} {v}" for k, v in src.items())
    age = f", {h['age_days']} day(s) old" if h.get("age_days") is not None else ""
    line = f"_Catalog as of {h['as_of'][:10]} ({s}{age})._"
    if h.get("age_days") is not None and h["age_days"] > 30:
        line += " _Run `codemap advise --refresh` for the lab's current catalog._"
    for n in h.get("notes", []):
        line += f"\n_{n}_"
    return line


def _tool_line(v: dict) -> str:
    bits = [f"**{v['name']}** — {_MARK[v['status']]}"]
    if v.get("version"):
        bits.append(f"v{v['version']}" if v["version"][:1].isdigit() else v["version"])
    if v.get("checked"):
        bits.append(f"checked {v['checked']}")
    if v.get("license"):
        bits.append(v["license"])
    head = " · ".join(bits)
    if v.get("status_note"):
        head += f" · {v['status_note']}"
    elif v.get("measured_on") and v["measured_on"] != ["python"]:
        head += f" · on {', '.join(v['measured_on'])}"
    if v.get("stale"):
        head += " · ⚠ stale"
    if v.get("drift"):
        head += f" · ⚠ measured {v['drift']['measured']}, latest {v['drift']['latest']}"
    lines = [f"- {head}"]
    for k, label in (("summary", ""), ("vs_codemap", "vs codemap: "), ("reason", "why not: "),
                     ("probe", "check it first: ")):
        if v.get(k):
            lines.append(f"  {label}{v[k]}")
    if v.get("evidence"):
        lines.append(f"  evidence: {v['evidence']}")
    elif v.get("url"):
        lines.append(f"  {v['url']}")
    return "\n".join(lines)


def _names(steps: list[dict]) -> str:
    return "; ".join(f"**{x['name']}** — {x['why']}" for x in steps) or "—"


def recipe_md(rows: list[dict]) -> str:
    """The recipe for a language: one row per audit axis, before anything else (design recipe_rust D8)."""
    langs = ", ".join(sorted({r["language"] for r in rows}))
    out = [f"## Recipe for {langs} — what to use, per axis", "",
           "The lab's measured choice per axis: native tools first, a lab tool only with a measured gain, and what "
           "to avoid.", "", "| axis | use | avoid |", "|---|---|---|"]
    for r in rows:
        out.append(f"| `{r['need']}` {r['summary']} | {_names(r['use'])} | {_names(r['avoid'])} |")
    ev = sorted({r["evidence"] for r in rows if r.get("evidence")})
    if ev:
        out += ["", "Evidence: " + ", ".join(ev)]
    return "\n".join(out)


def _recipe_row_md(r: dict) -> list[str]:
    out = [f"**Recipe ({r['language']}):** {r['summary']}", f"- use: {_names(r['use'])}"]
    if r["avoid"]:
        out.append(f"- avoid: {_names(r['avoid'])}")
    if r.get("evidence"):
        out.append(f"- evidence: {r['evidence']}")
    return out


def need_md(a: dict) -> str:
    cm = a["codemap"]
    out = [f"## {a['title']} (`{a['need']}`)", "", f"**codemap:** {_COV[cm['coverage']]}"
           + (f" — {cm['how']}" if cm.get("how") else "")]
    if cm.get("caveat"):
        out.append(f"  {cm['caveat']}")
    for r in a.get("recipe", []):
        out += [""] + _recipe_row_md(r)
    if a.get("note"):
        out += ["", a["note"]]
    if a["tools"]:
        out += ["", "**Other tools** (measured first; `read only` means the lab has not run it):"]
        out += [_tool_line(v) for v in a["tools"]]
    else:
        out += ["", "_No other tool in the catalog for this need._"]
    if a["rejected"]:
        out += ["", "**Tried and rejected:**"] + [_tool_line(v) for v in a["rejected"]]
    if a.get("excluded"):
        names = ", ".join(x["tool"] for x in a["excluded"])
        out += ["", f"_Not shown for {', '.join(a['language_filter'])}: {len(a['excluded'])} tool(s) whose recorded "
                f"languages do not include it — {names}._"]
    return "\n".join(out)


def overview_md(o: dict) -> str:
    c = o["claims"]
    head = (f"# What codemap covers, and what the lab knows about the rest\n\n"
            f"{len(o['needs'])} need(s), {o['tools']} tool(s); claims: "
            + ", ".join(f"{c[s]} {s}" for s in STATUSES) + ".")
    if o.get("languages"):
        head += f" Filtered to: {', '.join(o['languages'])}."
    rows = ["| need | codemap | best other tool | tools |", "|---|---|---|---|"]
    for r in o["needs"]:
        best = f"{r['best']['tool']} ({_MARK[r['best']['status']]})" if r["best"] else "—"
        rows.append(f"| `{r['need']}` {r['title']} | {_COV[r['codemap']]} | {best} | {r['tools']} |")
    return head + "\n\n" + "\n".join(rows) + "\n\n`codemap advise <need>` for one row in full."


def tool_md(t: dict) -> str:
    out = [f"## {t['name']} (`{t['id']}`)", "", " · ".join(x for x in (t.get("url"), t.get("license"),
                                                                       ", ".join(t.get("languages", []))) if x)]
    if t.get("card"):
        out.append(f"Card: {t['card']}")
    if t.get("latest"):
        out.append(f"Latest release seen: {t['latest']['version']} ({t['latest'].get('date', '?')})")
    out += ["", "| need | status | version | checked |", "|---|---|---|---|"]
    for v in t["claims"]:
        flag = " ⚠" if v.get("drift") or v.get("stale") else ""
        out.append(f"| `{v['need']}` | {_MARK[v['status']]}{flag} | {v.get('version', '')} | {v.get('checked', '')} |")
    for v in t["claims"]:
        if v.get("summary"):
            out.append(f"\n**{v['need']}:** {v['summary']}")
    if t["news"]:
        out += ["", "**News:**"] + [_news_line(n) for n in t["news"]]
    return "\n".join(out)


def _news_line(n: dict) -> str:
    v = "" if n.get("verified") else " _(unverified)_"
    tool = f"`{n['tool']}` " if n.get("tool") else ""
    return f"- {n['date']} · {n['kind']} · {tool}{n['text']}{v} — {n['source']}"


def answer_md(a: dict) -> str:
    parts = []
    if a.get("error"):
        listing = a.get("needs") or a.get("tools") or []
        parts.append(f"**{a['error']}.** Known: " + ", ".join(f"`{x}`" for x in listing))
    if a.get("recipe"):
        parts.append(recipe_md(a["recipe"]))
    if a.get("overview"):
        parts.append(overview_md(a["overview"]))
    for m in a.get("matches", []):
        parts.append(need_md(m))
    if a.get("tool"):
        parts.append(tool_md(a["tool"]))
    if "news" in a:
        parts.append("## News\n\n" + ("\n".join(_news_line(n) for n in a["news"]) or "_None in the window._"))
    parts.append(_catalog_line(a["catalog"]))
    return "\n\n".join(parts) + "\n"


def matrix_md(cat: Catalog) -> str:
    """``research/matrix.md``: generated, never edited by hand; a test compares it with this render."""
    o = overview(cat)
    out = ["# The tool matrix — what codemap covers, what the lab measured, what it has only read", "",
           "<!-- Generated from codemap/advise/data/ by `codemap advise --matrix`. Do not edit by hand: "
           "tests/test_r1c110_advise.py compares this file with the render. -->", "",
           f"Catalog as of {cat.as_of[:10]}. Agents get the same data through the MCP tool `advise` or "
           "`codemap advise`; `codemap advise --refresh` fetches the current catalog without a release.", "",
           "**Statuses.** `measured` — scored against the lab's truth, numbers in the card. `probed` — run on a "
           "real tree, not scored. `read only` — known from its docs or a survey; nobody here has run it. "
           "`rejected` — tried and unusable for that need.", "",
           overview_md(o).split("\n\n", 1)[1].rsplit("\n\n", 1)[0], ""]
    for lang in sorted({r["language"] for r in cat.matrix.get("recipe", [])}):
        out += [recipe_md(recipes(cat, {lang})), ""]
    for r in o["needs"]:
        a = need_answer(cat, r["need"])
        out += [need_md(a).replace("## ", "### ", 1), ""]
    out += ["## Tools", "", "| tool | license | languages | claims | card |", "|---|---|---|---|---|"]
    for tid in sorted(cat.tools):
        t = tool_answer(cat, tid)
        claims = ", ".join(f"{v['need']} ({_MARK[v['status']]})" for v in t["claims"])
        card = f"[card](../{cat.tools[tid]['card']})" if cat.tools[tid].get("card") else "—"
        out.append(f"| [{t['name']}]({t['url']}) | {t.get('license') or '?'} | "
                   f"{', '.join(t.get('languages', []))} | {claims} | {card} |")
    items = news(cat, today=None)[:20]
    out += ["", "## Latest news", ""] + ([_news_line(n) for n in items] or ["_None yet._"])
    return "\n".join(out).rstrip() + "\n"
