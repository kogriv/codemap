"""Canonical JSON store (DESIGN §2.2, §4).

JSON is the canonical, portable, diffable source of truth. Query backends
(networkx/SQLite/Neo4j) are derived from it — not the other way round (DESIGN §4).
"""

from __future__ import annotations

import json
from pathlib import Path

from codemap.model import Graph


def save(graph: Graph, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(graph.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def dumps(graph: Graph) -> str:
    return json.dumps(graph.to_dict(), ensure_ascii=False, indent=2)


def load(path: str | Path) -> Graph:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Graph.from_dict(data)
