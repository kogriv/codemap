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
    # the import graph must be acyclic.
    no_cycles = true
    # every core module's layer must appear in `layers` (catches a new,
    # undeclared top-level package slipping in).
    exhaustive = false

A layer is the component just under the package root (``pkg.<layer>...``) — the same
notion `Query.layers()` uses. Rules that reference a layer not present in the graph
are simply inert (no module → no edge to break), so a contract can be written ahead
of the code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ArchitectureContract:
    """Parsed ``[architecture]`` rules. Empty contract = nothing to enforce."""

    layers: tuple[str, ...] = ()
    independent: tuple[tuple[str, ...], ...] = ()
    forbidden: tuple[tuple[str, str], ...] = ()
    no_cycles: bool = False
    exhaustive: bool = False

    def is_empty(self) -> bool:
        return not (self.layers or self.independent or self.forbidden
                    or self.no_cycles or self.exhaustive)


@dataclass(frozen=True)
class Violation:
    """One broken rule, with the concrete import edges (or cycle) that break it."""

    rule: str            # layered | independent | forbidden | no_cycles | exhaustive
    summary: str         # human one-liner
    edges: tuple[tuple[str, str], ...] = field(default=())   # offending (importer, imported)
    modules: tuple[str, ...] = field(default=())             # for exhaustive / cycles


def load_contract(root: str | Path = ".") -> ArchitectureContract:
    """Read ``[architecture]`` from ``codemap.toml`` under ``root`` (empty if absent).

    Mirrors the integration gate's tolerance: a missing or malformed file yields an
    empty contract rather than raising — a broken toml must not wedge ``check``.
    """
    path = Path(root) / "codemap.toml"
    if not path.is_file():
        return ArchitectureContract()
    try:
        import tomllib
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ModuleNotFoundError):
        return ArchitectureContract()
    return parse_contract(data.get("architecture", {}))


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

    # -- no_cycles: import graph must be acyclic --------------------------------
    if contract.no_cycles:
        cycles = query.import_cycles()
        if cycles:
            worst = sorted(cycles, key=lambda c: (len(c), c))
            violations.append(Violation(
                "no_cycles",
                f"{len(cycles)} import cycle(s)",
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
