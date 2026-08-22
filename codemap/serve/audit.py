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


def load_dead_code_whitelist(root: str | None) -> tuple[str, ...]:
    """Read ``[dead_code].whitelist`` (exact ids / globs) from codemap.toml under ``root``.

    Empty on absent/malformed file — a bad whitelist must never break a report.
    """
    from pathlib import Path
    if not root:
        return ()
    path = Path(root) / "codemap.toml"
    if not path.is_file():
        return ()
    try:
        import tomllib
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ModuleNotFoundError):
        return ()
    return tuple(data.get("dead_code", {}).get("whitelist", []) or [])


def render_dead_code(query: Query, *, whitelist: tuple[str, ...] = (),
                     min_confidence: str | None = None) -> str:
    by_root = query.orphan_modules_by_root()
    core_orphans = by_root.get("core", [])
    consumer = {r: v for r, v in by_root.items() if r != "core"}
    dead = query.dead_code(whitelist=whitelist, min_confidence=min_confidence)
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
    # R1-C8: uncalled private functions, graded by confidence with a provenance reason.
    lines.append("")
    filt = f" (min-confidence: {min_confidence})" if min_confidence else ""
    wl = f", {len(whitelist)} whitelisted pattern(s)" if whitelist else ""
    lines.append(f"## Uncalled private functions: {len(dead)}{filt}{wl}")
    lines.append("")
    lines.append("_Private functions with no incoming resolved call, graded by how sure. "
                 "**high** = no inbound edge or hook; **medium** = a decorator/registry "
                 "may invoke it implicitly; **low** = something references it (likely alive)._")
    lines.append("")
    if not dead:
        lines.append("_none._")
    for level in ("high", "medium", "low"):
        rows = [c for c in dead if c["confidence"] == level]
        if not rows:
            continue
        lines.append(f"### {level} ({len(rows)})")
        lines.append("")
        for c in rows:
            reason = "; ".join(c["reasons"])
            lines.append(f"- `{c['id']}` — {reason}")
        lines.append("")
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

    # -- complexity (R1-C4) -------------------------------------------------
    scored = [(n, n.extras["complexity"]) for n in funcs if "complexity" in n.extras]
    if scored:
        ccs = [m["cc"] for _, m in scored]
        avg_cc = sum(ccs) / len(ccs)
        top = sorted(scored, key=lambda x: (-x[1]["cc"], x[0].id))[:10]
        lines.append("")
        lines.append(f"## Complexity ({len(scored)} functions, mean CC {avg_cc:.1f})")
        lines.append("")
        lines.append("_CC = McCabe cyclomatic; MI = Maintainability Index (0–100, higher is better)._")
        lines.append("")
        for n, m in top:
            lines.append(f"- `{n.id}` — CC {m['cc']}, MI {m['mi']} ({m['sloc']} sloc)")
    return "\n".join(lines).rstrip() + "\n"
