"""Query layer over the canonical graph (DESIGN §4, §1).

The canonical store is JSON; this is the in-memory query backend (networkx),
built from it — not the other way round. Answers the §1 catalog: find a symbol,
where it is defined (through re-exports), and module dependencies both ways.
Larger scale would swap networkx for SQLite/Neo4j behind this same surface (§4).
"""

from __future__ import annotations

import re

import networkx as nx

from codemap.model import Graph, Node

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# typing wrappers are containers, not the payload type we key flow on.
_TYPE_NOISE = {"Optional", "List", "Dict", "Tuple", "Set", "Union", "Any",
               "Sequence", "Iterable", "Mapping", "Callable", "Type", "None"}


def _type_tokens(type_str: str) -> set[str]:
    return {t for t in _IDENT.findall(type_str or "") if t not in _TYPE_NOISE}


# edge types that carry a "who depends on whom" signal for blast-radius (M6).
_IMPACT_EDGES = ("calls", "references", "inherits", "imports", "decorated_by")


class Query:
    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self._imports = nx.DiGraph()
        for n in graph.nodes.values():
            if n.kind == "module":
                self._imports.add_node(n.id)
        for e in graph.edges:
            if e.type == "imports":
                self._imports.add_edge(e.source, e.target)
        # export edges: name -> [target definition paths]
        self._exports: dict[str, list[str]] = {}
        for e in graph.edges:
            if e.type == "export":
                self._exports.setdefault(e.extras.get("as", ""), []).append(e.target)
        # inherits edges: class -> base (source imports base). Externals kept.
        self._inherits = nx.DiGraph()
        for e in graph.edges:
            if e.type == "inherits":
                self._inherits.add_edge(e.source, e.target)
        # decorated_by edges: keep as (source, decorator-path) pairs.
        self._decorated: list[tuple[str, str]] = [
            (e.source, e.target) for e in graph.edges if e.type == "decorated_by"
        ]
        # calls edges (M4 behavioral layer): caller -> callee.
        self._calls = nx.DiGraph()
        # F7: callee -> [(caller, edge extras)] to expose the argument contract.
        self._call_in: dict[str, list[tuple[str, dict]]] = {}
        for e in graph.edges:
            if e.type == "calls":
                self._calls.add_edge(e.source, e.target)
                self._call_in.setdefault(e.target, []).append((e.source, e.extras))
        # implements edges (M9/F4): concrete impl -> Protocol (structural typing,
        # synthesised via the registry family since it's never inherited).
        self._implements = nx.DiGraph()
        for e in graph.edges:
            if e.type == "implements":
                self._implements.add_edge(e.source, e.target)
        # string-key dataflow (M12/F6): column id -> {writers, readers}.
        self._col_writers: dict[str, set[str]] = {}
        self._col_readers: dict[str, set[str]] = {}
        for e in graph.edges:
            if e.type == "writes":
                self._col_writers.setdefault(e.target, set()).add(e.source)
            elif e.type == "reads":
                self._col_readers.setdefault(e.target, set()).add(e.source)
        # provenance (M6): node id -> root (core | tests | docs | ...).
        self._root_of = {n.id: n.extras.get("root", "core") for n in graph.nodes.values()}
        # inbound index for impact/blast-radius: target -> [(source, edge_type)].
        self._inbound: dict[str, list[tuple[str, str]]] = {}
        for e in graph.edges:
            if e.type in _IMPACT_EDGES:
                self._inbound.setdefault(e.target, []).append((e.source, e.type))

    # -- lookups -------------------------------------------------------------

    def find(self, name: str) -> list[Node]:
        """Definition nodes whose short name matches ``name``."""
        return sorted(
            (n for n in self.graph.nodes.values() if n.id.rsplit(".", 1)[-1] == name),
            key=lambda n: n.id,
        )

    def canonical(self, name_or_id: str) -> str | None:
        """Resolve a short name or **re-export id** to the canonical node id (F13).

        Relational edges are keyed by the definition id (``…detection.base.X``),
        but ``query`` surfaces re-export paths (``…detection.X``); feeding the
        latter to ``implementers``/``callers`` silently returned nothing. This maps
        either form to the real node so the natural chain works. Returns the chosen
        id only; use :meth:`canonical_info` to also learn if the choice was a guess.
        """
        info = self.canonical_info(name_or_id)
        return info["id"] if info else None

    def canonical_info(self, name_or_id: str) -> dict | None:
        """Resolve a name/re-export id **with an ambiguity signal** (M14/F13/F14).

        Returns ``{input, id, ambiguous, alternatives}`` or ``None`` if no node
        matches. ``ambiguous`` is True when ≥2 candidates tie on the disambiguation
        signal — i.e. the choice was **arbitrary** (a bare short name like
        ``calculate`` has 25 defs and no path to disambiguate). The B1 dogfood found
        such names resolve silently to one def (even a test mock), so relational ops
        can now warn instead of confidently answering about the wrong symbol.
        """
        if name_or_id in self.graph.nodes:
            return {"input": name_or_id, "id": name_or_id,
                    "ambiguous": False, "alternatives": []}
        short = name_or_id.rsplit(".", 1)[-1]
        cands = [n.id for n in self.find(short)]
        if not cands:
            return None
        if len(cands) == 1:
            return {"input": name_or_id, "id": cands[0],
                    "ambiguous": False, "alternatives": []}
        # prefer the node sharing the most path components with the requested id;
        # ambiguous iff ≥2 candidates tie on that max (the pick fell back to -len).
        parts = set(name_or_id.split("."))
        shared = {c: len(parts & set(c.split("."))) for c in cands}
        best = max(shared.values())
        chosen = max(cands, key=lambda c: (shared[c], -len(c)))
        ambiguous = sum(1 for c in cands if shared[c] == best) > 1
        return {"input": name_or_id, "id": chosen, "ambiguous": ambiguous,
                "alternatives": sorted(c for c in cands if c != chosen)}

    def search(self, term: str, *, kind: str | None = None, limit: int = 50) -> list[dict]:
        """Substring search over node ids — the discovery entry point (F9).

        Case-insensitive match on the id (so both short name and module path hit).
        Optional ``kind`` filter. Returns ``{id, kind, file, lineno}`` for a cold
        agent that does not yet know exact names.
        """
        t = term.lower()
        out = [
            {"id": n.id, "kind": n.kind, "file": n.file, "lineno": n.lineno}
            for n in self.graph.nodes.values()
            if (kind is None or n.kind == kind) and t in n.id.lower()
        ]
        return sorted(out, key=lambda r: (len(r["id"]), r["id"]))[:limit]

    # -- location → symbol (M15/F16 — the reviewer's diff entry point) --------

    def _defs_in_file(self, file: str):
        """(lineno, endlineno, id) for located definitions in ``file`` + module id."""
        defs, module = [], None
        for n in self.graph.nodes.values():
            if n.file != file:
                continue
            if n.kind == "module":
                module = n.id
            elif n.kind in ("function", "class", "attribute") and n.lineno is not None:
                defs.append((n.lineno, n.endlineno or n.lineno, n.id))
        return defs, module

    def symbol_at(self, file: str, line: int) -> str | None:
        """Innermost definition whose span contains ``(file, line)`` (M15/F16).

        The reviewer's entry point: a diff gives ``file:line``, not a symbol name.
        Nodes carry ``file``/``lineno``/``endlineno`` — this walks them to the
        tightest enclosing function/class/attribute, falling back to the **module**
        when the line is module-level code (between defs, e.g. a top-level dict) so a
        change there is never silently dropped. Returns None if the file is unknown
        (e.g. a consumer-root node that carries no ``file``).
        """
        defs, module = self._defs_in_file(file)
        best, best_span = None, None
        for lo, hi, nid in defs:
            if lo <= line <= hi and (best is None or (hi - lo) < best_span):
                best, best_span = nid, hi - lo
        return best or module

    def symbols_in_range(self, file: str, start: int, end: int) -> list[str]:
        """Distinct innermost symbols a hunk ``file:[start,end]`` touches (M15/F16).

        Per changed line, the tightest enclosing symbol (module fallback), deduped —
        so a hunk landing in one method of a big class yields that method, not the
        whole class. Powers change-set review from raw diff hunks.
        """
        defs, module = self._defs_in_file(file)
        if not defs and module is None:
            return []
        out: set[str] = set()
        for line in range(start, end + 1):
            best, best_span = None, None
            for lo, hi, nid in defs:
                if lo <= line <= hi and (best is None or (hi - lo) < best_span):
                    best, best_span = nid, hi - lo
            out.add(best or module)
        out.discard(None)
        return sorted(out)

    def where_defined(self, name: str) -> list[str]:
        """Canonical definition path(s) for ``name`` — resolving re-exports.

        Returns definition-node ids named ``name`` plus any re-export targets
        exposed under that name (e.g. ``analyze_zones`` -> its pipeline def).
        """
        ids = {n.id for n in self.find(name)}
        ids.update(self._exports.get(name, []))
        return sorted(ids)

    # -- module dependencies (both directions) ------------------------------

    def dependencies(self, module_id: str) -> list[str]:
        """Modules that ``module_id`` imports."""
        if module_id not in self._imports:
            return []
        return sorted(self._imports.successors(module_id))

    def dependents(self, module_id: str) -> list[str]:
        """Modules that import ``module_id``."""
        if module_id not in self._imports:
            return []
        return sorted(self._imports.predecessors(module_id))

    # -- class hierarchy (inherits edges) -----------------------------------

    def bases(self, class_id: str) -> list[str]:
        """Direct base classes of ``class_id`` (internal + external)."""
        if class_id not in self._inherits:
            return []
        return sorted(self._inherits.successors(class_id))

    def subclasses(self, class_id: str) -> list[str]:
        """Direct subclasses of ``class_id``."""
        if class_id not in self._inherits:
            return []
        return sorted(self._inherits.predecessors(class_id))

    def implementers(self, protocol_id: str) -> list[str]:
        """Concrete classes that implement ``protocol_id`` (registry family, M9)."""
        if protocol_id not in self._implements:
            return []
        return sorted(self._implements.predecessors(protocol_id))

    def implements(self, class_id: str) -> list[str]:
        """Protocol(s) ``class_id`` structurally satisfies (via its registry family)."""
        if class_id not in self._implements:
            return []
        return sorted(self._implements.successors(class_id))

    def family_siblings(self, class_id: str) -> list[str]:
        """Other impls of the same Protocol family as ``class_id`` (M9)."""
        sibs: set[str] = set()
        for proto in self.implements(class_id):
            sibs.update(self.implementers(proto))
        sibs.discard(class_id)
        return sorted(sibs)

    def decorated_with(self, decorator: str) -> list[str]:
        """Symbols decorated by ``decorator`` (matched on full path or short name)."""
        return sorted(
            src
            for src, dec in self._decorated
            if dec == decorator or dec.rsplit(".", 1)[-1] == decorator
        )

    # -- call graph (M4, best-effort — see gaps/ CM-09) ----------------------

    def callers(self, symbol_id: str) -> list[str]:
        """Functions that statically call ``symbol_id`` (resolved calls only)."""
        if symbol_id not in self._calls:
            return []
        return sorted(self._calls.predecessors(symbol_id))

    def callees(self, symbol_id: str) -> list[str]:
        """Internal symbols ``symbol_id`` statically calls."""
        if symbol_id not in self._calls:
            return []
        return sorted(self._calls.successors(symbol_id))

    def call_contract(self, symbol_id: str) -> list[dict]:
        """Per-caller argument contract of calls into ``symbol_id`` (+ members) — F7.

        For signature-change reasoning: each entry gives the calling function, how
        many call-sites it holds (``callsites`` — the collapse the edge hides), and
        the observed argument shape (``posargs`` / ``kwargs`` / ``splat``). Only
        resolved behavioral edges carry this; bridged (registry) edges do not.
        """
        out = []
        for tgt in sorted(self._member_ids(symbol_id)):
            for src, extras in self._call_in.get(tgt, []):
                if "callsites" not in extras:
                    continue  # bridge / edge without captured contract
                out.append({
                    "caller": src, "target": tgt,
                    "callsites": extras.get("callsites", 1),
                    "posargs": extras.get("posargs", []),
                    "kwargs": extras.get("kwargs", []),
                    "splat": extras.get("splat", False),
                })
        return sorted(out, key=lambda r: (r["caller"], r["target"]))

    # -- string-key dataflow (M12/F6) ----------------------------------------

    def column(self, name: str) -> dict | None:
        """Producers/consumers of the string key ``name`` (DataFrame column etc.).

        Returns ``{writes: [funcs], reads: [funcs]}`` or ``None`` if the key was
        never seen as a subscript. Over-set of true columns (dict keys included);
        querying a specific key is still precise. See gap-doc F6.
        """
        col_id = name if name.startswith("column:") else "column:" + name
        if col_id not in self.graph.nodes:
            return None
        return {
            "writes": sorted(self._col_writers.get(col_id, set())),
            "reads": sorted(self._col_readers.get(col_id, set())),
        }

    def columns(self, *, subscripted_only: bool = True) -> list[str]:
        """String-key column nodes (M14/F15).

        By default returns only keys ever accessed as a subscript (``x['k']``) — the
        real column-like set. The B1 dogfood found 71% of raw keys were dict-literal
        payload keys (result dicts, config, rcParams); ``subscripted_only=False``
        returns the full over-set (unchanged historical behavior).
        """
        return sorted(
            n.extras.get("key", n.id[len("column:"):])
            for n in self.graph.nodes.values()
            if n.kind == "column"
            and (not subscripted_only or n.extras.get("subscripted", True))
        )

    def columns_of(self, func_id: str) -> dict:
        """Which string keys ``func_id`` reads / writes — reverse dataflow (F11).

        The mirror of ``column()``: standing on a function, see the data it touches
        (``{reads: [key], writes: [key]}``), not just who touches a given key.
        """
        reads, writes = [], []
        for col_id, funcs in self._col_readers.items():
            if func_id in funcs:
                reads.append(col_id[len("column:"):])
        for col_id, funcs in self._col_writers.items():
            if func_id in funcs:
                writes.append(col_id[len("column:"):])
        return {"reads": sorted(reads), "writes": sorted(writes)}

    # -- registry families (M9/F4, surfaced for extension recipes — F10) ------

    def families(self) -> list[dict]:
        """Registry/Protocol families with their registration recipe (F9/F10).

        Each: the Protocol, its implementers, and per-member the registration
        ``decorator`` + ``key`` — i.e. how to add a new one. Lets a cold agent
        enumerate extension points and learn *how to plug in*, not just *what*.
        """
        out = []
        for pid in sorted({e.target for e in self.graph.edges if e.type == "implements"}):
            members = []
            for impl in self.implementers(pid):
                reg = self.graph.nodes[impl].extras.get("registry", {}) if impl in self.graph.nodes else {}
                members.append({"class": impl, "key": reg.get("key"),
                                "decorator": reg.get("decorator")})
            out.append({"protocol": pid, "members": members})
        return out

    def dead_symbols(self) -> list[str]:
        """Private functions with no incoming resolved call — dead-code candidates.

        Restricted to ``private`` symbols: a private function nothing calls is a
        far stronger signal than a public one (which may be external API). Still a
        heuristic — call resolution is partial (~1/4 of sites; gaps/ CM-09), so
        treat as candidates, never proof.
        """
        out = []
        for n in self.graph.nodes.values():
            if n.kind != "function" or n.visibility != "private":
                continue
            name = n.id.rsplit(".", 1)[-1]
            if name.startswith("__") and name.endswith("__"):
                continue  # dunder — invoked implicitly
            if n.id not in self._calls or self._calls.in_degree(n.id) == 0:
                out.append(n.id)
        return sorted(out)

    # -- impact / blast-radius (M6 — repo scope) -----------------------------

    def root_of(self, node_id: str) -> str:
        """Provenance root of a node (``core`` if untagged / single-package graph)."""
        return self._root_of.get(node_id, "core")

    def _member_ids(self, symbol_id: str) -> set[str]:
        """The symbol plus its members (a class' methods are called, not the class)."""
        return {
            i for i in self.graph.nodes
            if i == symbol_id or i.startswith(symbol_id + ".")
        }

    def references_to(self, symbol_id: str, *, include_members: bool = True) -> list[dict]:
        """Direct inbound references to ``symbol_id`` (+ members), each tagged by root.

        Spans every impact edge (calls / references / inherits / imports /
        decorated_by), so it reaches consumers outside the package (tests, docs,
        examples) once the graph was built repo-scoped (``extract_repo``).
        """
        targets = self._member_ids(symbol_id) if include_members else {symbol_id}
        out = []
        for t in sorted(targets):
            for src, etype in self._inbound.get(t, []):
                if src in targets:
                    continue  # self-internal (a method calling a sibling)
                out.append({"source": src, "type": etype,
                            "root": self.root_of(src), "target": t})
        return sorted(out, key=lambda r: (r["root"], r["type"], r["source"]))

    def impact(self, symbol_id: str, *, depth: int = 2) -> dict:
        """Blast radius of changing/removing ``symbol_id``.

        Distance 1 = direct references (incl. to its members); further distances
        follow inbound edges transitively up to ``depth``. Returns the ref list
        (each with ``distance``) plus a ``by_root`` count matrix. Best-effort —
        call resolution is partial (gaps/ CM-09), so this is a lower bound.
        """
        refs = self.references_to(symbol_id)
        for r in refs:
            r["distance"] = 1
        seen = self._member_ids(symbol_id) | {r["source"] for r in refs}
        current = {r["source"] for r in refs}
        dist = 1
        while dist < depth and current:
            nxt: set[str] = set()
            for node in sorted(current):
                for src, etype in self._inbound.get(node, []):
                    if src in seen:
                        continue
                    seen.add(src)
                    refs.append({"source": src, "type": etype,
                                 "root": self.root_of(src), "target": node,
                                 "distance": dist + 1})
                    nxt.add(src)
            current = nxt
            dist += 1

        by_root: dict[str, dict[str, int]] = {}
        for r in refs:
            by_root.setdefault(r["root"], {}).setdefault(r["type"], 0)
            by_root[r["root"]][r["type"]] += 1
        return {"symbol": symbol_id, "refs": refs, "by_root": by_root}

    # -- type flow (M4 — producers/consumers by signature type) --------------

    def producers(self, type_name: str) -> list[str]:
        """Functions whose return type mentions ``type_name``."""
        return sorted(
            n.id for n in self.graph.nodes.values()
            if n.kind == "function" and type_name in _type_tokens(n.extras.get("returns", ""))
        )

    def consumers(self, type_name: str) -> list[str]:
        """Functions that take a parameter whose type mentions ``type_name``."""
        out = []
        for n in self.graph.nodes.values():
            if n.kind != "function":
                continue
            for p in n.extras.get("params", []):
                if type_name in _type_tokens(p.get("type", "")):
                    out.append(n.id)
                    break
        return sorted(out)

    # -- graph-wide ----------------------------------------------------------

    def import_cycles(self) -> list[list[str]]:
        return [c for c in nx.simple_cycles(self._imports)]

    def orphan_modules(self, root: str | None = None) -> list[str]:
        """Modules with no incoming imports (dead-code candidates — heuristic).

        Excludes the package root and ``__init__``/``__main__`` (entry points).
        Static heuristic: dynamic imports / entry points are not visible.

        ``root`` (M6/F8): restrict to one provenance root. On a repo-scoped graph
        consumer roots (``tests``/``examples``/``scripts``/``research``) are orphan
        **by nature** — nothing imports an entrypoint — so ``root="core"`` isolates
        the only orphans that mean *dead code*. Default ``None`` = every root.
        """
        pkg_root = self.graph.target
        out = []
        for mid in self._imports.nodes:
            if mid == pkg_root or mid.rsplit(".", 1)[-1] in {"__init__", "__main__"}:
                continue
            if root is not None and self.root_of(mid) != root:
                continue
            if self._imports.in_degree(mid) == 0:
                out.append(mid)
        return sorted(out)

    def orphan_modules_by_root(self) -> dict[str, list[str]]:
        """Orphan modules grouped by provenance root (F8)."""
        grouped: dict[str, list[str]] = {}
        for mid in self.orphan_modules():
            grouped.setdefault(self.root_of(mid), []).append(mid)
        return {r: sorted(v) for r, v in sorted(grouped.items())}

    @property
    def import_graph(self) -> nx.DiGraph:
        return self._imports
