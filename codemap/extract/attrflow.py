"""Attribute-access pass — function → attribute read/write edges (R1-C20, issue #1).

codemap models relationships between *symbols* (calls/imports/inherits/…) and
between functions and *string-keyed columns* (reads/writes, M12) — but **not**
between code and Python *attributes*. So ``impact`` on a class field returned
``refs: []`` / ``risk: "none"`` (an affirmative "nothing depends on this") even
when the field had many real read/write sites: attribute nodes exist but nothing
in the graph pointed at them (gaps/attribute_impact_gap_2026-08-22).

This pass makes attribute access first-class, mirroring what ``dataflow.py`` did
for columns:

- an ``accesses`` edge (function → the ``attribute`` node it touches), with
  ``extras.access`` (``read`` | ``write``) and ``extras.resolution``.

**Access forms and how each resolves** (only edges whose target is a real
``attribute`` node are emitted — R1-C13-f2 soundness; everything else is a
counter, never an edge to nothing):

- ``self.field`` / ``cls.field`` → the enclosing class's attribute, via the same
  ``members`` owner-map behavior.py uses (``self.<inherited>`` → the base that
  defines it, R1-C13-f1). ``resolution = "self"``. Fast tier.
- ``ClassName.field`` → the named class's attribute, class resolved through
  imports / module members. ``resolution = "class"``. Fast tier.
- construction kwargs ``Cls(field=…)`` → a *write* to ``Cls.field`` (this is how
  dataclass fields are most often set). ``resolution = "construct"``. Fast tier.
- ``obj.field`` on a typed local → jedi types ``obj`` → its attribute.
  ``resolution = "deep"``. Deep tier only (``deep=True``).
- ``obj.field`` on an untyped local → **unresolved** (counter, no edge). Honest.

**Boundaries.** Method / ``property`` access is *not* an attribute access — the
target there is a ``function`` node, so the ``kind == "attribute"`` gate excludes
it (properties are functions in griffe; out of scope, by design). Dynamic access
(``getattr``/``setattr``) is never guessed. Value-level dataflow (which value
flows into the field) is out of scope — this is *access* modelling, not taint.
"""

from __future__ import annotations

import ast
from pathlib import Path

from codemap.extract.behavior import (
    _SKIP_RECEIVERS,
    _class_members,
    _index_modules,
    _jedi_project,
    _jedi_script,
    _named_functions,
    _node_id,
    _own_nodes,
)
from codemap.model import Edge


def add_attrflow(graph, griffe_root, target_pkg: str, *, deep: bool = False,
                 search_path=None) -> None:
    """Add ``accesses`` edges (function → attribute) for read/write sites.

    ``deep=True`` enables the jedi tier for ``obj.field`` on typed locals; the fast
    tier (``self.``/``ClassName.``/construction kwargs) needs only stdlib ``ast``.
    Per-function ``extras.attr_access`` coverage counts (out / resolved / unresolved)
    are recorded so the graph reports its own honesty, like ``extras.calls``.
    """
    modules = _index_modules(griffe_root)
    project = _jedi_project(search_path) if deep else None
    pkg = target_pkg + "."
    # (func_id, attr_id, access, resolution) — dedup collapses repeated sites.
    edges: set[tuple[str, str, str, str]] = set()
    for modpath in sorted(modules):
        if "samples.embedded" in modpath:
            continue  # embedded datasets are data, not code (matches dataflow.py)
        mod = modules[modpath]
        fp = getattr(mod, "filepath", None)
        if not fp:
            continue
        try:
            source = Path(fp).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue
        imports = dict(mod.imports or {})
        modmembers = set(mod.members.keys())
        script = _jedi_script(source, fp, project) if deep else None
        for fnode, class_stack in _named_functions(tree):
            node_id = _node_id(modpath, class_stack, fnode.name)
            if node_id not in graph.nodes:
                continue  # nested closure — not a definition node
            members = _class_members(mod, class_stack, modules) if class_stack else {}
            counts = {"out": 0, "resolved": 0, "unresolved": 0}
            for attr_id, access, resolution in _own_attr_uses(
                fnode, graph, modpath, members, imports, modmembers, pkg, script
            ):
                counts["out"] += 1
                if attr_id is None:
                    counts["unresolved"] += 1
                    continue
                counts["resolved"] += 1
                edges.add((node_id, attr_id, access, resolution))
            if counts["out"]:
                graph.nodes[node_id].extras["attr_access"] = counts

    for src, attr_id, access, resolution in sorted(edges):
        graph.add_edge(Edge("accesses", src, attr_id,
                            extras={"access": access, "resolution": resolution}))


