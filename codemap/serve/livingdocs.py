"""Living docs — a narrative document generated from the graph (R1-C15).

The honest answer to "auto-generated codebase wiki". Tools like CodeWiki / neuro-
articles narrate what code *does* by guessing; codemap only states what the graph
proves. Everything here is traceable: structure (modules/classes/functions/imports/
inheritance) is exact static fact; docstrings are the authors' own words, quoted
verbatim — never generated, and an undocumented symbol is *marked*, not invented;
call-flow-derived claims carry the static lower-bound caveat (epistemic: partial).

Organised by **discovered subsystem** (communities, R1-C18) rather than a flat
module list — "what is this made of, and how does it run" — and deterministic, so
re-running refreshes it (the "living" part). Feeds nothing it can't cite.
"""

from __future__ import annotations

from collections import defaultdict

from codemap.model import Graph
from codemap.query import Query

_SYM_KINDS = {"class", "function"}
_PER_SUBSYSTEM = 25   # symbols listed per subsystem before "+N more"
_ENTRY_POINTS = 15    # behavioural entry points listed
_FLOW_DEPTH = 4


def _first_line(docstring: str | None) -> str | None:
    if not docstring:
        return None
    for line in docstring.strip().splitlines():
        if line.strip():
            return line.strip()
    return None


def _module_of(node_id: str) -> str:
    return node_id.rsplit(".", 1)[0]


def _public_symbols_by_module(graph: Graph) -> dict[str, list]:
    """Public top-level class/function nodes of the **core** package, by module id.

    Core only: living docs document the package, not its tests/docs/examples
    (consumer roots), which on a repo-scoped graph would otherwise leak in.
    """
    by_module: dict[str, list] = defaultdict(list)
    for n in graph.nodes.values():
        if (n.kind in _SYM_KINDS and n.visibility == "public"
                and n.extras.get("root", "core") == "core"):
            by_module[_module_of(n.id)].append(n)
    return by_module


def _render_symbol(n) -> list[str]:
    name = n.id.rsplit(".", 1)[-1]
    head = n.signature or name
    marker = " **⚠ deprecated**" if n.is_deprecated else ""
    doc = _first_line(n.docstring)
    line = f"- **`{head}`** ({n.kind}){marker}"
    return [line, f"  - {doc}"] if doc else [line, "  - _(undocumented)_"]


def render_docs(query: Query) -> str:
    graph = query.graph
    target = graph.target
    by_module = _public_symbols_by_module(graph)
    kinds = defaultdict(int)
    for n in graph.nodes.values():
        kinds[n.kind] += 1
    total_public = sum(len(v) for v in by_module.values())

    out = [f"# {target} — living documentation", ""]
    out.append(
        f"_{kinds['module']} modules · {kinds['class']} classes · {kinds['function']} "
        f"functions · {total_public} public symbols. Generated from the code graph — "
        f"structure is exact static fact; docstrings are the authors' own words, "
        f"quoted verbatim._"
    )
    out.append("")

    # -- subsystems (communities) -------------------------------------------
    comms = query.communities()
    grouped_modules: set[str] = set()
    out.append("## Subsystems")
    out.append("")
    if not comms:
        out.append("_No import edges to cluster — see the module list below._")
        out.append("")
    for i, c in enumerate(comms, 1):
        out.append(f"### {i}. {c['label']} — {c['size']} modules")
        out.append("")
        syms = []
        for m in c["modules"]:
            grouped_modules.add(m)
            syms.extend(sorted(by_module.get(m, []), key=lambda n: n.id))
        if not syms:
            out.append("_No public symbols (internal-only subsystem)._")
            out.append("")
            continue
        for n in syms[:_PER_SUBSYSTEM]:
            out.extend(_render_symbol(n))
        if len(syms) > _PER_SUBSYSTEM:
            out.append(f"- _… {len(syms) - _PER_SUBSYSTEM} more public symbols_")
        out.append("")

    # -- ungrouped modules (completeness: nothing dropped) ------------------
    ungrouped = sorted(
        m for m in by_module
        if m not in grouped_modules and query.root_of(m) == "core" and by_module[m]
    )
    if ungrouped:
        out.append("## Other modules (no import clustering)")
        out.append("")
        for m in ungrouped:
            out.append(f"### `{m}`")
            out.append("")
            for n in sorted(by_module[m], key=lambda n: n.id)[:_PER_SUBSYSTEM]:
                out.extend(_render_symbol(n))
            out.append("")

    # -- behavioural entry points (flows) -----------------------------------
    eps = query.entry_points()
    if eps:
        out.append("## Behavioural entry points")
        out.append("")
        out.append(
            f"_Where execution starts — functions that call out but are never called "
            f"(resolved edges). Reach = symbols touched within {_FLOW_DEPTH} calls. "
            f"**Static lower bound** (epistemic: partial): Python call resolution is "
            f"incomplete, so an unresolved caller can leave a real internal here._"
        )
        out.append("")
        ranked = sorted(
            ((query.flow(ep, max_depth=_FLOW_DEPTH)["reached"], ep) for ep in eps),
            reverse=True,
        )
        for reached, ep in ranked[:_ENTRY_POINTS]:
            out.append(f"- `{ep}` → reaches {reached}")
        if len(ranked) > _ENTRY_POINTS:
            out.append(f"- _… {len(ranked) - _ENTRY_POINTS} more entry points_")
        out.append("")

    # -- architecture caveats (the honest health section) -------------------
    cycles = query.import_cycles()
    lazy = query.lazy_import_cycles()
    lay = query.layers()
    gods = query.hotspots()["god_classes"]
    out.append("## Architecture notes")
    out.append("")
    if cycles:
        out.append(f"- **{len(cycles)} import cycle(s)** — e.g. "
                   + "; ".join(" → ".join(c) for c in sorted(cycles, key=len)[:3]))
    else:
        # R1-C29: no cycle *found*, over the imports that run at import time — not a
        # proof of acyclicity, which this map cannot support.
        out.append("- No import cycle found in the eager import graph.")
    if lazy:
        out.append(f"- **{len(lazy)} dependency cycle(s) closed only by a function-local "
                   f"import** — deliberate, and still mutual coupling.")
    if lay["violations"]:
        out.append("- **Layer violations (mutual dependency):** "
                   + ", ".join(f"{a} ↔ {b}" for a, b in lay["violations"]))
    if gods:
        out.append("- **God-object candidates:** "
                   + ", ".join(f"`{g['class']}` ({g['methods']} methods)" for g in gods[:5]))
    out.append("")

    # -- honesty footer -----------------------------------------------------
    out.append("---")
    out.append("")
    out.append(
        "_Generated by codemap from the canonical code graph. **Exact:** modules, "
        "classes, functions, imports, inheritance (static parse). **Verbatim:** "
        "docstrings — the authors' words, never generated; undocumented symbols are "
        "marked, not invented. **Lower bound (epistemic: partial):** call-flows and "
        "entry-point reach — Python dynamism is not fully statically resolvable. "
        "Deterministic — re-run to refresh._"
    )
    return "\n".join(out).rstrip() + "\n"
