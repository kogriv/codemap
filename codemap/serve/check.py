"""Render the architecture-contract check (R1-C3) — structured + markdown.

The gate itself lives in ``codemap.arch``; this is the presentation layer shared by
the ``check`` CLI command and the ``check`` serve op. A clean run is deliberately
quiet (one line); a failing run names every offending import edge so the fix is
mechanical.
"""

from __future__ import annotations

from codemap.arch import ArchitectureContract, Violation

_EDGE_CAP = 25   # offending edges listed per rule before "+N more"


def _not_judged(query, contract: ArchitectureContract) -> list[dict]:
    """What an enforced rule did **not** look at (R1-C30-f2).

    `no_cycles` gates the *eager* import graph on purpose: a function-local import is the
    accepted way to break an import cycle, and failing a build for applying the remedy
    would be worse than the disease. But a gate that judges a subset and then reports
    "Contract satisfied" makes the reader's conclusion — the graph is acyclic — wider than
    the fact. That is the R1-C29 defect (a property claim over a partial map) moved from
    the report into the gate, and the second real target ran into it within a day.

    Declared **always** while the rule is enforced, `count: 0` included, on the R1-C28 rule:
    a field that appears only when there is something to say forces a machine consumer to
    tell "nothing was skipped" from "this build does not report skips", and it cannot.
    """
    if not contract.no_cycles or contract.no_lazy_cycles:
        return []   # not enforced, or the contract opted into judging them too
    lazy = query.lazy_import_cycles()
    return [{
        "rule": "no_cycles",
        "judged": "the eager import graph — imports that run at import time",
        "not_judged": "dependency cycles closed only by a function-local import",
        "count": len(lazy),
        "note": ("a lazy import does not run at import time, so such a cycle cannot break "
                 "on import; it is still mutual coupling. Set `no_lazy_cycles = true` to "
                 "gate these as well, or see `report architecture` for the list."),
    }]


def build_check(query, contract: ArchitectureContract, violations: list[Violation]) -> dict:
    """Structured result: ok flag + violations with their concrete edges.

    ``ok`` answers *may the pipeline proceed?*, so an unreadable ``codemap.toml`` makes it
    false with no violations listed — there are none to list, because no rule ever ran
    (R1-C27). ``contract_error`` says why. This is the JSON-first surface, so it carried
    the same lie as the markdown one and is fixed in the same place.

    ``scope`` says what each enforced rule did not judge — always present, so "nothing was
    left out" is a statement rather than an absence (R1-C30-f2).
    """
    return {
        "target": query.graph.target,
        "contract_empty": contract.is_empty(),
        "contract_error": contract.error,
        "ok": not violations and contract.error is None,
        "violations": [
            {"rule": v.rule, "summary": v.summary,
             "edges": [list(e) for e in v.edges],
             "modules": list(v.modules)}
            for v in violations
        ],
        "scope": _not_judged(query, contract),
    }


def render_check(query, contract: ArchitectureContract, violations: list[Violation]) -> str:
    target = query.graph.target
    # R1-C27: ask `error` before `is_empty()`. A contract that would not parse used to be
    # reported as a contract that does not exist, which is how one missing `]` turned a
    # failing gate green. Nothing was enforced either way — but only one of the two is the
    # user's decision, and the caller exits non-zero on this one.
    if contract.error:
        return (f"# Architecture check — `{target}`\n\n"
                f"❌ **Contract not read — nothing was enforced.** {contract.error}\n\n"
                "_Fix `codemap.toml` (or remove it) and run again. This is a failure, not "
                "an absent contract: rules may exist that no rule-check ran against._\n")
    if contract.is_empty():
        return (f"# Architecture check — `{target}`\n\n"
                "_No `[architecture]` contract found in codemap.toml — nothing to enforce._\n")
    if not violations:
        rules = []
        if contract.layers:
            rules.append(f"layered ({len(contract.layers)})")
        if contract.independent:
            rules.append(f"independent ({len(contract.independent)})")
        if contract.forbidden:
            rules.append(f"forbidden ({len(contract.forbidden)})")
        if contract.no_cycles:
            rules.append("no_cycles")
        if contract.no_lazy_cycles:
            rules.append("no_lazy_cycles")
        if contract.exhaustive:
            rules.append("exhaustive")
        return (f"# Architecture check — `{target}`\n\n"
                f"✅ **Contract satisfied.** Rules enforced: {', '.join(rules)}.\n"
                + _render_scope(query, contract))

    out = [f"# Architecture check — `{target}`", "",
           f"❌ **{len(violations)} rule(s) broken.**", ""]
    for v in violations:
        out.append(f"## `{v.rule}` — {v.summary}")
        out.append("")
        if v.edges:
            for u, w in v.edges[:_EDGE_CAP]:
                out.append(f"- `{u}` → `{w}`")
            if len(v.edges) > _EDGE_CAP:
                out.append(f"- _… {len(v.edges) - _EDGE_CAP} more_")
        for m in v.modules:
            out.append(f"- {m}")
        out.append("")
    return "\n".join(out).rstrip() + "\n" + _render_scope(query, contract)


def _render_scope(query, contract: ArchitectureContract) -> str:
    """The one line a passing `no_cycles` must never be read without."""
    scope = _not_judged(query, contract)
    if not scope:
        return ""
    s = scope[0]
    if not s["count"]:
        return ("\n_`no_cycles` judged the eager import graph; no dependency cycle is closed "
                "only by a function-local import either._\n")
    return (f"\n_`no_cycles` judged **the eager import graph only** — imports that run at "
            f"import time. **{s['count']}** dependency cycle(s) closed only by a "
            f"function-local import were **not** judged: such a cycle cannot break on "
            f"import, but the coupling is real. `report architecture` lists them; "
            f"`no_lazy_cycles = true` gates them._\n")