def _is_attribute_node(graph, node_id: str) -> bool:
    """True iff ``node_id`` is a real ``attribute`` node.

    The soundness gate (R1-C13-f2): only emit ``accesses`` to an attribute — this
    also excludes methods and ``property`` (function nodes) that share the ``.name``
    shape, so those stay in the calls layer where they belong.
    """
    node = graph.nodes.get(node_id)
    return node is not None and node.kind == "attribute"


def _resolve_class(name: str, modpath: str, imports: dict, modmembers: set,
                   pkg: str) -> str | None:
    """Canonical id of the package class ``name`` refers to (imports / module), else None.

    Mirrors behavior.py's call-target resolution: an imported name maps to its
    (griffe-resolved) target path; a module-level name to ``{modpath}.{name}``.
    """
    if name in imports:
        tgt = imports[name]
        return tgt if tgt.startswith(pkg) else None
    if name in modmembers:
        return f"{modpath}.{name}"
    return None


def _own_attr_uses(fnode, graph, modpath, members, imports, modmembers, pkg, script):
    """Yield (attr_id | None, access, resolution) for attribute uses in a function body.

    ``attr_id is None`` marks an access site we saw but could not resolve to an
    attribute node (an honest unresolved counter — never an edge to nothing).
    Skips nested defs/classes (their own scope), matching ``_own_nodes``.
    """
    nodes = list(_own_nodes(fnode))
    # Attributes that are the callee of a call (``self.foo()``) are *method calls*,
    # handled by the behavioral layer — not field access. Skip exactly those.
    call_funcs = {id(n.func) for n in nodes if isinstance(n, ast.Call)}

    for node in nodes:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            # construction kwargs: Cls(field=…) → write to Cls.field
            cls_id = _resolve_class(node.func.id, modpath, imports, modmembers, pkg)
            if cls_id is not None:
                for kw in node.keywords:
                    if kw.arg is None:
                        continue  # **kwargs splat — arity unknown, don't guess
                    attr_id = f"{cls_id}.{kw.arg}"
                    if _is_attribute_node(graph, attr_id):
                        yield attr_id, "write", "construct"
                    else:
                        yield None, "write", "construct"
            continue

        if not isinstance(node, ast.Attribute) or id(node) in call_funcs:
            continue
        recv = node.value
        if not isinstance(recv, ast.Name):
            # obj.attr where obj is itself an expression — deep tier only.
            yield from _deep_attr(node, graph, pkg, script)
            continue
        access = "write" if isinstance(node.ctx, ast.Store) else "read"
        if recv.id in _SKIP_RECEIVERS:
            # self.field / cls.field — resolve via the class member owner-map.
            owner = members.get(node.attr)
            attr_id = f"{owner}.{node.attr}" if owner else None
            if attr_id and _is_attribute_node(graph, attr_id):
                yield attr_id, access, "self"
            else:
                yield None, access, "self"
        else:
            cls_id = _resolve_class(recv.id, modpath, imports, modmembers, pkg)
            if cls_id is not None:
                # ClassName.field
                attr_id = f"{cls_id}.{node.attr}"
                if _is_attribute_node(graph, attr_id):
                    yield attr_id, access, "class"
                else:
                    yield None, access, "class"
            else:
                # obj.field on a local — deep tier resolves the type, else unresolved.
                yield from _deep_attr(node, graph, pkg, script)


def _deep_attr(node, graph, pkg, script):
    """Resolve ``obj.field`` via jedi (deep tier); yield (attr_id | None, access, 'deep').

    Infers the **type of the receiver** (``obj`` in ``obj.field``) → its class →
    ``{class}.{field}``, rather than ``goto``-ing the attribute name: jedi's goto on
    an instance attribute lands on whichever assignment statement it can see
    (``Class.method.field``), not the class-level field node. Inferring the receiver
    is exact and also threads chains (``self.cfg.field`` — the receiver ``self.cfg``
    is itself typed). Yields nothing on the fast tier (no jedi script) so a typed
    local isn't even counted as unresolved there — the fast tier makes no claim.
    """
    if script is None:
        return
    access = "write" if isinstance(node.ctx, ast.Store) else "read"
    recv = node.value
    end_line = getattr(recv, "end_lineno", None)
    end_col = getattr(recv, "end_col_offset", None)
    if end_line is None or end_col is None:
        yield None, access, "deep"
        return
    try:
        types = script.infer(end_line, end_col)
    except Exception:
        yield None, access, "deep"
        return
    for t in sorted(types, key=lambda d: d.full_name or ""):
        cls = t.full_name
        if not cls or not cls.startswith(pkg):
            continue
        attr_id = f"{cls}.{node.attr}"
        if _is_attribute_node(graph, attr_id):
            yield attr_id, access, "deep"
            return
    yield None, access, "deep"
