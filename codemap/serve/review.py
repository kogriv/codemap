"""Change-set review — turn a diff into a consolidated review dossier (M15/F17).

The reviewer's real input is a **diff** (files + changed line ranges), not a symbol
name. A11 dogfood found the pieces existed (impact, call_contract, columns_of,
references) but nothing stitched them: 4 changed symbols meant ~20 manual op-calls.

``build_review`` resolves hunks → symbols (via ``Query.symbols_in_range``), then per
symbol assembles callers / signature-change contract / touched columns / cross-root
consumers, plus a synthesized **risk** rank (the signals are all present — F17/R3),
a union blast-radius summary, and a risk-sorted order. ``render_review`` is the
human markdown. No schema change — pure aggregation over existing edges.
"""

from __future__ import annotations

from codemap.query import Query


def resolve_hunks(query: Query, hunks: list[dict]) -> list[str]:
    """[{file, ranges: [[start,end], …]}] → distinct changed symbol ids."""
    changed: set[str] = set()
    for h in hunks:
        file = h["file"]
        for rng in h.get("ranges", []):
            start, end = int(rng[0]), int(rng[-1])
            changed.update(query.symbols_in_range(file, start, end))
    return sorted(changed)


def _consumers_by_root(query: Query, sid: str) -> dict[str, int]:
    by_root: dict[str, int] = {}
    for ref in query.references_to(sid):
        by_root[ref["root"]] = by_root.get(ref["root"], 0) + 1
    return by_root


def _risk(caller_n: int, consumers: dict[str, int], contract_sites: int,
          touches_columns: bool) -> tuple[str, int]:
    """Synthesize a review-priority label from the blast signals (F17/R3).

    Heuristic, honest and documented — not a proof: more inbound reach, more
    external (cross-root) consumers, more distinct call-site shapes, and dataflow
    contact all raise how much a change here warrants scrutiny.
    """
    external = sum(v for r, v in consumers.items() if r != "core")
    score = caller_n + 2 * external + contract_sites + (1 if touches_columns else 0)
    if external or score >= 5:
        return "high", score
    if score >= 2:
        return "medium", score
    return "low", score


def build_symbol_dossier(query: Query, sid: str) -> dict:
    """Everything a reviewer needs about one changed symbol (F17)."""
    node = query.graph.nodes.get(sid)
    kind = node.kind if node else None
    callers = query.callers(sid)
    contract = query.call_contract(sid)
    cols = query.columns_of(sid) if kind == "function" else {"reads": [], "writes": []}
    consumers = _consumers_by_root(query, sid)
    touches = bool(cols["reads"] or cols["writes"])
    risk, score = _risk(len(callers), consumers, len(contract), touches)
    return {
        "symbol": sid,
        "kind": kind,
        "file": node.file if node else None,
        "lines": [node.lineno, node.endlineno] if node else None,
        "callers": callers,
        "callees": query.callees(sid) if kind == "function" else [],
        "call_contract": contract,      # signature-change surface (F7)
        "columns": cols,                # dataflow contact (F6/F11)
        "consumers_by_root": consumers,  # cross-root blast (F1)
        "risk": risk,
        "risk_score": score,
    }


def build_review(query: Query, *, hunks: list[dict] | None = None,
                 symbols: list[str] | None = None) -> dict:
    """Consolidated change-set review from diff hunks and/or explicit symbols.

    Returns ``{changed: [dossier…], summary}`` with dossiers risk-sorted (highest
    first). ``summary`` carries the symbol count, union blast-radius by root, and
    the count of unresolved hunks (module-level / unknown files) so nothing is
    silently dropped.
    """
    ids = set(symbols or [])
    unresolved = []
    if hunks:
        for h in hunks:
            file = h["file"]
            for rng in h.get("ranges", []):
                start, end = int(rng[0]), int(rng[-1])
                got = query.symbols_in_range(file, start, end)
                if got:
                    ids.update(got)
                else:
                    unresolved.append({"file": file, "range": [start, end]})
    ids = {query.canonical(i) or i for i in ids}
    dossiers = [build_symbol_dossier(query, sid) for sid in sorted(ids)]
    dossiers.sort(key=lambda d: (-d["risk_score"], d["symbol"]))

    union_by_root: dict[str, int] = {}
    for d in dossiers:
        for r, v in d["consumers_by_root"].items():
            union_by_root[r] = union_by_root.get(r, 0) + v
    summary = {
        "changed_symbols": len(dossiers),
        "blast_by_root": union_by_root,
        "high_risk": [d["symbol"] for d in dossiers if d["risk"] == "high"],
        "unresolved_hunks": unresolved,
    }
    return {"changed": dossiers, "summary": summary}


def render_review(query: Query, *, hunks: list[dict] | None = None,
                  symbols: list[str] | None = None) -> str:
    """Human markdown for a change-set review (highest risk first)."""
    rv = build_review(query, hunks=hunks, symbols=symbols)
    s = rv["summary"]
    out = ["# Change-set review", ""]
    out.append(f"**{s['changed_symbols']} changed symbol(s)**; "
               f"blast by root: {s['blast_by_root'] or '—'}.")
    if s["high_risk"]:
        out.append(f"**Review first (high risk):** {', '.join(s['high_risk'])}")
    if s["unresolved_hunks"]:
        out.append(f"_Unresolved hunks (module-level / unknown file): "
                   f"{len(s['unresolved_hunks'])} — inspect manually._")
    out.append("")
    for d in rv["changed"]:
        loc = f" ({d['file']}:{d['lines'][0]})" if d["file"] and d["lines"] else ""
        out.append(f"## [{d['risk']}] {d['symbol']}{loc}")
        if d["consumers_by_root"]:
            out.append(f"- Consumers by root: {d['consumers_by_root']}")
        if d["callers"]:
            out.append(f"- Callers ({len(d['callers'])}): "
                       f"{', '.join(d['callers'][:8])}{' …' if len(d['callers']) > 8 else ''}")
        if d["call_contract"]:
            out.append(f"- Call-site contract: {len(d['call_contract'])} site(s) "
                       f"— check on signature change")
        cols = d["columns"]
        if cols["reads"] or cols["writes"]:
            out.append(f"- Columns: reads {cols['reads'] or '—'}, writes {cols['writes'] or '—'}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# -- unified-diff hunk parsing (for CLI `codemap review <diff>`) --------------

def parse_unified_diff(text: str) -> list[dict]:
    """Parse a unified diff → [{file, ranges: [[start,end], …]}] (new-file lines).

    Reads ``+++ b/<path>`` targets and ``@@ -a,b +c,d @@`` hunk headers, taking the
    **new-file** side (``+c,d`` → lines ``c … c+d-1``). Deletions (``d == 0``)
    anchor a zero-width range at ``c`` so a pure deletion still maps to its site.
    """
    import re
    hdr = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
    files: dict[str, list] = {}
    current = None
    for ln in text.splitlines():
        if ln.startswith("+++ "):
            path = ln[4:].strip().split("\t")[0]
            if path.startswith("b/"):
                path = path[2:]
            current = None if path == "/dev/null" else path
            files.setdefault(current, [])
        elif current and (m := hdr.match(ln)):
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            end = start + count - 1 if count else start
            files[current].append([start, max(start, end)])
    return [{"file": f, "ranges": r} for f, r in files.items() if f and r]
