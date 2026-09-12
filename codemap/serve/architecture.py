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


def _tangle_head(tangles: list[dict]) -> str:
    """`N tangle(s) (M modules)` — the count that is stable under adding an edge.

    R1-C58: the previous head counted **simple cycles**, which is combinatorial. A tangle
    of three mutually-dependent modules has one head here and produced five entries there;
    pytest's `_pytest` produced 1080, 95 001 and 464 109 for one tangle each.
    """
    if not tangles:
        return "0"
    return (f"{len(tangles)} tangle(s), {sum(t['size'] for t in tangles)} module(s), "
            f"{sum(t['loops'] for t in tangles)} independent loop(s)")


def _tangle_lines(tangles: list[dict]) -> list[str]:
    """One block per tangle: its members, and one cycle through it as an example."""
    out: list[str] = []
    for tg in tangles:
        if tg["size"] == 1:
            out.append(f"- `{tg['modules'][0]}` — imports itself")
            continue
        out.append(f"- **{tg['size']} modules, {tg['loops']} independent loop(s):** "
                   + ", ".join(f"`{m}`" for m in tg["modules"]))
        ex = tg["example"]
        line = f"  - e.g. {' → '.join(ex)} → {ex[0]}"
        if tg.get("closed_by"):
            line += f" — held together by `{tg['closed_by'][0]}` → `{tg['closed_by'][1]}`"
        out.append(line)
    return out


def build_architecture(query: Query) -> dict:
    """Structured whole-system overview (cycles + layers + coupling + hotspots).

    Three kinds, by the weakest scope that closes the cycle (R1-C49): ``cycles`` break at
    import time, ``lazy_cycles`` need a function-local import (runtime coupling), and
    ``type_only_cycles`` need one under ``if TYPE_CHECKING:`` (no runtime dependency at
    all). Splitting them is the point — a lazy
    import is how a developer *fixes* an import cycle, so folding the two together would
    report someone's fix as their bug, while dropping the second (what this tool did
    until issue #11) hides that the modules are still inseparable. ``import_map`` is
    emitted always, zero included, so a reader can tell "no lazy imports" from "this
    build did not look".
    """
    return {
        "target": query.graph.target,
        # R1-C58: the unit is the tangle (a strongly connected group of modules). The
        # `*_cycles` keys stay, carrying **one example per tangle** — they used to carry
        # every simple cycle, a combinatorial quantity that reached 464 109 entries for a
        # single tangle of 78 modules and said nothing the tangle does not.
        "cycles": query.import_cycles(),
        "lazy_cycles": query.lazy_import_cycles(),
        "type_only_cycles": query.type_only_import_cycles(),
        "tangles": query.import_tangles(),
        "lazy_tangles": query.lazy_import_tangles(),
        "type_only_tangles": query.type_only_import_tangles(),
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
    # R1-C58/D4: a layer is the first path segment under the root. A package with no
    # subpackages therefore has one layer per module, and the section reads as an
    # architectural overview while saying only "this package is flat". Measured on
    # Pillow: "Layers (105)" over 105 modules. Say it instead of implying structure.
    degenerate = bool(lay["layers"]) and all(len(m) == 1 for m in lay["layers"].values())
    out.append(f"## Layers ({len(lay['layers'])})")
    out.append("")
    if degenerate:
        out.append("_This package has no subpackages, so **layer = module** here: the "
                   "grouping below is the module list, and the inter-layer view would "
                   "repeat the import graph edge for edge. Not a statement about "
                   "structure — a statement that there is none to report._")
        out.append("")
    for name, mods in lay["layers"].items():
        out.append(f"- **{name}** — {len(mods)} module(s)")
    out.append("")
    if not degenerate:
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
    out.append(f"## Import cycles: {_tangle_head(a['tangles'])}")
    out.append("")
    out.append("_A **tangle** is a group of modules that cannot be separated — the unit you "
               "would act on — and its **independent loops** are how many distinct ways it "
               "closes (the cycle rank). The number of *simple* cycles is combinatorial (one "
               "19-module tangle of a real package has 1080, and its 78-module tangle has "
               "464 109) and is deliberately not reported; one example cycle per tangle is._")
    out.append("")
    out.extend(_tangle_lines(a["tangles"])
               or ["_none found in the eager import graph._"])
    out.append("")
    out.append(f"_Read {im['module_level']} module-level, {im['function_local']} "
               f"function-local, {im['type_checking']} `TYPE_CHECKING` and {im['stub']} "
               f"`.pyi` import(s). Only module-level imports run at import time, so only "
               f"they can break on import; an import under `if TYPE_CHECKING:` never runs, "
               f"and a `.pyi` is not executed at all._")
    out.append("")
    if a["lazy_cycles"]:
        out.append(f"### Dependency cycles closed only by a function-local import: "
                   f"{_tangle_head(a['lazy_tangles'])}")
        out.append("")
        out.append("_These do **not** break at import time — the lazy import is what "
                   "prevents that, and is usually deliberate. They are listed because "
                   "the modules are still mutually dependent at run time: neither can be "
                   "extracted without the other._")
        out.append("")
        out.extend(_tangle_lines(a["lazy_tangles"]))
        out.append("")
    if a["type_only_cycles"]:
        # R1-C49: the third kind, kept apart from the second because the difference is the
        # whole point — these modules have no runtime dependency on each other at all.
        out.append(f"### Dependency cycles closed only by an import that never runs "
                   f"(`if TYPE_CHECKING:` or a `.pyi`): {_tangle_head(a['type_only_tangles'])}")
        out.append("")
        out.append("_Neither module pulls the other at any moment of execution — they name "
                   "each other's types. Not an import-time failure and not runtime coupling; "
                   "`no_type_only_cycles = true` gates them if the type layer must not close "
                   "a cycle either._")
        out.append("")
        out.extend(_tangle_lines(a["type_only_tangles"]))
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
