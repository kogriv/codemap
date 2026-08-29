"""Multi-root extraction — repo scope / impact (DESIGN §10.12, M6).

The single-package :func:`~codemap.extract.griffe_extractor.extract` sees only the
core package, so blast-radius questions ("who uses X / can I delete it") miss the
consumers that live *outside* the package — tests, examples, scripts, docs. That
was the dominant gap the dogfood found (gaps/observability_dogfood_2026-07-28, F1).

:func:`extract_repo` keeps the core on griffe (deep import/inheritance resolution)
and adds **consumer** and **doc** roots by a light stdlib-``ast`` / regex scan for
references *into the core*. Consumers are typically loose script dirs (no package
``__init__``), so we do not griffe-load them — we only need their edges into core.

Every node carries provenance in ``extras.root`` (``core`` | the consumer dir name
| ``docs``). Two modes, both real, selectable for empirical comparison:

- **thin** (default): a consumer file is one ``module`` node; its uses of core
  symbols become ``references``/``calls`` edges from that file. Cheap; answers
  "which files/roots reference X". No consumer-internal structure.
- **full**: consumer functions/classes are materialized as nodes (``contains``),
  and each use edge is sourced from the enclosing function — "which test *function*
  calls X". Richer, more nodes/noise.

Docs (``*.md``) can't be ``ast``-parsed; a doc file becomes a ``doc`` node with
``references`` edges to every core symbol it names via ``from core… import`` /
exact dotted mention (piggybacking the doc-parity convention).
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

from codemap.extract.behavior import _arg_contract, _arg_shape
from codemap.extract.griffe_extractor import extract
from codemap.provenance import canonicalize
from codemap.model import Edge, Graph, Node

_CONSUMER_SKIP_DIRS = {"__pycache__", ".venv", ".git", "node_modules"}


def roots_base(core: str | Path, consumers=(), docs=()) -> Path:
    """The one directory every path in a repo-scoped graph is relative to (R1-C31).

    Each root used to be its own origin: core files were written relative to the core
    package's parent and consumer files relative to their own root's parent. When the
    roots sit side by side those coincide and nothing shows; when they do not — `src/pkg`
    beside `tests/`, or roots one level down in `research/` — a single graph carried two
    coordinate systems and said so nowhere. Both `pkg/mod.py` and `tests/test_mod.py`
    read as repo-relative, and at most one of them was.

    So: one origin, the nearest common ancestor of every root's parent, and every `file`
    in the graph relative to it. A single-package build is unaffected (one root, and its
    parent is the origin as before). The directory itself is **not** stored in the graph
    — that is a machine location (design D5); it goes in the sidecar, which is the file
    that stays home.
    """
    parents = [Path(core).resolve().parent]
    parents += [Path(p).resolve().parent for p in (*consumers, *docs)]
    return Path(os.path.commonpath([str(p) for p in parents]))


def _reroot_files(graph, offset: str) -> None:
    """Prefix every node's ``file`` with ``offset`` (the core pass wrote them relative to
    the core's own parent, which may be below the common origin)."""
    if offset in ("", "."):
        return
    for node in graph.nodes.values():
        if node.file:
            node.file = f"{offset}/{node.file}"


def extract_repo(
    core: str | Path,
    *,
    consumers: tuple[str | Path, ...] = (),
    docs: tuple[str | Path, ...] = (),
    mode: str = "thin",
    deep: bool = False,
) -> Graph:
    """Build a repo-scoped graph: core package + consumer roots + doc roots.

    ``core`` is analysed exactly as the single-package extractor (griffe, plus the
    behavioral pass when ``deep``). ``consumers`` and ``docs`` are extra root
    directories scanned for references into the core. ``mode`` is ``"thin"`` or
    ``"full"`` (see module docstring).
    """
    if mode not in ("thin", "full"):
        raise ValueError(f"mode must be 'thin' or 'full', got {mode!r}")

    graph = extract(core, deep=deep)
    core_pkg = graph.target
    for node in graph.nodes.values():
        node.extras.setdefault("root", "core")

    # R1-C31: one origin for every path in this graph (see `roots_base`).
    base = roots_base(core, consumers, docs)
    _reroot_files(graph, _rel_to(Path(core).resolve().parent, base))

    index = _CoreIndex(graph, core_pkg)
    for path in consumers:
        _scan_consumer_root(graph, Path(path).resolve(), index, mode, base)
    for path in docs:
        _scan_doc_root(graph, Path(path).resolve(), index, base)
    # R1-C25: the roots are part of what this graph *is* — a core-only graph and a
    # repo-scoped one answer `impact` differently, and `diff` must not silently compare
    # the two. Relative to the graph's own origin, never an absolute location (design D5);
    # a basename was less than that and lost the segment between origin and root (#12).
    graph.provenance = canonicalize({**graph.provenance, "roots": {
        "core": _rel_to(Path(core).resolve(), base),
        "consumers": sorted(_rel_to(Path(p).resolve(), base) for p in consumers),
        "docs": sorted(_rel_to(Path(p).resolve(), base) for p in docs),
        "mode": mode,
    }})
    return graph


