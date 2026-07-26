"""RAG export — consumer A (DESIGN §1-A, §4, M2.1).

One self-contained *chunk* per symbol for retrieval-augmented generation: what it
is, where it lives, and its graph neighborhood (calls / callers / bases /
subclasses / module). Emits JSONL (one chunk per line — the standard RAG ingest
format); the ``text`` field is a compact rendering ready to embed.

The neighborhood is exactly what a plain source read does NOT cheaply give an AI:
"what calls this", "what this returns and who consumes it", "its subclasses" —
resolved across the whole package, not one file.
"""

from __future__ import annotations

import json

from codemap.query import Query

_SYMBOL_KINDS = {"class", "function"}


def build_chunks(query: Query) -> list[dict]:
    """Structured RAG chunks for every class/function symbol, sorted by id."""
    graph = query.graph
    chunks = []
    for node in sorted(graph.nodes.values(), key=lambda n: n.id):
        if node.kind not in _SYMBOL_KINDS:
            continue
        module = node.id.rsplit(".", 1)[0]
        neighbors = _neighbors(query, node)
        chunk = {
            "id": node.id,
            "kind": node.kind,
            "module": module,
            "file": node.file,
            "lines": [node.lineno, node.endlineno],
            "signature": node.signature,
            "docstring": node.docstring,
            "deprecated": node.is_deprecated or None,
            "neighbors": neighbors,
            "text": _embed_text(node, module, neighbors),
        }
        chunks.append({k: v for k, v in chunk.items() if v not in (None, {}, [])})
    return chunks


def render_rag(query: Query) -> str:
    """RAG chunks as JSONL (one JSON object per line)."""
    return "".join(
        json.dumps(c, ensure_ascii=False) + "\n" for c in build_chunks(query)
    )


def _neighbors(query: Query, node) -> dict:
    n: dict = {}
    if node.kind == "function":
        callees = query.callees(node.id)
        callers = query.callers(node.id)
        if callees:
            n["calls"] = callees
        if callers:
            n["called_by"] = callers
        ret = node.extras.get("returns")
        if ret:
            n["returns"] = ret
    if node.kind == "class":
        bases = query.bases(node.id)
        subs = query.subclasses(node.id)
        if bases:
            n["bases"] = bases
        if subs:
            n["subclasses"] = subs
        reg = node.extras.get("registry")
        if reg:
            n["registered_as"] = reg.get("key")
    return n


def _embed_text(node, module, neighbors) -> str:
    """A compact, self-contained string for the embedding model."""
    name = node.id.rsplit(".", 1)[-1]
    parts = [f"{node.kind} {name} in {module}."]
    if node.signature:
        parts.append(f"Signature: {node.signature}.")
    if node.docstring:
        first = node.docstring.strip().splitlines()[0].strip()
        if first:
            parts.append(first)
    if neighbors.get("bases"):
        parts.append("Inherits: " + ", ".join(_short(b) for b in neighbors["bases"]) + ".")
    if neighbors.get("calls"):
        parts.append("Calls: " + ", ".join(_short(c) for c in neighbors["calls"][:8]) + ".")
    if neighbors.get("called_by"):
        parts.append("Called by: " + ", ".join(_short(c) for c in neighbors["called_by"][:8]) + ".")
    if neighbors.get("registered_as"):
        parts.append(f"Registered as '{neighbors['registered_as']}'.")
    return " ".join(parts)


def _short(node_id: str) -> str:
    return node_id.rsplit(".", 1)[-1]
