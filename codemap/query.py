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
        for e in graph.edges:
            if e.type == "calls":
                self._calls.add_edge(e.source, e.target)

    # -- lookups -------------------------------------------------------------

    def find(self, name: str) -> list[Node]:
        """Definition nodes whose short name matches ``name``."""
        return sorted(
            (n for n in self.graph.nodes.values() if n.id.rsplit(".", 1)[-1] == name),
            key=lambda n: n.id,
        )

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

    def orphan_modules(self) -> list[str]:
        """Modules with no incoming imports (dead-code candidates — heuristic).

        Excludes the package root and ``__init__``/``__main__`` (entry points).
        Static heuristic: dynamic imports / entry points are not visible.
        """
        root = self.graph.target
        out = []
        for mid in self._imports.nodes:
            if mid == root or mid.rsplit(".", 1)[-1] in {"__init__", "__main__"}:
                continue
            if self._imports.in_degree(mid) == 0:
                out.append(mid)
        return sorted(out)

    @property
    def import_graph(self) -> nx.DiGraph:
        return self._imports
