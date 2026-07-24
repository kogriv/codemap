"""Python extractor backed by griffe (DESIGN §10.8).

Static analysis only — griffe parses source without importing the target, so it
works on any package (installed or not). griffe also resolves the hard parts
(signatures, docstrings, __all__ visibility); we consume that, we don't reinvent
it (DESIGN §3.1). Import/alias *edges* are M1 — M0 emits definition nodes +
`contains` structure for the API-surface slice.
"""

from __future__ import annotations

from pathlib import Path

import griffe

from codemap.model import Edge, Graph, Node

# griffe object kinds we turn into nodes (aliases/re-exports are M1).
_NODE_KINDS = {"module", "class", "function", "attribute"}


def extract(package_path: str | Path) -> Graph:
    """Build a code graph from a Python package directory.

    Args:
        package_path: Path to the package directory (the one holding __init__.py).

    Returns:
        A neutral :class:`Graph`.
    """
    pkg_dir = Path(package_path).resolve()
    if not pkg_dir.is_dir():
        raise NotADirectoryError(f"Not a package directory: {pkg_dir}")

    module_name = pkg_dir.name
    search_path = pkg_dir.parent

    root = griffe.load(module_name, search_paths=[str(search_path)])

    graph = Graph(target=module_name)
    _add_node(graph, root, search_path)
    _walk(graph, root, search_path)
    return graph


def _walk(graph: Graph, obj, root: Path) -> None:
    for member in obj.members.values():
        if member.is_alias:  # re-exports/imports -> M1 (alias edges)
            continue
        if member.kind.value not in _NODE_KINDS:
            continue
        _add_node(graph, member, root)
        graph.add_edge(
            Edge(type="contains", source=obj.canonical_path, target=member.canonical_path)
        )
        if member.kind.value in {"module", "class"}:
            _walk(graph, member, root)


def _add_node(graph: Graph, obj, root: Path) -> None:
    decorators = _decorator_names(obj)
    node = Node(
        id=obj.canonical_path,
        kind=obj.kind.value,
        file=_rel(obj.filepath, root),
        lineno=getattr(obj, "lineno", None),
        endlineno=getattr(obj, "endlineno", None),
        signature=_signature(obj),
        docstring=obj.docstring.value if obj.docstring else None,
        visibility="public" if obj.is_public else "private",
        decorators=decorators,
        is_deprecated=any(d.split(".")[-1] == "deprecated" for d in decorators),
    )
    graph.add_node(node)


def _signature(obj) -> str | None:
    if obj.kind.value != "function":
        return None
    parts = []
    for p in obj.parameters:
        s = p.name
        if p.annotation is not None:
            s += f": {p.annotation}"
        if p.default is not None:
            s += f" = {p.default}"
        parts.append(s)
    sig = f"{obj.name}({', '.join(parts)})"
    if obj.returns is not None:
        sig += f" -> {obj.returns}"
    return sig


def _decorator_names(obj) -> list[str]:
    names = []
    for d in getattr(obj, "decorators", []) or []:
        path = getattr(d, "callable_path", None)
        names.append(str(path) if path else str(getattr(d, "value", d)))
    return names


def _rel(filepath, root: Path) -> str | None:
    if filepath is None:
        return None
    try:
        return str(Path(filepath).resolve().relative_to(root.resolve()))
    except ValueError:
        return str(filepath)
