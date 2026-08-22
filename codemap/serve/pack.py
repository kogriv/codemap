"""Token-budgeted context pack (R1-C6) — codemap as a context provider.

codemap answers point queries; this adds the other half an AI-context tool needs:
*ranking* (what matters most) + a *budgeted render* (fit the most relevant slice of
the graph into N tokens). Nodes are scored by personalized PageRank
(:meth:`codemap.query.Query.rank`) — global importance, or relevance to ``seeds``
you're working on — then rendered highest-rank-first until the token budget is spent.

Token counting is a deterministic, dependency-free heuristic (~4 chars/token, the
common rule of thumb) — no tokenizer to install, and stable across runs. The pack is
a *lower bound on relevance, upper bound on size*: it never exceeds the budget, and
top hubs land before leaves (the acceptance).
"""

from __future__ import annotations

from codemap.query import Query

# The signals a context consumer wants per symbol, compact. Kept deterministic.
_KIND_TAG = {"module": "mod", "class": "class", "function": "fn"}


def estimate_tokens(text: str) -> int:
    """Cheap, deterministic token estimate (~4 chars/token); >=1 for any content."""
    return max(1, len(text) // 4)


def _item_text(node) -> str:
    """One compact context line for a symbol: id, kind, signature, docstring head."""
    tag = _KIND_TAG.get(node.kind, node.kind)
    sig = f" {node.signature}" if node.signature else ""
    doc = ""
    if node.docstring:
        first = node.docstring.strip().splitlines()[0].strip()
        if first:
            doc = f" — {first}"
    dep = " [deprecated]" if node.is_deprecated else ""
    return f"{node.id} ({tag}){sig}{dep}{doc}"


def build_pack(query: Query, *, budget: int, seeds=(), root: str | None = None) -> dict:
    """Rank symbols and greedily pack the most relevant under ``budget`` tokens.

    Returns ``{budget, used_tokens, total_ranked, included, truncated, items}`` where
    ``items`` is rank-ordered ``[{id, kind, rank, tokens, text}]``. Rank-order iteration
    means top hubs (or seed-relevant symbols) are included before leaves; an item that
    would overflow the budget is skipped so smaller relevant items can still fit.
    """
    ranked = query.rank(seeds=seeds, root=root)
    order = sorted(ranked, key=lambda n: (-ranked[n], n))  # rank desc, id tiebreak
    items: list[dict] = []
    used = 0
    truncated = False
    for nid in order:
        node = query.graph.nodes.get(nid)
        if node is None:
            continue
        text = _item_text(node)
        cost = estimate_tokens(text)
        if used + cost > budget:
            truncated = True
            continue  # skip; a later, smaller item may still fit
        items.append({"id": nid, "kind": node.kind, "rank": ranked[nid],
                      "tokens": cost, "text": text})
        used += cost
    return {
        "budget": budget,
        "used_tokens": used,
        "total_ranked": len(order),
        "included": len(items),
        "truncated": truncated,
        "items": items,
    }


def render_pack(query: Query, *, budget: int, seeds=(), root: str | None = None) -> str:
    """Human/agent-readable markdown for a budgeted context pack."""
    p = build_pack(query, budget=budget, seeds=seeds, root=root)
    seed_note = f" · seeds: {', '.join(seeds)}" if seeds else " · global importance"
    lines = [
        f"# Context pack — `{query.graph.target}`{seed_note}",
        "",
        f"_{p['included']} / {p['total_ranked']} symbols · "
        f"{p['used_tokens']} / {p['budget']} tokens"
        f"{' · truncated (budget reached)' if p['truncated'] else ''}. "
        "Ranked by PageRank importance; token estimate ≈ 4 chars/token._",
        "",
    ]
    for it in p["items"]:
        lines.append(f"- {it['text']}")
    if not p["items"]:
        lines.append("_nothing fit the budget._")
    return "\n".join(lines).rstrip() + "\n"
