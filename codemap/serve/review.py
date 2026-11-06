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


def _module_dossier(query: Query, sid: str, node) -> dict:
    """A changed line of module-level code (R1-C82 D2): about the module, not its members.

    The generic dossier sums callers and call sites over every member, which turned a
    one-line constant edit into "[high] … 123 site(s) — check on signature change". A
    module has no signature; what module-level code reaches is whoever imports it.
    """
    consumers: dict[str, int] = {}
    for ref in query.references_to(sid, include_members=False):
        consumers[ref["root"]] = consumers.get(ref["root"], 0) + 1
    importers = sum(consumers.values())
    risk, score = _risk(importers, {r: v for r, v in consumers.items() if r != "core"}, 0, False)
    return {
        "symbol": sid, "kind": "module", "file": node.file if node else None, "lines": None,
        "callers": [], "callees": [], "call_contract": [],
        "columns": {"reads": [], "writes": []},
        "consumers_by_root": consumers,
        "module_level": True,
        "risk": risk, "risk_score": score,
    }


def place_files(query: Query, files: list[str]) -> dict:
    """Diff paths → graph paths: exact, else a unique suffix match either way (R1-C87 D1).

    A diff is relative to the git root; a graph to the common parent of its build roots
    (R1-C31). Built from a subdirectory, the two differ, and an exact-only match turned a
    real change into "0 changed symbol(s)". Placed by a suffix at a ``/`` boundary — the
    diff longer (``research/shared/x.py`` → ``shared/x.py``) or the graph longer — and only
    when exactly one graph file fits; several are named, not chosen between.
    """
    known = {n.file for n in query.graph.nodes.values() if n.file}
    placed: dict[str, str] = {}
    mapped: dict[str, str] = {}
    unplaced: list[dict] = []
    skipped: list[str] = []
    for f in dict.fromkeys(files):
        if f in known:
            placed[f] = f
            continue
        cands = sorted(g for g in known if f.endswith("/" + g) or g.endswith("/" + f))
        if len(cands) == 1:
            placed[f] = mapped[f] = cands[0]
        elif f.endswith((".py", ".pyi")):
            unplaced.append({"file": f, "candidates": cands})
        else:
            skipped.append(f)
    return {"placed": placed, "mapped": mapped, "unplaced": unplaced, "skipped": skipped}


def _doc_entry(query: Query, doc_id: str) -> dict:
    """A changed doc page and the symbols it documents (R1-C89)."""
    node = query.graph.nodes.get(doc_id)
    documents = sorted({e.target for e in query.graph.edges
                        if e.source == doc_id and e.type == "references"})
    return {"doc": doc_id, "file": node.file if node else None, "documents": documents}


