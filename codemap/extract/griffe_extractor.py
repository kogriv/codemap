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
import os
from dataclasses import dataclass, field
from pathlib import Path

import griffe

from codemap.extract.attrflow import add_attrflow
from codemap.extract.behavior import add_behavior
from codemap.extract.dataflow import add_dataflow
from codemap.extract.dispatch import add_dispatch, add_family_links
from codemap.extract.gsource import module_file, module_identity
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
    root = griffe.load(module_name, search_paths=[str(search_path)])

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


def extract(package_path: str | Path, *, deep: bool = False) -> Graph:
    """Build a code graph from a Python package directory.

    ``deep=True`` runs the jedi-backed call resolver (M5) — richer call-graph
    (local-variable type inference) at ~1 min build cost; default is the fast
    ast tier (sub-second). See ``extract/behavior.py``.
    """
    graph, root, module_name, search_path = build_structural(package_path)
    add_behavioral_layer(graph, root, module_name, search_path, deep=deep)
    # R1-C25: even a library-built graph says which tool and which tier made it. The
    # input identity (scope_id, source commit) is added by whoever resolved the scope —
    # `extract` deliberately does not hash the tree a second time.
    graph.provenance = build_provenance(tier="deep" if deep else "fast",
                                        inputs=graph.provenance.get("inputs"))
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


def _star_import_targets(module) -> list[str]:
    """Modules pulled in by ``from X import *`` (R1-C23 / design D3).

    Fed into the same ``imports`` list griffe fills, so the target resolves — and gets
    the flat-layout retry — through exactly one code path.

    Cost is why this is a substring gate before a parse: ``module.source`` is already in
    griffe's cache, and scanning every module of the dogfood target for ``import *`` takes
    0.065s and yields zero candidates. Only a file that contains the text is parsed, so
    the answer is exact rather than a regex guess about what is inside a string literal.
    """
    try:
        src = module.source
    except Exception:                       # no source (namespace dir, synthetic)
        return []
    if "import *" not in src:
        return []
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return []                            # unreadable: D2's report owns this file
    modpath = module.canonical_path
    f = module_file(module)
    is_pkg = f is not None and f.name == "__init__.py"
    base = modpath.split(".") if is_pkg else modpath.split(".")[:-1]
    targets = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if not any(a.name == "*" for a in node.names):
            continue
        if node.level:
            anchor = base[:len(base) - (node.level - 1)]
            target = ".".join(anchor + ([node.module] if node.module else []))
        else:
            target = node.module or ""
        if target:
            targets.append(target)
    return targets


def _nested_import_targets(module) -> list[tuple[str, str]]:
    """``(target, scope)`` for imports griffe's module-level map does not carry (R1-C29).

    griffe records the imports written in the module body — including those under
    ``try:`` or ``if:``, which are still module-body statements. Two shapes escape it,
    and they are *not* the same fact:

    - **inside a function** → ``scope="function"``. It does not run at import time. This
      is the one issue #11 is about: left out entirely, and it is the very construct a
      developer uses to break an import cycle, so the missing edges were the ones most
      likely to close one.
    - **inside a class body** → ``scope="module"``. It runs at class-definition time,
      i.e. at import time, so it is an ordinary eager dependency and *can* close a real
      import cycle. griffe does not record it either (measured, not assumed).

    Same hook and cost discipline as :func:`_star_import_targets`: the source is already
    in griffe's cache, and only a file whose text contains ``import`` is parsed. A
    relative target is anchored the way the module's own package resolves it.
    """
    try:
        src = module.source
    except Exception:                        # no source (namespace dir, synthetic)
        return []
    if "import" not in src:
        return []
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return []                            # unreadable: D2's report owns this file
    modpath = module.canonical_path
    f = module_file(module)
    is_pkg = f is not None and f.name == "__init__.py"
    base = modpath.split(".") if is_pkg else modpath.split(".")[:-1]

    # Scope each nested import node once. A function inside a class is a function (it
    # does not run at import time), so the function pass is applied after and wins.
    scope_of: dict[int, str] = {}
    for holder in ast.walk(tree):
        if isinstance(holder, ast.ClassDef):
            for node in ast.walk(holder):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    scope_of[id(node)] = "module"
    for holder in ast.walk(tree):
        if isinstance(holder, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(holder):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    scope_of[id(node)] = "function"

    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        scope = scope_of.get(id(node))
        if scope is None:
            continue
        if isinstance(node, ast.Import):
            out.extend((a.name, scope) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = base[:len(base) - (node.level - 1)]
                target = ".".join(anchor + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            if not target:
                continue
            # `from pkg.mod import name` → keep the member paths, so the resolver walks
            # down to the containing module exactly as it does for the module-level map;
            # the bare target covers `from pkg import *` and the module itself.
            out.append((target, scope))
            out.extend((f"{target}.{a.name}", scope)
                       for a in node.names if a.name != "*")
    return out


def _collect(graph, obj, root, target_pkg, walk) -> None:
    if obj.kind.value == "module":
        _claim(obj, walk)  # the root claims its own path before any member is walked
        _add_node(graph, obj, root)
        for name, tgt in (obj.imports or {}).items():
            walk.imports.append((obj.canonical_path, tgt, "module"))
        # R1-C23/D3: griffe expands `from .m import *` into member aliases but records
        # no import, so the dependency itself was invisible — a star-import is the least
        # explicit dependency in the language and the one most worth surfacing.
        for tgt in _star_import_targets(obj):
            walk.imports.append((obj.canonical_path, tgt, "module"))
        # R1-C29 / issue #11: an import written *inside a function* is a real dependency
        # that griffe's module-level map does not carry. Leaving it out was not a neutral
        # omission — a function-local import is the standard way to break an import
        # cycle, so the edges we could not see were exactly the ones most likely to close
        # one. The blind spot was anti-correlated with the question.
        for tgt, scope in _nested_import_targets(obj):
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

    for parent_module, name, target_path, is_public in aliases:
        if not (target_path == target_pkg or target_path.startswith(target_pkg + ".")):
            continue  # external re-export (e.g. `import numpy as np`) — out of scope
        graph.add_edge(
            Edge(
                "export",
                parent_module,
                target_path,
                extras={"as": name, "public": is_public},
            )
        )

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
    known_modules = set(module_ids)
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


def _signature(obj) -> str | None:
    if obj.kind.value != "function":
        return None
    parts = []
    for p in obj.parameters:
        s = p.name
        if p.annotation is not None:
            s += f": {p.annotation}"
        if p.default is not None:
            s += f" = {p.default}"
        parts.append(s)
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
