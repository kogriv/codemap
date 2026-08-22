"""Semantic search via a retrieval adapter, enriched to codemap symbols (R1-C16).

The codemap-native half of a retrieval adapter. Lives in ``serve`` (not
``integrations``) because it needs the query layer: the ``integrations`` layer is a
near-leaf opt-in gate and may not depend on ``query`` (enforced by codemap's own
architecture contract). So the adapter returns raw location hits (no graph), and
this module — allowed to use both ``query`` and ``integrations`` — resolves each
``(file, line)`` to the **exact codemap symbol** at that location. The external tool
supplies fuzzy relevance; codemap supplies exact structure — the composition (fuzzy
retrieval → codemap symbols) neither gives alone.

Adapter-mode only (``mode=ADAPTER``): a router can only forward its answer as-is, so
it can't be enriched — for a router-only semantic tool (e.g. GitNexus, NC-licensed),
use ``codemap route semantic-search`` instead. The core works without any of this:
no enabled+installed adapter → ``{resolver: None, hits: []}``, never an error.
"""

from __future__ import annotations

from typing import Any

from codemap.integrations import (
    IntegrationConfig, IntegrationMode, SemanticHit, is_permissive, load_config, resolve,
)
from codemap.query import Query


def semantic_search(query: Query, text: str, *, root: str = ".",
                    config: IntegrationConfig | None = None,
                    limit: int = 10) -> dict[str, Any]:
    """Resolve a semantic-search adapter, run it, enrich hits to codemap symbols.

    Returns ``{resolver, disclaimer, hits}`` where ``hits`` is a list of
    :class:`~codemap.integrations.base.SemanticHit` dicts sorted by score (each
    de-duplicated to one entry per resolved symbol, keeping its best-scoring chunk).
    ``resolver`` is None when no adapter is enabled+installed — the caller degrades.
    """
    cfg = config if config is not None else load_config(root)
    adapter = resolve("semantic-search", config=cfg, root=root,
                      mode=IntegrationMode.ADAPTER)
    if adapter is None:
        return {"resolver": None, "disclaimer": None, "hits": []}

    raw = adapter.search("semantic-search", text, root=root, limit=limit)
    hits: list[SemanticHit] = []
    seen: dict[str, int] = {}  # symbol id → index in `hits` (dedup, keep best score)
    for r in raw:
        file, line = r["file"], r["start_line"]
        symbol = query.symbol_at(file, line)
        hit = SemanticHit(
            file=file, start_line=line, end_line=r.get("end_line"),
            score=r["score"], symbol=symbol,
            resolution="symbol" if symbol else "unresolved",
        )
        if symbol is not None and symbol in seen:
            if hit.score > hits[seen[symbol]].score:  # same symbol → keep higher score
                hits[seen[symbol]] = hit
            continue
        if symbol is not None:
            seen[symbol] = len(hits)
        hits.append(hit)

    hits.sort(key=lambda h: (-h.score, h.file, h.start_line))
    # Adapters are permissive by policy, so disclaimer is normally None; kept for
    # uniformity with the router path (and any future edge case).
    disclaimer = None if is_permissive(adapter.license) else adapter.disclaimer()
    return {
        "resolver": adapter.name,
        "disclaimer": disclaimer,
        "hits": [h.to_dict() for h in hits],
    }