def build_symbol_dossier(query: Query, sid: str) -> dict:
    """Everything a reviewer needs about one changed symbol (F17)."""
    node = query.graph.nodes.get(sid)
    kind = node.kind if node else None
    if kind == "module":
        return _module_dossier(query, sid, node)
    callers = query.callers(sid)
    contract = query.call_contract(sid)
    cols = query.columns_of(sid) if kind == "function" else {"reads": [], "writes": []}
    consumers = _consumers_by_root(query, sid)
    touches = bool(cols["reads"] or cols["writes"])
    # R1-C82: an attribute has no callers; its reach is who reads or writes it (the
    # `accesses` edges D3 added), or a widely read constant would rank "low".
    reach = sum(consumers.values()) if kind == "attribute" else len(callers)
    risk, score = _risk(reach, consumers, len(contract), touches)
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
                 symbols: list[str] | None = None, base_graph=None) -> dict:
    """Consolidated change-set review from diff hunks and/or explicit symbols.

    Returns ``{changed: [dossier…], summary}`` with dossiers risk-sorted (highest
    first). ``summary`` carries the symbol count, union blast-radius by root, and
    the count of unresolved hunks (lines in placed files outside any symbol) and, apart
    from them, the diff files not in the graph (R1-C87) so nothing is
    silently dropped.

    ``base_graph`` (R1-C5): a 'before' graph to API-diff against. Hunk-based review
    sees only *modified* lines; the diff adds the symbols hunks miss — **removed**
    and **added** public symbols and **breaking** signature changes — under
    ``api_diff``.
    """
    ids = set(symbols or [])
    unresolved = []
    placement = place_files(query, [h["file"] for h in hunks or []])
    # R1-C89: a doc page is a node without lines; its hunks name the page, not nothing.
    doc_of = {n.file: n.id for n in query.graph.nodes.values() if n.kind == "doc" and n.file}
    docs: set[str] = set()
    if hunks:
        for h in hunks:
            file = placement["placed"].get(h["file"])
            if file is None:
                continue                  # R1-C87 D2: reported as unplaced, not as unresolved
            if file in doc_of:
                docs.add(doc_of[file])
                continue
            for rng in h.get("ranges", []):
                start, end = int(rng[0]), int(rng[-1])
                got = query.symbols_in_range(file, start, end)
                if got:
                    ids.update(got)
                else:
                    unresolved.append({"file": file, "range": [start, end]})
            for rng in h.get("soft", []):
                # D1b: a blank/comment line names its definition, never the module
                start, end = int(rng[0]), int(rng[-1])
                _defs, module = query._defs_in_file(file)
                ids.update(s for s in query.symbols_in_range(file, start, end) if s != module)
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
        "changed_docs": len(docs),
        "mapped_paths": placement["mapped"],
        "unplaced_files": placement["unplaced"],
        "skipped_files": placement["skipped"],
    }
    result = {"changed": dossiers, "summary": summary,
              "changed_docs": [_doc_entry(query, d) for d in sorted(docs)]}
    if base_graph is not None:
        from codemap.serve.apidiff import build_apidiff
        result["api_diff"] = build_apidiff(base_graph, query.graph)
    return result


def render_review(query: Query, *, hunks: list[dict] | None = None,
                  symbols: list[str] | None = None, base_graph=None) -> str:
    """Human markdown for a change-set review (highest risk first)."""
    rv = build_review(query, hunks=hunks, symbols=symbols, base_graph=base_graph)
    s = rv["summary"]
    out = ["# Change-set review", ""]
    if s["unplaced_files"]:
        names = ", ".join(u["file"] + (f" (ambiguous: {', '.join(u['candidates'])})"
                                       if u["candidates"] else "") for u in s["unplaced_files"])
        out.append(f"**{len(s['unplaced_files'])} Python file(s) in the diff are not in this graph "
                   f"— nothing in them was reviewed**: {names}. Build the graph over them, or check "
                   f"the diff's path base (`git diff --relative=<dir>`).")
    out.append(f"**{s['changed_symbols']} changed symbol(s)**; "
               f"blast by root: {s['blast_by_root'] or '—'}.")
    if rv["changed_docs"]:
        out.append(f"**{len(rv['changed_docs'])} changed doc page(s)** — check they still "
                   f"describe the code:")
        for d in rv["changed_docs"]:
            names = d["documents"]
            more = f" (+{len(names) - 8} more)" if len(names) > 8 else ""
            out.append(f"- `{d['file'] or d['doc']}` documents {', '.join(names[:8]) or '—'}{more}")
    if s["mapped_paths"]:
        out.append("_Diff paths placed in the graph by suffix: " + ", ".join(
            f"`{a}` → `{b}`" for a, b in sorted(s["mapped_paths"].items())) + "._")
    if s["skipped_files"] and not s["changed_symbols"] and not s["unplaced_files"]:
        out.append(f"_{len(s['skipped_files'])} non-Python file(s) in the diff, not part of a "
                   f"code graph: {', '.join(s['skipped_files'])}._")
    if "api_diff" in rv:
        ad = rv["api_diff"]["summary"]
        out.append(f"**API diff vs baseline:** {ad['breaking_total']} breaking, "
                   f"{ad['removed']} removed, {ad['added']} added.")
    if s["high_risk"]:
        out.append(f"**Review first (high risk):** {', '.join(s['high_risk'])}")
    if s["unresolved_hunks"]:
        out.append(f"_Unresolved hunks (lines outside any symbol): "
                   f"{len(s['unresolved_hunks'])} — inspect manually._")
    out.append("")
    if "api_diff" in rv:
        ad = rv["api_diff"]
        breaking = [c for c in ad["changes"] if c["severity"] == "breaking"]
        if ad["removed"] or breaking:
            out.append("## API breaking changes (not in the hunks)")
            for sym in ad["removed"][:20]:
                out.append(f"- **removed** `{sym}`")
            for c in breaking[:20]:
                out.append(f"- **{c['kind']}** `{c['symbol']}` — {c['detail']}")
            out.append("")
    for d in rv["changed"]:
        loc = f" ({d['file']}:{d['lines'][0]})" if d["file"] and d["lines"] else ""
        out.append(f"## [{d['risk']}] {d['symbol']}{loc}")
        if d.get("module_level"):
            n = sum(d["consumers_by_root"].values())
            out.append(f"- Module-level code changed (outside any definition) — runs on import; "
                       f"referenced directly by {n} site(s): {d['consumers_by_root'] or '—'}")
        elif d["consumers_by_root"]:
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

