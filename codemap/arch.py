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
    no_type_only_cycles = false
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
    no_type_only_cycles: bool = False
    exhaustive: bool = False
    # R1-C62: the mirror of `exhaustive`. That one asks "is every layer of the code
    # declared?"; this asks "does every declared name exist?". Opt-in, because a contract
    # written ahead of the code is a documented, legitimate use (see the module docstring)
    # and failing on it by default would turn that practice red on somebody else's tree.
    no_phantom_rules: bool = False
    error: str | None = None
    # R1-C35: the file this contract was looked for in. "No contract found" is only
    # actionable next to *where* we looked — a reader in the wrong directory cannot tell
    # an absent contract from a mislocated one, and both exit 0.
    path: str | None = None

    def is_empty(self) -> bool:
        return not (self.layers or self.independent or self.forbidden
                    or self.no_cycles or self.no_lazy_cycles
                    or self.no_type_only_cycles or self.exhaustive
                    or self.no_phantom_rules)


@dataclass(frozen=True)
class Violation:
    """One broken rule, with the concrete import edges (or cycle) that break it."""

    rule: str            # layered | independent | forbidden | no_cycles | no_lazy_cycles
    #                      | no_type_only_cycles | exhaustive
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
    near = _near_miss_tables(data)
    if near:
        return ArchitectureContract(error=near, path=str(path))
    return replace(parse_contract(data.get("architecture", {})), path=str(path))


def _near_miss_tables(data: dict) -> str | None:
    """R1-C76 (design ``contract_table_typo.md``): a table named like ``[architecture]`` but not it.

    ``[architectur]`` used to read as "no contract", exit 0: R1-C69 closed the schema inside the
    table, and the table name stayed the one typo that turned a gate green. Refused even beside a
    real ``[architecture]`` (D2): its rules would never run. Other tables are not checked (D3).
    """
    import difflib

    names = [k for k, v in data.items()
             if k != "architecture" and isinstance(v, dict)
             and difflib.SequenceMatcher(None, k.lower(), "architecture").ratio() >= 0.8]
    if not names:
        return None
    listed = ", ".join(f"`[{k}]`" for k in names)
    return (f"{listed} looks like a misspelling of `[architecture]`; codemap reads only "
            "`[architecture]`, so its rules would never run")


#: R1-C69: the closed schema of ``[architecture]``. A key outside it is an error, not a skip.
_FLAGS = ("no_cycles", "no_lazy_cycles", "no_type_only_cycles", "exhaustive", "no_phantom_rules")
_KNOWN_KEYS = ("layers", "independent", "forbidden") + _FLAGS


def _is_str_list(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def contract_problems(section) -> list[str]:
    """Every way ``section`` departs from the ``[architecture]`` schema, in reading order (R1-C69).

    Empty when the section is valid. Design ``docs/design/contract_validation.md`` D1: unknown
    keys (with the nearest known one suggested), values of the wrong type — `"false"` is a
    string and used to switch a rule *on* — and malformed items, each named by key and index.
    Names that do not exist in the graph are not a schema question (D3, R1-C62).
    """
    import difflib

    if not isinstance(section, dict):
        return [f"`[architecture]` must be a table, got {type(section).__name__}"]
    problems: list[str] = []
    for key in section:
        if key not in _KNOWN_KEYS:
            near = difflib.get_close_matches(key, _KNOWN_KEYS, n=1, cutoff=0.6)
            hint = f" (did you mean `{near[0]}`?)" if near else ""
            problems.append(f"unknown key `{key}`{hint}; known keys: {', '.join(_KNOWN_KEYS)}")
    if "layers" in section and not _is_str_list(section["layers"]):
        problems.append("`layers` must be a list of strings")
    if "independent" in section:
        groups = section["independent"]
        if not isinstance(groups, list):
            problems.append("`independent` must be a list of lists of strings")
        else:
            for i, grp in enumerate(groups):
                if not _is_str_list(grp) or len(grp) < 2:
                    problems.append(f"`independent[{i}]` must be a list of at least 2 strings")
    if "forbidden" in section:
        items = section["forbidden"]
        if not isinstance(items, list):
            problems.append("`forbidden` must be a list of `{ from = \"…\", to = \"…\" }` tables")
        else:
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    problems.append(f"`forbidden[{i}]` must be a table `{{ from = \"…\", to = \"…\" }}`")
                    continue
                extra = sorted(set(item) - {"from", "to"})
                missing = [k for k in ("from", "to") if k not in item]
                wrong = [k for k in ("from", "to") if k in item and not isinstance(item[k], str)]
                if extra:
                    problems.append(f"`forbidden[{i}]` has unknown key(s) "
                                    + ", ".join(f"`{k}`" for k in extra))
                if missing:
                    problems.append(f"`forbidden[{i}]` is missing " + ", ".join(f"`{k}`" for k in missing))
                if wrong:
                    problems.append(f"`forbidden[{i}]`: " + ", ".join(f"`{k}`" for k in wrong)
                                    + " must be a string")
    for flag in _FLAGS:
        if flag in section and not isinstance(section[flag], bool):
            problems.append(f"`{flag}` must be true or false, got {type(section[flag]).__name__} "
                            f"`{section[flag]!r}`")
    return problems


def parse_contract(section: dict) -> ArchitectureContract:
    """Build a contract from the parsed ``[architecture]`` table.

    R1-C69: validated against a closed schema first. A section with any problem is **not
    enforced at all** — it comes back as an ``error`` contract, the R1-C27 path, so the CLI
    exits 2 and MCP answers ``ok: false`` naming every problem. Enforcing the valid half used
    to be the silent part: ``forbiden = [...]`` beside ``no_cycles = true`` printed a green
    tick over a rule the gate never ran.
    """
    problems = contract_problems(section)
    if problems:
        return ArchitectureContract(
            error="`[architecture]` is not a valid contract: " + "; ".join(problems))
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
        no_type_only_cycles=bool(section.get("no_type_only_cycles", False)),
        exhaustive=bool(section.get("exhaustive", False)),
        no_phantom_rules=bool(section.get("no_phantom_rules", False)),
    )


