"""Registry-aware call bridging — reconnect the dispatch seams (DESIGN §7, M7).

The behavioral pass (M4/M5) leaves calls that go through a factory/registry
*unresolved*: bquant wires plugins by string key, not import —
``self.swing_strategy = create_swing_strategy(name)`` then
``self.swing_strategy.calculate_global(data)``. So the call chain from
``analyze_zones`` dies exactly at the plugin seams — the swing/shape/… strategies
and the zone detector, which is *where the real work happens* (dogfood F5).

But codemap already holds the dispatch table: M1.5 recorded every
``@Registry.register('key')`` binding in ``extras.registry`` ({key → class}). This
pass uses it to bridge the seams with **candidate** edges — an honest
over-approximation ("dispatches to one of {zigzag, find_peaks, …}") flagged
``resolution="registry-candidate"``; a literal key resolves to a single class
(``resolution="registry"``). Concrete strategies do NOT inherit their Protocol,
so families are grouped by the *registrar*, not by inheritance.

Bridged forms:
- ``self.attr = create_X(...)`` in a class → ``self.attr.method(...)`` elsewhere in
  that class → edges to ``{impl}.method`` for every impl of family X;
- a direct factory/getter call → edges to the family's implementation classes
  (exact class when the key argument is a string literal).
"""

from __future__ import annotations

import ast

from codemap.extract.behavior import _index_modules, _named_functions, _node_id, _own_calls
from codemap.model import Edge

_DISPATCH_VERBS = ("get", "create", "make", "build", "new")


def add_dispatch(graph, griffe_root, target_pkg: str) -> None:
    """Bridge factory/registry dispatch seams using the M1.5 registry table."""
    families = _build_families(graph)
    if not families:
        return
    recognizer = _Recognizer(families)

    modules = _index_modules(griffe_root)
    edges: dict[tuple[str, str, str], str] = {}  # (src, tgt, kind) -> resolution (best)
    for modpath in sorted(modules):
        mod = modules[modpath]
        fp = getattr(mod, "filepath", None)
        if not fp:
            continue
        try:
            tree = ast.parse(open(fp, encoding="utf-8").read())
        except (OSError, SyntaxError):
            continue
        funcs = _named_functions(tree)
        # pass A: bind class attributes to families (self.attr = create_X(...)).
        attr_family: dict[str, dict[str, tuple]] = {}
        for fnode, class_stack in funcs:
            if not class_stack:
                continue
            class_id = ".".join([modpath, *class_stack])
            for attr, fam in _attr_bindings(fnode, recognizer):
                attr_family.setdefault(class_id, {})[attr] = fam
        # pass B: bridge dispatch call-sites to family members.
        for fnode, class_stack in funcs:
            node_id = _node_id(modpath, class_stack, fnode.name)
            if node_id not in graph.nodes:
                continue
            class_id = ".".join([modpath, *class_stack]) if class_stack else ""
            binds = attr_family.get(class_id, {})
            for call in _own_calls(fnode):
                for tgt, resolution in _bridge_call(call, recognizer, binds, families, graph):
                    key = (node_id, tgt, "calls")
                    # prefer the exact "registry" resolution over "registry-candidate".
                    if key not in edges or resolution == "registry":
                        edges[key] = resolution

    for (src, tgt, _kind), resolution in edges.items():
        graph.add_edge(Edge("calls", src, tgt, extras={"resolution": resolution}))


# -- family table (from extras.registry) -------------------------------------

def _build_families(graph) -> dict:
    """family_id (reg_class, token) -> {'members': {key: class_id}, 'token': str}."""
    families: dict = {}
    for node in graph.nodes.values():
        reg = node.extras.get("registry")
        if not reg:
            continue
        fid = _family_of(reg.get("decorator", ""))
        fam = families.setdefault(fid, {"members": {}, "token": fid[1]})
        fam["members"][reg.get("key")] = node.id
    return families


def _family_of(decorator_path: str) -> tuple[str, str]:
    """(registry_class, family_token) from a register decorator path.

    ``StrategyRegistry.register_swing_strategy`` -> ("StrategyRegistry", "swing")
    ``ZoneDetectionRegistry.register``           -> ("ZoneDetectionRegistry", "")
    """
    parts = decorator_path.split(".")
    reg_class = parts[-2] if len(parts) >= 2 else ""
    method = parts[-1]
    token = method
    for pre in ("register_", "register"):
        if token.startswith(pre):
            token = token[len(pre):]
            break
    token = token.replace("_strategy", "").replace("strategy", "").strip("_")
    return reg_class, token


class _Recognizer:
    """Decide which family (if any) a call-site dispatches."""

    def __init__(self, families: dict):
        self.by_regclass: dict[str, list] = {}
        self.token_families: list = []  # (token, fid)
        for fid in families:
            reg_class, token = fid
            self.by_regclass.setdefault(reg_class, []).append(fid)
            if token:
                self.token_families.append((token, fid))

    def family_of_call(self, call) -> tuple | None:
        f = call.func
        # <RegistryClass>.get_x(...) / .get(...) / .create(...)
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            recv, meth = f.value.id, f.attr
            if recv in self.by_regclass and _is_dispatch_verb(meth):
                for fid in self.by_regclass[recv]:
                    token = fid[1]
                    if token == "" or token in meth:
                        return fid
        # create_x(...) module factory — matched by family token in the name.
        name = f.id if isinstance(f, ast.Name) else None
        if name and _is_dispatch_verb(name):
            for token, fid in self.token_families:
                if token and token in name:
                    return fid
        return None


def _is_dispatch_verb(name: str) -> bool:
    return name.split("_", 1)[0] in _DISPATCH_VERBS


# -- ast bridging -------------------------------------------------------------

def _attr_bindings(fnode, recognizer):
    """Yield (attr, family) for ``self.attr = <dispatch call>`` in a method body."""
    for node in ast.walk(fnode):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        fam = recognizer.family_of_call(node.value)
        if fam is None:
            continue
        for tgt in node.targets:
            if isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name) \
                    and tgt.value.id == "self":
                yield tgt.attr, fam


def _bridge_call(call, recognizer, binds, families, graph):
    """Yield (target_id, resolution) candidate edges for one call-site."""
    f = call.func
    # self.attr.method(...) where self.attr is bound to a family -> impl.method
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Attribute) \
            and isinstance(f.value.value, ast.Name) and f.value.value.id == "self":
        fam = binds.get(f.value.attr)
        if fam is not None:
            method = f.attr
            for class_id in families[fam]["members"].values():
                target = f"{class_id}.{method}"
                if target in graph.nodes:
                    yield target, "registry-candidate"
            return

    # direct factory/getter call -> implementation class(es)
    fam = recognizer.family_of_call(call)
    if fam is not None:
        members = families[fam]["members"]
        key = _literal_key(call)
        if key is not None and key in members:
            yield members[key], "registry"  # exact — literal key
        else:
            for class_id in members.values():
                yield class_id, "registry-candidate"


def _literal_key(call):
    """First positional arg if it's a string literal, else None."""
    if call.args and isinstance(call.args[0], ast.Constant) \
            and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None
