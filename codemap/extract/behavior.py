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
from pathlib import Path

from codemap.model import Edge

_BUILTINS = set(vars(__import__("builtins")))
_SKIP_RECEIVERS = {"self", "cls", "super"}


def add_behavior(graph, griffe_root, target_pkg: str, *, deep: bool = False,
                 search_path=None) -> None:
    """Augment ``graph`` (built by the griffe pass) with the behavioral layer.

    ``deep=True`` swaps the ast name-resolver for jedi type inference on calls
    (``search_path`` is the dir containing the package, used as the jedi project).
    """
    modules = _index_modules(griffe_root)
    project = _jedi_project(search_path) if deep else None
    for modpath in sorted(modules):
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
            members = _class_scope(mod, class_stack, modules) if class_stack else set()
            class_prefix = ".".join([modpath, *class_stack]) if class_stack else ""
            if script is not None:
                def resolve(call, _s=script):
                    return _resolve_jedi(call, _s, target_pkg)
            else:
                def resolve(call, _cp=class_prefix, _im=imports, _mm=modmembers, _me=members):
                    return _resolve(call, modpath, _cp, _im, _mm, _me)
            _process_function(graph, node_id, fnode, resolve)


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


def _class_scope(mod, class_stack, modules) -> set:
    """Member names of the enclosing class, including internal base classes."""
    obj = mod
    for cname in class_stack:
        obj = obj.members.get(cname)
        if obj is None:
            return set()
    names = set(obj.members.keys())
    for base in getattr(obj, "bases", None) or []:
        bpath = getattr(base, "canonical_path", None) or ""
        if bpath.startswith(f"{mod.canonical_path.split('.')[0]}."):
            *modparts, cname = bpath.split(".")
            bmod = modules.get(".".join(modparts))
            if bmod and cname in bmod.members:
                names |= set(bmod.members[cname].members.keys())
    return names


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
    calls = []

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # belongs to the nested scope
            if isinstance(child, ast.Call):
                calls.append(child)
            visit(child)

    visit(fnode)
    return calls


# -- per-function resolution + control ---------------------------------------

_EDGE_RESOLUTIONS = {"module", "self", "imported", "deep"}


def _process_function(graph, node_id, fnode, resolve) -> None:
    counts = {"out": 0, "resolved": 0, "external": 0, "unresolved": 0, "dynamic": 0}
    seen_targets: set[str] = set()
    for call in _own_calls(fnode):
        counts["out"] += 1
        target, resolution = resolve(call)
        if resolution in _EDGE_RESOLUTIONS:
            counts["resolved"] += 1
            if target and target not in seen_targets:
                seen_targets.add(target)
                graph.add_edge(
                    Edge("calls", node_id, target, extras={"resolution": resolution})
                )
        elif resolution == "external":
            counts["external"] += 1
        elif resolution == "dynamic":
            counts["dynamic"] += 1
        else:
            counts["unresolved"] += 1

    node = graph.nodes[node_id]
    node.extras["calls"] = counts
    node.extras["control"] = _control(fnode)


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
                # method call on self — resolve within the enclosing class scope
                return f"{class_prefix}.{attr}", "self"
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
