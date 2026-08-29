"""API-surface report — view D (DESIGN §4.1-D), the M0 deliverable.

The public surface of the target: public symbols grouped by module, with
signatures, first docstring line and a deprecated marker. Reads the canonical
graph; renders Markdown.
"""

from __future__ import annotations

from collections import defaultdict

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
    return {
        "kind": "api-surface",
        "target": graph.target,
        "totals": {"symbols": sum(len(m["symbols"]) for m in modules),
                   "modules_with_symbols": len(modules),
                   "public_modules": len(public_modules)},
        "modules": modules,
    }


def render_api_surface(graph: Graph) -> str:
    """Render the public API surface of ``graph`` as Markdown."""
    by_module: dict[str, list] = defaultdict(list)
    for node in graph.nodes.values():
        if node.visibility != "public" or node.kind not in _SYMBOL_KINDS:
            continue
        module = node.id.rsplit(".", 1)[0]
        by_module[module].append(node)

    lines = [f"# API surface — `{graph.target}`", ""]
    public_modules = sorted(
        n.id for n in graph.nodes.values() if n.kind == "module" and n.visibility == "public"
    )
    total = sum(len(v) for v in by_module.values())
    lines.append(f"_{total} public symbols across {len(public_modules)} modules._")
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

    return "\n".join(lines).rstrip() + "\n"


def _first_line(docstring: str | None) -> str | None:
    if not docstring:
        return None
    for line in docstring.strip().splitlines():
        line = line.strip()
        if line:
            return line
    return None