def _rel_to(path: Path, base: Path) -> str:
    """``path`` relative to ``base``, as a posix string ("" when they are the same)."""
    try:
        rel = path.relative_to(base)
    except ValueError:                      # not below base — cannot happen for a root
        return path.name
    return rel.as_posix() if rel.parts else ""


# -- core resolver: dotted reference (incl. re-exports) -> canonical node id ---

class _CoreIndex:
    """Resolve a dotted path that names a core symbol to its canonical node id.

    Handles the re-export case: ``from bquant.indicators import MACDZoneAnalyzer``
    names ``bquant.indicators.MACDZoneAnalyzer`` (the re-export path), which the
    core graph exposes via an ``export`` edge to the canonical
    ``bquant.indicators.macd.MACDZoneAnalyzer``.
    """

    def __init__(self, graph: Graph, core_pkg: str):
        self.core_pkg = core_pkg
        self.node_ids = set(graph.nodes)
        self.module_ids = sorted(
            (n.id for n in graph.nodes.values() if n.kind == "module"),
            key=len,
            reverse=True,
        )
        # R1-C21-f1 (issue #6): whether the *core* is itself a flat layout, which decides
        # if a consumer's bare-name import can reach it at all. Structural, not statistical:
        # a properly packaged core is never on sys.path, so `from alpha import f` in a
        # script cannot be reaching `core/alpha.py` — inferring an edge there would invent
        # one. Both flat shapes satisfy this: a namespace directory (root has no file), or a
        # directory whose own imports needed the flat inference.
        root = graph.nodes.get(core_pkg)
        self.core_is_flat = (root is not None and root.file is None) or any(
            e.type == "imports" and e.extras.get("resolution") == "flat" for e in graph.edges
        )
        self.top_modules = {
            mid.split(".", 1)[1].split(".")[0]
            for mid in self.module_ids
            if mid.startswith(core_pkg + ".")
        }
        self.exports: dict[str, str] = {}
        for e in graph.edges:
            if e.type == "export":
                self.exports[f"{e.source}.{e.extras.get('as')}"] = e.target

    def is_core(self, qualname: str) -> bool:
        return qualname == self.core_pkg or qualname.startswith(self.core_pkg + ".")

    def qualify_flat(self, module_name: str) -> str | None:
        """Core-qualify a consumer's **bare-name** import, or None (R1-C21-f1, issue #6).

        `from alpha import f` in a consumer root names the same module that a sibling
        inside the package names that way — the flat layout puts the core directory on
        `sys.path`, so both reach it. Gated on ``core_is_flat`` (see ``__init__``) and on
        the head naming a real top-level core module, so it is inert on a packaged core.
        """
        if not self.core_is_flat or self.is_core(module_name):
            return None
        if module_name.split(".")[0] not in self.top_modules:
            return None
        return f"{self.core_pkg}.{module_name}"

    def resolve(self, qualname: str) -> str | None:
        """Canonical node id for a core-qualified path, or None if out of core."""
        if not self.is_core(qualname):
            return None
        if qualname in self.node_ids:
            return qualname
        if qualname in self.exports:
            return self.exports[qualname]
        # longest prefix that is a node or a re-export, then re-append the rest.
        parts = qualname.split(".")
        for cut in range(len(parts) - 1, 0, -1):
            prefix = ".".join(parts[:cut])
            base = self.exports.get(prefix) or (prefix if prefix in self.node_ids else None)
            if base is None:
                continue
            candidate = base + "." + ".".join(parts[cut:])
            return candidate if candidate in self.node_ids else base
        # fallback: the core module that contains it (still a real node).
        return self._containing_module(qualname)

    def _containing_module(self, qualname: str) -> str | None:
        for mid in self.module_ids:  # sorted longest-first
            if qualname == mid or qualname.startswith(mid + "."):
                return mid
        return None


# -- consumer roots (.py) ----------------------------------------------------

