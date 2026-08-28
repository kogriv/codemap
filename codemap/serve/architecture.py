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

from codemap.diagnostics import render_lines
from codemap.query import Query


def build_architecture(query: Query) -> dict:
    """Structured whole-system overview (cycles + layers + coupling + hotspots).

    R1-C29: ``cycles`` are the **import-time** ones and ``lazy_cycles`` the dependency
    cycles closed only by a function-local import. Splitting them is the point — a lazy
    import is how a developer *fixes* an import cycle, so folding the two together would
    report someone's fix as their bug, while dropping the second (what this tool did
    until issue #11) hides that the modules are still inseparable. ``import_map`` is
    emitted always, zero included, so a reader can tell "no lazy imports" from "this
    build did not look".
    """
    return {
        "target": query.graph.target,
        "cycles": query.import_cycles(),
        "lazy_cycles": query.lazy_import_cycles(),
        "import_map": query.import_map(),
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
    # R1-C21: with an empty import graph, "no layer violations" and "acyclic" below are
    # *vacuous*, not clean. Each check states its own consequence (issue #8).
    out.extend(render_lines(query.graph))

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
    # R1-C29: never state acyclicity as a property. The map is only as complete as the
    # imports it read, and the reader cannot see which those were unless we say so.
    im = a["import_map"]
    out.append(f"## Import cycles: {len(a['cycles'])}")
    out.append("")
    out.extend([f"- {' → '.join(c)} → {c[0]}" for c in
                sorted(a["cycles"], key=lambda c: (len(c), c))]
               or ["_none found in the eager import graph._"])
    out.append("")
    out.append(f"_Read {im['module_level']} module-level and {im['function_local']} "
               f"function-local import(s). Only module-level imports run at import time, "
               f"so only they can break on import._")
    out.append("")
    if a["lazy_cycles"]:
        out.append(f"### Dependency cycles closed only by a function-local import: "
                   f"{len(a['lazy_cycles'])}")
        out.append("")
        out.append("_These do **not** break at import time — the lazy import is what "
                   "prevents that, and is usually deliberate. They are listed because "
                   "the modules are still mutually dependent: neither can be extracted "
                   "without the other._")
        out.append("")
        out.extend(f"- {' → '.join(c)} → {c[0]}" for c in
                   sorted(a["lazy_cycles"], key=lambda c: (len(c), c))[:20])
        if len(a["lazy_cycles"]) > 20:
            out.append(f"- _… {len(a['lazy_cycles']) - 20} more_")
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
    out.append("_methods = concentration of behaviour; ΣCC / maxCC = McCabe complexity across them._")
    out.append("")
    out.extend([f"- `{g['class']}` — {g['methods']} methods, ΣCC {g['total_cc']}, maxCC {g['max_cc']}"
                for g in hs["god_classes"]] or ["_none above threshold._"])
    out.append("")
    complex_fns = hs.get("complex_functions", [])
    out.append(f"## Most complex functions (cyclomatic ≥ threshold): {len(complex_fns)}")
    out.append("")
    out.append("_CC = McCabe cyclomatic; MI = Maintainability Index (0–100, higher is better)._")
    out.append("")
    out.extend([f"- `{f['id']}` — CC {f['cc']}, MI {f['mi']} ({f['sloc']} sloc)"
                for f in complex_fns] or ["_none above threshold._"])
    out.append("")
    out.append("## Call-graph hubs (in+out degree)")
    out.append("")
    out.append("_`pervasive` = logging/util that hubs by nature — expected noise, not risk._")
    out.append("")
    for h in hs["call_hubs"][:12]:
        tag = " _(pervasive)_" if h["pervasive"] else ""
        out.append(f"- `{h['id']}` — {h['degree']}{tag}")
    return "\n".join(out).rstrip() + "\n"
