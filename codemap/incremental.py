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

**That bar is reachable on the fast tier only** — and saying it without a tier was
wrong twice over (R1-C43). Two full *deep* builds of an unchanged tree are not
byte-identical to each other (R1-C42), so there is no fixed artifact to be identical
*to*. Worse, measurement found a divergence this path introduces on its own:

- The splice **freezes a sample.** An edge jedi missed in the old build is copied
  forward verbatim; measured 0 recoveries in 5 incremental builds against 5 in 5 full
  builds of the same tree. "Build it again and see" — the standard answer to tier
  noise — does not work here.
- The splice **blinds the invalidation that would undo it.** ``_affected_modules``
  rule (b) below reads the *old* graph, so a missing edge is a missing reason to
  recompute: editing the module that owns the target left the writer unaffected when
  the edge was absent, and affected when it was present. Same edit, same tree.

The `unresolved` set cannot be indexed by the changed module — not knowing where an
edge went is what `unresolved` *means* — so this is structural for a cache keyed on
its own incomplete answer, not an oversight. What we do about it today is declare it:
``provenance.incremental`` marks such a graph and the diagnostic says what follows.

Measurement: ``gaps/incremental_noise_persistence_2026-09-02.md``.
"""

from __future__ import annotations

import copy
from pathlib import Path

from codemap.extract.griffe_extractor import (
    add_behavioral_layer, build_structural, extract,
)
from codemap.model import Graph
from codemap.provenance import build_provenance, tool_identity
from codemap.scope import diff_scopes

# Behavioral `calls` resolutions produced by add_behavior (vs registry-dispatch,
# which add_dispatch produces whole & fresh — those must NOT be spliced from old).
_BEHAVIOR_CALL_RES = frozenset({"module", "self", "imported", "deep"})
# R1-C22: `references` resolutions the behavioral pass owns (a name used as a value, or
# as a type annotation). The consumer/doc references carry other resolutions and belong
# to the repo-scope pass, which the incremental path does not touch.
_BEHAVIOR_REF_RES = frozenset({"name", "annotation"})
# Node-extras keys owned by the two jedi-sensitive passes (spliced for unaffected).
_BEHAVIORAL_EXTRAS = ("calls", "control", "complexity", "attr_access")
# Old edge types whose target landing in a changed/removed module makes the source
# module stale (it must re-resolve). Only the spliced passes matter here.
_DEP_EDGE_TYPES = frozenset({"calls", "accesses", "references"})

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
    # R1-C43, the limit stated where it lives: this reads the OLD graph, so on the deep
    # tier it is only as complete as that build's jedi sample. An edge the old build
    # missed is a dependency this rule cannot see — measured: with the edge present the
    # writer was invalidated, with the same edge missing it was not, on the same edit.
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
        elif e.type == "references" and e.extras.get("resolution") in _BEHAVIOR_REF_RES:
            keep = module_of(e.source) in unaffected  # R1-C22: name/annotation refs
        if keep:
            new_graph.add_edge(copy.deepcopy(e))
    for nid, node in new_graph.nodes.items():
        if module_of(nid) in unaffected and nid in old_graph.nodes:
            old_extras = old_graph.nodes[nid].extras
            for k in _BEHAVIORAL_EXTRAS:
                if k in old_extras:
                    node.extras[k] = copy.deepcopy(old_extras[k])


def _same_builder(provenance: dict, tier: str) -> bool:
    """Was the old graph produced by *this* codemap, on this tier? (R1-C25)

    A graph with no provenance (pre-0.12) cannot answer, so it is treated as a
    different builder — the conservative direction: a needless full rebuild costs a
    minute, a silently stale graph costs a wrong answer.
    """
    if not provenance:
        return False
    return (provenance.get("tool") == tool_identity()
            and provenance.get("tier") == tier)


def update_graph(old_graph: Graph, package_path, old_scope: dict, new_scope: dict,
                 *, deep: bool = False) -> tuple[Graph, dict]:
    """Incrementally rebuild ``old_graph`` for the current source tree.

    Returns ``(graph, info)`` where ``info`` records the decision (``mode``:
    ``unchanged`` | ``incremental`` | ``full`` and the affected module list). The cheap
    layers are rebuilt whole; the expensive jedi passes are recomputed for the affected
    modules and spliced from the old graph for the rest.

    On the **fast** tier the result is byte-identical to ``extract(package_path,
    deep=deep)``. On the **deep** tier it is not, and not only because the target moves
    (R1-C42): the spliced regions carry the *previous* build's sample, and the splice
    is self-perpetuating — see the module docstring (R1-C43). Such a graph is stamped
    ``provenance.incremental: true``.
    """
    target_pkg = old_graph.target
    tier = "deep" if deep else "fast"
    # R1-C25: the input is not the only thing that can change. `unchanged` below decides
    # from the source tree alone, so an upgraded codemap over an untouched tree used to
    # return yesterday's graph built by yesterday's extractor — the exact confusion the
    # provenance block exists to name. A different tool or tier is a full rebuild.
    if not _same_builder(old_graph.provenance, tier):
        graph = extract(package_path, deep=deep)
        return graph, {"mode": "full", "affected": [], "reason": "builder-changed"}

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
        graph.provenance = build_provenance(tier=tier, inputs=graph.provenance.get("inputs"))
        return graph, {"mode": "full", "affected": sorted(affected)}

    add_behavioral_layer(graph, root, module_name, search_path, deep=deep,
                         behavior_only=affected, attr_only=affected)
    unaffected = module_ids - affected
    _splice_unaffected(graph, old_graph, unaffected, module_of)
    graph.provenance = build_provenance(tier=tier, inputs=graph.provenance.get("inputs"),
                                        incremental=True)
    return graph, {"mode": "incremental", "affected": sorted(affected)}
