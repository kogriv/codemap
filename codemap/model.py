"""Neutral code-graph model (DESIGN §2).

Language-neutral core: a node is ``kind + attrs``; edges are typed. Python-isms
live in ``extras`` provided by the extractor, never baked into the core. The JSON
form (DESIGN §2.2) is the canonical store: deterministic (sorted, no timestamps)
so it diffs cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# Bump on any change to the JSON schema (invariant, like bquant's CACHE_SCHEMA_VERSION).
# 0.2: M1.5 — inherits / decorated_by edges; attribute annotations, is_dataclass and
#      dynamic-registration keys in node extras (closes gap-doc CM-01/02/06/07/08).
# 0.3: M4 — best-effort `calls` edges (resolution-labeled); per-function extras
#      `calls` coverage, `control` skeleton, structured `params`/`returns` for
#      type-flow (partially closes CM-03/09/10/11/12).
# 0.4: M6 — repo scope / impact (multi-root). Nodes carry provenance
#      (`extras.root`: core | tests | examples | research | scripts | docs);
#      `doc` node kind + `references` edge (consumer/doc → core symbol) let
#      blast-radius reach beyond the package (closes gap-doc F1).
# 0.5: M7 — registry-aware call bridging. `calls` edges gain resolution
#      `registry` (literal key → exact impl) and `registry-candidate` (factory/
#      getter → all family impls, honest over-approximation) so the call chain
#      reconnects at factory/registry dispatch seams (closes gap-doc F5).
# 0.6: M9 — registry-family Protocol links. `implements` edge (concrete impl →
#      the Protocol it structurally satisfies, matched via the registry family)
#      makes the family queryable and diagrammable though it's never inherited
#      (closes gap-doc F4).
# 0.7: M11 — call-site argument contract. `calls` edges carry `callsites`
#      (how many call expressions collapsed into this edge) and the observed
#      argument shape (`posargs` / `kwargs` / `splat`) so signature-change
#      reasoning is possible (closes gap-doc F7).
# 0.8: M12 — string-key dataflow. `column` node per string subscript key
#      (`column:macd_hist`) with `writes`/`reads` edges (function → column) so
#      "who produces/consumes this DataFrame column" is queryable (closes
#      gap-doc F6). Over-set of columns (dict keys land here too — honest).
# 0.9: M14 — dataflow access-form (soundness/F15). `column` node carries
#      `extras.subscripted` (bool — key was ever accessed as `x['k']`, not only a
#      dict-literal payload key); `reads`/`writes` edges carry `extras.access`
#      (`subscript` | `dict-literal`). B1 dogfood found 71% of column nodes were
#      dict-literal-only payload keys (result dicts, config, rcParams) — the
#      `subscripted` flag lets aggregates surface the ~29% real column-like set
#      while per-key queries and the F6 producer edge stay intact.
# 0.10: R1-C4 — per-function complexity metrics. `extras.complexity` on function
#      nodes carries `cc` (McCabe cyclomatic), `volume` (Halstead), `sloc` (physical
#      span) and `mi` (Maintainability Index, 0–100). Computed in the behavioral AST
#      pass (source-only, stdlib-only, deterministic); Query.hotspots blends them with
#      structural coupling so "complex by McCabe" ranks alongside "big by connectivity".
# 0.11: R1-C20 — attribute-access edges. `accesses` edge (function → the `attribute`
#      node it reads/writes), `extras.access` (`read` | `write`) + `extras.resolution`
#      (`self` | `class` | `construct` | `deep`). Emitted by the `extract/attrflow.py`
#      pass (fast `ast` for self./ClassName./construction-kwargs, deep `jedi` for typed
#      `obj.field`). Wired into impact/references_to so a field's blast-radius is real;
#      an attribute with no modelled accessor reports risk `unknown` (lower bound), never
#      `none` (closes the issue #1 honesty gap — see gaps/attribute_impact_gap_2026-08-22).
# 0.12: R1-C25 — build provenance. New top-level ``provenance`` block: tool identity
#       (name/version/commit — commit absent, never guessed, when installed from a
#       wheel), ``tier`` (fast|deep), input ``scope_id`` (M19.A) and the source vcs
#       commit + dirty flag. **Timestamp-free and path-free by construction** — the
#       clock and the absolute `cwd` stay in the `*.meta.json` sidecar, so the graph
#       remains byte-identical across two builds of a frozen tree and safe to publish.
#       ``codemap_schema`` is now *read* on load: a mismatch raises a diagnostic instead
#       of being silently accepted (gaps/graph_provenance_2026-08-25 — the same tree
#       built four commits apart gave 30 vs 38 edges under one declared schema).
# 0.13: R1-C31 — one path origin per graph, and consumer symbols have a file (issue #12).
#       Every ``file`` in a repo-scoped graph is relative to the **nearest common ancestor
#       of the roots' parents**, not to each root's own parent: with roots in different
#       directories (`src/pkg` beside `tests/`, or both under `research/`) a single graph
#       used to carry two coordinate systems and say so nowhere, so a printed path looked
#       repo-relative when it was not. ``provenance.roots`` records each root relative to
#       that origin rather than by basename — still no absolute path (D5); the origin
#       itself is a machine location and stays in the ``*.meta.json`` sidecar as
#       ``roots_base``. Function/class nodes under a consumer root now carry ``file``
#       (they had ``lineno`` alone, so `search` answered a line number with no file).
SCHEMA_VERSION = "0.13"

# Closed vocabulary of edge types (R1-C7). Node ``kind`` is deliberately an OPEN set
# (DESIGN §2 — new entity kinds may appear), but edges are TYPED: every relationship
# codemap emits is one of these, each with a fixed meaning. This is the machine-
# checkable contract — a new relationship must be added here (and documented) rather
# than emitted silently; ``tests/test_r1c7_edge_vocab.py`` fails if a graph carries a
# type not in this set (or if a declared type stops appearing on the dogfood target).
EDGE_TYPES = frozenset({
    "contains",       # parent → member (module→class/func, class→method)
    "imports",        # module → module it imports (internal, resolved to canonical)
    "export",         # package → symbol it re-exports (extras.public marks __all__)
    "inherits",       # class → base class (extras.external for out-of-package bases)
    "decorated_by",   # symbol → the decorator applied to it
    "calls",          # caller function → callee (extras.resolution: how it resolved)
    "references",     # consumer/doc/dispatch site → the core symbol it names
    "implements",     # concrete class → the Protocol it structurally satisfies (M9)
    "reads",          # function → string-keyed column it reads (extras.access)
    "writes",         # function → string-keyed column it writes (extras.access)
    "accesses",       # function → attribute node it reads/writes (extras.access, R1-C20)
})

# The subset of EDGE_TYPES an incremental build splices from the old graph for modules
# it did not recompute (``incremental.py``) — and therefore the classes a deep+incremental
# graph answers from an *earlier* build's jedi sample (R1-C43). Lives with the vocabulary
# because two layers that may not import each other need it: the extractor's union
# (R1-C45) and the serve layer, which derives from it which ops must say so (R1-C44 / D4).
SPLICED_EDGE_TYPES = frozenset({"calls", "accesses", "references"})


@dataclass
class Node:
    """A code entity. ``id`` is its canonical definition path (DESIGN §2.1)."""

    id: str
    kind: str  # module | class | function | attribute | doc | column (open set — DESIGN §2)
    file: str | None = None
    lineno: int | None = None
    endlineno: int | None = None
    signature: str | None = None
    docstring: str | None = None
    visibility: str = "public"  # public | private
    decorators: list[str] = field(default_factory=list)
    is_deprecated: bool = False
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    """A typed relationship between two nodes (by id)."""

    type: str  # one of EDGE_TYPES (closed vocabulary, R1-C7): contains | imports |
    #            export | inherits | decorated_by | calls | references | implements |
    #            reads | writes | accesses  (§2)
    source: str
    target: str
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class Graph:
    """The code graph: nodes + edges over a single target package."""

    target: str
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    #: R1-C25 — what produced this graph (see ``codemap/provenance.py``). Serialized.
    provenance: dict[str, Any] = field(default_factory=dict)
    #: The ``codemap_schema`` this graph was *loaded* from, or None for a fresh build.
    #: Not serialized and not part of equality — it describes the file, not the graph.
    loaded_schema: str | None = field(default=None, compare=False, repr=False)

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)

    # -- canonical serialization (deterministic — DESIGN §2.2) --------------

    def to_dict(self) -> dict[str, Any]:
        import json as _json
        nodes = [asdict(self.nodes[nid]) for nid in sorted(self.nodes)]
        # Sort by the full edge content, not just (type, source, target): two edges
        # can share that triple but differ in `extras` (e.g. a behavioral `calls` and
        # a registry-dispatch `calls`). Including a stable render of `extras` in the
        # key makes the order **insertion-independent**, so an incremental rebuild
        # (R1-C9), which splices edges in a different order, serializes identically to
        # a full build.
        edges = sorted(
            (asdict(e) for e in self.edges),
            key=lambda e: (e["type"], e["source"], e["target"],
                           _json.dumps(e["extras"], sort_keys=True, ensure_ascii=False)),
        )
        return {
            "codemap_schema": SCHEMA_VERSION,
            "target": self.target,
            # R1-C25: always emitted, even empty — a stable shape diffs cleanly, and an
            # empty block is itself the honest statement "this build recorded nothing".
            "provenance": self.provenance,
            "nodes": nodes,
            "edges": edges,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Graph":
        g = cls(target=data["target"])
        g.provenance = data.get("provenance") or {}
        # Read the schema the file declares (R1-C25/D3). It used to be written and never
        # read, so a graph predating an extraction change was consumed without a word.
        # "" (not None) when the file declared nothing: None must keep meaning
        # "this graph was never loaded from a file", so a fresh build stays quiet.
        g.loaded_schema = data.get("codemap_schema", "")
        for n in data["nodes"]:
            g.add_node(Node(**n))
        for e in data["edges"]:
            g.add_edge(Edge(**e))
        return g
