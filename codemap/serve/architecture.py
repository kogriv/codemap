"""Architecture overview — the whole-system shape in one view (M16 / A9).

The A9 dogfood found every local view existed (symbol, diff, column) but no
*global* one: an architect asking "what shape is this system?" had only
``report dependencies`` (import cycles + in-degree). This synthesises the pieces
already in the graph — import cycles, **layers** + direction/violations (F18),
**coupling** Ca/Ce/instability (F19), **god-objects & call-hubs** (F20) — into one
report. No schema change: pure aggregation over the import graph / calls / contains
/ provenance.
"""

from __future__ import annotations

from codemap.query import Query


def build_architecture(query: Query) -> dict:
    """Structured whole-system overview (cycles + layers + coupling + hotspots)."""
    return {
        "target": query.graph.target,
        "cycles": query.import_cycles(),
        "layers": query.layers(),
        "coupling": query.coupling(),
        "hotspots": query.hotspots(),
    }


def render_architecture(query: Query) -> str:
    """Human markdown for the architecture overview (highest-signal first)."""
    a = build_architecture(query)
    ig = query.import_graph
    core_mods = [m for m in ig.nodes if query.root_of(m) == "core"]
    out = [f"# Architecture overview — `{a['target']}`", ""]
    out.append(f"_{len(core_mods)} core modules, {ig.number_of_edges()} import edges._")
    out.append("")

    # -- layers -------------------------------------------------------------
    lay = a["layers"]
    out.append(f"## Layers ({len(lay['layers'])})")
    out.append("")
    for name, mods in lay["layers"].items():
        out.append(f"- **{name}** — {len(mods)} module(s)")
    out.append("")
    out.append("### Inter-layer dependencies")
    out.append("")
    out.extend([f"- {edge} ({n})" for edge, n in lay["edges"].items()] or ["_none._"])
    out.append("")
    if lay["violations"]:
        out.append("### ⚠ Layer violations (mutual dependency)")
        out.append("")
        out.extend(f"- {a} ↔ {b}" for a, b in lay["violations"])
    else:
        out.append("_No layer violations (no mutually-dependent layer pair)._")
    out.append("")

    # -- cycles -------------------------------------------------------------
    out.append(f"## Import cycles: {len(a['cycles'])}")
    out.append("")
    out.extend([f"- {' → '.join(c)} → {c[0]}" for c in
                sorted(a["cycles"], key=lambda c: (len(c), c))]
               or ["_none — import graph is acyclic._"])
    out.append("")

    # -- coupling -----------------------------------------------------------
    out.append("## Coupling (top by afferent Ca)")
    out.append("")
    out.append("_Ca = depended-on-by, Ce = depends-on, I = Ce/(Ca+Ce): 0 stable → 1 unstable._")
    out.append("")
    for r in a["coupling"][:12]:
        out.append(f"- `{r['module']}` — Ca {r['ca']}, Ce {r['ce']}, I {r['instability']:.2f}")
    out.append("")

    # -- hotspots -----------------------------------------------------------
    hs = a["hotspots"]
    out.append(f"## God-object candidates (≥ methods): {len(hs['god_classes'])}")
    out.append("")
    out.extend([f"- `{g['class']}` — {g['methods']} methods" for g in hs["god_classes"]]
               or ["_none above threshold._"])
    out.append("")
    out.append("## Call-graph hubs (in+out degree)")
    out.append("")
    out.append("_`pervasive` = logging/util that hubs by nature — expected noise, not risk._")
    out.append("")
    for h in hs["call_hubs"][:12]:
        tag = " _(pervasive)_" if h["pervasive"] else ""
        out.append(f"- `{h['id']}` — {h['degree']}{tag}")
    return "\n".join(out).rstrip() + "\n"
