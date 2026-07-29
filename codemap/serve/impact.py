"""Impact / blast-radius report — consumer C (DESIGN §10.12, M6).

"Can I change / remove X, and what breaks?" — the question the single-package
graph could not answer (the blast radius lives in tests/docs/examples, outside
the package; dogfood F1). Needs a repo-scoped graph (``extract_repo``); on a
core-only graph it simply reports in-package references.
"""

from __future__ import annotations

from codemap.query import Query


def render_impact(query: Query, symbol: str, *, depth: int = 2) -> str:
    """Markdown blast-radius for the symbol matching ``symbol`` (short or full)."""
    matches = query.find(symbol)
    ids = [n.id for n in matches] or query.where_defined(symbol)
    lines = [f"# Impact — `{symbol}`", ""]
    lines.append(
        "_Best-effort static blast radius: who references the symbol (and its "
        "members), grouped by repo root. Call resolution is partial (gaps/ CM-09), "
        "so this is a **lower bound** — pair with grep before deleting._"
    )
    lines.append("")
    if not ids:
        lines.append(f"_No definition found for `{symbol}`._")
        return "\n".join(lines) + "\n"

    for sid in ids:
        rep = query.impact(sid, depth=depth)
        refs = rep["refs"]
        by_root = rep["by_root"]
        lines.append(f"## `{sid}`")
        lines.append("")
        if not refs:
            lines.append("_No inbound references — isolated in the analysed roots._")
            lines.append("")
            continue
        total = len(refs)
        roots = ", ".join(f"{r} ({sum(by_root[r].values())})" for r in sorted(by_root))
        lines.append(f"**{total} references across roots:** {roots}")
        lines.append("")
        # per-root breakdown, direct refs first.
        for root in sorted(by_root):
            counts = ", ".join(f"{t}×{c}" for t, c in sorted(by_root[root].items()))
            lines.append(f"### {root} — {counts}")
            direct = sorted(
                {r["source"] for r in refs if r["root"] == root and r["distance"] == 1}
            )
            for src in direct[:40]:
                lines.append(f"- `{src}`")
            if len(direct) > 40:
                lines.append(f"- _… {len(direct) - 40} more_")
            indirect = {r["source"] for r in refs if r["root"] == root and r["distance"] > 1}
            if indirect:
                lines.append(f"- _+{len(indirect)} transitive (distance >1)_")
            lines.append("")

        # F7: argument contract of the call-sites — what a signature change touches.
        contract = query.call_contract(sid)
        if contract:
            sites = sum(c["callsites"] for c in contract)
            lines.append(f"### Call-site contract ({sites} sites — for signature change)")
            lines.append("")
            for c in contract:
                pos = "/".join(map(str, c["posargs"])) or "0"
                kw = ", ".join(c["kwargs"]) or "—"
                splat = " +splat" if c["splat"] else ""
                lines.append(
                    f"- `{c['caller']}` ×{c['callsites']} — {pos} positional, kwargs: {kw}{splat}"
                )
            lines.append("")
            lines.append(
                "_Positional counts / kwarg names observed at the call-sites (resolved "
                "edges only). Use to see which sites break under an arity/keyword change._"
            )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
