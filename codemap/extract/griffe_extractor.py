"""Python extractor backed by griffe (DESIGN §10.8).

Static analysis only — griffe parses source without importing the target, and
resolves the hard parts for us (signatures, docstrings, __all__ visibility, and
relative-import / re-export resolution — DESIGN §3.1); we consume that, we don't
reinvent it.

Emits (M0 + M1):
- definition nodes (module/class/function/attribute) + `contains` structure;
- `export` edges for re-exports/aliases (module re-exposes a symbol — §2.1);
- `imports` edges between modules (dependency graph — §1, §3.1).
"""

from __future__ import annotations

from pathlib import Path

import griffe

from codemap.model import Edge, Graph, Node

# griffe object kinds we turn into definition nodes (aliases handled separately).
_NODE_KINDS = {"module", "class", "function", "attribute"}


def extract(package_path: str | Path) -> Graph:
    """Build a code graph from a Python package directory."""
    pkg_dir = Path(package_path).resolve()
    if not pkg_dir.is_dir():
        raise NotADirectoryError(f"Not a package directory: {pkg_dir}")

    module_name = pkg_dir.name
    search_path = pkg_dir.parent
    root = griffe.load(module_name, search_paths=[str(search_path)])

    graph = Graph(target=module_name)
    aliases: list[tuple[str, str, str]] = []  # (parent_module_id, name, target_path)
    imports: list[tuple[str, str]] = []  # (module_id, target_symbol_path)

    _collect(graph, root, search_path, aliases, imports)
    _resolve_edges(graph, module_name, aliases, imports)
    return graph


# -- pass 1: definition nodes + contains, collect aliases/imports ------------

def _collect(graph, obj, root, aliases, imports) -> None:
    if obj.kind.value == "module":
        _add_node(graph, obj, root)
        for name, tgt in (obj.imports or {}).items():
            imports.append((obj.canonical_path, tgt))
    for name, member in obj.members.items():
        if member.is_alias:
            # capture ALL re-exports (public flag kept) — a symbol can be importable
            # via a module without being in its __all__ (e.g. bquant.analysis.zones
            # re-exports analyze_zones but its __all__ lists only the legacy API).
            aliases.append(
                (obj.canonical_path, name, member.target_path, member.is_public)
            )
            continue
        if member.kind.value not in _NODE_KINDS:
            continue
        if member.kind.value != "module":  # modules add themselves in the branch above
            _add_node(graph, member, root)
        graph.add_edge(Edge("contains", obj.canonical_path, member.canonical_path))
        if member.kind.value in {"module", "class"}:
            _collect(graph, member, root, aliases, imports)


# -- pass 2: resolve export + import edges against known nodes ----------------

def _resolve_edges(graph, target_pkg, aliases, imports) -> None:
    module_ids = sorted(
        (n.id for n in graph.nodes.values() if n.kind == "module"), key=len, reverse=True
    )

    for parent_module, name, target_path, is_public in aliases:
        if not (target_path == target_pkg or target_path.startswith(target_pkg + ".")):
            continue  # external re-export (e.g. `import numpy as np`) — out of scope
        graph.add_edge(
            Edge(
                "export",
                parent_module,
                target_path,
                extras={"as": name, "public": is_public},
            )
        )

    seen: set[tuple[str, str]] = set()
    for src_module, target_path in imports:
        if not (target_path == target_pkg or target_path.startswith(target_pkg + ".")):
            continue  # external (pandas, typing, ...) — out of the internal dep graph
        tgt_module = _containing_module(target_path, module_ids)
        if tgt_module is None or tgt_module == src_module:
            continue
        key = (src_module, tgt_module)
        if key in seen:
            continue
        seen.add(key)
        graph.add_edge(Edge("imports", src_module, tgt_module))


def _containing_module(symbol_path: str, module_ids: list[str]) -> str | None:
    """Longest module-id that is a prefix of (or equals) the symbol path."""
    for mid in module_ids:  # already sorted longest-first
        if symbol_path == mid or symbol_path.startswith(mid + "."):
            return mid
    return None


# -- node building (M0) ------------------------------------------------------

def _add_node(graph, obj, root) -> None:
    decorators = _decorator_names(obj)
    graph.add_node(
        Node(
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
    )


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