def _scan_consumer_root(graph: Graph, root_dir: Path, index: _CoreIndex, mode: str,
                        origin: Path | None = None) -> None:
    if not root_dir.is_dir():
        return
    label = root_dir.name
    base = root_dir.parent
    origin = origin or base
    for py in sorted(root_dir.rglob("*.py")):
        if any(part in _CONSUMER_SKIP_DIRS for part in py.parts):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        _scan_consumer_module(graph, py, base, label, tree, index, mode, origin)


def _module_id(py: Path, base: Path) -> str:
    rel = py.resolve().relative_to(base)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _scan_consumer_module(graph, py, base, label, tree, index, mode, origin=None) -> None:
    # the id is the import path (relative to the root's parent); the file is a location
    # (relative to the graph's one origin). They differ whenever a root sits deeper.
    mod_id = _module_id(py, base)
    rel = py.resolve().relative_to(origin or base).as_posix()
    graph.add_node(Node(id=mod_id, kind="module", file=rel, extras={"root": label}))

    symbol_map, module_aliases, flat_targets = _consumer_imports(tree, index)
    # module -> core module `imports` edges (dedup).
    seen_imp: set[str] = set()
    for tgt in list(symbol_map.values()) + [p for p in module_aliases.values()]:
        cm = index.resolve(tgt)
        cm = cm if cm in index.node_ids and _is_module(graph, cm) else index._containing_module(tgt)
        if cm and cm not in seen_imp:
            seen_imp.add(cm)
            # R1-C21-f1: label the sys.path inference on the import edge, exactly as the
            # in-package resolution does; the calls/references it enables stay "imported".
            extras = {"resolution": "flat"} if tgt in flat_targets else {}
            graph.add_edge(Edge("imports", mod_id, cm, extras=extras))

    if mode == "full":
        _materialize_defs(graph, tree, mod_id, label, rel)

    # use edges: (source_id, target_id) -> {called?, arg shapes at call-sites}.
    uses: dict[tuple[str, str], dict] = {}
    call_by_func = {id(n.func): n for n in ast.walk(tree) if isinstance(n, ast.Call)}
    inner_attr_ids = {
        id(n.value) for n in ast.walk(tree)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute)
    }
    func_ranges = _func_ranges(tree) if mode == "full" else []

    for node in ast.walk(tree):
        target = None
        use_node = node
        if isinstance(node, ast.Name) and node.id in symbol_map:
            target = index.resolve(symbol_map[node.id])
        elif isinstance(node, ast.Attribute) and id(node) not in inner_attr_ids:
            dotted = _dotted(node)
            if dotted:
                head, _, rest = dotted.partition(".")
                if head in module_aliases:
                    full = module_aliases[head] + ("." + rest if rest else "")
                    target = index.resolve(full)
        if not target:
            continue
        src = _source_for(use_node, mod_id, func_ranges) if mode == "full" else mod_id
        entry = uses.setdefault((src, target), {"called": False, "shapes": []})
        call_node = call_by_func.get(id(use_node))
        if call_node is not None:
            entry["called"] = True
            entry["shapes"].append(_arg_shape(call_node))  # F7: capture call-site contract

    for (src, target), entry in sorted(uses.items()):
        etype = "calls" if entry["called"] else "references"
        extras = {"resolution": "imported"}
        if etype == "calls" and entry["shapes"]:
            extras.update(_arg_contract(entry["shapes"]))
        graph.add_edge(Edge(etype, src, target, extras=extras))


def _consumer_imports(tree, index: _CoreIndex):
    """Return (symbol_map, module_aliases) for imports that reach into core.

    ``symbol_map``: local name -> core-qualified symbol path (``from core.x import Y``).
    ``module_aliases``: local root name -> core module prefix (``import core.x [as z]``).
    """
    symbol_map: dict[str, str] = {}
    module_aliases: dict[str, str] = {}
    flat_targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            module, flat = node.module, False
            if not index.is_core(module):
                # R1-C21-f1: a bare-name import of a core module, in a flat layout.
                qualified = index.qualify_flat(module)
                if qualified is None:
                    continue
                module, flat = qualified, True
            for alias in node.names:
                if alias.name == "*":
                    module_aliases.setdefault(module.split(".")[0], module)
                    if flat:
                        flat_targets.add(module)
                    continue
                target = f"{module}.{alias.name}"
                symbol_map[alias.asname or alias.name] = target
                if flat:
                    flat_targets.add(target)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name, flat = alias.name, False
                if not index.is_core(name):
                    qualified = index.qualify_flat(name)
                    if qualified is None:
                        continue
                    name, flat = qualified, True
                if alias.asname:
                    module_aliases[alias.asname] = name
                else:
                    # a flat `import alpha` binds the bare name, not the core prefix.
                    local = (alias.name if flat else name).split(".")[0]
                    module_aliases[local] = name if flat else name.split(".")[0]
                if flat:
                    flat_targets.add(name)
    return symbol_map, module_aliases, flat_targets


