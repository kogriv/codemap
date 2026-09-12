"""Query layer over the canonical graph (DESIGN §4, §1).

The canonical store is JSON; this is the in-memory query backend (networkx),
built from it — not the other way round. Answers the §1 catalog: find a symbol,
where it is defined (through re-exports), and module dependencies both ways.
Larger scale would swap networkx for SQLite/Neo4j behind this same surface (§4).
"""

from __future__ import annotations

import fnmatch
import re

import networkx as nx

from codemap.model import CONFIDENCE_ORDER, Graph, Node, confidence_of


def _grade_rank(grade: str | None) -> int:
    """Route grades ordered strongest-first (R1-C39); an unknown one sorts last."""
    return CONFIDENCE_ORDER.index(grade) if grade in CONFIDENCE_ORDER else len(CONFIDENCE_ORDER)


def _canonical_cycles(cycles) -> list[list[str]]:
    """Cycles in a stable form: each rotated to start at its smallest node, then sorted.

    R1-C54, reported by the lab as [issue #20](https://github.com/kogriv/codemap/issues/20).
    ``nx.simple_cycles`` yields a cycle starting wherever its traversal happened to enter
    it, and that traversal follows set-iteration order, i.e. string hashes. The chain is
    the *same cycle* either way — but three consumers print it, and they printed three
    different texts for one graph across eight hash seeds.

    The sort afterwards is the point of the rotation: ``arch.py`` already sorted cycles by
    ``(len, c)`` and that looked like canonicalisation, except the key itself moved with
    the rotation — ``["a","b"]`` and ``["b","a"]`` are one cycle and two keys. Rotating
    first makes the existing sort mean what it appeared to mean.
    """
    out = [c[i:] + c[:i] for c in (list(x) for x in cycles)
           if (i := c.index(min(c))) >= 0]
    return sorted(out, key=lambda c: (len(c), c))


def _check_grade(min_confidence: str | None) -> None:
    if min_confidence is not None and min_confidence not in CONFIDENCE_ORDER:
        raise ValueError(f"min_confidence must be one of {CONFIDENCE_ORDER}, "
                         f"got {min_confidence!r}")


# Dead-code confidence, most-certain first (R1-C8). "high" = no inbound edge of any
# kind and no decorator/registry hook; "medium" = an implicit-use hook (decorator /
# registry) could invoke it; "low" = something references it, so it's likely alive.
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# typing wrappers are containers, not the payload type we key flow on.
_TYPE_NOISE = {"Optional", "List", "Dict", "Tuple", "Set", "Union", "Any",
               "Sequence", "Iterable", "Mapping", "Callable", "Type", "None"}


def _type_tokens(type_str: str) -> set[str]:
    return {t for t in _IDENT.findall(type_str or "") if t not in _TYPE_NOISE}


# edge types that carry a "who depends on whom" signal for blast-radius (M6).
# ``accesses`` (R1-C20) always targets an ``attribute`` node, so adding it here
# extends impact/references_to to fields *only* — it never touches non-attribute
# blast-radius. Columns' ``reads``/``writes`` stay out on purpose (M12): a column
# is a data key, not a symbol whose change breaks a caller.
_IMPACT_EDGES = ("calls", "references", "inherits", "imports", "decorated_by",
                 "accesses")

# Edges that carry "usage / dependency" for relevance ranking (R1-C6). Directed
# user→used, so PageRank accumulates rank on heavily-depended-upon symbols. contains
# is excluded on purpose (structural, would just inflate big modules).
_RANK_EDGE_TYPES = ("calls", "imports", "references", "inherits", "implements")

# Test-mapping walk (R1-C24). Execution and naming relations only: `imports` is
# module→module and would spread the answer across the package without saying anything
# about what a *test* runs; `inherits` is kept because exercising a subclass does exercise
# its base. Deliberately narrower than _IMPACT_EDGES, which answers a different question.
_TEST_WALK_EDGES = ("calls", "references", "accesses", "inherits")

#: How far back a *confident* answer may look. Not taste — measured against coverage.py
#: ground truth on codemap's own suite (R1-C24 D6), where precision falls off a cliff and
#: the answer size explodes at the fourth hop:
#:
#:   nearest hop   symbols   median precision   median tests returned
#:             1        63               1.00                       2
#:             2        91               1.00                       4
#:             3        44               1.00                       8
#:             4        61               0.67                      78
#:             5        29               0.33                      78
#:
#: By the fourth hop the walk has reached shared test infrastructure and is answering
#: "most of the suite" — worse than useless as a default, so it is available only when
#: asked for explicitly, and labelled `low`.
_TEST_MAX_DEPTH = 3
_TEST_DEEP_DEPTH = 6
#: Cap on tests listed per answer. Truncation is always *stated* — a silently trimmed
#: list reads as "these are all of them", which is issue #5 in a new costume.
_TEST_CAP = 25
#: Distance → how much the answer is worth, from the same measurement.
_TEST_CONFIDENCE = {1: "high", 2: "high", 3: "medium"}


def _pagerank(g: "nx.DiGraph", personalization: dict[str, float] | None,
              *, alpha: float = 0.85, max_iter: int = 100, tol: float = 1.0e-9) -> dict:
    """Pure-Python personalized PageRank (power iteration) — no numpy/scipy dep.

    networkx's ``pagerank`` needs scipy; codemap stays lightweight (griffe/jedi/
    networkx only), so we run the standard algorithm ourselves. Deterministic: nodes
    are processed in sorted order and the iteration is a fixed contraction.
    """
    nodes = sorted(g)
    n = len(nodes)
    if n == 0:
        return {}
    if personalization and sum(personalization.values()) > 0:
        s = sum(personalization.values())
        p = {v: personalization.get(v, 0.0) / s for v in nodes}
    else:
        p = {v: 1.0 / n for v in nodes}
    outdeg = {v: g.out_degree(v) for v in nodes}
    dangling = [v for v in nodes if outdeg[v] == 0]
    x = dict(p)
    for _ in range(max_iter):
        xlast = x
        x = {v: 0.0 for v in nodes}
        danglesum = alpha * sum(xlast[v] for v in dangling)
        for v in nodes:
            share = alpha * xlast[v] / outdeg[v] if outdeg[v] else 0.0
            for w in sorted(g.successors(v)):
                x[w] += share
        for v in nodes:
            x[v] += danglesum * p[v] + (1.0 - alpha) * p[v]
        if sum(abs(x[v] - xlast[v]) for v in nodes) < n * tol:
            break
    return x


