"""Impact / blast-radius report — consumer C (DESIGN §10.12, M6).

"Can I change / remove X, and what breaks?" — the question the single-package
graph could not answer (the blast radius lives in tests/docs/examples, outside
the package; dogfood F1). Needs a repo-scoped graph (``extract_repo``); on a
core-only graph it simply reports in-package references.
"""

from __future__ import annotations

from codemap.query import Query


_FLOW_ROWS = 40


def _flow_section(rep: dict) -> list[str]:
    """R1-C40: which scenarios the change lands on, and at which step.

    The three partialities of `Query.flows_to` are rendered as words, not left for the
    reader to infer from a short list: an empty flow list next to twenty references is
    the exact shape that reads as "nothing will break" when it means "the flow layer
    cannot see this kind of edge".
    """
    lines = [f"### Flows reached ({len(rep['flows'])} of {rep['entry_points']} "
             f"entry point(s) in root `{rep['root']}`)", ""]
    if not rep["in_call_graph"]:
        lines += ["_The call layer never modelled this symbol — no resolved call reaches "
                  "it or leaves it — so there is nothing to say about flows here. This is "
                  "not 'no flow reaches it'._", ""]
        return lines
    if rep["flows"]:
        lines.append("_`step` — where in the flow the change first lands: 1 means the "
                     "entry point calls it directly, 0 that the entry point is the "
                     "symbol itself (or one of its members), so the flow starts inside "
                     "the change._")
        lines.append("")
        for f in rep["flows"][:_FLOW_ROWS]:
            ext = f.get("external_callers") or {}
            tail = ("  _(entered from " + ", ".join(f"{r} ×{n}" for r, n in ext.items())
                    + ")_" if ext else "")
            lines.append(f"- `{f['entry']}` — step {f['first_step']}{tail}")
        if len(rep["flows"]) > _FLOW_ROWS:
            lines.append(f"- _… {len(rep['flows']) - _FLOW_ROWS} more_")
    elif rep["nearest_beyond"] is not None:
        # R1-C50/D9: an empty list with a head one step past the bound is not the same
        # answer as an empty list, and it is the one a reader can act on.
        lines.append(f"_No entry point within {rep['max_depth']} step(s) — but "
                     f"{rep['beyond_depth']} reach it further out, the nearest at step "
                     f"**{rep['nearest_beyond']}**. Re-run with `--flow-depth "
                     f"{rep['nearest_beyond']}` to see them._")
    elif rep["inbound_calls"]:
        lines.append(f"_No entry point reaches it, at any depth — yet {rep['inbound_calls']} "
                     "resolved call(s) do reach it. Every chain above it is either closed "
                     "in a call cycle (no head to start from) or starts outside root "
                     f"`{rep['root']}`. Not 'nothing calls it'._")
    else:
        lines.append(f"_No entry point reaches it within {rep['max_depth']} step(s), and "
                     "no resolved call reaches it either._")
    lines.append("")
    notes = []
    if rep["beyond_depth"] and rep["flows"]:
        notes.append(f"{rep['beyond_depth']} further entry point(s) reach it **beyond** "
                     f"{rep['max_depth']} steps (nearest at step "
                     f"{rep['nearest_beyond']}) — counted, not listed.")
    if rep["non_call_refs"]:
        notes.append(f"{rep['non_call_refs']} direct reference(s) arrive by an edge that "
                     "is not a call (import / inheritance / decoration / attribute) and "
                     "cannot appear in a flow at all.")
    notes.append("Flows follow resolved `calls` edges only, and the entry-point set is "
                 "best-effort in **both** directions: an unresolved caller leaves a real "
                 "internal looking like an entry point (the denominator is an upper "
                 "bound), while resolving one *removes* an entry point and can lengthen "
                 "a chain past `--flow-depth` — so a **more** complete graph can answer "
                 "with **fewer** flows. A call from another root (`tests`, `examples`) is "
                 "a use, not an internal caller, and does not disqualify a head. "
                 "*Reached*, not *broken*: the graph knows the symbol is on the path, not "
                 "whether the change breaks it.")
    lines.append("_" + " ".join(notes) + "_")
    lines.append("")
    return lines


def render_impact(query: Query, symbol: str, *, depth: int = 2,
                  flow_depth: int = 5) -> str:
    """Markdown blast-radius for the symbol matching ``symbol`` (short or full)."""
    ids = query.impact_targets(symbol)  # F23: short name / full id / re-export
    lines = [f"# Impact — `{symbol}`", ""]
    lines.append(
        "_Best-effort static blast radius: who references the symbol (and its "
        "members), grouped by repo root. Call resolution is partial (gaps/ CM-09), "
        "so this is a **lower bound** — pair with grep before deleting._"
    )
    lines.append("")
    if not ids:
        lines.append(f"_No definition found for `{symbol}` — nothing is known about it; "
                     "this is not an empty blast radius. Check the name (ids start with "
                     "the package directory's name)._")
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
        # R1-C19: risk triage + depth histogram (transitive reach at a glance).
        hist = ", ".join(f"d{d}×{rep['by_distance'][d]}" for d in sorted(rep["by_distance"]))
        lines.append(
            f"**Risk: {rep['risk'].upper()}** — depth reached {rep['max_distance']}"
            + (f"; distances: {hist}" if hist else "")
            + " _(heuristic: breadth × reach × root-spread)_"
        )
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

        # R1-C40: from "who references" to "what stops working, and where".
        lines += _flow_section(query.flows_to(sid, max_depth=flow_depth))

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