def _dotted(node) -> str | None:
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _is_module(graph, node_id) -> bool:
    n = graph.nodes.get(node_id)
    return n is not None and n.kind == "module"


# -- full mode: materialize consumer defs -----------------------------------

def _materialize_defs(graph, tree, mod_id, label, file: str | None = None) -> None:
    # R1-C31 (#12): with no `file`, a consumer symbol answered `search` as a line number
    # and nothing else — `{"file": null, "lineno": 278}` — while every core symbol carried
    # both. The module node had the path all along; the def nodes simply were not given it.
    for fnode, class_stack in _defs(tree):
        node_id = ".".join([mod_id, *class_stack, fnode.name])
        kind = "class" if isinstance(fnode, ast.ClassDef) else "function"
        graph.add_node(Node(id=node_id, kind=kind, file=file, lineno=fnode.lineno,
                            extras={"root": label}))
        parent = ".".join([mod_id, *class_stack]) if class_stack else mod_id
        graph.add_edge(Edge("contains", parent, node_id))


def _defs(tree):
    """Yield (def-node, [enclosing class/def names]) for top-level & nested defs."""
    results = []

    def visit(node, stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                results.append((child, list(stack)))
                visit(child, stack + [child.name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                results.append((child, list(stack)))
                visit(child, stack + [child.name])
            else:
                visit(child, stack)

    visit(tree, [])
    return results


def _func_ranges(tree):
    """(start, end, node_id) for each def, longest-first, to place a use by line."""
    ranges = []

    def visit(node, mod_stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nid = ".".join([*mod_stack, child.name])
                end = getattr(child, "end_lineno", child.lineno)
                ranges.append((child.lineno, end, nid))
                visit(child, mod_stack + [child.name])
            else:
                visit(child, mod_stack)

    visit(tree, [])
    # inner scopes first so a use inside a nested def is attributed to it.
    ranges.sort(key=lambda r: (r[1] - r[0]))
    return ranges


def _source_for(use_node, mod_id, func_ranges) -> str:
    line = getattr(use_node, "lineno", None)
    if line is not None:
        for start, end, nid in func_ranges:  # smallest-range first
            if start <= line <= end:
                return f"{mod_id}.{nid}"
    return mod_id


# -- doc roots (.md) ---------------------------------------------------------

def _doc_patterns(core_pkg: str):
    """Regexes keyed to the core package name (not hardcoded)."""
    pkg = re.escape(core_pkg)
    from_import = re.compile(rf"from\s+({pkg}[\w.]*)\s+import\s+([^\n#]+)")
    dotted = re.compile(rf"\b{pkg}(?:\.[A-Za-z_]\w*)+\b")
    return from_import, dotted


def _scan_doc_root(graph: Graph, root_dir: Path, index: _CoreIndex,
                   origin: Path | None = None) -> None:
    if not root_dir.is_dir():
        return
    base = origin or root_dir.parent
    patterns = _doc_patterns(index.core_pkg)
    for md in sorted(root_dir.rglob("*.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        _scan_doc_file(graph, md, base, text, index, patterns)


def _scan_doc_file(graph, md, base, text, index, patterns) -> None:
    from_import, dotted = patterns
    rel = str(md.resolve().relative_to(base))
    doc_id = rel
    targets: set[str] = set()

    # from-import lines pin re-exported symbols precisely.
    for module, names in from_import.findall(text):
        if not index.is_core(module):
            continue
        for raw in names.replace("(", " ").replace(")", " ").split(","):
            name = raw.strip().split(" as ")[0].strip()
            if not name or name == "*":
                continue
            tgt = index.resolve(f"{module}.{name}")
            if tgt:
                targets.add(tgt)

    # exact dotted mentions that resolve to a real node (filters prose noise).
    for token in dotted.findall(text):
        if token in index.node_ids:
            targets.add(token)
        elif token in index.exports:
            targets.add(index.exports[token])

    if not targets:
        return
    graph.add_node(Node(id=doc_id, kind="doc", file=rel, extras={"root": "docs"}))
    for tgt in sorted(targets):
        graph.add_edge(Edge("references", doc_id, tgt, extras={"resolution": "doc"}))
