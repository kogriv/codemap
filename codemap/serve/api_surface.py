"""API-surface report — view D (DESIGN §4.1-D), the M0 deliverable.

The public surface of the target: public symbols grouped by module, with
signatures, first docstring line and a deprecated marker. Reads the canonical
graph; renders Markdown.
"""

from __future__ import annotations

from collections import defaultdict

from codemap.model import Graph

_SYMBOL_KINDS = {"class", "function", "attribute"}


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