def _graph_layers(query) -> set[str]:
    """Layer names that exist in the core import graph."""
    return {query._layer_of(m) for m in query.import_graph.nodes
            if query.root_of(m) == "core"}


def applicability(query, contract: ArchitectureContract) -> dict:
    """Per-rule *declared* vs *applicable* counts, plus the names that do not exist (R1-C62).

    A rule naming a layer the graph does not contain is **inert by design** — no module, no
    edge, nothing to break — which is what lets a contract be written ahead of the code. The
    defect that made this function necessary is not the inertness: it is that the gate
    counted such a rule as *enforced*, so a renamed layer left a green tick over a rule that
    could no longer fire.

    Applicability is presence of the **name**, nothing cleverer: `layers` needs the layer,
    `independent` needs at least two members of the group (one cannot import itself), and
    `forbidden` needs both ends. Whether a violation is even possible between two existing
    layers is not asked, and should not be.
    """
    present = _graph_layers(query)
    named = set(contract.layers) | {m for grp in contract.independent for m in grp}
    named |= {n for pair in contract.forbidden for n in pair}
    return {
        "layers": {"declared": len(contract.layers),
                   "applicable": sum(1 for x in contract.layers if x in present)},
        "independent": {"declared": len(contract.independent),
                        "applicable": sum(1 for g in contract.independent
                                          if len([x for x in g if x in present]) >= 2)},
        "forbidden": {"declared": len(contract.forbidden),
                      "applicable": sum(1 for (a, b) in contract.forbidden
                                        if a in present and b in present)},
        "absent_names": tuple(sorted(n for n in named if n not in present)),
    }


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



def _tangle_line(tangle: dict) -> str:
    """One gate line per tangle: the example cycle, then the members (R1-C58).

    The example comes first because it is what a reader acts on; the membership follows
    because the tangle, not the cycle, is what has to be broken.
    """
    ex = tangle["example"]
    head = " → ".join(ex) + " → " + ex[0]
    if tangle["size"] <= len(ex):
        return head
    return f"{head} (tangle of {tangle['size']}: {', '.join(tangle['modules'])})"


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
        tangles = query.import_tangles()
        if tangles:
            # R1-C58: one violation per **tangle**, not per simple cycle. A tangle of 19
            # modules used to produce 1080 violations that were all the same problem, and
            # the gate's own output then took a thousand lines to say it once.
            violations.append(Violation(
                "no_cycles",
                f"{len(tangles)} import tangle(s), "
                f"{sum(t['size'] for t in tangles)} module(s)",
                modules=tuple(_tangle_line(t) for t in tangles),
            ))

    # -- no_lazy_cycles: opt in to gating the coupling a lazy import hides -------
    # Both facts are true at once — a gate you walk around by making the import lazy is
    # not a gate, and a lazy import is the accepted way to break an import cycle — so this
    # is the contract owner's call to state, not a default to pick on their behalf.
    if contract.no_lazy_cycles:
        lazy = query.lazy_import_tangles()
        if lazy:
            violations.append(Violation(
                "no_lazy_cycles",
                f"{len(lazy)} tangle(s) closed only by a function-local import, "
                f"{sum(t['size'] for t in lazy)} module(s)",
                modules=tuple(_tangle_line(t) for t in lazy),
            ))

    # -- no_type_only_cycles: the third kind, and the one with no runtime dependency ----
    # R1-C49 (issue #18): a cycle that needs an import under `if TYPE_CHECKING:` cannot
    # break at import time and does not couple the modules at run time either — the two
    # only name each other's types. Gating it is a style choice about the type layer, so
    # it is opt-in and separate: the consumer who asked for this had `no_lazy_cycles` on
    # against lazy imports used as a way around `no_cycles`, and the standard typing
    # idiom is not that.
    if contract.no_type_only_cycles:
        type_only = query.type_only_import_tangles()
        if type_only:
            violations.append(Violation(
                "no_type_only_cycles",
                f"{len(type_only)} tangle(s) closed only by an import that never runs "
                f"(`if TYPE_CHECKING:` or a `.pyi`), "
                f"{sum(t['size'] for t in type_only)} module(s)",
                modules=tuple(_tangle_line(t) for t in type_only),
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

    # -- no_phantom_rules: every name the contract mentions must exist -----------
    # R1-C62, the mirror of `exhaustive`. Off by default on purpose: inert rules are how a
    # contract gets written ahead of the code. On, it catches the drift the count alone
    # only *discloses* — a layer renamed while the contract kept guarding the old name.
    if contract.no_phantom_rules:
        absent = applicability(query, contract)["absent_names"]
        if absent:
            violations.append(Violation(
                "no_phantom_rules",
                f"{len(absent)} name(s) in the contract are absent from the graph, "
                "so the rules naming them cannot apply",
                modules=absent,
            ))

    return violations
