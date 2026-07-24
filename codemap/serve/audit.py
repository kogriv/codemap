"""Audit reports — consumer C (DESIGN §1-C): dependencies/cycles, dead code."""

from __future__ import annotations

from codemap.query import Query


def render_dependencies(query: Query) -> str:
    g = query.import_graph
    lines = [f"# Module dependencies — `{query.graph.target}`", ""]
    lines.append(f"_{g.number_of_nodes()} modules, {g.number_of_edges()} import edges._")
    lines.append("")

    cycles = query.import_cycles()
    lines.append(f"## Import cycles: {len(cycles)}")
    lines.append("")
    if cycles:
        for cyc in sorted(cycles, key=lambda c: (len(c), c)):
            lines.append(f"- {' → '.join(cyc)} → {cyc[0]}")
    else:
        lines.append("_none — import graph is acyclic._")
    lines.append("")

    lines.append("## Most-depended-on modules (top 15)")
    lines.append("")
    ranked = sorted(g.nodes, key=lambda m: g.in_degree(m), reverse=True)
    for mid in ranked[:15]:
        deg = g.in_degree(mid)
        if deg == 0:
            break
        lines.append(f"- `{mid}` — imported by {deg}")
    return "\n".join(lines).rstrip() + "\n"


def render_dead_code(query: Query) -> str:
    orphans = query.orphan_modules()
    lines = [f"# Dead-code candidates — `{query.graph.target}`", ""]
    lines.append(
        "_Modules with **no incoming imports** (heuristic — static only: dynamic "
        "imports, CLI entry points and test targets are not visible)._"
    )
    lines.append("")
    lines.append(f"## Orphan modules: {len(orphans)}")
    lines.append("")
    if orphans:
        for mid in orphans:
            lines.append(f"- `{mid}`")
    else:
        lines.append("_none._")
    return "\n".join(lines).rstrip() + "\n"
