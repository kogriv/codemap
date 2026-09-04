"""Python extractor backed by griffe (DESIGN §10.8).

Static analysis only — griffe parses source without importing the target, and
resolves the hard parts for us (signatures, docstrings, __all__ visibility,
base-class / relative-import / re-export resolution — DESIGN §3.1); we consume
that, we don't reinvent it.

Emits (M0 + M1 + M1.5):
- definition nodes (module/class/function/attribute) + `contains` structure;
- `export` edges for re-exports/aliases (module re-exposes a symbol — §2.1);
- `imports` edges between modules (dependency graph — §1, §3.1);
- `inherits` edges (class → base class; external bases flagged — §2);
- `decorated_by` edges (symbol → decorator callable — §2);
- node `extras`: attribute `annotation`, class `is_dataclass`, and dynamic
  `registry` binding (decorator + literal key) for factory/registry wiring (§7).
"""

from __future__ import annotations

import ast
import multiprocessing
import os
from dataclasses import dataclass, field
from pathlib import Path

import griffe

from codemap.extract.attrflow import add_attrflow
from codemap.extract.behavior import add_behavior
from codemap.extract.dataflow import add_dataflow
from codemap.extract.dispatch import add_dispatch, add_family_links
from codemap.extract.gsource import NESTED_IMPORT_HINT, module_file, module_identity
from codemap.extract.union import merge_samples
from codemap.provenance import build_provenance
from codemap.model import Edge, Graph, Node

# griffe object kinds we turn into definition nodes (aliases handled separately).
_NODE_KINDS = {"module", "class", "function", "attribute"}

#: Why an input file produced no module (R1-C23 / design D2).
SKIP_ENCODING, SKIP_SYNTAX, SKIP_IO, SKIP_UNREAD = "encoding", "syntax", "io", "unread"



@dataclass
class _Walk:
    """What one structural walk accumulates besides nodes and edges."""

    aliases: list = field(default_factory=list)   # (parent_module, name, target, public)
    #: (module_id, target_symbol_path, scope) — scope is "module" or, since R1-C29,
    #: "function" for an import written inside a function body.
    imports: list = field(default_factory=list)
    #: canonical real path → the module id that claimed it (R1-C23/D1, symlink cycles)
    claimed: dict = field(default_factory=dict)
    #: module ids skipped because their file was already read under another name
    aliased: list = field(default_factory=list)   # (skipped_id, owner_id)


def _assert_is_the_target(loaded, pkg_dir: Path, module_name: str) -> None:
    """Raise unless what griffe loaded is the directory we were handed (R1-C36).

    Separate from its caller so the decision can be tested on shapes that a single
    ``search_paths`` entry cannot produce end to end. A **namespace package reports a
    list** of directories rather than one path — the shape that once crashed the
    extractor (issue #4) — and a package assembled from several parts is a legitimate
    hit as long as the requested directory is one of them.

    An empty ``loaded`` is not treated as a mismatch: "griffe told us nothing about the
    file" is not "griffe told us the wrong file", and inventing a failure from silence
    is the same error in the other direction.
    """
    candidates = loaded if isinstance(loaded, (list, tuple)) else ([loaded] if loaded else [])
    dirs = {(q if q.is_dir() else q.parent).resolve() for q in map(Path, candidates)}
    if dirs and pkg_dir not in dirs:
        raise ValueError(
            f"resolved `{module_name}` to {', '.join(sorted(str(d) for d in dirs))} but was "
            f"asked for {pkg_dir}. A same-named package is shadowing the target (an "
            "installed copy, or one in the current directory). Build from a different "
            "working directory, or rename the target."
        )


