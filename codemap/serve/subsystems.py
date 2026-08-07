"""Subsystems view — module communities + call flows (R1-C18).

A narrative "what is the system made of, and how does a flow run through it" view,
built natively on codemap's own graph (the GitNexus разбор showed the value —
Leiden clusters + process/flow tracing; we compute it deterministically without
the external dependency). Feeds living docs (R1-C15).

  * :func:`render_communities` — data-driven module subsystems (greedy modularity).
  * :func:`render_flows` — forward call-flow from an entry symbol, or the list of
    detected entry points with their reach when no symbol is given.
"""

from __future__ import annotations

from codemap.query import Query

_CAP = 40  # list cap so a hub subsystem / wide flow stays readable


def render_communities(query: Query) -> str:
    comms = query.communities()
    lines = ["# Subsystems — module communities", ""]
    if not comms:
        lines.append("_No import edges to cluster (core-only or empty graph)._")
        return "\n".join(lines) + "\n"
    lines.append(
        f"_{len(comms)} data-driven clusters via greedy modularity over the import "
        f"graph (deterministic). A cluster = modules that import each other more than "
        f"the rest — a candidate subsystem, labelled by dominant layer._"
    )
    lines.append("")
    for i, c in enumerate(comms, 1):
        lines.append(f"## {i}. {c['label']} — {c['size']} modules")
        for m in c["modules"][:_CAP]:
            lines.append(f"- `{m}`")
        if c["size"] > _CAP:
            lines.append(f"- _… {c['size'] - _CAP} more_")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_flows(query: Query, symbol: str | None = None, *, depth: int = 5) -> str:
    lines = ["# Call flows", ""]
    if symbol is None:
        eps = query.entry_points()
        lines.append(
            f"_{len(eps)} entry points (functions that call out but are never called "
            f"— resolved edges). Forward reach at depth {depth}. Best-effort: call "
            f"resolution is partial, so an unresolved caller can leave a real internal "
            f"here._"
        )
        lines.append("")
        rows = sorted(
            ((query.flow(ep, max_depth=depth)["reached"], ep) for ep in eps),
            reverse=True,
        )
        for reached, ep in rows[:_CAP]:
            lines.append(f"- `{ep}` → reaches {reached}")
        if len(rows) > _CAP:
            lines.append(f"- _… {len(rows) - _CAP} more entry points_")
        return "\n".join(lines).rstrip() + "\n"

    ids = query.impact_targets(symbol)
    if not ids:
        lines.append(f"_No definition found for `{symbol}`._")
        return "\n".join(lines) + "\n"
    for sid in ids:
        f = query.flow(sid, max_depth=depth)
        lines.append(f"## `{sid}` — reaches {f['reached']} (depth {f['max_depth']})")
        lines.append("")
        if not f["edges"]:
            lines.append("_Calls out to nothing resolved — a leaf in the call graph._")
            lines.append("")
            continue
        by_dist: dict[int, list[str]] = {}
        for e in f["edges"]:
            by_dist.setdefault(e["distance"], []).append(f"{e['source']} → {e['target']}")
        for d in sorted(by_dist):
            lines.append(f"### depth {d} — {len(by_dist[d])} calls")
            for pair in by_dist[d][:_CAP]:
                lines.append(f"- `{pair}`")
            if len(by_dist[d]) > _CAP:
                lines.append(f"- _… {len(by_dist[d]) - _CAP} more_")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
