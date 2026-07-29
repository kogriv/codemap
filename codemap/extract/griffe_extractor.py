"""Python extractor backed by griffe (DESIGN §10.8).

Static analysis only — griffe parses source without importing the target, and
resolves the hard parts for us (signatures, docstrings, __all__ visibility,
base-class / relative-import / re-export resolution — DESIGN §3.1); we consume
that, we don't reinvent it.

Emits (M0 + M1 + M1.5):
- definition nodes (module/class/function/attribute) + `contains` structure;
- `export` edges for re-exports/aliases (module re-exposes a symbol — §2.1);
- `imports` edges between modules (dependency graph — §1, §3.1);
- `inherits` edges (class → base class; external bases flagged — §2);
- `decorated_by` edges (symbol → decorator callable — §2);
- node `extras`: attribute `annotation`, class `is_dataclass`, and dynamic
  `registry` binding (decorator + literal key) for factory/registry wiring (§7).
"""

from __future__ import annotations

from pathlib import Path

import griffe

from codemap.extract.behavior import add_behavior
from codemap.extract.dispatch import add_dispatch, add_family_links
from codemap.model import Edge, Graph, Node

# griffe object kinds we turn into definition nodes (aliases handled separately).
_NODE_KINDS = {"module", "class", "function", "attribute"}


def extract(package_path: str | Path, *, deep: bool = False) -> Graph:
    """Build a code graph from a Python package directory.

    ``deep=True`` runs the jedi-backed call resolver (M5) — richer call-graph
    (local-variable type inference) at ~1 min build cost; default is the fast
    ast tier (sub-second). See ``extract/behavior.py``.
    """
    pkg_dir = Path(package_path).resolve()
    if not pkg_dir.is_dir():
        raise NotADirectoryError(f"Not a package directory: {pkg_dir}")

    module_name = pkg_dir.name
    search_path = pkg_dir.parent
    root = griffe.load(module_name, search_paths=[str(search_path)])

    graph = Graph(target=module_name)
    aliases: list[tuple[str, str, str, bool]] = []  # (parent_module, name, target, public)
    imports: list[tuple[str, str]] = []  # (module_id, target_symbol_path)

    _collect(graph, root, search_path, module_name, aliases, imports)
    _resolve_edges(graph, module_name, aliases, imports)
    # M4/M5: call-graph + control skeleton (deep=jedi type inference).
    add_behavior(graph, root, module_name, deep=deep, search_path=search_path)
    # M7: bridge factory/registry dispatch seams using the M1.5 registry table.
    add_dispatch(graph, root, module_name)
    # M9 (F4): link registry-family members to the Protocol they satisfy.
    add_family_links(graph)
    return graph


# -- pass 1: definition nodes + contains/inherits/decorated_by, collect aliases/imports --

def _collect(graph, obj, root, target_pkg, aliases, imports) -> None:
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
        _emit_decorated_by(graph, member)
        if member.kind.value == "class":
            _emit_inherits(graph, member, target_pkg)
        if member.kind.value in {"module", "class"}:
            _collect(graph, member, root, target_pkg, aliases, imports)


# -- semantic edges resolvable inline (griffe gives absolute targets) --------

def _emit_inherits(graph, cls, target_pkg) -> None:
    """One `inherits` edge per base; griffe resolves the base to a canonical path."""
    for base in getattr(cls, "bases", None) or []:
        target = getattr(base, "canonical_path", None) or str(base)
        internal = target == target_pkg or target.startswith(target_pkg + ".")
        graph.add_edge(
            Edge(
                "inherits",
                cls.canonical_path,
                target,
                extras={} if internal else {"external": True},
            )
        )


def _emit_decorated_by(graph, obj) -> None:
    """One `decorated_by` edge per decorator (target = its callable path)."""
    for name in _decorator_names(obj):
        graph.add_edge(Edge("decorated_by", obj.canonical_path, name))


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


# -- node building (M0 + M1.5 extras) ----------------------------------------

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
            extras=_extras(obj, decorators),
        )
    )


def _extras(obj, decorators) -> dict:
    """Language-specific facts kept off the neutral core (DESIGN §2)."""
    extras: dict = {}
    kind = obj.kind.value
    if kind == "attribute" and getattr(obj, "annotation", None) is not None:
        extras["annotation"] = str(obj.annotation)  # e.g. "List[ZoneInfo]" (CM-01)
    if kind == "function":
        # structured param/return types — basis for type-flow (M4) and CM-03.
        params = [
            {"name": p.name, "type": str(p.annotation)}
            for p in obj.parameters
            if p.annotation is not None
        ]
        if params:
            extras["params"] = params
        if obj.returns is not None:
            extras["returns"] = str(obj.returns)
    if kind == "class":
        if any(d.split(".")[-1] == "dataclass" for d in decorators):
            extras["is_dataclass"] = True  # CM-02
        binding = _registry_binding(obj)  # CM-07: @Registry.register('key')
        if binding is not None:
            extras["registry"] = binding
    return extras


def _registry_binding(obj) -> dict | None:
    """Dynamic registration via a decorator call with a literal string key.

    Turns ``@ZoneDetectionRegistry.register('zero_crossing', ...)`` into
    ``{"decorator": "...register", "key": "zero_crossing"}`` so factory/registry
    wiring is queryable instead of hidden in a decorator string (DESIGN §7).
    """
    for d in getattr(obj, "decorators", []) or []:
        path = getattr(d, "callable_path", None)
        value = getattr(d, "value", None)
        if path is None or "register" not in str(path).lower():
            continue
        args = getattr(value, "arguments", None)
        if not args:
            continue
        first = args[0]  # griffe gives a string-literal arg as quoted source text
        if isinstance(first, str) and len(first) >= 2 and first[0] in "'\"":
            key = first.strip("'\"")
            if key:
                return {"decorator": str(path), "key": key}
    return None


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
