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
    by_root = query.orphan_modules_by_root()
    core_orphans = by_root.get("core", [])
    consumer = {r: v for r, v in by_root.items() if r != "core"}
    dead = query.dead_symbols()
    lines = [f"# Dead-code candidates — `{query.graph.target}`", ""]
    lines.append(
        "_Static heuristics only — dynamic imports, CLI entry points, test targets "
        "and partial call resolution (~1/4 of sites, gaps/ CM-09) are blind spots. "
        "**Candidates, not proof.**_"
    )
    lines.append("")
    # F8: on a repo-scoped graph, consumer roots are orphan by nature (nobody
    # imports an entrypoint). Only core orphans are candidate dead code.
    lines.append(f"## Orphan modules — core (no incoming imports): {len(core_orphans)}")
    lines.append("")
    lines.extend([f"- `{mid}`" for mid in core_orphans] or ["_none._"])
    if consumer:
        total = sum(len(v) for v in consumer.values())
        breakdown = ", ".join(f"{r} {len(v)}" for r, v in sorted(consumer.items()))
        lines.append("")
        lines.append(f"## Consumer entrypoints (orphan by nature, not dead code): {total}")
        lines.append("")
        lines.append(
            f"_{breakdown} — tests/examples/scripts/research are never imported; "
            "expected orphan. Excluded from dead-code candidates (F8)._"
        )
    lines.append("")
    lines.append(f"## Uncalled private functions: {len(dead)}")
    lines.append("")
    lines.append("_Private functions with no incoming resolved call._")
    lines.append("")
    lines.extend([f"- `{sid}`" for sid in dead] or ["_none._"])
    return "\n".join(lines).rstrip() + "\n"


def render_behavior(query: Query) -> str:
    """Consumer A/C: honest call-graph coverage + type-flow spot-check (M4)."""
    graph = query.graph
    funcs = [n for n in graph.nodes.values() if n.kind == "function"]
    with_cov = [n for n in funcs if "calls" in n.extras]
    agg = {"out": 0, "resolved": 0, "external": 0, "unresolved": 0, "dynamic": 0}
    for n in with_cov:
        for k, v in n.extras["calls"].items():
            agg[k] += v
    total = agg["out"] or 1
    lines = [f"# Behavioral layer — `{graph.target}`", ""]
    lines.append(
        "_Best-effort static call-graph (DESIGN §7). Calls on local variables need "
        "type inference and are left unresolved on purpose (gaps/ CM-09/10)._"
    )
    lines.append("")
    lines.append(f"## Call-site resolution ({agg['out']} sites in {len(with_cov)} functions)")
    lines.append("")
    lines.append(f"- resolved to internal edges: **{agg['resolved']}** ({100*agg['resolved']/total:.1f}%)")
    lines.append(f"- external / builtin (flagged): {agg['external']} ({100*agg['external']/total:.1f}%)")
    lines.append(f"- dynamic string-keyed: {agg['dynamic']} ({100*agg['dynamic']/total:.1f}%)")
    lines.append(f"- unresolved (local vars — parked): {agg['unresolved']} ({100*agg['unresolved']/total:.1f}%)")
    lines.append("")
    by_res: dict[str, int] = {}
    for e in graph.edges:
        if e.type == "calls":
            by_res[e.extras.get("resolution", "?")] = by_res.get(e.extras.get("resolution", "?"), 0) + 1
    calls_edges = sum(by_res.values())
    lines.append(f"_Emitted {calls_edges} `calls` edges (deduped caller→callee)._")
    bridged = by_res.get("registry", 0) + by_res.get("registry-candidate", 0)
    if bridged:
        lines.append("")
        lines.append(
            f"## Registry-bridged dispatch (M7): {bridged} edges "
            f"({by_res.get('registry', 0)} exact, {by_res.get('registry-candidate', 0)} candidate)"
        )
        lines.append("")
        lines.append(
            "_Factory/registry seams (`create_x`, `Registry.get`) bridged to registered "
            "impls via the M1.5 table. **Candidate** edges are an over-approximation "
            "(dispatches to one of a family) — real for navigation, not for exact counts._"
        )
    return "\n".join(lines).rstrip() + "\n"
