"""Mermaid diagram views — consumer A/B (DESIGN §4.1-A, M2.3).

Renders scoped subgraphs of the canonical graph as Mermaid text (browsable in
Obsidian, GitHub, docs):

- ``class`` — class hierarchy from ``inherits`` edges (``classDiagram``);
- ``deps``  — module dependency graph from ``imports`` edges;
- ``calls`` — call graph around a root symbol from ``calls`` edges (BFS).

Scoping keeps diagrams legible: ``scope`` filters to an id-prefix subtree; the
call graph is always rooted with a depth bound (§4.2 — scoped subgraphs).
"""

from __future__ import annotations

from codemap.query import Query


def _san(node_id: str) -> str:
    """Mermaid-safe node id (dots/brackets break the parser)."""
    return node_id.replace(".", "_").replace("[", "_").replace("]", "_")


def _short(node_id: str) -> str:
    return node_id.rsplit(".", 1)[-1]


def _in_scope(node_id: str, scope: str | None) -> bool:
    return scope is None or node_id == scope or node_id.startswith(scope + ".")


def render_class_diagram(query: Query, scope: str | None = None) -> str:
    """Class hierarchy as a Mermaid ``classDiagram``.

    ``inherits`` edges render as inheritance (``<|--``); ``implements`` edges
    (M9/F4 — registry-family members → Protocol, never inherited) render as
    realization (``<|..``), so a strategy family is no longer an empty diagram.
    """
    graph = query.graph
    inh = sorted({(e.source, e.target) for e in graph.edges if e.type == "inherits"})
    inh = [(s, t) for s, t in inh if _in_scope(s, scope)]
    impl = sorted({(e.source, e.target) for e in graph.edges if e.type == "implements"})
    impl = [(s, t) for s, t in impl if _in_scope(s, scope) or _in_scope(t, scope)]
    nodes = {n for pair in inh + impl for n in pair}

    lines = ["```mermaid", "classDiagram"]
    for nid in sorted(nodes):
        lines.append(f'    class {_san(nid)}["{_short(nid)}"]')
    for sub, base in inh:
        # Mermaid: Base <|-- Sub  (arrow points from subclass to base)
        lines.append(f"    {_san(base)} <|-- {_san(sub)}")
    for cls, proto in impl:
        # realization: Protocol <|.. Impl
        lines.append(f"    {_san(proto)} <|.. {_san(cls)}")
    lines.append("```")
    return "\n".join(lines) + "\n"


def render_dep_graph(query: Query, scope: str | None = None) -> str:
    """Module dependency graph (``imports`` edges) as a Mermaid flowchart."""
    graph = query.graph
    edges = sorted(
        {(e.source, e.target) for e in graph.edges if e.type == "imports"}
    )
    edges = [(s, t) for s, t in edges if _in_scope(s, scope) and _in_scope(t, scope)]
    nodes = {n for pair in edges for n in pair}

    lines = ["```mermaid", "graph LR"]
    for nid in sorted(nodes):
        lines.append(f'    {_san(nid)}["{_short(nid)}"]')
    for src, tgt in edges:
        lines.append(f"    {_san(src)} --> {_san(tgt)}")
    lines.append("```")
    return "\n".join(lines) + "\n"


def render_call_graph(query: Query, root: str, depth: int = 2) -> str:
    """Call graph reachable from ``root`` within ``depth`` hops (``calls`` edges)."""
    if root not in query.graph.nodes:
        matches = query.find(root)
        if not matches:
            raise KeyError(f"symbol not found: {root}")
        root = matches[0].id

    seen = {root}
    frontier = [root]
    edges: set[tuple[str, str]] = set()
    for _ in range(max(depth, 0)):
        nxt = []
        for node in frontier:
            for callee in query.callees(node):
                edges.add((node, callee))
                if callee not in seen:
                    seen.add(callee)
                    nxt.append(callee)
        frontier = nxt

    lines = ["```mermaid", "graph LR"]
    for nid in sorted(seen):
        marker = ":::root" if nid == root else ""
        lines.append(f'    {_san(nid)}["{_short(nid)}"]{marker}')
    for src, tgt in sorted(edges):
        lines.append(f"    {_san(src)} --> {_san(tgt)}")
    lines.append("    classDef root fill:#f9f,stroke:#333;")
    lines.append("```")
    return "\n".join(lines) + "\n"


_KINDS = {"class": render_class_diagram, "deps": render_dep_graph}


def render_mermaid(query: Query, kind: str, scope: str | None = None,
                   root: str | None = None, depth: int = 2) -> str:
    if kind == "calls":
        if not root:
            raise ValueError("mermaid 'calls' needs --root <symbol>")
        return render_call_graph(query, root, depth)
    if kind not in _KINDS:
        raise ValueError(f"unknown mermaid kind: {kind}")
    return _KINDS[kind](query, scope)
