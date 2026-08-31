"""Architecture contracts + enforcement gate (R1-C3).

`architecture` (M16) *describes* the system shape — layers, cycles, coupling. This
turns description into a **declarative contract that fails in CI**, the import-linter
/ ArchUnit move: you write the intended architecture down once, and any import that
breaks it is a non-zero exit with the offending edges named.

The contract lives in ``codemap.toml`` under ``[architecture]`` (same file the
integration gate reads). All rules operate on the **core** module import graph
(consumer roots — tests/examples/… — are never subject to layering):

    [architecture]
    # ordered top → bottom; a layer may import only layers *below* it.
    layers = ["visualization", "analysis", "indicators", "data", "core"]
    # groups whose members must not import one another (either direction).
    independent = [["indicators", "data"]]
    # hard bans regardless of layering: `from` must not import `to`.
    forbidden = [{ from = "core", to = "analysis" }]
    # the import graph must be acyclic *at import time* (the eager graph).
    no_cycles = true
    # also gate the coupling a lazy import hides: cycles closed only by an import
    # written inside a function. Off by default — see below.
    no_lazy_cycles = false
    # every core module's layer must appear in `layers` (catches a new,
    # undeclared top-level package slipping in).
    exhaustive = false

A layer is the component just under the package root (``pkg.<layer>...``) — the same
notion `Query.layers()` uses. Rules that reference a layer not present in the graph
are simply inert (no module → no edge to break), so a contract can be written ahead
of the code.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from codemap.tomlio import read_toml


@dataclass(frozen=True)
class ArchitectureContract:
    """Parsed ``[architecture]`` rules. Empty contract = nothing to enforce.

    ``error`` carries the reason ``codemap.toml`` could not be read, if it could not be
    (R1-C27). It is *not* folded into ``is_empty()``: "there are no rules" and "there may
    be rules and I could not read them" are different answers, and a caller that treats
    them the same is the bug this field exists to prevent. Ask ``error`` first.
    """

    layers: tuple[str, ...] = ()
    independent: tuple[tuple[str, ...], ...] = ()
    forbidden: tuple[tuple[str, str], ...] = ()
    no_cycles: bool = False
    no_lazy_cycles: bool = False
    exhaustive: bool = False
    error: str | None = None
    # R1-C35: the file this contract was looked for in. "No contract found" is only
    # actionable next to *where* we looked — a reader in the wrong directory cannot tell
    # an absent contract from a mislocated one, and both exit 0.
    path: str | None = None

    def is_empty(self) -> bool:
        return not (self.layers or self.independent or self.forbidden
                    or self.no_cycles or self.no_lazy_cycles or self.exhaustive)


@dataclass(frozen=True)
class Violation:
    """One broken rule, with the concrete import edges (or cycle) that break it."""

    rule: str            # layered | independent | forbidden | no_cycles | no_lazy_cycles
    #                      | exhaustive
    summary: str         # human one-liner
    edges: tuple[tuple[str, str], ...] = field(default=())   # offending (importer, imported)
    modules: tuple[str, ...] = field(default=())             # for exhaustive / cycles


def load_contract(root: str | Path = ".") -> ArchitectureContract:
    """Read ``[architecture]`` from ``codemap.toml`` under ``root`` (empty if absent).

    Tolerant by design — a broken toml must not wedge ``check``, so nothing raises. But a
    file that will not parse is reported through ``error`` rather than being returned as an
    absent contract: a typo used to turn a failing gate green (R1-C27).
    """
    # Absolute on purpose: "not found in codemap.toml" is what the reader already
    # assumed. The whole value of the line is *which* codemap.toml, so it answers with a
    # path that is unambiguous from any working directory. (The graph artifact stays free
    # of absolute paths — D5 — but this is terminal output, not the artifact.)
    path = Path(root).resolve() / "codemap.toml"
    data, error = read_toml(path)
    if error:
        return ArchitectureContract(error=error, path=str(path))
    return replace(parse_contract(data.get("architecture", {})), path=str(path))


def parse_contract(section: dict) -> ArchitectureContract:
    """Build a contract from the parsed ``[architecture]`` table (validated leniently)."""
    forbidden = []
    for item in section.get("forbidden", []) or []:
        if isinstance(item, dict) and "from" in item and "to" in item:
            forbidden.append((str(item["from"]), str(item["to"])))
    independent = tuple(
        tuple(str(x) for x in grp)
        for grp in (section.get("independent", []) or [])
        if isinstance(grp, (list, tuple)) and len(grp) >= 2
    )
    return ArchitectureContract(
        layers=tuple(str(x) for x in (section.get("layers", []) or [])),
        independent=independent,
        forbidden=tuple(forbidden),
        no_cycles=bool(section.get("no_cycles", False)),
        no_lazy_cycles=bool(section.get("no_lazy_cycles", False)),
        exhaustive=bool(section.get("exhaustive", False)),
    )


def _core_layer_edges(query) -> list[tuple[str, str, str, str]]:
    """Cross-layer core→core import edges as (importer, imported, layer_i, layer_j)."""
    ig = query.import_graph
    out = []
    for u, v in ig.edges():
        if query.root_of(u) != "core" or query.root_of(v) != "core":
            continue
        lu, lv = query._layer_of(u), query._layer_of(v)
        if lu != lv:
            out.append((u, v, lu, lv))
    return out


def check_contract(query, contract: ArchitectureContract) -> list[Violation]:
    """Evaluate every rule against the graph; return the violations (empty = clean)."""
    if contract.is_empty():
        return []
    violations: list[Violation] = []
    edges = _core_layer_edges(query)

    # -- layered: a layer may import only layers below it in the ordered list ----
    if contract.layers:
        rank = {name: i for i, name in enumerate(contract.layers)}
        bad = tuple(
            (u, v) for (u, v, lu, lv) in edges
            if lu in rank and lv in rank and rank[lv] < rank[lu]
        )
        if bad:
            violations.append(Violation(
                "layered",
                f"{len(bad)} import(s) point up the layer stack "
                f"({' → '.join(contract.layers)})",
                edges=tuple(sorted(bad)),
            ))

    # -- independent: members of a group must not import one another -------------
    for grp in contract.independent:
        gset = set(grp)
        bad = tuple(
            (u, v) for (u, v, lu, lv) in edges
            if lu in gset and lv in gset and lu != lv
        )
        if bad:
            violations.append(Violation(
                "independent",
                f"layers {{{', '.join(grp)}}} must be independent but import each other",
                edges=tuple(sorted(bad)),
            ))

    # -- forbidden: explicit from→to bans ---------------------------------------
    for frm, to in contract.forbidden:
        bad = tuple((u, v) for (u, v, lu, lv) in edges if lu == frm and lv == to)
        if bad:
            violations.append(Violation(
                "forbidden",
                f"`{frm}` must not import `{to}`",
                edges=tuple(sorted(bad)),
            ))

    # -- no_cycles: no cycle among imports that run at import time ---------------
    # R1-C29: deliberately the eager graph. `no_cycles` is a gate against the import-order
    # failure, and a function-local import is the accepted fix for it — failing a build
    # because someone applied that fix would punish the remedy.
    #
    # R1-C30-f2 settles what §7 of gaps/import_map_module_level_2026-08-28.md left open,
    # after the second real target ran the gate: what it must NOT do is *stay silent*. A
    # clean `no_cycles` run on a tree with 48 lazy cycles printed "Contract satisfied.
    # Rules enforced: no_cycles", from which a reader concludes the graph is acyclic — the
    # same property claim over a partial judgement that R1-C29 removed from the report,
    # migrated into the gate. So: the gate stays eager, the *disclosure* is mandatory (see
    # `build_check`), and a contract that wants the coupling gated says so.
    if contract.no_cycles:
        cycles = query.import_cycles()
        if cycles:
            worst = sorted(cycles, key=lambda c: (len(c), c))
            violations.append(Violation(
                "no_cycles",
                f"{len(cycles)} import cycle(s)",
                modules=tuple(" → ".join(c) + " → " + c[0] for c in worst),
            ))

    # -- no_lazy_cycles: opt in to gating the coupling a lazy import hides -------
    # Both facts are true at once — a gate you walk around by making the import lazy is
    # not a gate, and a lazy import is the accepted way to break an import cycle — so this
    # is the contract owner's call to state, not a default to pick on their behalf.
    if contract.no_lazy_cycles:
        lazy = query.lazy_import_cycles()
        if lazy:
            worst = sorted(lazy, key=lambda c: (len(c), c))
            violations.append(Violation(
                "no_lazy_cycles",
                f"{len(lazy)} dependency cycle(s) closed only by a function-local import",
                modules=tuple(" → ".join(c) + " → " + c[0] for c in worst),
            ))

    # -- exhaustive: every core module's layer must be declared -----------------
    if contract.exhaustive and contract.layers:
        declared = set(contract.layers)
        undeclared = sorted({
            query._layer_of(m) for m in query.import_graph.nodes
            if query.root_of(m) == "core"
            and query._layer_of(m) not in declared
            and query._layer_of(m) != "(root)"
        })
        if undeclared:
            violations.append(Violation(
                "exhaustive",
                f"{len(undeclared)} undeclared layer(s) not in the contract",
                modules=tuple(undeclared),
            ))

    return violations