def build_structural(package_path: str | Path):
    """The cheap, deterministic base: griffe load + definition nodes + structural
    edges (contains / imports / inherits / decorated_by / export). No behavioral
    layer. Shared by :func:`extract` and the incremental path (R1-C9), which both
    add the (expensive, tier-sensitive) behavioral passes on top.

    Returns ``(graph, root, module_name, search_path)``.
    """
    pkg_dir = Path(package_path).resolve()
    if not pkg_dir.is_dir():
        raise NotADirectoryError(f"Not a package directory: {pkg_dir}")

    module_name = pkg_dir.name
    search_path = pkg_dir.parent
    # R1-C36: `try_relative_path` (griffe's default) reinterprets the module *name* as a
    # path relative to the current directory, and that wins over `search_paths`. Run from
    # a repo whose root holds `pkg/`, `build /elsewhere/pkg` then silently analysed the
    # local `pkg` — same shape of answer, different code. We always know the directory we
    # were handed, so the name must resolve through `search_paths` and nowhere else.
    root = griffe.load(module_name, search_paths=[str(search_path)], try_relative_path=False)
    # Defence in depth: whatever the finder does next (a .pth file, a namespace package,
    # a future default), a graph must describe the directory that was asked for. A wrong
    # answer here is invisible downstream — it is well-formed, complete and about the
    # wrong tree — so it fails loudly instead.
    _assert_is_the_target(getattr(root, "filepath", None), pkg_dir, module_name)

    graph = Graph(target=module_name)
    walk = _Walk()

    _collect(graph, root, search_path, module_name, walk)
    _resolve_edges(graph, module_name, walk.aliases, walk.imports)
    # R1-C23/D2: an input the extractor could not read used to vanish without a word,
    # and the graph then reported on a tree it had not fully seen. Record what was
    # missed *in the artifact*, so a consumer holding only the graph is told.
    graph.provenance = {"inputs": _input_report(graph, pkg_dir, search_path, walk)}
    return graph, root, module_name, search_path


def add_behavioral_layer(graph, root, module_name, search_path, *, deep: bool,
                         behavior_only=None, attr_only=None) -> None:
    """Add every behavioral pass on top of a structural base (in the fixed order).

    ``behavior_only`` / ``attr_only`` (module-path sets) restrict the two expensive
    jedi-sensitive passes to those modules — the incremental hook (R1-C9). The cheap,
    tier-independent passes (dispatch / family / dataflow) always run whole.
    """
    # M4/M5: call-graph + control skeleton (deep=jedi type inference).
    add_behavior(graph, root, module_name, deep=deep, search_path=search_path,
                 only=behavior_only)
    # M7: bridge factory/registry dispatch seams using the M1.5 registry table.
    add_dispatch(graph, root, module_name)
    # M9 (F4): link registry-family members to the Protocol they satisfy.
    add_family_links(graph)
    # M12 (F6): column/string-key dataflow (reads/writes on `df['col']`).
    add_dataflow(graph, root, module_name)
    # R1-C20 (issue #1): attribute-access edges (accesses: function → attribute).
    add_attrflow(graph, root, module_name, deep=deep, search_path=search_path,
                 only=attr_only)


def _sample_worker(package_path: str, deep: bool) -> dict:
    """One full extraction in a child interpreter; returns the graph as a dict (R1-C45)."""
    graph, root, module_name, search_path = build_structural(package_path)
    add_behavioral_layer(graph, root, module_name, search_path, deep=deep)
    return graph.to_dict()


def collect_samples(package_path, *, deep: bool, runs: int,
                    workers: int | None = None) -> list[Graph]:
    """``runs`` independent samples of ``package_path``, each in a fresh interpreter.

    Lives here, beside the two functions the worker calls, so ``extract/union.py`` stays
    a pure merge and the import graph stays acyclic — codemap's own ``no_lazy_cycles``
    contract caught the first draft, which reached back from ``union`` with a
    function-local import. ``workers`` bounds concurrency (default: the machine's core
    count, capped at ``runs``). Spawn, not fork: a forked child would inherit exactly the
    state that makes an in-process repeat correlate with the pass before it.
    """
    ctx = multiprocessing.get_context("spawn")
    procs = max(1, min(runs, workers or os.cpu_count() or 1))
    with ctx.Pool(processes=procs) as pool:
        dicts = pool.starmap(_sample_worker, [(str(package_path), deep)] * runs)
    samples = []
    for d in dicts:
        g = Graph.from_dict(d)
        g.loaded_schema = None  # a fresh build, not a file — keep schema_diagnostic quiet
        samples.append(g)
    return samples


