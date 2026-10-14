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

The answer also says what it did with the question (pack honesty,
``docs/design/pack_honesty.md``): what each seed became, that a seed which resolved to
nothing is a refusal rather than a silent global pack, which kinds of node can never be
in a pack, and — with seeds — that the walk runs from the seeds to what they *use*, so
their callers are never in it.
"""

from __future__ import annotations

from collections import Counter

from codemap.query import RANKED_KINDS, Query

# The signals a context consumer wants per symbol, compact. Kept deterministic.
_KIND_TAG = {"module": "mod", "class": "class", "function": "fn"}

_DIRECTION_GLOBAL = ("global importance: a symbol ranks by how much of the graph uses it "
                     "(usage edges, user→used)")
_DIRECTION_SEEDED = ("from the seeds to what they use, directly or transitively; callers "
                     "of a seed are never reached, so never in this pack")


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


def _coverage(query: Query, *, seeded: bool, root: str | None) -> dict:
    """What a pack can never contain, said every time (R1-C28: a field that appears
    only when something is wrong cannot be read by a machine)."""
    never = Counter(n.kind for nid, n in query.graph.nodes.items()
                    if n.kind not in RANKED_KINDS
                    and (root is None or query.root_of(nid) == root))
    return {"ranked_kinds": sorted(RANKED_KINDS),
            "never_in_pack": dict(sorted(never.items())),
            "direction": _DIRECTION_SEEDED if seeded else _DIRECTION_GLOBAL}


def build_pack(query: Query, *, budget: int, seeds=(), root: str | None = None) -> dict:
    """Rank symbols and greedily pack the most relevant under ``budget`` tokens.

    Returns ``{budget, used_tokens, total_ranked, included, truncated, items, seeds,
    unreachable_from_seeds, coverage}`` where ``items`` is rank-ordered
    ``[{id, kind, rank, tokens, text}]``. Rank-order iteration means top hubs (or
    seed-relevant symbols) are included before leaves; an item that would overflow the
    budget is skipped so smaller relevant items can still fit.

    With seeds, only what the seeds can reach is packed, and the count left out is
    ``unreachable_from_seeds`` (``None`` without seeds — the notion does not apply).
    If **no** seed resolves to a rankable symbol the answer is a refusal —
    ``{error, budget, seeds, coverage}`` and no items — never the global pack, which
    answers a different question under the same header.
    """
    seeds = tuple(seeds or ())
    coverage = _coverage(query, seeded=bool(seeds), root=root)
    seed_block = None
    reach = None
    if seeds:
        res = query.seed_resolution(seeds, root=root)
        seed_block = {"requested": res["seeds"], "unresolved": res["unresolved"]}
        if not res["ids"]:
            return {
                "error": "no seed resolved to a rankable symbol "
                         f"({', '.join(res['unresolved'])}); refusing rather than "
                         "returning the global pack, which answers a different question",
                "budget": budget,
                "seeds": seed_block,
                "coverage": coverage,
            }
        reach = query.reachable_from(res["ids"], root=root)
    ranked = query.rank(seeds=seeds, root=root)
    order = sorted(ranked, key=lambda n: (-ranked[n], n))  # rank desc, id tiebreak
    unreachable = None
    if reach is not None:
        unreachable = sum(1 for n in order if n not in reach)
        order = [n for n in order if n in reach]
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
        "total_ranked": len(ranked),
        "included": len(items),
        "truncated": truncated,
        "items": items,
        "seeds": seed_block,
        "unreachable_from_seeds": unreachable,
        "coverage": coverage,
    }


def _seed_lines(block: dict | None) -> list[str]:
    if not block:
        return []
    lines = []
    for s in block["requested"]:
        if s["ambiguous"]:
            lines.append(f"_Ambiguous seed `{s['input']}`: {len(s['matched'])} definitions, "
                         f"the pack is biased to all of them — "
                         f"{', '.join(f'`{m}`' for m in s['matched'])}._")
    for s in block["requested"]:
        if s["matched"]:
            continue
        why = ("no symbol, file or node id by that name" if s["via"] == "none" else
               "matched only " + ", ".join(f"{n} {k}" for k, n in s["unrankable"].items())
               + " — not ranked")
        lines.append(f"_Unresolved seed `{s['input']}` — biases nothing: {why}._")
    return lines


def _coverage_line(cov: dict, unreachable: int | None) -> str:
    never = ", ".join(f"{n} {k}" for k, n in cov["never_in_pack"].items()) or "none"
    line = (f"_Never in a pack: {never} nodes (only {', '.join(cov['ranked_kinds'])} are "
            f"ranked). Direction: {cov['direction']}")
    if unreachable is not None:
        line += f"; {unreachable} symbols unreachable from the seeds were left out"
    return line + "._"


def render_payload(p: dict, *, target: str, seeds=()) -> str:
    """Markdown for a payload :func:`build_pack` already computed (one ranking, one
    answer — the CLI renders the same dict it decides its exit code from)."""
    seeds = tuple(seeds or ())
    if "error" in p:
        lines = [f"# Context pack — `{target}` · refused", "",
                 "_No seed resolved to a rankable symbol, so there is nothing to rank "
                 "relevance by — not falling back to global importance, which answers a "
                 "different question._", ""]
        for note in _seed_lines(p["seeds"]):
            lines += [note, ""]
        lines += [_coverage_line(p["coverage"], None)]
        return "\n".join(lines).rstrip() + "\n"
    seed_note = f" · seeds: {', '.join(seeds)}" if seeds else " · global importance"
    lines = [
        f"# Context pack — `{target}`{seed_note}",
        "",
        f"_{p['included']} / {p['total_ranked']} symbols · "
        f"{p['used_tokens']} / {p['budget']} tokens"
        f"{' · truncated (budget reached)' if p['truncated'] else ''}. "
        "Ranked by PageRank importance; token estimate ≈ 4 chars/token._",
        "",
    ]
    for note in _seed_lines(p["seeds"]):  # one paragraph each — joined they read as one
        lines += [note, ""]
    lines += [_coverage_line(p["coverage"], p["unreachable_from_seeds"]), ""]
    for it in p["items"]:
        lines.append(f"- {it['text']}")
    if not p["items"]:
        lines.append("_nothing fit the budget._")
    return "\n".join(lines).rstrip() + "\n"


def render_pack(query: Query, *, budget: int, seeds=(), root: str | None = None) -> str:
    """Human/agent-readable markdown for a budgeted context pack."""
    p = build_pack(query, budget=budget, seeds=seeds, root=root)
    return render_payload(p, target=query.graph.target, seeds=seeds)
