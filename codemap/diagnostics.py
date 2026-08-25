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
NO_CROSS_ROOT_EDGES = "no_cross_root_edges"
SCHEMA_MISMATCH = "schema_mismatch"

#: A ``warning`` invalidates the conclusions a surface draws from the graph — read them as
#: unknown. A ``note`` states a fact about how the graph was built and invalidates nothing.
#: Each check owns its own ``consequence`` sentence: presenters must not supply one, or a
#: correct result ends up captioned with another check's meaning (issue #8).
WARNING = "warning"
NOTE = "note"


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
        "severity": WARNING,
        "modules": modules,
        "consequence": ("Findings below are derived from that empty import graph — read "
                        "them as **unknown**, not as a clean bill of health."),
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
        "severity": NOTE,   # a fact about provenance; it invalidates nothing (issue #8)
        "target": graph.target,
        "message": (
            f"`{graph.target}` has no __init__.py — it is a namespace package, so its "
            "modules are only a package by directory. Imports between them are resolved "
            "by codemap's flat-layout inference (edges labelled resolution=\"flat\"), "
            "not by packaging."
        ),
    }


def cross_root_diagnostic(graph) -> dict | None:
    """Flag consumer/doc roots that reach the core **not at all** (R1-C21-f1, issue #6).

    ``--consumer`` exists so ``impact`` can answer "who uses X across the whole repo".
    If roots were supplied and *nothing* in them references the core, the answer to that
    question is a confident zero — and the far likelier cause is that their imports were
    not understood than that four directories of code genuinely use none of it.

    Deliberately separate from :func:`import_graph_diagnostic`: the case that prompted it
    had 75 import edges (so the "empty graph" check stayed quiet) and none of them crossing
    a root boundary. One check per dimension, rather than one check trying to be general.
    """
    root_of = {n.id: (n.extras.get("root") or "core") for n in graph.nodes.values()}
    outer = sorted({r for r in root_of.values() if r != "core"})
    if not outer:
        return None  # single-package graph: no boundary to cross
    for e in graph.edges:
        if root_of.get(e.source, "core") != "core" and root_of.get(e.target, "core") == "core":
            return None
    return {
        "code": NO_CROSS_ROOT_EDGES,
        "severity": WARNING,
        "roots": outer,
        "consequence": ("Any cross-root finding below — who uses a symbol outside its own "
                        "root — is **unknown**, not empty."),
        "message": (
            f"{len(outer)} non-core root(s) supplied ({', '.join(outer)}) but not one "
            "reference from them reaches the core — cross-root `impact` will read as "
            "\"isolated\" for every symbol. Usually an import form the scanner did not "
            "understand, not an unused core."
        ),
    }


def schema_diagnostic(graph) -> dict | None:
    """Flag a stored graph whose schema is not the running tool's (R1-C25 / D3).

    ``codemap_schema`` was written and never read: a graph built before an extraction
    change was consumed by a later tool without a word, and answered with that tool's
    confidence over the older tool's blindness. Measured: one frozen tree, two codemap
    builds four commits apart — 30 edges vs 38, and ``dead-code high`` 12 vs 7 — with
    **both files declaring 0.11**, because only open ``extras`` had changed. So the
    check cannot prove semantic equivalence; what it can do is stop a *known* mismatch
    from passing silently.

    Only fires for a graph that came from a file (``loaded_schema is None`` on a fresh
    build). Never a refusal: every stored graph in existence predates 0.12, and turning
    an upgrade into an outage is not the honest option — a labelled answer is (R1-C13).
    """
    from codemap.model import SCHEMA_VERSION
    from codemap.provenance import MATCH, NEWER, OLDER, describe, schema_status
    if graph.loaded_schema is None:
        return None
    status = schema_status(graph.loaded_schema or None, SCHEMA_VERSION)
    if status == MATCH:
        return None
    declared = graph.loaded_schema or "none declared"
    direction = {OLDER: "predates this tool",
                 NEWER: "is newer than this tool"}.get(status, "declares no usable version")
    return {
        "code": SCHEMA_MISMATCH,
        "severity": WARNING,
        "loaded": graph.loaded_schema,
        "running": SCHEMA_VERSION,
        "status": status,
        "provenance": describe(graph.provenance),
        "consequence": ("Findings below may differ from a fresh build of the same source "
                        "— rebuild before trusting a close call."),
        "message": (
            f"graph declares schema {declared}, this codemap writes {SCHEMA_VERSION} "
            f"— the artifact {direction}. Extraction semantics change without a schema "
            f"bump (open `extras`), so the two are not interchangeable. "
            f"Built by: {describe(graph.provenance)}."
        ),
    }


def diagnostics(graph) -> list[dict]:
    """Every diagnostic that applies to ``graph`` (empty list when it looks sound)."""
    checks = (import_graph_diagnostic(graph), namespace_target_diagnostic(graph),
              cross_root_diagnostic(graph), schema_diagnostic(graph))
    return [d for d in checks if d is not None]


def render_lines(graph) -> list[str]:
    """Markdown blockquote lines for a report header (empty when the graph looks sound).

    Presenters call this instead of formatting diagnostics themselves — a caption that
    belongs to one check must never end up under another (issue #8: the namespace *note*
    was rendered with the empty-import-graph *warning*'s "everything below is unknown",
    on a graph with 404 import edges).
    """
    lines: list[str] = []
    for d in diagnostics(graph):
        mark = "⚠️" if d.get("severity", WARNING) == WARNING else "ℹ️"
        text = " ".join(part for part in (d["message"], d.get("consequence")) if part)
        lines.extend([f"> {mark} {text}", ""])
    return lines