def extract(package_path: str | Path, *, deep: bool = False, repeat: int = 1) -> Graph:
    """Build a code graph from a Python package directory.

    ``deep=True`` runs the jedi-backed call resolver (M5) — richer call-graph
    (local-variable type inference) at ~1 min build cost; default is the fast
    ast tier (sub-second). See ``extract/behavior.py``.

    ``repeat=N`` (R1-C45) builds N samples — **each in a fresh interpreter**, the
    regime whose recovery share was measured; in-process repeats come in correlated
    streaks (see ``extract/union.py``) — and unions them: a deep build is one sample
    of jedi's bounded inference, and an edge seen in fewer than N runs carries
    ``extras.seen``.
    """
    if repeat > 1:
        graph, stats = merge_samples(collect_samples(package_path, deep=deep, runs=repeat))
    else:
        graph, root, module_name, search_path = build_structural(package_path)
        add_behavioral_layer(graph, root, module_name, search_path, deep=deep)
        stats = {"runs": 1}
    # R1-C25: even a library-built graph says which tool and which tier made it. The
    # input identity (scope_id, source commit) is added by whoever resolved the scope —
    # `extract` deliberately does not hash the tree a second time.
    graph.provenance = build_provenance(tier="deep" if deep else "fast",
                                        inputs=graph.provenance.get("inputs"),
                                        samples=stats)
    return graph


# -- pass 1: definition nodes + contains/inherits/decorated_by, collect aliases/imports --

def _enumerate_sources(pkg_dir: Path) -> list[Path]:
    """Every ``.py`` under the package, each real file once (R1-C23 / design D1+D2).

    Symlinks *are* followed — a symlinked source directory is a legitimate layout — but a
    directory whose real path was already walked is not re-entered, which is what keeps a
    ``loop -> .`` link from generating an unbounded tree. Deterministic order.
    """
    out: list[Path] = []
    seen: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(pkg_dir, followlinks=True):
        real = os.path.realpath(dirpath)
        if real in seen:
            dirnames[:] = []
            continue
        seen.add(real)
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        out.extend(Path(dirpath) / n for n in sorted(filenames) if n.endswith(".py"))
    return out


def _skip_reason(path: Path) -> str:
    """Why this file produced no module — asked only of files that produced none."""
    try:
        src = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return SKIP_ENCODING
    except OSError:
        return SKIP_IO
    try:
        ast.parse(src)
    except (SyntaxError, ValueError):
        return SKIP_SYNTAX
    return SKIP_UNREAD          # parses here but griffe produced nothing — say so plainly


def _input_report(graph, pkg_dir: Path, root: Path, walk) -> dict:
    """What the walk read, and what it could not (R1-C23 / design D2).

    Lives in the graph's ``provenance`` rather than in a sidecar because a consumer
    holding only ``graph.json`` is exactly the one who must be told that the tree was
    read incompletely. Paths are relative to the search root — the artifact travels.
    """
    files = _enumerate_sources(pkg_dir)
    have = {n.file for n in graph.nodes.values() if n.kind == "module" and n.file}
    py = sorted(_rel(f, root) for f in files)
    skipped = [{"path": rel, "reason": _skip_reason(root / rel)}
               for rel in py if rel not in have]
    report: dict = {"python_files": len(py)}
    if skipped:
        report["skipped"] = skipped
    if walk.aliased:
        report["aliased_modules"] = [
            {"id": mid, "same_as": owner} for mid, owner in sorted(walk.aliased)
        ]
    return report


