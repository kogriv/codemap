"""Canonical JSON store (DESIGN §2.2, §4).

JSON is the canonical, portable, diffable source of truth. Query backends
(networkx/SQLite/Neo4j) are derived from it — not the other way round (DESIGN §4).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from codemap.model import Graph


def save(graph: Graph, path: str | Path) -> None:
    """Serialise first, then publish atomically (R1-C124): a failed or interrupted save leaves the previous graph
    intact, and a concurrent reader (the `--watch` reload) never reads half a file."""
    from codemap import atomic
    text = json.dumps(graph.to_dict(), ensure_ascii=False, indent=2) + "\n"
    atomic.write_text(path, text)


def dumps(graph: Graph) -> str:
    return json.dumps(graph.to_dict(), ensure_ascii=False, indent=2)


def load(path: str | Path) -> Graph:
    return load_snapshot(path)[0]


def load_snapshot(path: str | Path) -> tuple[Graph, float]:
    """Load the graph and the mtime of the same open artifact."""
    with Path(path).open(encoding="utf-8") as stream:
        data = json.load(stream)
        mtime = os.fstat(stream.fileno()).st_mtime
    return Graph.from_dict(data), mtime