class Query:
    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        # R1-C29 (issue #11): two import graphs, because two different questions.
        # `_imports` is every import edge — a dependency is a dependency, whether it is
        # written at module level or inside a function, and coupling / layers / orphans
        # all want the complete picture. `_imports_eager` drops the function-local ones,
        # because *import-cycle* means "breaks at import time", and a lazy import is the
        # standard fix for exactly that. Reporting one number for both questions is what
        # made an incomplete map read as a safety property.
        self._imports = nx.DiGraph()
        self._imports_eager = nx.DiGraph()
        # R1-C49: between the two — everything that can execute. A `TYPE_CHECKING` import
        # never does, so a cycle that needs one is not runtime coupling at all.
        self._imports_runtime = nx.DiGraph()
        self._import_scopes = {"module": 0, "function": 0, "type_checking": 0}
        for n in graph.nodes.values():
            if n.kind == "module":
                self._imports.add_node(n.id)
                self._imports_eager.add_node(n.id)
                self._imports_runtime.add_node(n.id)
        for e in graph.edges:
            if e.type == "imports":
                self._imports.add_edge(e.source, e.target)
                scope = e.extras.get("scope")
                if scope in ("function", "type_checking"):
                    # R1-C29: runs when the function runs; R1-C48: never runs. Neither
                    # is an import-time edge — but only the first is a runtime one.
                    self._import_scopes[scope] += 1
                    if scope == "function":
                        self._imports_runtime.add_edge(e.source, e.target)
                else:
                    self._imports_runtime.add_edge(e.source, e.target)
                    self._imports_eager.add_edge(e.source, e.target)
                    self._import_scopes["module"] += 1
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
                # R1-C39: the grade of the route rides on the graph edge, so `callers` /
                # `callees` can answer "only what a binding found". Two edges may collapse
                # onto one pair (a call resolved exactly at one site, fanned out from a
                # registry at another) — the *strongest* wins: the pair is genuinely
                # connected by a binding, whatever else also points that way.
                grade = confidence_of(e, strict=False)
                prev = self._calls.edges.get((e.source, e.target), {}).get("confidence")
                if prev is not None and _grade_rank(prev) < _grade_rank(grade):
                    grade = prev
                self._calls.add_edge(e.source, e.target, confidence=grade)
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
        # attribute access (R1-C20): attribute id -> {writers, readers}, from the
        # `accesses` edges (extras.access read/write). Powers readers()/writers()
        # and the honest field-impact answer (issue #1).
        self._attr_writers: dict[str, set[str]] = {}
        self._attr_readers: dict[str, set[str]] = {}
        for e in graph.edges:
            if e.type == "accesses":
                bucket = (self._attr_writers if e.extras.get("access") == "write"
                          else self._attr_readers)
                bucket.setdefault(e.target, set()).add(e.source)
        # provenance (M6): node id -> root (core | tests | docs | ...).
        self._root_of = {n.id: n.extras.get("root", "core") for n in graph.nodes.values()}
        # inbound index for impact/blast-radius: target -> [(source, edge_type)].
        self._inbound: dict[str, list[tuple[str, str]]] = {}
        for e in graph.edges:
            if e.type in _IMPACT_EDGES:
                self._inbound.setdefault(e.target, []).append((e.source, e.type))
        # R1-C24: the same index forward, for `covers` (what does this test exercise).
        self._outbound: dict[str, list[tuple[str, str]]] = {}
        for e in graph.edges:
            if e.type in _IMPACT_EDGES:
                self._outbound.setdefault(e.source, []).append((e.target, e.type))
        self._module_ids = [n.id for n in graph.nodes.values() if n.kind == "module"]
        self._test_ids = {i for i in self.graph.nodes if self._is_test(i)}

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

    def search(self, term: str, *, kind: str | None = None,
               limit: int | None = 50) -> list[dict]:
        """Substring search over node ids — the discovery entry point (F9).

        Case-insensitive match on the id (so both short name and module path hit).
        Optional ``kind`` filter. Returns ``{id, kind, file, lineno}`` for a cold
        agent that does not yet know exact names.

        ``limit=None`` returns everything. R1-C28: the serve layer asks for the full
        list so it can report the *true* total alongside the slice — a limit is a
        lower bound on the answer, and a lower bound has to be countable to be honest.
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

    def impact_targets(self, name_or_id: str) -> list[str]:
        """Node id(s) to run impact over, from a name / **full id** / re-export (F23).

        The blast-radius surface previously resolved the input via short-name
        ``find`` only, so a canonical/full id (``pkg.mod.Class`` — exactly what the
        agent gets back from ``query``/``search``) matched nothing and returned an
        empty impact, even for a widely-used symbol. Order: an existing node id maps
        to itself; else all short-name matches (kept — a bare name like ``calculate``
        legitimately fans out); else the canonical resolution of a re-export; else
        ``where_defined``.
        """
        if name_or_id in self.graph.nodes:
            return [name_or_id]
        matches = [n.id for n in self.find(name_or_id)]
        if matches:
            return matches
        canon = self.canonical(name_or_id)
        return [canon] if canon else self.where_defined(name_or_id)

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

    def callers(self, symbol_id: str, *, min_confidence: str | None = None) -> list[str]:
        """Functions that statically call ``symbol_id`` (resolved calls only).

        ``min_confidence`` (R1-C39) keeps only edges whose route grades at least that
        strong — ``"exact"`` asks for calls a *binding* found and drops the honest
        over-approximations (a factory fanned out across a registry family). Default:
        every resolved edge, whatever found it.
        """
        _check_grade(min_confidence)  # before the membership test: a bad argument must
        if symbol_id not in self._calls:  # not pass silently just because the symbol is
            return []                     # absent from the call graph
        return sorted(src for src in self._calls.predecessors(symbol_id)
                      if self._passes(src, symbol_id, min_confidence))

    def callees(self, symbol_id: str, *, min_confidence: str | None = None) -> list[str]:
        """Internal symbols ``symbol_id`` statically calls (see :meth:`callers`)."""
        _check_grade(min_confidence)
        if symbol_id not in self._calls:
            return []
        return sorted(tgt for tgt in self._calls.successors(symbol_id)
                      if self._passes(symbol_id, tgt, min_confidence))

    def _passes(self, source: str, target: str, min_confidence: str | None) -> bool:
        if min_confidence is None:
            return True
        grade = self._calls.edges[source, target].get("confidence")
        return _grade_rank(grade) <= _grade_rank(min_confidence)

    def confidence_map(self) -> dict[str, dict[str, int]]:
        """Edge counts by route grade, and by (edge type, resolution) pair — R1-C39.

        The answer to "how much of this graph was found by a binding, and how much by a
        name match", which no field of the artifact stated before: the route was on every
        edge, but nothing said what a route is worth. Edges with no route at all
        (``contains``, ``inherits``, …) are counted under ``none`` rather than dropped —
        absence is a number here too (R1-C28).
        """
        by_grade: dict[str, int] = {}
        by_pair: dict[str, int] = {}
        for e in self.graph.edges:
            grade = confidence_of(e, strict=False) or "none"
            by_grade[grade] = by_grade.get(grade, 0) + 1
            if e.extras.get("resolution") is not None:
                key = f"{e.type}:{e.extras['resolution']}"
                by_pair[key] = by_pair.get(key, 0) + 1
        return {"by_grade": dict(sorted(by_grade.items())),
                "by_pair": dict(sorted(by_pair.items()))}

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

    # -- attribute access (R1-C20, issue #1) ---------------------------------

    def readers(self, attr_id: str) -> list[str]:
        """Functions that *read* the attribute ``attr_id`` (resolves name/re-export).

        The attribute analog of ``column().reads``: standing on a class field, see
        who consumes it. Lower bound — attribute resolution is best-effort (fast
        ``self.``/``ClassName.``/construction; deep ``obj.field``), like the calls
        layer. Returns ``[]`` for an unknown id or one with no modelled reader.
        """
        canon = self.canonical(attr_id) or attr_id
        return sorted(self._attr_readers.get(canon, set()))

    def writers(self, attr_id: str) -> list[str]:
        """Functions that *write* the attribute ``attr_id`` (assignment / construction).

        The write side of :meth:`readers`; construction kwargs (``Cls(field=…)``)
        count as writes to ``Cls.field`` (D3). Lower bound, same caveat.
        """
        canon = self.canonical(attr_id) or attr_id
        return sorted(self._attr_writers.get(canon, set()))

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
        """Ids of all uncalled-private-function candidates (any confidence).

        Thin back-compat wrapper over :meth:`dead_code` (unfiltered) — a private
        function with no incoming resolved call. See ``dead_code`` for the graded,
        provenance-annotated form. Sorted by id (as before the grading was added).
        """
        return sorted(c["id"] for c in self.dead_code())

    def dead_code(self, *, whitelist: tuple[str, ...] = (),
                  min_confidence: str | None = None) -> list[dict]:
        """Graded dead-code candidates with a provenance reason (R1-C8).

        A candidate is a **private** function with no incoming *resolved call*
        (dunders excluded — invoked implicitly). Restricted to private because a
        public uncalled function may be external API. Call resolution is partial
        (~1/4 of sites; gaps/ CM-09), so this is triage, never proof — but codemap's
        cross-root graph lets us grade each candidate instead of listing flat, which
        is what cuts the false positives a call-only tool (vulture) can't:

        - **high** — no inbound edge of *any* kind (call / reference / re-export) and
          no decorator or registry hook: the strongest dead signal.
        - **medium** — no inbound reference, but a decorator or registry membership
          could invoke it implicitly (a framework hook, dispatched impl).
        - **low** — something *references* it (a re-export, a name put in a list, a
          registration): probably alive; the reason names who, so you can judge.

        Symbols declared only in a ``.pyi`` stub are excluded outright (R1-C23): a stub
        is a declaration, not code, so "nothing calls it" says nothing about it.

        ``whitelist`` suppresses candidates by exact id or glob (``fnmatch``).
        ``min_confidence`` (``low``/``medium``/``high``) drops anything below it.
        Sorted most-confident first, then by id.
        """
        out: list[dict] = []
        for n in self.graph.nodes.values():
            if n.kind != "function" or n.visibility != "private":
                continue
            name = n.id.rsplit(".", 1)[-1]
            if name.startswith("__") and name.endswith("__"):
                continue  # dunder — invoked implicitly
            if n.extras.get("stub"):
                continue  # R1-C23/D5: a `.pyi` declaration has no body to be dead
            if n.id in self._calls and self._calls.in_degree(n.id) > 0:
                continue  # has a resolved caller — not a candidate
            if any(fnmatch.fnmatch(n.id, pat) for pat in whitelist):
                continue  # explicitly suppressed
            out.append(self._grade_dead(n))

        out.sort(key=lambda c: (-_CONFIDENCE_RANK[c["confidence"]], c["id"]))
        if min_confidence:
            floor = _CONFIDENCE_RANK[min_confidence]
            out = [c for c in out if _CONFIDENCE_RANK[c["confidence"]] >= floor]
        return out

    def _overridden_base(self, n: Node) -> tuple[str, int] | None:
        """The ancestor method ``n`` overrides, and that ancestor's inbound calls (R1-C55).

        An override is not reached by its own name: the base is called and dynamic
        dispatch lands here, so "no inbound calls" is a statement about the *name*, not
        about the body. Measured on Pillow, where 40 of 63 ``high`` candidates were
        ``_open`` implementations of a template method the graph itself records as
        called from ``ImageFile.__init__`` — the strongest grade, on the most ordinary
        shape in object-oriented Python.

        Walks ``inherits`` transitively and weighs **every** ancestor that declares the
        name, not just the nearest: in a three-deep chain the middle link is an override
        too, so it has no inbound call of its own, and stopping there would report "the
        base is itself uncalled" while the call sits one level further up. An ancestor
        with inbound calls therefore wins; failing that, the nearest one is named.
        """
        cls, _, meth = n.id.rpartition(".")
        if not cls or cls not in self._inherits:
            return None
        nearest: tuple[str, int] | None = None
        seen, queue = {cls}, [cls]
        while queue:  # breadth-first, so `nearest` is the closest declaration
            for base in self.bases(queue.pop(0)):
                if base in seen:
                    continue
                seen.add(base)
                queue.append(base)
                cand = f"{base}.{meth}"
                if cand not in self.graph.nodes:
                    continue
                in_calls = self._calls.in_degree(cand) if cand in self._calls else 0
                if in_calls:
                    return cand, in_calls
                nearest = nearest or (cand, 0)
        return nearest

    def _grade_dead(self, n: Node) -> dict:
        """Score one uncalled-private candidate → {id, confidence, root, reasons}."""
        refs = self.references_to(n.id)  # inbound of every kind, across roots
        registry = n.extras.get("registry")
        override = self._overridden_base(n)
        if override and not refs:
            # R1-C55: the name is uncalled; the body is reachable through the base.
            base, in_calls = override
            if in_calls:
                return {"id": n.id, "confidence": "low", "root": self.root_of(n.id),
                        "reasons": [f"overrides {base}, which has {in_calls} inbound "
                                    f"call(s) — reached by dispatch, not by name"]}
            return {"id": n.id, "confidence": "medium", "root": self.root_of(n.id),
                    "reasons": [f"overrides {base}, which is itself uncalled here — "
                                f"dead only if the base is"]}
        if refs:
            by: dict[tuple[str, str], int] = {}
            for r in refs:
                by[(r["root"], r["type"])] = by.get((r["root"], r["type"]), 0) + 1
            reasons = [f"referenced ({t}) by {root}×{c}"
                       for (root, t), c in sorted(by.items())]
            confidence = "low"
        elif n.decorators or registry:
            reasons = [f"decorated by @{d.rsplit('.', 1)[-1]} — may be invoked implicitly"
                       for d in (n.decorators or [])]
            if registry:
                reasons.append(
                    f"registered as {registry.get('key', '?')!r} — may be dispatched")
            confidence = "medium"
        else:
            reasons = ["no inbound calls, references, or decorators"]
            confidence = "high"
        return {"id": n.id, "confidence": confidence,
                "root": self.root_of(n.id), "reasons": reasons}

    def shadowed_definitions(self) -> list[dict]:
        """Definitions that replaced an earlier definition of the same name (R1-C46).

        Not a graded candidate: a body a later ``def`` in the same scope replaced can
        never run, and no inbound edge changes that — so it is listed apart from
        :meth:`dead_code`, whose bands all mean "probably". Read from ``extras.shadows``,
        which the extractor stamps on the surviving node (``extract/behavior.py``).
        """
        out = []
        for n in self.graph.nodes.values():
            shadows = n.extras.get("shadows")
            if shadows:
                out.append({"id": n.id, "kind": n.kind, "root": self.root_of(n.id),
                            "file": n.file, "lineno": n.lineno,
                            "shadows": list(shadows)})
        out.sort(key=lambda d: d["id"])
        return out

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
        # R1-C19: depth histogram (refs per transitive distance) + a triage risk
        # label from the blast-radius shape — from the GitNexus разбор, built on
        # our own graph (no external dep).
        by_distance: dict[int, int] = {}
        for r in refs:
            by_distance[r["distance"]] = by_distance.get(r["distance"], 0) + 1
        max_distance = max(by_distance) if by_distance else 0
        node = self.graph.nodes.get(symbol_id)
        kind = node.kind if node else None
        out = {"symbol": symbol_id, "refs": refs, "by_root": by_root,
               "by_distance": by_distance, "max_distance": max_distance,
               "risk": self._impact_risk(len(refs), max_distance, len(by_root),
                                         kind=kind)}
        # R1-C44 / D1: a symbol the graph does not hold has no blast radius to report —
        # `none` here used to be an affirmative "nothing depends on it" about a name the
        # tool had never seen (a typo, another tree, a copy under another directory name).
        if node is None:
            out["risk"] = "unknown"
            out["risk_reason"] = ("symbol not in graph — nothing is known about it; "
                                  "this is not an empty blast radius")
            return out
        # Honesty (R1-C20 P0, issue #1): a field with no modelled accessor is a
        # *lower bound*, not proof of safety — attribute access resolution is
        # best-effort. Say so instead of the affirmative "none".
        if kind == "attribute" and not refs:
            out["risk_reason"] = ("attribute access is modelled best-effort; "
                                  "no accessor found is a lower bound, not proof "
                                  "nothing depends on this field")
        return out

    @staticmethod
    def _impact_risk(breadth: int, reach: int, roots: int, *,
                     kind: str | None = None) -> str:
        """Heuristic change-risk from blast-radius shape (breadth × reach × root-spread).

        Not a proof — a triage signal (like dead-code confidence). Breadth (how many
        references) dominates; transitive ``reach`` and ``roots`` (how many provenance
        roots — core/tests/docs/… — are touched) amplify it, since a symbol used
        across roots is costlier to change. Pair with the ref list before acting.

        For an ``attribute`` (R1-C20) an empty blast-radius is ``unknown``, not
        ``none``: attribute access is modelled best-effort, so "no accessor" is a
        lower bound. For a function/class the call/reference layer does target them,
        so empty stays the honest ``none``.
        """
        if breadth == 0:
            return "unknown" if kind == "attribute" else "none"
        if breadth >= 30 or roots >= 4 or (breadth >= 15 and reach >= 3):
            return "high"
        if breadth >= 5 or roots >= 2 or reach >= 2:
            return "medium"
        return "low"

    # -- subsystems: communities + flows (R1-C18) ----------------------------

    def communities(self) -> list[dict]:
        """Module subsystems via greedy modularity over the (undirected) import graph.

        A community is a set of modules that import each other more than the rest —
        a data-driven *subsystem*. Uses ``greedy_modularity_communities``, which is
        **deterministic** (order-stable) — on-brand vs seed-dependent Louvain. Each
        cluster is labelled by its dominant layer (component under the package root).
        Inspired by the GitNexus разбор (Leiden clusters); computed natively on our
        own graph — no external dependency. Sorted by size desc, then first module.
        """
        from collections import Counter
        from networkx.algorithms import community as _comm
        # Subsystems of the *package* = core modules only; consumer roots
        # (tests/docs/examples) are not subsystems and would drag labels to
        # "(root)" (they live outside the package namespace). Matches entry_points.
        core_mods = [m for m in self._imports.nodes if self.root_of(m) == "core"]
        ug = self._imports.subgraph(core_mods).to_undirected()
        if ug.number_of_edges() == 0:
            return []
        out = []
        for members in _comm.greedy_modularity_communities(ug):
            mods = sorted(members)
            layers = Counter(self._layer_of(m) for m in mods)
            out.append({"label": layers.most_common(1)[0][0],
                        "size": len(mods), "modules": mods})
        out.sort(key=lambda c: (-c["size"], c["modules"][0]))
        return out

    def entry_points(self, root: str = "core") -> list[str]:
        """Call-forest roots: functions that call out and are called by nothing *in
        their own root* (resolved calls only).

        Where behaviour starts — public API / mains / not-yet-triggered. Restricted to
        one provenance ``root`` (default core).

        R1-C50: "called by nothing" used to mean in-degree zero **across the whole
        graph**, which on a library means the public API is never an entry point — the
        one function a user enters the package through is called from `tests`,
        `examples` and `scripts`, and those 43 calls were what disqualified it. A call
        from a consumer root is a *use*, not an internal caller; being used is not
        evidence of being reachable-from-elsewhere. Reported by the dogfood target as
        [issue #19](https://github.com/kogriv/codemap/issues/19). On a single-package
        graph every node is `core`, so this is the same set as before by construction.

        Best-effort in **both** directions: an unresolved caller leaves a real internal
        looking like an entry point (the set is an over-estimate), and resolving one
        *removes* an entry point (it is an under-estimate of heads whose chain the
        resolver cannot close). The second direction is what #19 measured.
        """
        return sorted(
            n for n in self._calls.nodes
            if self.root_of(n) == root
            and self._calls.out_degree(n) > 0
            and not any(self.root_of(p) == root
                        for p in self._calls.predecessors(n))
        )

    def external_callers(self, symbol_id: str, root: str = "core") -> dict[str, int]:
        """Resolved callers of ``symbol_id`` living **outside** ``root``, by root.

        R1-C50/D8: on an entry point this is the evidence that the head is public —
        `{"tests": 43}` says the package is entered here, which is exactly what the
        in-degree rule used to read as a disqualification.
        """
        out: dict[str, int] = {}
        if symbol_id in self._calls:
            for p in self._calls.predecessors(symbol_id):
                r = self.root_of(p)
                if r != root:
                    out[r] = out.get(r, 0) + 1
        return dict(sorted(out.items()))

    def caller_grades(self, symbol_id: str) -> dict[str, int]:
        """Histogram of the route grades of the resolved calls *into* ``symbol_id``.

        R1-C51: what `callers(min_confidence=…)` would drop, so a filtered answer can
        say so instead of coming back as a bare empty list. Reported by the dogfood
        target with the measurement that makes it matter: of the 25 symbols their
        registry fan-out reaches, **13 have no `exact` caller at all** — every strategy
        method — so `min_confidence="exact"` answers `[]` about symbols that are called
        on every run, through an object a factory returned for a string key.
        """
        out: dict[str, int] = {}
        if symbol_id in self._calls:
            for p in self._calls.predecessors(symbol_id):
                g = self._calls.edges[p, symbol_id].get("confidence") or "unknown"
                out[g] = out.get(g, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: _grade_rank(kv[0])))

    def callee_grades(self, symbol_id: str) -> dict[str, int]:
        """Histogram of the route grades of the resolved calls *out of* ``symbol_id``."""
        out: dict[str, int] = {}
        if symbol_id in self._calls:
            for t in self._calls.successors(symbol_id):
                g = self._calls.edges[symbol_id, t].get("confidence") or "unknown"
                out[g] = out.get(g, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: _grade_rank(kv[0])))

    def flow(self, entry: str, *, max_depth: int = 5) -> dict:
        """Forward call-flow from ``entry`` along ``calls`` edges, bounded by depth.

        The mirror of :meth:`impact` (which walks inbound): *what does calling this
        set in motion*. Each edge is tagged with its distance from the entry; each
        node is expanded once (cycle-safe). Partial (resolution gaps) → lower bound.
        """
        if entry not in self._calls:
            return {"entry": entry, "edges": [], "reached": 0, "max_depth": 0}
        edges: list[dict] = []
        seen = {entry}
        current = {entry}
        dist = 0
        while dist < max_depth and current:
            nxt: set[str] = set()
            for src in sorted(current):
                for tgt in sorted(self._calls.successors(src)):
                    edges.append({"source": src, "target": tgt, "distance": dist + 1})
                    if tgt not in seen:
                        seen.add(tgt)
                        nxt.add(tgt)
            current = nxt
            dist += 1
        return {"entry": entry, "edges": edges, "reached": len(seen) - 1,
                "max_depth": max((e["distance"] for e in edges), default=0)}

    def flows_to(self, symbol_id: str, *, max_depth: int = 5,
                 root: str = "core") -> dict:
        """Which flows a change to ``symbol_id`` lands on, and at which step (R1-C40).

        The join of the two ends codemap already had: :meth:`impact` walks inbound
        ("who references"), :meth:`flow` walks outbound ("what a call sets in
        motion"), and neither answers the question asked *before* a change — "what
        stops working, and where in the scenario". A flow here is what ``flows``
        already calls one: an entry point of ``root`` (:meth:`entry_points`).
        ``first_step`` is the shortest distance in ``calls`` edges from that entry
        to the symbol **or one of its members** — shortest because "first" is what
        was asked, and a BFS gives the minimum by construction.

        Computed as one reverse BFS from the targets rather than a forward walk per
        entry: the distance is the same measured from either end, and the cost drops
        from O(entries × graph) to O(graph). The equivalence is what the acceptance
        test checks against :meth:`flow`.

        Says "reached", never "broken" (design D3): the graph knows the symbol lies
        on the path, not whether the edit breaks it. Three separate partialities are
        named rather than folded into the list — ``non_call_refs`` (a reference that
        arrives by import / inheritance / decoration / attribute access cannot appear
        in a flow at all), ``beyond_depth`` (entries that do reach, further than
        ``max_depth`` — counted, not silently dropped), and the standing note that
        call resolution is a lower bound. ``in_call_graph: False`` is the honest
        "nothing to say about flows" for a symbol the call layer never modelled — not
        the same answer as an empty list (R1-C44).
        """
        targets = {i for i in self._member_ids(symbol_id) if i in self._calls}
        entries = self.entry_points(root)
        refs = self.references_to(symbol_id)
        out = {
            "symbol": symbol_id, "root": root, "max_depth": max_depth,
            "in_call_graph": bool(targets), "entry_points": len(entries),
            "flows": [], "beyond_depth": 0, "nearest_beyond": None,
            "inbound_calls": sum(len(self._calls.pred[t]) for t in targets),
            "non_call_refs": sum(1 for r in refs if r["type"] != "calls"),
        }
        if not targets:
            return out
        dist = {t: 0 for t in targets}
        frontier, step = set(targets), 0
        while frontier:
            nxt: set[str] = set()
            for node in sorted(frontier):
                for pred in self._calls.predecessors(node):
                    if pred not in dist:
                        dist[pred] = step + 1
                        nxt.add(pred)
            frontier, step = nxt, step + 1
        reaching = sorted((dist[e], e) for e in entries if e in dist)
        out["flows"] = [{"entry": e, "first_step": d,
                         "external_callers": self.external_callers(e, root)}
                        for d, e in reaching if d <= max_depth]
        beyond = [d for d, _ in reaching if d > max_depth]
        # R1-C50/D9: "0 flows" and "0 flows, and the nearest head is one step past the
        # bound" are different answers, and the second one is actionable. Naming only
        # the count made the headline read as unreachable — measured on a deep graph
        # where four real heads sat at step 6 under a bound of 5.
        out["beyond_depth"] = len(beyond)
        out["nearest_beyond"] = min(beyond) if beyond else None
        return out

    # -- relevance ranking (R1-C6) -------------------------------------------

    def _expand_seeds(self, seeds) -> set[str]:
        """Map each seed (node id / short name / file path) to concrete node ids."""
        out: set[str] = set()
        files = {n.file for n in self.graph.nodes.values() if n.file}
        for s in seeds:
            if s in self.graph.nodes:
                out.add(s)
            elif s in files:
                out.update(n.id for n in self.graph.nodes.values() if n.file == s)
            else:
                out.update(n.id for n in self.find(s))  # short name → matches
        return out

    def rank(self, *, seeds=(), edge_types=_RANK_EDGE_TYPES,
             root: str | None = None) -> dict[str, float]:
        """Importance rank over usage edges via PageRank (R1-C6).

        Without ``seeds``: global importance — heavily-depended-upon symbols (imports
        /calls/references pointing at them) rank high. With ``seeds`` (node ids, short
        names, or file paths): personalized restart biased to them → relevance to that
        context (aider's repo-map trick). ``root`` restricts to one provenance root.
        Deterministic: PageRank is a fixed power-iteration; scores rounded, ties broken
        by id at the call sites that order them.
        """
        g = nx.DiGraph()
        for nid, n in self.graph.nodes.items():
            if n.kind in ("module", "class", "function") and (
                    root is None or self.root_of(nid) == root):
                g.add_node(nid)
        ets = set(edge_types)
        for e in self.graph.edges:
            if e.type in ets and e.source in g and e.target in g:
                g.add_edge(e.source, e.target)
        if g.number_of_nodes() == 0:
            return {}
        personalization = None
        if seeds:
            seed_ids = {s for s in self._expand_seeds(seeds) if s in g}
            if seed_ids:  # restart biased to seeds (normalized inside _pagerank)
                personalization = {n: (1.0 if n in seed_ids else 0.0) for n in g}
        pr = _pagerank(g, personalization)
        return {n: round(v, 8) for n, v in pr.items()}

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
        """Cycles that exist in the **eager** import graph — the import-order landmines.

        R1-C29: deliberately *not* computed over every import edge. A function-local
        import does not run at import time, so a cycle closed only by one does not break
        on import — it is what a developer writes to stop it breaking. Counting it here
        would report someone's fix as their bug. Those cycles are still real coupling
        and are returned by :meth:`lazy_import_cycles`.
        """
        return _canonical_cycles(nx.simple_cycles(self._imports_eager))

    def lazy_import_cycles(self) -> list[list[str]]:
        """Dependency cycles that close **only** through a function-local import.

        Not an import-time failure, and not nothing: the modules still cannot be
        separated at run time, and the lazy import is the evidence someone already hit
        this. Before R1-C29 these were invisible — on the target this project benchmarks
        on, eight of the nine cycles present were of this kind and the report said "1".

        R1-C49 narrowed this back after R1-C48 briefly widened it: a cycle that needs an
        import under ``if TYPE_CHECKING:`` is not runtime coupling at all and is returned
        by :meth:`type_only_import_cycles`. The partition is by the **weakest scope that
        closes the cycle**, not by which scopes appear in it — a pair coupled through a
        function-local import stays *lazy* however many type imports also run between
        them, or a tree could hide real coupling by adding one.
        """
        eager = {frozenset(c) for c in nx.simple_cycles(self._imports_eager)}
        return _canonical_cycles(c for c in nx.simple_cycles(self._imports_runtime)
                                 if frozenset(c) not in eager)

    def type_only_import_cycles(self) -> list[list[str]]:
        """Dependency cycles that close **only** with an import under ``if TYPE_CHECKING:``.

        The third kind (R1-C49, issue #18). These modules name each other's types and have
        **no runtime dependency whatever**: neither import pulls the other at any moment of
        execution. That is why they are not gated by ``no_lazy_cycles`` — which exists
        against a lazy import used to walk *around* ``no_cycles`` — and get their own
        opt-in rule instead.
        """
        runtime = {frozenset(c) for c in nx.simple_cycles(self._imports_runtime)}
        return _canonical_cycles(c for c in nx.simple_cycles(self._imports)
                                 if frozenset(c) not in runtime)

    def import_map(self) -> dict:
        """How much of the import graph each scope contributed (R1-C29).

        Emitted by every consumer of the import graph, **always**, including when
        ``function_local`` is zero — the same rule as the ``limit`` block (R1-C28): a
        reader must never have to distinguish "no lazy imports here" from "this build
        did not look for them".
        """
        return {"module_level": self._import_scopes["module"],
                "function_local": self._import_scopes["function"],
                "type_checking": self._import_scopes["type_checking"]}

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

    # -- architecture: whole-system shape (M16 / A9) -------------------------

    def _layer_of(self, module_id: str) -> str:
        """Layer = the component just under the package root (``bquant.<layer>``)."""
        pkg = self.graph.target
        parts = module_id.split(".")
        if parts[0] == pkg and len(parts) >= 2:
            return parts[1]
        return "(root)"

    def layers(self) -> dict:
        """Layer dependency structure of the **core** package (M16/F18).

        Groups modules into layers (the component under the package root), sums
        inter-layer import edges, and flags **violations** order-free: a layer pair
        with edges in *both* directions (mutual dependency) is a coupling smell
        regardless of intended layering — no hardcoded ``core < analysis`` order.
        """
        ig = self._imports
        members: dict[str, list[str]] = {}
        for m in ig.nodes:
            if self.root_of(m) == "core":
                members.setdefault(self._layer_of(m), []).append(m)
        edges: dict[tuple[str, str], int] = {}
        for u, v in ig.edges():
            if self.root_of(u) != "core" or self.root_of(v) != "core":
                continue
            lu, lv = self._layer_of(u), self._layer_of(v)
            if lu != lv:
                edges[(lu, lv)] = edges.get((lu, lv), 0) + 1
        violations = sorted(
            {tuple(sorted((a, b))) for (a, b) in edges if (b, a) in edges}
        )
        return {
            "layers": {k: sorted(v) for k, v in sorted(members.items())},
            "edges": {f"{a} -> {b}": n for (a, b), n in
                      sorted(edges.items(), key=lambda x: (-x[1], x[0]))},
            "violations": [list(v) for v in violations],
        }

    def coupling(self, *, root: str = "core", limit: int = 20) -> list[dict]:
        """Per-module afferent/efferent coupling + instability (M16/F19).

        Ca = modules that import me, Ce = modules I import, Instability
        I = Ce/(Ca+Ce) (0 = maximally stable, 1 = maximally unstable). Sorted most-
        depended-on first. Restricted to ``root`` provenance (default core).
        """
        ig = self._imports
        out = []
        for m in ig.nodes:
            if self.root_of(m) != root:
                continue
            ca, ce = ig.in_degree(m), ig.out_degree(m)
            tot = ca + ce
            out.append({"module": m, "ca": ca, "ce": ce,
                        "instability": round(ce / tot, 2) if tot else 0.0})
        out.sort(key=lambda r: (-r["ca"], r["module"]))
        return out[:limit]

    def hotspots(self, *, root: str = "core", min_methods: int = 12,
                 min_cc: int = 8, limit: int = 15) -> dict:
        """God-object classes + call-graph hubs + complex functions (M16/F20, R1-C4).

        ``god_classes``: classes with ``>= min_methods`` methods (concentration of
        behavior), each annotated with aggregate method complexity (``total_cc`` /
        ``max_cc``) — the second axis, so "big by connectivity" and "complex by
        McCabe" are both visible. ``complex_functions``: functions with the highest
        cyclomatic complexity (``>= min_cc``), the sharpest per-symbol risk signal.
        ``call_hubs``: symbols with the highest call-graph degree (in+out) — pervasive
        utilities (a logger, sample loaders) hub by nature, so each is flagged
        ``pervasive`` and the reader discounts expected noise, not real risk.
        """
        method_counts: dict[str, int] = {}
        class_cc: dict[str, list[int]] = {}
        for e in self.graph.edges:
            if e.type != "contains":
                continue
            src = self.graph.nodes.get(e.source)
            tgt = self.graph.nodes.get(e.target)
            if src and src.kind == "class" and tgt and tgt.kind == "function" \
                    and self.root_of(e.source) == root:
                method_counts[e.source] = method_counts.get(e.source, 0) + 1
                cc = (tgt.extras.get("complexity") or {}).get("cc")
                if cc is not None:
                    class_cc.setdefault(e.source, []).append(cc)
        god = sorted(((c, n) for c, n in method_counts.items() if n >= min_methods),
                     key=lambda x: (-x[1], x[0]))[:limit]

        # Second axis: individual functions ranked by cyclomatic complexity.
        complex_fns = []
        for nid, node in self.graph.nodes.items():
            if node.kind != "function" or self.root_of(nid) != root:
                continue
            metrics = node.extras.get("complexity")
            if metrics and metrics.get("cc", 0) >= min_cc:
                complex_fns.append({"id": nid, "cc": metrics["cc"], "mi": metrics["mi"],
                                    "sloc": metrics["sloc"]})
        complex_fns.sort(key=lambda r: (-r["cc"], r["id"]))

        cg = self._calls
        hubs = []
        for nid in cg.nodes:
            if self.root_of(nid) != root:
                continue
            deg = cg.in_degree(nid) + cg.out_degree(nid)
            short = nid.rsplit(".", 1)[-1]
            recv = nid.rsplit(".", 2)[-2] if nid.count(".") >= 2 else ""
            pervasive = any(t in (recv + "." + short).lower()
                            for t in ("logger", "log", "get_sample", "warning",
                                      "debug", "info", "error"))
            hubs.append({"id": nid, "degree": deg, "pervasive": pervasive})
        hubs.sort(key=lambda r: (-r["degree"], r["id"]))

        def _class_entry(c: str, n: int) -> dict:
            ccs = class_cc.get(c, [])
            return {"class": c, "methods": n,
                    "total_cc": sum(ccs), "max_cc": max(ccs) if ccs else 0}

        return {
            "god_classes": [_class_entry(c, n) for c, n in god],
            "complex_functions": complex_fns[:limit],
            "call_hubs": hubs[:limit],
        }

    # -- test mapping (R1-C24, axis A10) -------------------------------------

    def _module_of(self, node_id: str) -> "Node | None":
        """The module node containing ``node_id`` — longest module id that prefixes it."""
        best = None
        for mid in self._module_ids:
            if node_id == mid or node_id.startswith(mid + "."):
                if best is None or len(mid) > len(best):
                    best = mid
        return self.graph.nodes.get(best) if best else None

    def _is_test(self, node_id: str) -> bool:
        """Would pytest collect this node as a test? (design D1 — derived, not stored)

        Three conditions, all syntax over data already in the graph: it lives under a
        consumer root whose role is ``tests``; its module file is a file pytest collects
        (``test_*.py`` / ``*_test.py`` — which is what keeps helper packages under
        ``tests/fixtures/`` out); and the function itself follows the naming rule,
        including the ``Test*`` class case. Derived rather than stamped at build time so
        the artifact does not carry one framework's naming convention, and so an existing
        graph gains the feature with no rebuild.
        """
        node = self.graph.nodes.get(node_id)
        if node is None or node.kind != "function" or self.root_of(node_id) != "tests":
            return False
        mod = self._module_of(node_id)
        if mod is None or not mod.file:
            return False
        base = mod.file.rsplit("/", 1)[-1]
        if not (base.startswith("test_") or base.endswith("_test.py")):
            return False
        tail = node_id[len(mod.id) + 1:].split(".")
        if not tail or not tail[-1].startswith("test"):
            return False
        if len(tail) == 1:
            return True
        return len(tail) == 2 and tail[0].startswith("Test")

    def pytest_nodeid(self, node_id: str) -> str | None:
        """Graph id → the id you can paste after ``pytest`` (design D5).

        ``tests.test_x.TestFoo.test_y`` → ``tests/test_x.py::TestFoo::test_y``. Without
        this the answer is a reading exercise instead of a command.
        """
        mod = self._module_of(node_id)
        if mod is None or not mod.file:
            return None
        tail = node_id[len(mod.id) + 1:]
        return mod.file + ("::" + "::".join(tail.split(".")) if tail else "")

    def _test_caveats(self, *, truncated: int, searched: int, found: bool) -> list[str]:
        """The two labels every answer carries, plus whatever this graph earns.

        Both are required (R1-C13): an over-set because reaching a symbol is not
        asserting on it, and a lower bound because dynamic dispatch is invisible.
        """
        out = [
            "over-set: a test that reaches this symbol does not necessarily assert on it",
            "lower bound: dynamic dispatch, fixtures resolved by name and monkeypatched "
            "calls are invisible to a static graph",
        ]
        tier = (self.graph.provenance or {}).get("tier")
        if tier == "fast":
            out.append("built on the fast tier — method calls are largely unresolved "
                       "(21% vs 56% measured); rebuild with `--deep` for a usable set")
        elif tier is None:
            out.append("graph records no tier (built before schema 0.12) — if it is the "
                       "fast tier, method calls are largely unresolved")
        if not self._test_ids:
            out.append("no test functions in this graph — build repo-scoped with "
                       "`--consumer tests --mode full` (thin mode yields files, not tests)")
        if truncated:
            out.append(f"{truncated} further test(s) at this distance not listed (cap)")
        if not found:
            out.append(f"unknown, not none: no test reaches this symbol within {searched} "
                       "hop(s). 16% of symbols that coverage.py proves are exercised look "
                       "like this — ask for a deeper walk (`depth=6`) for low-confidence "
                       "candidates, but do not read silence as 'untested'")
        else:
            out.append(f"searched {searched} hop(s) back")
        return out

    def tests_for(self, symbol_id: str, *, depth: int = _TEST_MAX_DEPTH,
                  cap: int = _TEST_CAP) -> dict:
        """Which tests exercise ``symbol_id`` — nearest band first (R1-C24, axis A10).

        Distance 1 is not the question: measured on codemap's own repo, only **18%** of
        core symbols have a direct inbound edge from a test (68/380), because a test calls
        ``extract()`` and ``extract()`` calls two hundred things. Bounded backwards
        reachability answers 59% on the fast tier and 80% on deep.

        Nor is "everything reachable" the answer: that returns a median of 21 tests and a
        maximum of 126 out of 416 — the suite. So the walk returns the **nearest non-empty
        band** (median 6.5), and deeper bands only on request. Ranking is the feature here,
        not a polish item.

        Ranking is by graph distance and nothing else: distance is a fact about the graph,
        while name similarity or file adjacency would be a guess about intent, which is
        outside "source-only, deterministic".
        """
        targets = self._member_ids(symbol_id)
        seen = set(targets)
        frontier = set(targets)
        for dist in range(1, max(1, depth) + 1):
            nxt: set[str] = set()
            for node in sorted(frontier):
                for src, etype in self._inbound.get(node, []):
                    if src not in seen and etype in _TEST_WALK_EDGES:
                        seen.add(src)
                        nxt.add(src)
            if not nxt:
                frontier = nxt
                break
            frontier = nxt
            hits = sorted(n for n in nxt if n in self._test_ids)
            if hits:
                return self._tests_envelope(symbol_id, hits, dist, cap, dist)
        return self._tests_envelope(symbol_id, [], None, cap, depth)

    def _tests_envelope(self, symbol_id, hits, dist, cap, searched) -> dict:
        shown, truncated = hits[:cap], max(0, len(hits) - cap)
        return {
            "symbol": symbol_id,
            "tier": (self.graph.provenance or {}).get("tier"),
            "distance": dist,
            # `unknown` — never "none". A confident empty is the failure this project has
            # now shipped five fixes for (#1 risk:"none", #3, #5, #7, R1-C23).
            "confidence": _TEST_CONFIDENCE.get(dist, "low") if dist else "unknown",
            "tests": [self._test_row(t, dist) for t in shown],
            "total_at_distance": len(hits),
            "truncated": truncated,
            "caveats": self._test_caveats(truncated=truncated, searched=searched,
                                          found=bool(dist)),
        }

    def _test_row(self, node_id: str, dist) -> dict:
        n = self.graph.nodes.get(node_id)
        return {"id": node_id, "node_id": self.pytest_nodeid(node_id),
                "line": getattr(n, "lineno", None), "distance": dist}

    def covers(self, test_id: str, *, depth: int = _TEST_MAX_DEPTH,
               cap: int = _TEST_CAP) -> dict:
        """The inverse: which core symbols a test reaches (R1-C24 / design D5).

        Same index read the other way, so it costs nothing extra — and it answers "is
        this test exercising the thing its name claims?" during review.
        """
        out: dict[str, int] = {}
        seen = {test_id}
        frontier = {test_id}
        for dist in range(1, max(1, depth) + 1):
            nxt: set[str] = set()
            for node in sorted(frontier):
                for e in self._outbound.get(node, []):
                    tgt, etype = e
                    if tgt in seen or etype not in _TEST_WALK_EDGES:
                        continue
                    seen.add(tgt)
                    nxt.add(tgt)
                    if self.root_of(tgt) == "core":
                        out.setdefault(tgt, dist)
            if not nxt:
                break
            frontier = nxt
        rows = sorted(out.items(), key=lambda kv: (kv[1], kv[0]))
        return {
            "test": test_id,
            "node_id": self.pytest_nodeid(test_id),
            "tier": (self.graph.provenance or {}).get("tier"),
            "symbols": [{"id": s, "distance": d} for s, d in rows[:cap]],
            "total": len(rows),
            "truncated": max(0, len(rows) - cap),
            "caveats": self._test_caveats(truncated=max(0, len(rows) - cap),
                                          searched=depth, found=bool(rows)),
        }
