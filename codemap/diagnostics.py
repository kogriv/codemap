"""Build-level diagnostics derived from a graph (R1-C21 / design D5).

A graph can be *well-formed and vacuous*: if the extractor did not understand the
target's layout, whole edge classes come out empty and every conclusion drawn from
them inverts. The worst case found in the wild (issues #4/#5) was a flat module
directory: 0 ``imports`` edges, after which ``architecture`` reports "no layer
violations / acyclic" and ``dead-code`` calls every live module an orphan. Absence of
data rendered as a clean bill of health.

These checks name that condition wherever the graph is presented. They are
**derived, never stored** — ``graph.json`` keeps no diagnostic field, so there is
nothing to keep in sync, and any consumer recomputes the signal from the graph it
already holds.
"""

from __future__ import annotations

NO_IMPORT_EDGES = "no_import_edges"
NAMESPACE_TARGET = "namespace_target"


def import_graph_diagnostic(graph) -> dict | None:
    """Flag an empty import graph over a multi-module target, else ``None``.

    A single-module package legitimately has no imports, so the check needs ≥2
    modules; beyond that, a Python package whose modules never import one another
    is far rarer than a layout the extractor failed to parse.
    """
    modules = sum(1 for n in graph.nodes.values() if n.kind == "module")
    if modules < 2:
        return None
    if any(e.type == "imports" for e in graph.edges):
        return None
    return {
        "code": NO_IMPORT_EDGES,
        "modules": modules,
        "message": (
            f"0 import edges across {modules} modules — the import graph is empty, so "
            "layers, cycles, coupling and orphan detection are vacuous rather than clean. "
            "This usually means a layout the extractor did not understand (e.g. a flat "
            "module directory whose files import each other by bare name)."
        ),
    }


def namespace_target_diagnostic(graph) -> dict | None:
    """Flag a target that is a **namespace package** (a directory with no ``__init__.py``).

    Derived, like the rest: griffe gives such a directory no source file, so the target's
    own module node carries ``file=None`` while its children have real files. Worth naming
    because the layout is a silent fork in behaviour — sibling imports resolve only by the
    flat-layout inference (labelled ``resolution="flat"`` on the edge), not by packaging.
    """
    root = graph.nodes.get(graph.target)
    if root is None or root.kind != "module" or root.file is not None:
        return None
    children = [n for n in graph.nodes.values() if n.kind == "module" and n.id != root.id]
    if not children:
        return None
    return {
        "code": NAMESPACE_TARGET,
        "target": graph.target,
        "message": (
            f"`{graph.target}` has no __init__.py — it is a namespace package, so its "
            "modules are only a package by directory. Imports between them are resolved "
            "by codemap's flat-layout inference (edges labelled resolution=\"flat\"), "
            "not by packaging."
        ),
    }


def diagnostics(graph) -> list[dict]:
    """Every diagnostic that applies to ``graph`` (empty list when it looks sound)."""
    checks = (import_graph_diagnostic(graph), namespace_target_diagnostic(graph))
    return [d for d in checks if d is not None]
