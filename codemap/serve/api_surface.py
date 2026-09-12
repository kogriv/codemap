"""API-surface report — view D (DESIGN §4.1-D), the M0 deliverable.

The public surface of the target: public symbols grouped by module, with
signatures, first docstring line and a deprecated marker. Reads the canonical
graph; renders Markdown.
"""

from __future__ import annotations

from collections import defaultdict

from codemap.diagnostics import diagnostics, render_lines
from codemap.model import Graph

_SYMBOL_KINDS = {"class", "function", "attribute"}


def build_api_surface(graph: Graph) -> dict:
    """The same report as :func:`render_api_surface`, structured (R1-C32, issue #14).

    `report --format json` used to print the whole graph for every kind, so a consumer
    that asked for this report parsed a valid document that was not the one it asked for.
    Same content as the markdown, one level deeper: the caller gets each symbol's kind,
    signature, deprecation and first docstring line without parsing prose.
    """
    by_module: dict[str, list] = defaultdict(list)
    for node in graph.nodes.values():
        if node.visibility != "public" or node.kind not in _SYMBOL_KINDS:
            continue
        by_module[node.id.rsplit(".", 1)[0]].append(node)
    public_modules = sorted(
        n.id for n in graph.nodes.values() if n.kind == "module" and n.visibility == "public"
    )
    modules = []
    for module in public_modules:
        symbols = sorted(by_module.get(module, []), key=lambda n: n.id)
        if not symbols:
            continue
        modules.append({"module": module, "symbols": [
            {"id": n.id, "name": n.id.rsplit(".", 1)[1], "kind": n.kind,
             "signature": n.signature, "deprecated": bool(n.is_deprecated),
             "doc": _first_line(n.docstring), "file": n.file, "lineno": n.lineno}
            for n in symbols
        ]})
    reexported = _reexported_from_outside(graph)
    return {
        "kind": "api-surface",
        "target": graph.target,
        "totals": {"symbols": sum(len(m["symbols"]) for m in modules),
                   "modules_with_symbols": len(modules),
                   "public_modules": len(public_modules),
                   # R1-C57: always present, zero included — a reader must not have to
                   # tell "this package re-exports nothing" from "we did not look".
                   "reexported_from_outside": len(reexported)},
        "modules": modules,
        "reexported_from_outside": reexported,
        "diagnostics": diagnostics(graph),
    }


def _reexported_from_outside(graph: Graph) -> list[dict]:
    """Public names this package exposes whose definition lives outside it (R1-C57).

    The facade layout — `pytest` re-exporting 90 names from `_pytest`, `attrs` from
    `attr` — has almost no symbols of its own, so counting nodes reported a public
    surface of **one** for a package whose whole purpose is its API. These names are
    the surface; the definitions are simply not in this graph, and the answer says so
    instead of omitting them.
    """
    out = []
    for e in graph.edges:
        if e.type == "export" and e.extras.get("external") and e.extras.get("public"):
            out.append({"name": e.extras.get("as", ""), "module": e.source,
                        "defined_at": e.target})
    return sorted(out, key=lambda r: (r["module"], r["name"]))


def render_api_surface(graph: Graph) -> str:
    """Render the public API surface of ``graph`` as Markdown."""
    by_module: dict[str, list] = defaultdict(list)
    for node in graph.nodes.values():
        if node.visibility != "public" or node.kind not in _SYMBOL_KINDS:
            continue
        module = node.id.rsplit(".", 1)[0]
        by_module[module].append(node)

    lines = [f"# API surface — `{graph.target}`", ""]
    # R1-C57: every other report carried the build's diagnostics and this one did not, so
    # a facade package printed its surface with no hint that the import graph behind it was
    # empty. A warning that reaches four reports out of five is a warning the reader can
    # miss by asking the wrong question.
    lines.extend(render_lines(graph))
    public_modules = sorted(
        n.id for n in graph.nodes.values() if n.kind == "module" and n.visibility == "public"
    )
    total = sum(len(v) for v in by_module.values())
    reexported = _reexported_from_outside(graph)
    lines.append(f"_{total} public symbols across {len(public_modules)} modules; "
                 f"{len(reexported)} more re-exported from outside this root._")
    lines.append("")
    if reexported:
        lines.append(f"> ⚠ This package exposes **{len(reexported)}** name(s) it does not "
                     f"define — the facade layout. Their definitions are in another root "
                     f"and are **not judged here**; build that package to see them.")
        lines.append("")

    for module in public_modules:
        symbols = sorted(by_module.get(module, []), key=lambda n: n.id)
        if not symbols:
            continue
        lines.append(f"## `{module}`")
        lines.append("")
        for node in symbols:
            name = node.id.rsplit(".", 1)[1]
            head = node.signature or name
            marker = " **⚠ deprecated**" if node.is_deprecated else ""
            lines.append(f"- **`{head}`** ({node.kind}){marker}")
            doc = _first_line(node.docstring)
            if doc:
                lines.append(f"  - {doc}")
        lines.append("")

    if reexported:
        lines.append("## Re-exported from outside this root")
        lines.append("")
        for r in reexported:
            lines.append(f"- **`{r['name']}`** → `{r['defined_at']}` (via `{r['module']}`)")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _first_line(docstring: str | None) -> str | None:
    if not docstring:
        return None
    for line in docstring.strip().splitlines():
        line = line.strip()
        if line:
            return line
    return None