def _source_import_targets(module) -> list[tuple[str, str]]:
    """``(target, scope)`` for the imports griffe's module-level map does not carry.

    Two families, one traversal, one parse — griffe records neither, and both used to be
    invisible to the import graph:

    - **`from X import *`** at module level (R1-C23 / design D3). griffe expands it into
      member aliases but records no import, so the dependency itself vanished — the least
      explicit dependency in the language and the one most worth surfacing. Scope
      ``"module"``: it runs at import time.
    - **imports written inside a function** (R1-C29 / issue #11) → scope ``"function"``.
      They do not run at import time. This is the construct a developer uses to break an
      import cycle, so the edges that were missing were exactly the ones most likely to
      close one — the blind spot was anti-correlated with the question.
    - **imports written in a class body** → scope ``"module"``. They run at
      class-definition time, i.e. at import time, so they are ordinary eager dependencies
      and *can* close a real import cycle. griffe does not record them either (measured).

    Cost discipline, and it is not theoretical: the first version of this walked every
    function's subtree separately, which is quadratic in nesting and cost the dogfood
    target **4 seconds of a 7-second build**. One pre-order descent that carries the
    current scope is linear, and the substring gate keeps a file without the word
    ``import`` from being parsed at all. ``module.source`` is already in griffe's cache;
    the parse is the expense, so it happens once per module for both families.
    """
    try:
        src = module.source
    except Exception:                       # no source (namespace dir, synthetic)
        return []
    if not NESTED_IMPORT_HINT.search(src):
        return []
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return []                            # unreadable: D2's report owns this file
    modpath = module.canonical_path
    f = module_file(module)
    is_pkg = f is not None and f.name == "__init__.py"
    base = modpath.split(".") if is_pkg else modpath.split(".")[:-1]

    def resolve(node: ast.ImportFrom) -> str:
        if node.level:
            anchor = base[:len(base) - (node.level - 1)]
            return ".".join(anchor + ([node.module] if node.module else []))
        return node.module or ""

    out: list[tuple[str, str]] = []

    def visit(node, scope: str | None) -> None:
        """``scope`` is None at module level (griffe has those), else module|function."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, "function")
            elif isinstance(child, ast.ClassDef):
                # A class body runs at import time — unless we are already inside a
                # function, in which case the whole thing does not.
                visit(child, "function" if scope == "function" else "module")
            elif isinstance(child, ast.Import):
                if scope is not None:
                    out.extend((a.name, scope) for a in child.names)
            elif isinstance(child, ast.ImportFrom):
                target = resolve(child)
                if not target:
                    continue
                star = any(a.name == "*" for a in child.names)
                if scope is None:
                    if star:                 # the D3 case: griffe records nothing
                        out.append((target, "module"))
                    continue
                # `from pkg.mod import name` → keep the member paths so the resolver walks
                # down to the containing module exactly as it does for the module-level
                # map; the bare target covers a star import and the module itself.
                out.append((target, scope))
                out.extend((f"{target}.{a.name}", scope)
                           for a in child.names if a.name != "*")
            else:
                visit(child, scope)

    visit(tree, None)
    return out


def _collect(graph, obj, root, target_pkg, walk) -> None:
    if obj.kind.value == "module":
        _claim(obj, walk)  # the root claims its own path before any member is walked
        _add_node(graph, obj, root)
        for name, tgt in (obj.imports or {}).items():
            walk.imports.append((obj.canonical_path, tgt, "module"))
        # R1-C23/D3 (star imports) + R1-C29 (function-local and class-body imports):
        # everything griffe's module-level map does not carry, in one parse.
        for tgt, scope in _source_import_targets(obj):
            walk.imports.append((obj.canonical_path, tgt, scope))
    for name, member in obj.members.items():
        if member.is_alias:
            # capture ALL re-exports (public flag kept) — a symbol can be importable
            # via a module without being in its __all__ (e.g. bquant.analysis.zones
            # re-exports analyze_zones but its __all__ lists only the legacy API).
            walk.aliases.append(
                (obj.canonical_path, name, member.target_path, member.is_public)
            )
            continue
        if member.kind.value not in _NODE_KINDS:
            continue
        # R1-C23/D1: a directory symlink into its own ancestry makes the same file
        # reachable under unboundedly many names. Refuse the second name — before the
        # `contains` edge, or the graph keeps an edge to a node that is never added.
        if member.kind.value == "module" and not _claim(member, walk):
            continue
        if member.kind.value != "module":  # modules add themselves in the branch above
            _add_node(graph, member, root)
        graph.add_edge(Edge("contains", obj.canonical_path, member.canonical_path))
        _emit_decorated_by(graph, member)
        if member.kind.value == "class":
            _emit_inherits(graph, member, target_pkg)
        if member.kind.value in {"module", "class"}:
            _collect(graph, member, root, target_pkg, walk)


def _claim(module, walk) -> bool:
    """Claim a module's real path for it; False when another module already holds it.

    The survivor is whichever module the walk reached first — the walk descends from the
    package root, so that is always the shallower, real name (``hardpkg.api`` over
    ``hardpkg.loop.api``). A module with no resolvable path cannot be proven a duplicate
    and is always kept: omitting real code is the worse error.
    """
    key = module_identity(module)
    if key is None:
        return True
    owner = walk.claimed.get(key)
    if owner is None:
        walk.claimed[key] = module.canonical_path
        return True
    if owner == module.canonical_path:
        return True
    walk.aliased.append((module.canonical_path, owner))
    return False


# -- semantic edges resolvable inline (griffe gives absolute targets) --------

def _emit_inherits(graph, cls, target_pkg) -> None:
    """One `inherits` edge per base; griffe resolves the base to a canonical path."""
    for base in getattr(cls, "bases", None) or []:
        target = getattr(base, "canonical_path", None) or str(base)
        internal = target == target_pkg or target.startswith(target_pkg + ".")
        graph.add_edge(
            Edge(
                "inherits",
                cls.canonical_path,
                target,
                extras={} if internal else {"external": True},
            )
        )


def _emit_decorated_by(graph, obj) -> None:
    """One `decorated_by` edge per decorator (target = its callable path)."""
    for name in _decorator_names(obj):
        graph.add_edge(Edge("decorated_by", obj.canonical_path, name))


# -- pass 2: resolve export + import edges against known nodes ----------------

def _resolve_edges(graph, target_pkg, aliases, imports) -> None:
    module_ids = sorted(
        (n.id for n in graph.nodes.values() if n.kind == "module"), key=len, reverse=True
    )

    known_modules = set(module_ids)
    for parent_module, name, target_path, is_public in aliases:
        extras = {"as": name, "public": is_public}
        if not (target_path == target_pkg or target_path.startswith(target_pkg + ".")):
            # R1-C30-f1: the same flat-layout blind spot pass B fixes for `imports`, on
            # the re-export side. `from inner import helper` in a flat tree records the
            # source-literal `inner.helper`, indistinguishable from `pandas.DataFrame`
            # here — so every re-export in such a tree was filed as external and produced
            # no edge at all. Same narrow gate as pass B: only when the head names a
            # module sitting beside the re-exporter, and labelled as the inference it is.
            if _flat_sibling(parent_module, target_path, known_modules) is None:
                continue  # external re-export (e.g. `import numpy as np`) — out of scope
            target_path = f"{parent_module.rsplit('.', 1)[0]}.{target_path}"
            extras["resolution"] = "flat"
        graph.add_edge(Edge("export", parent_module, target_path, extras=extras))

    seen: set[tuple[str, str]] = set()
    unresolved: list[tuple[str, str, str]] = []

    # R1-C29: module-level entries first, so a pair imported both ways is recorded as
    # the eager import it is. `scope` only ever *weakens* to "function" for a pair that
    # has no module-level import at all — the edge says how the dependency is reached at
    # its earliest, never how it happens to appear last in the walk.
    ordered = sorted(imports, key=lambda t: t[2] == "function")

    # pass A — package-qualified targets. Exact, and run first so that a pair reachable
    # both ways is recorded as exact rather than inferred.
    for src_module, target_path, scope in ordered:
        if not (target_path == target_pkg or target_path.startswith(target_pkg + ".")):
            unresolved.append((src_module, target_path, scope))  # external, or flat (B)
            continue
        tgt_module = _containing_module(target_path, module_ids)
        if tgt_module is None or tgt_module == src_module:
            continue
        key = (src_module, tgt_module)
        if key in seen:
            continue
        seen.add(key)
        extras = {"scope": "function"} if scope == "function" else {}
        graph.add_edge(Edge("imports", src_module, tgt_module, extras=extras))

    # pass B — flat layout (R1-C21): sibling modules importing each other by bare name
    # (`from alpha import X`), which works at runtime because the directory itself is on
    # sys.path. griffe records the source-literal target, so pass A cannot tell it from
    # `pandas.DataFrame`. Retry it against the importer's own package — and label it, since
    # this is an inference about sys.path, not something the source states.
    for src_module, target_path, scope in unresolved:
        tgt_module = _flat_sibling(src_module, target_path, known_modules)
        if tgt_module is None or tgt_module == src_module:
            continue
        key = (src_module, tgt_module)
        if key in seen:
            continue
        seen.add(key)
        extras = {"resolution": "flat"}
        if scope == "function":
            extras["scope"] = "function"
        graph.add_edge(Edge("imports", src_module, tgt_module, extras=extras))


def _flat_sibling(src_module: str, target_path: str, known_modules: set[str]) -> str | None:
    """The flat-layout sibling of ``src_module`` named by ``target_path``, or None.

    Deliberately narrow (design D2): it only ever sees targets that resolved to nothing
    as package-qualified, and it only fires when the target's head names a module sitting
    **beside the importer**. Measured on two real packages (codemap, bquant): fires zero
    times, so a correctly-laid-out package cannot be disturbed by it.
    """
    if "." not in src_module:
        return None  # a top-level module has no package for siblings to live in
    parent = src_module.rsplit(".", 1)[0]
    candidate = f"{parent}.{target_path.split('.', 1)[0]}"
    return candidate if candidate in known_modules else None


def _containing_module(symbol_path: str, module_ids: list[str]) -> str | None:
    """Longest module-id that is a prefix of (or equals) the symbol path."""
    for mid in module_ids:  # already sorted longest-first
        if symbol_path == mid or symbol_path.startswith(mid + "."):
            return mid
    return None


# -- node building (M0 + M1.5 extras) ----------------------------------------

def _add_node(graph, obj, root) -> None:
    decorators = _decorator_names(obj)
    graph.add_node(
        Node(
            id=obj.canonical_path,
            kind=obj.kind.value,
            file=_rel(module_file(obj), root),  # None for a namespace dir (R1-C21)
            lineno=getattr(obj, "lineno", None),
            endlineno=getattr(obj, "endlineno", None),
            signature=_signature(obj),
            docstring=obj.docstring.value if obj.docstring else None,
            visibility="public" if obj.is_public else "private",
            decorators=decorators,
            is_deprecated=any(d.split(".")[-1] == "deprecated" for d in decorators),
            extras=_stub_marked(_extras(obj, decorators), obj),
        )
    )


def _stub_marked(extras: dict, obj) -> dict:
    """Label a symbol that exists only in a ``.pyi`` stub (R1-C23 / design D5).

    A stub-only module has no runtime counterpart, so its symbols are declarations, not
    code. Labelling beats both alternatives: dropping them loses the declared surface of
    a stubs distribution, and leaving them unmarked presents a function that does not
    exist as if it did. Consumers that reason about execution (dead-code) exclude them.
    """
    f = module_file(obj)
    if f is not None and f.suffix == ".pyi":
        extras = {**extras, "stub": True}
    return extras


def _extras(obj, decorators) -> dict:
    """Language-specific facts kept off the neutral core (DESIGN §2)."""
    extras: dict = {}
    kind = obj.kind.value
    if kind == "attribute" and getattr(obj, "annotation", None) is not None:
        extras["annotation"] = str(obj.annotation)  # e.g. "List[ZoneInfo]" (CM-01)
    if kind == "function":
        # structured param/return types — basis for type-flow (M4) and CM-03.
        params = [
            {"name": p.name, "type": str(p.annotation)}
            for p in obj.parameters
            if p.annotation is not None
        ]
        if params:
            extras["params"] = params
        if obj.returns is not None:
            extras["returns"] = str(obj.returns)
    if kind == "class":
        if any(d.split(".")[-1] == "dataclass" for d in decorators):
            extras["is_dataclass"] = True  # CM-02
        binding = _registry_binding(obj)  # CM-07: @Registry.register('key')
        if binding is not None:
            extras["registry"] = binding
    return extras


def _registry_binding(obj) -> dict | None:
    """Dynamic registration via a decorator call with a literal string key.

    Turns ``@ZoneDetectionRegistry.register('zero_crossing', ...)`` into
    ``{"decorator": "...register", "key": "zero_crossing"}`` so factory/registry
    wiring is queryable instead of hidden in a decorator string (DESIGN §7).
    """
    for d in getattr(obj, "decorators", []) or []:
        path = getattr(d, "callable_path", None)
        value = getattr(d, "value", None)
        if path is None or "register" not in str(path).lower():
            continue
        args = getattr(value, "arguments", None)
        if not args:
            continue
        first = args[0]  # griffe gives a string-literal arg as quoted source text
        if isinstance(first, str) and len(first) >= 2 and first[0] in "'\"":
            key = first.strip("'\"")
            if key:
                return {"decorator": str(path), "key": key}
    return None


def _param(p, *, bare: bool = False) -> str:
    """One parameter, PEP8-spaced: ``x=1`` bare, ``x: int = 1`` annotated.

    ``bare`` is for ``*args`` / ``**kwargs``, where griffe reports a default of
    ``()`` / ``{}``. That default is the collection the callee receives, not
    something written in the source, and printing it invents an argument.
    """
    s = p.name
    if p.annotation is not None:
        s += f": {p.annotation}"
    if not bare and p.default is not None:
        s += f" = {p.default}" if p.annotation is not None else f"={p.default}"
    return s


def _signature(obj) -> str | None:
    """The declared signature, as written — including parameter *kind*.

    R1-C34. The first version of this dropped kind entirely: `*args` came out as a
    parameter named `args` with a default of `()`, `**kw` as `kw={}`, and both `/`
    and the bare `*` marker vanished. So `def h(*args, **kw)` — accepts anything —
    and `def h(args=(), kw={})` — two optional positionals — rendered to the same
    string, and `def f(a, b)` -> `def f(a, *, b)`, which breaks every positional
    caller, was invisible to `apidiff` because both sides rendered `f(a, b)`.

    The string is consumed by `report api-surface`, `apidiff` (which re-parses it as
    `def <sig>: ...`), the exports, and — since R1-C33 — the `query` dossier. All
    four were reading a signature that could not be called.
    """
    if obj.kind.value != "function":
        return None
    params = list(obj.parameters)
    kinds = [getattr(p.kind, "name", "positional_or_keyword") for p in params]
    parts: list[str] = []
    star = False  # a `*` or `*args` is already in scope, so `*` must not repeat
    for i, (p, kind) in enumerate(zip(params, kinds)):
        if kind != "positional_only" and i and kinds[i - 1] == "positional_only":
            parts.append("/")
        if kind == "var_positional":
            parts.append("*" + _param(p, bare=True))
            star = True
        elif kind == "var_keyword":
            parts.append("**" + _param(p, bare=True))
        elif kind == "keyword_only":
            if not star:
                parts.append("*")
                star = True
            parts.append(_param(p))
        else:
            parts.append(_param(p))
    if kinds and kinds[-1] == "positional_only":
        parts.append("/")
    sig = f"{obj.name}({', '.join(parts)})"
    if obj.returns is not None:
        sig += f" -> {obj.returns}"
    return sig


def _decorator_names(obj) -> list[str]:
    names = []
    for d in getattr(obj, "decorators", []) or []:
        path = getattr(d, "callable_path", None)
        names.append(str(path) if path else str(getattr(d, "value", d)))
    return names


def _rel(filepath, root: Path) -> str | None:
    if filepath is None:
        return None
    try:
        return str(Path(filepath).resolve().relative_to(root.resolve()))
    except ValueError:
        return str(filepath)
