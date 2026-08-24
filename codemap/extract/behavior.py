"""Behavioral pass — best-effort call-graph + control skeleton (DESIGN §7, M4/M5).

griffe gives the API surface but not the call sites; this second pass parses the
same source files with the stdlib ``ast`` and adds a *bounded* behavioral layer:

- `calls` edges (caller function → internal callee), each labeled by how it was
  resolved (``extras.resolution``);
- per-function ``extras.calls`` coverage counts (out / resolved / external /
  unresolved / dynamic) so the graph reports its own honesty;
- per-function ``extras.control`` skeleton (branches / loops / try / generator /
  async) — structure, not semantics.

**Two tiers** (see gaps/ call_resolution_spike_2026-07-26 for the measurement):

- **fast** (default): stdlib ``ast`` name resolution — module / self / imported.
  Sub-second, zero heavy deps, deterministic. Leaves local-variable calls
  (``result.data``, ``fig.write_html``) ``unresolved`` on purpose — resolving them
  needs type inference. ~19% of call-sites on bquant.
- **deep** (``deep=True``, jedi): local-variable type inference cracks the tail
  ``self.*`` → ~99%, ``x.foo()`` on locals → new edges. ~28% on bquant; ~1 min
  build. Python's dynamism caps even this — the remainder is genuinely undecidable.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

from codemap.extract.gsource import module_file, module_imports
from codemap.model import Edge

_BUILTINS = set(vars(__import__("builtins")))
_SKIP_RECEIVERS = {"self", "cls", "super"}

# Halstead operators are the AST operator-symbol node families (radon's scheme):
# arithmetic/bitwise ``ast.operator``, unary ``ast.unaryop``, boolean ``ast.boolop``,
# comparison ``ast.cmpop``. Operands are names and literal constants.
_OPERATOR_NODES = (ast.operator, ast.unaryop, ast.boolop, ast.cmpop)


def add_behavior(graph, griffe_root, target_pkg: str, *, deep: bool = False,
                 search_path=None, only=None) -> None:
    """Augment ``graph`` (built by the griffe pass) with the behavioral layer.

    ``deep=True`` swaps the ast name-resolver for jedi type inference on calls
    (``search_path`` is the dir containing the package, used as the jedi project).
    ``only`` (a set of module paths) restricts the pass to those modules — the
    incremental hook (R1-C9): the caller reuses the old graph's edges/extras for the
    modules left out. When ``None`` (default) every module is processed.
    """
    modules = _index_modules(griffe_root)
    known_modules = set(modules)  # R1-C21: flat-layout sibling lookup
    project = _jedi_project(search_path) if deep else None
    for modpath in sorted(modules):
        if only is not None and modpath not in only:
            continue
        mod = modules[modpath]
        fp = module_file(mod)  # None for a namespace dir (R1-C21)
        if fp is None:
            continue
        try:
            source = fp.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue
        imports = module_imports(mod, modpath, known_modules)  # R1-C21: flat-aware
        modmembers = set(mod.members.keys())
        script = _jedi_script(source, fp, project) if deep else None
        nested: dict[tuple[str, str], dict] = {}
        for fnode, class_stack, scope in _named_functions_scoped(tree):
            node_id = _node_id(modpath, class_stack, fnode.name)
            if node_id not in graph.nodes:
                # R1-C22 D3: a closure / dynamically-built class body is not a definition
                # node, but the calls inside it are real. Attribute them to the innermost
                # definition that *does* exist instead of discarding them.
                owner = _nearest_owner(graph, modpath, scope)
                if owner is not None:
                    _collect_nested_calls(graph, owner, fnode, modpath, imports,
                                          modmembers, script, target_pkg, nested)
                continue
            members = _class_members(mod, class_stack, modules) if class_stack else {}
            class_prefix = ".".join([modpath, *class_stack]) if class_stack else ""
            if script is not None:
                def resolve(call, _s=script):
                    return _resolve_jedi(call, _s, target_pkg)
            else:
                def resolve(call, _cp=class_prefix, _im=imports, _mm=modmembers, _me=members):
                    return _resolve(call, modpath, _cp, _im, _mm, _me)
            _process_function(graph, node_id, fnode, resolve)
            # R1-C22 D1: functions/classes named as *values* here (dispatch tables,
            # `default=` callbacks) — a use the call layer cannot see.
            _emit_name_references(graph, node_id, fnode, modpath, imports, modmembers,
                                  decorators_of=fnode)
        # R1-C22 D2: module-level statements are a scope of their own, never walked
        # above — import-time calls and dispatch tables live here.
        if script is not None:
            def mod_resolve(call, _s=script):
                return _resolve_jedi(call, _s, target_pkg)
        else:
            def mod_resolve(call, _im=imports, _mm=modmembers):
                return _resolve(call, modpath, "", _im, _mm, {})
        _process_module_level(graph, modpath, tree, mod_resolve, imports, modmembers)
        _emit_nested_calls(graph, nested)


# -- jedi (deep tier) --------------------------------------------------------

def _jedi_project(search_path):
    import jedi
    return jedi.Project(str(search_path)) if search_path else None


def _jedi_script(source, path, project):
    import jedi
    return jedi.Script(code=source, path=str(path), project=project)


def _callee_pos(func):
    """(line, column) of the callee name for jedi.goto (jedi cols are 0-based+1)."""
    if isinstance(func, ast.Name):
        return func.lineno, func.col_offset + 1
    if isinstance(func, ast.Attribute):
        return func.end_lineno, func.end_col_offset  # last char of the attr name
    return None


def _resolve_jedi(call, script, target_pkg):
    """Resolve a call-site to a definition via jedi type inference.

    Returns (target_id, resolution). ``deep`` = internal hit; ``external`` =
    resolved outside the package; ``unresolved`` = jedi found nothing.
    """
    pos = _callee_pos(call.func)
    if pos is None:
        return "", "unresolved"
    try:
        defs = script.goto(pos[0], pos[1], follow_imports=True, follow_builtin_imports=False)
    except Exception:
        return "", "unresolved"
    if not defs:
        return "", "unresolved"
    internal = sorted(
        d.full_name for d in defs
        if d.full_name and (d.full_name == target_pkg or d.full_name.startswith(target_pkg + "."))
    )
    if internal:
        return internal[0], "deep"
    return "", "external"


# -- griffe context ----------------------------------------------------------

def _index_modules(root) -> dict:
    out: dict = {}

    def walk(o):
        if o.kind.value == "module":
            out[o.canonical_path] = o
        for m in o.members.values():
            if not m.is_alias and m.kind.value in ("module", "class"):
                walk(m)

    walk(root)
    return out


def _class_members(mod, class_stack, modules) -> dict:
    """Map ``member_name -> owning-class canonical id`` for the enclosing class.

    Includes members inherited from internal base classes, each keyed to the base
    class that actually defines it — so ``self.<inherited>()`` resolves to the base
    method's real id, not a phantom ``ThisClass.<inherited>`` that is not a node
    (fast-tier soundness, R1-C13-f1). Own members win over inherited (override).
    """
    obj = mod
    for cname in class_stack:
        obj = obj.members.get(cname)
        if obj is None:
            return {}
    owners = {name: obj.canonical_path for name in obj.members}
    for base in getattr(obj, "bases", None) or []:
        bpath = getattr(base, "canonical_path", None) or ""
        if bpath.startswith(f"{mod.canonical_path.split('.')[0]}."):
            *modparts, cname = bpath.split(".")
            bmod = modules.get(".".join(modparts))
            if bmod and cname in bmod.members:
                bclass = bmod.members[cname]
                for name in bclass.members:
                    owners.setdefault(name, bclass.canonical_path)  # own already set → keep
    return owners


# -- ast scope walking -------------------------------------------------------

def _named_functions(tree):
    """Yield (FunctionDef, [class names]) for functions reachable as definitions.

    Tracks the class nesting so we can rebuild canonical ids. Functions nested
    inside other functions are still yielded but filtered out by the caller
    (their id won't match a graph node).
    """
    results = []

    def visit(node, class_stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, class_stack + [child.name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                results.append((child, list(class_stack)))
                visit(child, class_stack)  # descend for nested classes/defs
            else:
                visit(child, class_stack)

    visit(tree, [])
    return results


def _node_id(modpath: str, class_stack: list[str], funcname: str) -> str:
    return ".".join([modpath, *class_stack, funcname])


def _own_calls(fnode):
    """Call nodes in a function's own body — not inside nested defs/classes."""
    return [n for n in _own_nodes(fnode) if isinstance(n, ast.Call)]


def _own_nodes(fnode):
    """Every AST node in a function's own body — not descending into nested defs/classes.

    Same scope boundary as ``_own_calls``: a nested/closure ``def`` (or a class body)
    is its own definition node with its own metrics, so we stop at it to avoid
    double-counting its complexity in the enclosing function.
    """
    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # belongs to the nested scope
            yield child
            yield from visit(child)

    yield from visit(fnode)


# -- per-function resolution + control ---------------------------------------

_EDGE_RESOLUTIONS = {"module", "self", "imported", "deep"}


def _process_function(graph, node_id, fnode, resolve) -> None:
    counts = {"out": 0, "resolved": 0, "external": 0, "unresolved": 0, "dynamic": 0}
    # F7: edges are deduped caller->callee, so aggregate the per-call-site argument
    # contract before emitting — a refactorer needs "how is it called", and the
    # collapse itself (2 sites -> 1 edge) must stay visible via `callsites`.
    by_target: dict[str, dict] = {}
    for call in _own_calls(fnode):
        counts["out"] += 1
        target, resolution = resolve(call)
        # Soundness (R1-C13-f1/f2): an internal call edge must point at a real
        # graph node. A resolver can name a non-node — a local variable jedi typed
        # to its own scope-path, or a nested/closure function that is not a
        # definition node — so downgrade any such target to unresolved rather than
        # emit an edge to nothing (which would poison callers/callees/impact).
        if resolution in _EDGE_RESOLUTIONS and target and target in graph.nodes:
            counts["resolved"] += 1
            agg = by_target.setdefault(target, {"resolution": resolution, "shapes": []})
            agg["shapes"].append(_arg_shape(call))
        elif resolution == "external":
            counts["external"] += 1
        elif resolution == "dynamic":
            counts["dynamic"] += 1
        else:
            counts["unresolved"] += 1

    for target in sorted(by_target):
        agg = by_target[target]
        extras = {"resolution": agg["resolution"], **_arg_contract(agg["shapes"])}
        graph.add_edge(Edge("calls", node_id, target, extras=extras))

    node = graph.nodes[node_id]
    node.extras["calls"] = counts
    node.extras["control"] = _control(fnode)
    node.extras["complexity"] = _complexity(fnode)


def _arg_shape(call) -> tuple:
    """(positional_count | None, sorted kwnames, splat?) for one call-site.

    ``None`` positional count / ``splat=True`` mean ``*args``/``**kwargs`` made the
    arity partly unknown — an honest signal for change-set reasoning.
    """
    splat = any(isinstance(a, ast.Starred) for a in call.args) \
        or any(kw.arg is None for kw in call.keywords)
    posargs = None if any(isinstance(a, ast.Starred) for a in call.args) else \
        sum(1 for a in call.args if not isinstance(a, ast.Starred))
    kwnames = sorted(kw.arg for kw in call.keywords if kw.arg is not None)
    return posargs, tuple(kwnames), splat


def _arg_contract(shapes: list[tuple]) -> dict:
    """Aggregate call-site shapes into an edge argument contract (F7)."""
    posargs = sorted({s[0] for s in shapes if s[0] is not None})
    kwnames = sorted({k for s in shapes for k in s[1]})
    splat = any(s[2] for s in shapes)
    contract: dict = {"callsites": len(shapes)}
    if posargs:
        contract["posargs"] = posargs
    if kwnames:
        contract["kwargs"] = kwnames
    if splat:
        contract["splat"] = True
    return contract


def _resolve(call, modpath, class_prefix, imports, modmembers, members):
    """Return (target_id, resolution). Only module/self/imported become edges."""
    pkg = modpath.split(".")[0] + "."
    f = call.func
    if isinstance(f, ast.Name):
        name = f.id
        if name in imports:
            tgt = imports[name]
            if tgt.startswith(pkg):
                return tgt, "imported"
            return tgt, "external"
        if name in modmembers:
            return f"{modpath}.{name}", "module"
        if name in _BUILTINS:
            return name, "external"
        return name, "unresolved"
    if isinstance(f, ast.Attribute):
        attr = f.attr
        recv = f.value
        if isinstance(recv, ast.Name):
            if recv.id in _SKIP_RECEIVERS and attr in members and class_prefix:
                # method call on self — resolve to the class that actually defines
                # the member (own or a base), never a phantom same-class id.
                return f"{members[attr]}.{attr}", "self"
            if recv.id in imports:
                tgt = imports[recv.id]
                if tgt.startswith(pkg):
                    return f"{tgt}.{attr}", "imported"
                return f"{tgt}.{attr}", "external"
            if recv.id in modmembers:
                return f"{modpath}.{recv.id}.{attr}", "module"
        # X.method('literal', ...) — dynamic string-keyed dispatch (registry/dict)
        if call.args and isinstance(call.args[0], ast.Constant) \
                and isinstance(call.args[0].value, str) and attr in ("create", "get", "register"):
            return "", "dynamic"
        return "", "unresolved"
    return "", "unresolved"


def _control(fnode) -> dict:
    """Coarse control-flow skeleton of a function body (structure, not meaning)."""
    branches = loops = 0
    has_try = has_yield = False
    for node in ast.walk(fnode):
        if isinstance(node, ast.If):
            branches += 1
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            loops += 1
        elif isinstance(node, ast.Try):
            has_try = True
        elif isinstance(node, (ast.Yield, ast.YieldFrom)):
            has_yield = True
    out = {"branches": branches, "loops": loops}
    if has_try:
        out["try"] = True
    if has_yield:
        out["generator"] = True
    if isinstance(fnode, ast.AsyncFunctionDef):
        out["async"] = True
    return out


# -- complexity metrics (R1-C4) ----------------------------------------------
#
# Source-only, deterministic, stdlib-only — computed in the same AST pass as the
# control skeleton, over the function's *own* body (nested defs are separate nodes
# with their own metrics). All numbers are intrinsic to the code, so they live on
# the node in extras and need no source at query time. codemap's value here is not
# the metrics themselves (radon has those) but combining them with the graph's
# structural signals (coupling, fan-in/out) — see Query.hotspots.

def _cyclomatic(fnode) -> int:
    """McCabe cyclomatic complexity = 1 + number of decision points.

    Decision points (radon-compatible): ``if``/``elif`` (each ``elif`` is a nested
    ``If``), ternary ``IfExp``, ``for``/``while``, each ``except`` handler, each
    boolean operand join (``a and b and c`` → +2), each comprehension clause and its
    filters, and each ``match`` case.
    """
    cc = 1
    for node in _own_nodes(fnode):
        if isinstance(node, (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While,
                             ast.ExceptHandler)):
            cc += 1
        elif isinstance(node, ast.BoolOp):
            cc += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            cc += 1 + len(node.ifs)
        elif isinstance(node, ast.match_case):
            cc += 1
    return cc


def _halstead_volume(fnode) -> float:
    """Halstead volume ``N * log2(η)`` over operator-symbol nodes + names/constants.

    η = distinct operators + distinct operands; N = their total counts. A body with
    no operators/operands (e.g. ``return``-only) has volume 0.
    """
    op_kinds: set[str] = set()
    operands: set[str] = set()
    n_ops = n_operands = 0
    for node in _own_nodes(fnode):
        if isinstance(node, _OPERATOR_NODES):
            op_kinds.add(type(node).__name__)
            n_ops += 1
        elif isinstance(node, ast.Name):
            operands.add(node.id)
            n_operands += 1
        elif isinstance(node, ast.Constant):
            operands.add(f"{type(node.value).__name__}:{node.value!r}")
            n_operands += 1
    vocab = len(op_kinds) + len(operands)
    length = n_ops + n_operands
    if vocab == 0 or length == 0:
        return 0.0
    return round(length * math.log2(vocab), 2)


def _maintainability(cc: int, volume: float, sloc: int) -> float:
    """Maintainability Index, radon-normalized to 0–100 (higher = more maintainable).

    ``171 − 5.2·ln(V) − 0.23·CC − 16.2·ln(SLOC)`` rescaled to [0, 100]. The comment
    term is omitted (we score per symbol, not per file). ``ln`` inputs are floored at
    1 so a trivial one-liner scores ~100 instead of blowing up.
    """
    ln_v = math.log(volume) if volume > 1 else 0.0
    ln_sloc = math.log(sloc) if sloc > 1 else 0.0
    raw = 171.0 - 5.2 * ln_v - 0.23 * cc - 16.2 * ln_sloc
    return round(max(0.0, raw * 100.0 / 171.0), 1)


def _complexity(fnode) -> dict:
    """Per-function complexity: cyclomatic, Halstead volume, MI, and physical SLOC."""
    cc = _cyclomatic(fnode)
    volume = _halstead_volume(fnode)
    end = getattr(fnode, "end_lineno", None)
    start = getattr(fnode, "lineno", None)
    sloc = (end - start + 1) if (end and start) else 1
    return {"cc": cc, "volume": volume, "sloc": sloc,
            "mi": _maintainability(cc, volume, sloc)}


def _own_name_loads(scope, *, decorators_of=None):
    """Bare ``Name`` loads in a scope's own body that **use a symbol**, not call it.

    Yields ``(node, kind)`` where kind is ``"name"`` (the value form — a dict entry, a
    list element, a ``default=`` callback, an assignment RHS) or ``"annotation"`` (the
    symbol names a *type*). Both are real references and both were missing from the graph,
    but they mean different things — a dispatch table implies runtime liveness, an
    annotation implies a contract — so R1-C22 labels them apart rather than blurring them.

    Excludes the callee position (that is a `calls` edge) and the scope's own decorator
    list (that is `decorated_by`).
    """
    nodes = list(_own_nodes(scope)) if not isinstance(scope, ast.Module) \
        else list(_module_level_nodes(scope))
    skip = {id(n.func) for n in nodes if isinstance(n, ast.Call)}
    for deco in (decorators_of.decorator_list if decorators_of is not None else []):
        skip |= {id(n) for n in ast.walk(deco)}
    annotated: set[int] = set()
    for n in nodes + ([decorators_of] if decorators_of is not None else []):
        for ann in _annotation_nodes(n):
            annotated |= {id(x) for x in ast.walk(ann)}
    return [(n, "annotation" if id(n) in annotated else "name")
            for n in nodes
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and id(n) not in skip]


def _annotation_nodes(node):
    """The annotation sub-trees hanging off one AST node (params, return, AnnAssign)."""
    if isinstance(node, ast.AnnAssign) and node.annotation is not None:
        yield node.annotation
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.returns is not None:
            yield node.returns
        args = node.args
        for a in [*args.posonlyargs, *args.args, *args.kwonlyargs,
                  args.vararg, args.kwarg]:
            if a is not None and a.annotation is not None:
                yield a.annotation


def _module_level_nodes(tree):
    """Every node in module-level code — not descending into any def/class body.

    `add_behavior` walks named functions, so import-time statements were never visited:
    `_register_all_indicators()` at the bottom of a module produced no edge, and the whole
    class of import-time behaviour (registration, availability probes, singletons) was
    invisible to the call graph (R1-C22).
    """
    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # its own definition node — walked separately
            yield child
            yield from visit(child)

    yield from visit(tree)


def _resolve_name(name, modpath, imports, modmembers):
    """(target_id, resolution) for a bare name used as a value — the `_resolve` rules for
    ``ast.Name`` minus the call. Only module/imported become edges."""
    pkg = modpath.split(".")[0] + "."
    if name in imports:
        tgt = imports[name]
        return (tgt, "imported") if tgt.startswith(pkg) else (tgt, "external")
    if name in modmembers:
        return f"{modpath}.{name}", "module"
    return None, "unresolved"


def _emit_name_references(graph, src_id, scope, modpath, imports, modmembers,
                          *, decorators_of=None) -> None:
    """`references` edges for functions/classes named as values (R1-C22 D1).

    No new edge type: `references` is already "dispatch site → the symbol it names".
    Labelled ``resolution="name"`` so an intra-core name-load stays distinguishable from
    the consumer/doc references, and deduped per target with a site count.
    """
    counts: dict[tuple[str, str], int] = {}
    for node, kind in _own_name_loads(scope, decorators_of=decorators_of):
        target, resolution = _resolve_name(node.id, modpath, imports, modmembers)
        if resolution not in ("module", "imported") or not target:
            continue
        tgt_node = graph.nodes.get(target)
        if tgt_node is None or tgt_node.kind not in ("function", "class"):
            continue  # a value, not a callable definition — nothing to reference
        if target == src_id:
            continue  # self-reference (recursion by name) says nothing about liveness
        counts[(target, kind)] = counts.get((target, kind), 0) + 1
    for target, kind in sorted(counts):
        graph.add_edge(Edge("references", src_id, target,
                            extras={"resolution": kind, "sites": counts[(target, kind)]}))


def _process_module_level(graph, modpath, tree, resolve, imports, modmembers) -> None:
    """Calls and value-references in module-level code, sourced from the module (D1/D2)."""
    by_target: dict[str, dict] = {}
    for call in (n for n in _module_level_nodes(tree) if isinstance(n, ast.Call)):
        target, resolution = resolve(call)
        if resolution in _EDGE_RESOLUTIONS and target and target in graph.nodes:
            agg = by_target.setdefault(target, {"resolution": resolution, "shapes": []})
            agg["shapes"].append(_arg_shape(call))
    for target in sorted(by_target):
        agg = by_target[target]
        graph.add_edge(Edge("calls", modpath, target,
                            extras={"resolution": agg["resolution"],
                                    **_arg_contract(agg["shapes"])}))
    _emit_name_references(graph, modpath, tree, modpath, imports, modmembers)


def _named_functions_scoped(tree):
    """Like :func:`_named_functions`, plus the **full** enclosing scope names.

    ``_named_functions`` tracks only class nesting, which is all a definition id needs.
    R1-C22 D3 also has to answer "which definition *contains* this code" for a function
    that is not a definition node itself (a closure, or a method of a dynamically-built
    class), so the whole def/class chain is carried here. Kept as a separate generator
    because `dataflow`/`dispatch`/`attrflow` unpack the two-tuple.
    """
    results = []

    def visit(node, class_stack, scope):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, class_stack + [child.name], scope + [child.name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                results.append((child, list(class_stack), list(scope)))
                visit(child, class_stack, scope + [child.name])
            else:
                visit(child, class_stack, scope)

    visit(tree, [], [])
    return results


def _nearest_owner(graph, modpath, scope) -> str | None:
    """The innermost enclosing definition of ``scope`` that is a real graph node.

    A call inside a closure is a real call; only the *node it is attributed to* is an
    approximation, so the edge carries ``extras.via="nested"`` (R1-C13 discipline).
    """
    for cut in range(len(scope), 0, -1):
        candidate = ".".join([modpath, *scope[:cut]])
        if candidate in graph.nodes:
            return candidate
    return modpath if modpath in graph.nodes else None


def _collect_nested_calls(graph, owner, fnode, modpath, imports, modmembers,
                          script, target_pkg, out) -> None:
    """Resolve a non-node function's own calls and stage them under ``owner`` (D3)."""
    for call in _own_calls(fnode):
        if script is not None:
            target, resolution = _resolve_jedi(call, script, target_pkg)
        else:
            target, resolution = _resolve(call, modpath, "", imports, modmembers, {})
        if resolution not in _EDGE_RESOLUTIONS or not target or target not in graph.nodes:
            continue
        if target == owner:
            continue  # a closure calling its own enclosing function — recursion, not a dep
        agg = out.setdefault((owner, target), {"resolution": resolution, "shapes": []})
        agg["shapes"].append(_arg_shape(call))


def _emit_nested_calls(graph, nested) -> None:
    """Emit staged nested calls, skipping pairs the owner already calls directly (D3).

    A duplicate ``owner → target`` edge would double-count in every degree/hub metric, so
    an existing direct call wins: the relationship is already recorded, and this would add
    only a weaker-provenance copy of it.
    """
    if not nested:
        return
    existing = {(e.source, e.target) for e in graph.edges if e.type == "calls"}
    for (owner, target) in sorted(nested):
        if (owner, target) in existing:
            continue
        agg = nested[(owner, target)]
        graph.add_edge(Edge("calls", owner, target,
                            extras={"resolution": agg["resolution"], "via": "nested",
                                    **_arg_contract(agg["shapes"])}))
