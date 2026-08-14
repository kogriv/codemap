"""Render the two-graph API diff (R1-C5) — structured + markdown.

The engine lives in ``codemap.apidiff``; this is the presentation shared by the
``diff`` CLI command and the ``diff`` serve op. Breaking changes lead (that is what
fails a release gate); removed public symbols are listed with them, since a deleted
symbol is itself breaking.
"""

from __future__ import annotations

from codemap.apidiff import ApiDiff, BREAKING, INFO, WARNING, diff_api
from codemap.model import Graph

_CAP = 40


def build_apidiff(old: Graph, new: Graph) -> dict:
    """Structured API diff: {old_target, new_target, ...ApiDiff.to_dict()}."""
    d = diff_api(old, new).to_dict()
    d["old_target"] = old.target
    d["new_target"] = new.target
    # a removed public symbol is itself a breaking change — fold into the count.
    d["summary"]["breaking_total"] = d["summary"]["breaking"] + d["summary"]["removed"]
    d["ok"] = d["summary"]["breaking_total"] == 0
    return d


def _bullets(items, cap=_CAP):
    for x in items[:cap]:
        yield f"- `{x}`"
    if len(items) > cap:
        yield f"- _… {len(items) - cap} more_"


def render_apidiff(old: Graph, new: Graph) -> str:
    d = build_apidiff(old, new)
    s = d["summary"]
    out = [f"# API diff — `{old.target}` → `{new.target}`", ""]
    verdict = ("✅ **No breaking changes.**" if d["ok"]
               else f"❌ **{s['breaking_total']} breaking change(s).**")
    out.append(f"{verdict} {s['added']} added, {s['removed']} removed, "
               f"{s['changed_symbols']} changed.")
    out.append("")

    removed = d["removed"]
    if removed:
        out.append(f"## Removed public symbols — breaking ({len(removed)})")
        out.extend(_bullets(removed))
        out.append("")

    by_sev = {BREAKING: [], WARNING: [], INFO: []}
    for c in d["changes"]:
        by_sev[c["severity"]].append(c)
    labels = {BREAKING: "Breaking signature changes", WARNING: "Warnings (review)",
              INFO: "Compatible changes"}
    for sev in (BREAKING, WARNING, INFO):
        rows = by_sev[sev]
        if not rows:
            continue
        out.append(f"## {labels[sev]} ({len(rows)})")
        for c in rows[:_CAP]:
            out.append(f"- `{c['symbol']}` — {c['detail']}")
        if len(rows) > _CAP:
            out.append(f"- _… {len(rows) - _CAP} more_")
        out.append("")

    if d["added"]:
        out.append(f"## Added public symbols ({len(d['added'])})")
        out.extend(_bullets(d["added"]))
        out.append("")
    return "\n".join(out).rstrip() + "\n"