def _soft(text: str) -> bool:
    """A blank or comment-only line: no code changed on it (R1-C82 D1b)."""
    t = text.strip()
    return not t or t.startswith("#")


def _runs(lines: list[int]) -> list[list[int]]:
    """Sorted line numbers → [[start, end], …] of consecutive runs."""
    out: list[list[int]] = []
    for n in sorted(set(lines)):
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return out


def parse_unified_diff(text: str) -> list[dict]:
    """Parse a unified diff → [{file, ranges, soft}] in new-file line numbers.

    R1-C82 D1: only **changed** lines count. The ``@@ +c,d @@`` header spans the hunk's
    context too (three lines each side by default), and reading it whole put untouched
    neighbours — and, through module-level comments, the whole module — into a review of
    a one-line change. Now ``+`` lines give their own numbers; a run of ``-`` lines with no
    ``+`` (a pure deletion) anchors a zero-width range at the new-file line where it stood.

    D1b: a changed line that is blank or a comment goes to ``soft`` instead of ``ranges``.
    Inside a definition it still names that definition; outside every definition it
    names nothing — a comment between two functions is not a change to the module.
    """
    import re
    hdr = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    hard: dict[str, list[int]] = {}
    soft: dict[str, list[int]] = {}
    current = None
    cur = old_left = new_left = 0       # the header's counts tell body lines from headers
    pending: list[str] = []             # texts of a run of '-' lines not yet followed by '+'

    def flush():
        if current and pending:
            (soft if all(_soft(t) for t in pending) else hard)[current].append(cur)
        pending.clear()

    for ln in text.splitlines():
        if old_left > 0 or new_left > 0:              # inside a hunk body
            if ln.startswith("\\"):
                continue                              # "\ No newline at end of file"
            tag, body = (ln[:1], ln[1:]) if ln else (" ", "")
            if tag == "+":
                pending.clear()                       # a replacement: '+' lines carry it
                if current:
                    (soft if _soft(body) else hard)[current].append(cur)
                cur += 1
                new_left -= 1
            elif tag == "-":
                pending.append(body)
                old_left -= 1
            else:                                     # context
                flush()
                cur += 1
                old_left -= 1
                new_left -= 1
            if old_left <= 0 and new_left <= 0:
                flush()
            continue
        if ln.startswith("+++ "):
            path = ln[4:].strip().split("\t")[0]
            if path.startswith("b/"):
                path = path[2:]
            current = None if path == "/dev/null" else path
            if current:
                hard.setdefault(current, [])
                soft.setdefault(current, [])
        elif m := hdr.match(ln):
            old_left = int(m.group(1)) if m.group(1) is not None else 1
            cur = int(m.group(2))
            new_left = int(m.group(3)) if m.group(3) is not None else 1
            if new_left == 0:
                cur += 1        # "+c,0": the deletion sits after new line c
    out = []
    for f in hard:
        h, so = _runs(hard[f]), _runs(soft.get(f, []))
        if h or so:
            out.append({"file": f, "ranges": h, "soft": so})
    return out
