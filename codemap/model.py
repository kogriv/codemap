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
SCHEMA_VERSION = "0.1"


@dataclass
class Node:
    """A code entity. ``id`` is its canonical definition path (DESIGN §2.1)."""

    id: str
    kind: str  # module | class | function | attribute (open set — DESIGN §2)
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

    type: str  # contains | imports | inherits | exports | decorated_by (DESIGN §2)
    source: str
    target: str
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class Graph:
    """The code graph: nodes + edges over a single target package."""

    target: str
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)

    # -- canonical serialization (deterministic — DESIGN §2.2) --------------

    def to_dict(self) -> dict[str, Any]:
        nodes = [asdict(self.nodes[nid]) for nid in sorted(self.nodes)]
        edges = sorted(
            (asdict(e) for e in self.edges),
            key=lambda e: (e["type"], e["source"], e["target"]),
        )
        return {
            "codemap_schema": SCHEMA_VERSION,
            "target": self.target,
            "nodes": nodes,
            "edges": edges,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Graph":
        g = cls(target=data["target"])
        for n in data["nodes"]:
            g.add_node(Node(**n))
        for e in data["edges"]:
            g.add_edge(Edge(**e))
        return g
