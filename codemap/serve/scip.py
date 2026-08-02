"""SCIP export — codemap's graph as a SCIP index (R1-C1).

SCIP (Sourcegraph Code Intelligence Protocol) is the ascendant open interchange
format for precise code intelligence: emit one ``index.scip`` and Sourcegraph,
Glean and any SCIP consumer light up go-to-definition, symbol search and type
hierarchy across the ecosystem. The research landscape (``research/00_landscape.md``)
ranked this the highest-value interop move.

**Honest scope.** codemap's graph is *symbol-level*: edges relate symbol→symbol
but carry no call-site coordinates. SCIP occurrences are *location-based*. So this
exporter emits exactly what codemap knows precisely:

- **Definition occurrences** — one per node with a file location (module / class /
  function / attribute) → go-to-definition + symbol search.
- **SymbolInformation** — kind, docstring, and ``inherits`` / ``implements`` as SCIP
  ``relationships`` (``is_implementation``) → type hierarchy.

It does **not** emit reference occurrences (find-references): that needs token
positions codemap does not track. Emitting fake positions would be worse than
omitting them, so we omit them and say so — consistent with codemap's other
lower-bound disclaimers.

``protobuf`` is an **optional** dependency (``pip install codemap[scip]``); the
vendored bindings (``_scip_pb2.py``) are generated from the official ``scip.proto``.
The import is lazy so codemap works without it.
"""

from __future__ import annotations

import os

from codemap.model import Graph
from codemap.query import Query

# Descriptor suffix per node kind (SCIP symbol grammar): namespace ``/``, type
# ``#``, method ``().``, term ``.``. Functions and methods both use the method
# descriptor (as scip-python does). Unknown intermediates default to namespace.
_SUFFIX = {"module": "/", "class": "#", "function": "().", "attribute": "."}

# Names outside this set must be backtick-escaped in a SCIP symbol (grammar).
_SIMPLE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_+$")


def _load_pb2():
    """Import the vendored SCIP bindings, with a friendly error if protobuf is absent."""
    try:
        from codemap.serve import _scip_pb2  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - exercised via the extra
        raise RuntimeError(
            "SCIP export needs the optional 'scip' extra — install it with "
            "`pip install codemap[scip]` (adds protobuf)."
        ) from exc
    return _scip_pb2


def _escape(name: str) -> str:
    """Escape a descriptor name per the SCIP symbol grammar (backtick-wrap if needed)."""
    if name and all(c in _SIMPLE for c in name):
        return name
    return "`" + name.replace("`", "``") + "`"


def _symbol(nodes: dict, node_id: str, prefix: str) -> str:
    """Build the SCIP symbol string for ``node_id`` from its ancestor chain.

    Each dotted segment becomes a descriptor whose suffix is chosen by the kind of
    the node at that prefix (looked up in the graph); missing intermediates default
    to a namespace descriptor.
    """
    parts = node_id.split(".")
    out = []
    for i in range(1, len(parts) + 1):
        pid = ".".join(parts[:i])
        node = nodes.get(pid)
        last = i == len(parts)
        kind = node.kind if node else ("attribute" if last else "module")
        out.append(_escape(parts[i - 1]) + _SUFFIX.get(kind, "/"))
    return prefix + "".join(out)


def _kind(pb2, kind: str, parent_kind: str | None):
    K = pb2.SymbolInformation.Kind
    if kind == "module":
        return K.Module
    if kind == "class":
        return K.Class
    if kind == "function":
        return K.Method if parent_kind == "class" else K.Function
    if kind == "attribute":
        return K.Field if parent_kind == "class" else K.Variable
    return K.UnspecifiedKind


def _language(file: str, pb2) -> str:
    return "Python" if file.endswith(".py") else ""


def build_scip(
    query: Query,
    *,
    project_root: str,
    package: str | None = None,
    version: str = ".",
    tool_version: str = "0.0.1",
    scheme: str = "codemap",
    manager: str = "python",
):
    """Build a ``scip_pb2.Index`` from the graph (definitions + symbol info)."""
    pb2 = _load_pb2()
    graph: Graph = query.graph
    nodes = graph.nodes
    package = package or graph.target
    prefix = f"{scheme} {manager} {package} {version} "

    # Index edges by source for relationship lookup (inherits / implements).
    rels_by_src: dict[str, list[tuple[str, str]]] = {}
    for e in graph.edges:
        if e.type in ("inherits", "implements"):
            rels_by_src.setdefault(e.source, []).append((e.type, e.target))

    # Group definition occurrences + symbol info by file.
    by_file: dict[str, dict] = {}
    for nid in sorted(nodes):
        node = nodes[nid]
        if node.kind not in _SUFFIX or not node.file:
            continue  # skip synthetic column nodes, doc nodes, locationless overlays
        sym = _symbol(nodes, nid, prefix)
        line0 = (node.lineno - 1) if node.lineno else 0
        parent_kind = None
        if "." in nid:
            parent = nodes.get(nid.rsplit(".", 1)[0])
            parent_kind = parent.kind if parent else None

        occ = pb2.Occurrence(symbol=sym, symbol_roles=pb2.SymbolRole.Definition)
        occ.single_line_range.line = line0
        occ.single_line_range.start_character = 0
        occ.single_line_range.end_character = 0
        # Test-code provenance (honest signal to consumers).
        if node.extras.get("root") == "tests":
            occ.symbol_roles |= pb2.SymbolRole.Test
        # Enclosing range = the full definition span (proto guidance for defs).
        if node.endlineno and node.endlineno - 1 != line0:
            occ.multi_line_enclosing_range.start_line = line0
            occ.multi_line_enclosing_range.start_character = 0
            occ.multi_line_enclosing_range.end_line = node.endlineno - 1
            occ.multi_line_enclosing_range.end_character = 0

        info = pb2.SymbolInformation(symbol=sym, kind=_kind(pb2, node.kind, parent_kind))
        if node.docstring:
            info.documentation.append(node.docstring)
        for _etype, target in sorted(rels_by_src.get(nid, [])):
            if target in nodes:  # only relate to symbols we can name canonically
                info.relationships.append(
                    pb2.Relationship(symbol=_symbol(nodes, target, prefix),
                                     is_implementation=True))

        bucket = by_file.setdefault(node.file, {"occ": [], "sym": []})
        bucket["occ"].append(occ)
        bucket["sym"].append(info)

    index = pb2.Index()
    index.metadata.version = pb2.ProtocolVersion.UnspecifiedProtocolVersion
    index.metadata.tool_info.name = "codemap"
    index.metadata.tool_info.version = tool_version
    index.metadata.project_root = "file://" + os.path.abspath(project_root)
    index.metadata.text_document_encoding = pb2.TextEncoding.UTF8

    for rel_path in sorted(by_file):
        bucket = by_file[rel_path]
        doc = pb2.Document(
            relative_path=rel_path,
            language=_language(rel_path, pb2),
            position_encoding=pb2.PositionEncoding.UTF8CodeUnitOffsetFromLineStart,
        )
        doc.occurrences.extend(sorted(bucket["occ"], key=lambda o: o.symbol))
        doc.symbols.extend(sorted(bucket["sym"], key=lambda s: s.symbol))
        index.documents.append(doc)
    return index


def write_scip(index) -> bytes:
    """Serialize a SCIP ``Index`` to deterministic protobuf bytes."""
    return index.SerializeToString(deterministic=True)
