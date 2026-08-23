"""Incremental graph rebuild — recompute only what changed (R1-C9).

A full deep extract of bquant is ~97s, and **~93s of that is the jedi type-inference
tier** (the two passes ``add_behavior(deep=True)`` and ``add_attrflow(deep=True)``);
everything else — griffe load, structural nodes/edges, dispatch, family links,
string-key dataflow — is ~4s together. So the incremental win is entirely in *not
re-running jedi on modules that didn't change*.

The strategy, given that split:

1. Rebuild the **cheap, deterministic** part whole and fresh every time (structural
   base + dispatch + family + dataflow). This is always identical to a full build, so
   there is zero splice risk there.
2. Run the **expensive** jedi passes only on the *affected* modules.
3. **Splice** the two jedi-produced contributions (behavioral ``calls`` edges +
   ``accesses`` edges, and the per-function ``calls``/``control``/``complexity``/
   ``attr_access`` node extras) for the unaffected modules straight from the old graph.

**Affected set** = changed/added/removed modules, plus any module that (a) freshly
imports a changed/added module, or (b) had an old behavioral edge into a changed or
removed module. That covers both fast-tier (import/module resolution to a renamed
symbol) and deep-tier (jedi reaching a changed target) staleness. When the affected
set is large relative to the package, a full rebuild is cheaper and certainly correct,
so we fall back to it.

The acceptance bar (BACKLOG R1-C9) is **byte-identical to a full rebuild**; the test
suite pins exactly that across edit / add / remove scenarios on both tiers.
"""

from __future__ import annotations

import copy
from pathlib import Path

from codemap.extract.griffe_extractor import add_behavioral_layer, build_structural
from codemap.model import Graph
from codemap.scope import diff_scopes

# Behavioral `calls` resolutions produced by add_behavior (vs registry-dispatch,
# which add_dispatch produces whole & fresh — those must NOT be spliced from old).
_BEHAVIOR_CALL_RES = frozenset({"module", "self", "imported", "deep"})
# Node-extras keys owned by the two jedi-sensitive passes (spliced for unaffected).
_BEHAVIORAL_EXTRAS = ("calls", "control", "complexity", "attr_access")
# Old edge types whose target landing in a changed/removed module makes the source
# module stale (it must re-resolve). Only the spliced passes matter here.
_DEP_EDGE_TYPES = frozenset({"calls", "accesses"})

# Above this fraction of modules affected, a full rebuild is cheaper (and trivially
# correct) — no point splicing most of the graph.
_FULL_FALLBACK_FRACTION = 0.5


def _path_to_module(rel_path: str, target_pkg: str) -> str | None:
    """Map a scope file path to a package module id, or None if it's not package code.

    ``bquant/analysis/pipeline.py`` → ``bquant.analysis.pipeline``;
    ``bquant/analysis/__init__.py`` → ``bquant.analysis``; ``bquant/__init__.py`` →
    ``bquant``. Non-``.py`` files and files outside the package return None (they
    don't produce module nodes in a single-package extract).
    """
    p = rel_path.replace("\\", "/")
    if not p.endswith(".py"):
        return None
    parts = p.split("/")
    if not parts or parts[0] != target_pkg:
        return None
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]  # strip .py
    return ".".join(parts)


def _module_indexer(module_ids):
    """Return ``module_of(node_id)`` — the longest module id that owns the node."""
    ordered = sorted(module_ids, key=len, reverse=True)

    def module_of(node_id: str) -> str | None:
        for m in ordered:
            if node_id == m or node_id.startswith(m + "."):
                return m
        return None

    return module_of


def _affected_modules(old_graph, new_graph, base_mods, changed_removed, module_of):
    """Modules whose jedi passes must re-run (see module docstring for the rules)."""
    affected = set(base_mods)
    # rule (a): a module that freshly imports a changed/added module.
    for e in new_graph.edges:
        if e.type == "imports" and e.target in base_mods:
            affected.add(e.source)
    # rule (b): a module whose old behavioral edge targeted a changed/removed module.
    for e in old_graph.edges:
        if e.type in _DEP_EDGE_TYPES:
            tgt_mod = module_of(e.target)
            if tgt_mod in changed_removed:
                src_mod = module_of(e.source)
                if src_mod is not None:
                    affected.add(src_mod)
    return affected


def _splice_unaffected(new_graph, old_graph, unaffected, module_of) -> None:
    """Copy the two jedi passes' output for unaffected modules from the old graph."""
    for e in old_graph.edges:
        keep = False
        if e.type == "calls" and e.extras.get("resolution") in _BEHAVIOR_CALL_RES:
            keep = module_of(e.source) in unaffected
        elif e.type == "accesses":
            keep = module_of(e.source) in unaffected
        if keep:
            new_graph.add_edge(copy.deepcopy(e))
    for nid, node in new_graph.nodes.items():
        if module_of(nid) in unaffected and nid in old_graph.nodes:
            old_extras = old_graph.nodes[nid].extras
            for k in _BEHAVIORAL_EXTRAS:
                if k in old_extras:
                    node.extras[k] = copy.deepcopy(old_extras[k])


def update_graph(old_graph: Graph, package_path, old_scope: dict, new_scope: dict,
                 *, deep: bool = False) -> tuple[Graph, dict]:
    """Incrementally rebuild ``old_graph`` for the current source tree.

    Returns ``(graph, info)`` where ``info`` records the decision (``mode``:
    ``unchanged`` | ``incremental`` | ``full`` and the affected module list). The
    result is byte-identical to ``extract(package_path, deep=deep)`` — the cheap
    layers are rebuilt whole and the expensive jedi passes are recomputed for the
    affected modules and spliced from the old graph for the rest.
    """
    target_pkg = old_graph.target
    d = diff_scopes(old_scope, new_scope)
    changed = {m for p in d["changed"] if (m := _path_to_module(p, target_pkg))}
    added = {m for p in d["added"] if (m := _path_to_module(p, target_pkg))}
    removed = {m for p in d["removed"] if (m := _path_to_module(p, target_pkg))}

    # No package .py file changed → a single-package graph is unaffected (doc/consumer
    # edits don't touch it). Return the old graph untouched.
    if not (changed or added or removed):
        return old_graph, {"mode": "unchanged", "affected": []}

    graph, root, module_name, search_path = build_structural(package_path)
    module_ids = {n.id for n in graph.nodes.values() if n.kind == "module"}
    module_of = _module_indexer(module_ids)

    base_mods = (changed | added | removed) & module_ids
    changed_removed = (changed | removed)
    affected = _affected_modules(old_graph, graph, base_mods, changed_removed,
                                 module_of) & module_ids

    if not module_ids or len(affected) >= _FULL_FALLBACK_FRACTION * len(module_ids):
        add_behavioral_layer(graph, root, module_name, search_path, deep=deep)
        return graph, {"mode": "full", "affected": sorted(affected)}

    add_behavioral_layer(graph, root, module_name, search_path, deep=deep,
                         behavior_only=affected, attr_only=affected)
    unaffected = module_ids - affected
    _splice_unaffected(graph, old_graph, unaffected, module_of)
    return graph, {"mode": "incremental", "affected": sorted(affected)}
