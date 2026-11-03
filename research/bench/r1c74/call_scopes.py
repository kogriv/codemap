"""Every ast.Call in a package, by the scope that runs it. Independent of codemap.

Usage: python3 -I call_scopes.py <package dir> [--per-node]   (prints JSON)

Scopes, matching how codemap attributes code:
- function   : the own body of a definition node, meaning a module-level function or a method of a
               (nested) module-level class. Its decorators, defaults and annotations are included, since
               they are children of the def node, as in codemap's `_own_nodes`. When one name is
               defined twice at one level, the last definition is the node (R1-C46).
- shadowed   : every call in a definition replaced by a later one of the same name, by R1-C46's documented
               rule: only a *direct* statement of a module, class or function body shadows (a definition under
               if/try/with neither shadows nor is shadowed), and a legitimate rebinding is not shadowing (the
               later one decorated `.setter`/`.getter`/`.deleter`/`.register` or named `_`, or the earlier one
               `@overload`). Two bodies that both stand (conditional, or legitimate) belong to one node, and
               their calls add up.
  (Revised after the first acceptance run: the pre-registered version used "the last definition wins,
  through if/try", which is not codemap's documented rule. See the design's reconciliation.)
- nested     : every call inside a def, lambda-free class or def nested in a function node.
- class_body : calls in a class body outside its methods, plus its bases, keywords and decorators.
- module     : module-level statements outside any def or class.
The five sum to every ast.Call in the source; the script asserts it.
"""
import ast
import json
import pathlib
import sys

DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)


def own_calls(node):
    """Calls among the descendants of `node`, not entering nested defs or classes."""
    n = 0
    for c in ast.iter_child_nodes(node):
        if isinstance(c, DEFS + (ast.ClassDef,)):
            continue
        n += isinstance(c, ast.Call) + own_calls(c)
    return n


def every_call(node):
    return sum(isinstance(x, ast.Call) for x in ast.walk(node))


def nested_defs(node):
    """Defs and classes nested anywhere inside `node`'s own code (not inside each other)."""
    for c in ast.iter_child_nodes(node):
        if isinstance(c, DEFS + (ast.ClassDef,)):
            yield c
        else:
            yield from nested_defs(c)


def level(stmts):
    """Definitions at one level, through if/try branches, in order; plus the other statements."""
    defs, other = [], []

    def walk(body):
        for s in body:
            if isinstance(s, DEFS + (ast.ClassDef,)):
                defs.append(s)
            elif isinstance(s, (ast.If, ast.Try)):
                other.append(("head", s))
                for fld in ("body", "orelse", "finalbody"):
                    walk(getattr(s, fld, None) or [])
                for h in getattr(s, "handlers", None) or []:
                    other.append(("handler", h))
                    walk(h.body)
            else:
                other.append(("stmt", s))
    walk(stmts)
    return defs, other


def head_calls(kind, node):
    """Calls in an if-test / except-type: the parts of a compound statement that are not a block."""
    if kind == "stmt":
        return isinstance(node, ast.Call) + own_calls(node)
    if kind == "handler":
        return every_call(node.type) if node.type is not None else 0
    if isinstance(node, ast.If):
        return every_call(node.test)
    return 0


EXEMPT_EARLIER, EXEMPT_LATER = {"overload"}, {"setter", "getter", "deleter", "register"}


def tails(d):
    return [ast.unparse(x).split("(", 1)[0].rsplit(".", 1)[-1] for x in d.decorator_list]


def shadow_skip(tree):
    """R1-C46's documented rule, re-stated: direct statements of a module/def/class body only."""
    skip = set()

    def walk(node):
        if isinstance(node, (ast.Module,) + DEFS + (ast.ClassDef,)):
            last = {}
            for st in node.body:
                if not isinstance(st, DEFS + (ast.ClassDef,)):
                    continue
                prev = last.get(st.name)
                legit = prev is not None and (st.name == "_" or set(tails(prev)) & EXEMPT_EARLIER
                                              or set(tails(st)) & EXEMPT_LATER)
                if prev is not None and not legit:
                    skip.add(id(prev))
                last[st.name] = st
        for c in ast.iter_child_nodes(node):
            if id(c) not in skip:
                walk(c)
    walk(tree)
    return skip


def calls_excl(node, skip):
    """Every call under `node`, not entering skipped definitions."""
    n = 0
    for c in ast.iter_child_nodes(node):
        if id(c) in skip:
            continue
        n += isinstance(c, ast.Call) + calls_excl(c, skip)
    return n


def scan(path, module_id, tot, per_node):
    tree = ast.parse(path.read_text())
    skip = shadow_skip(tree)
    # shadowed: calls inside skipped subtrees, not counting a skipped subtree inside another twice
    seen = set()
    for node in ast.walk(tree):
        if id(node) in skip:
            seen.update(id(c) for c in ast.walk(node) if isinstance(c, ast.Call))
    tot["shadowed"] += len(seen)

    def define(stmts, prefix, scope_for_other):
        defs, other = level(stmts)
        for kind, node in other:
            tot[scope_for_other] += head_calls(kind, node)
        for d in defs:
            if id(d) in skip:
                continue
            nid = f"{prefix}.{d.name}"
            if isinstance(d, DEFS):
                k = own_calls(d)
                tot["function"] += k
                per_node[nid] = per_node.get(nid, 0) + k
                for inner in nested_defs(d):
                    if id(inner) not in skip:
                        tot["nested"] += isinstance(inner, ast.Call) + calls_excl(inner, skip)
            else:
                tot["class_body"] += sum(every_call(x) for x in d.bases + [kw.value for kw in d.keywords]
                                         + d.decorator_list)
                define(d.body, nid, "class_body")

    define(tree.body, module_id, "module")


def main():
    root = pathlib.Path(sys.argv[1])
    tot = dict.fromkeys(("function", "nested", "module", "class_body", "shadowed"), 0)
    per_node, total = {}, 0
    for f in sorted(root.rglob("*.py")):
        parts = list(f.relative_to(root.parent).with_suffix("").parts)
        scan(f, ".".join(parts[:-1] if parts[-1] == "__init__" else parts), tot, per_node)
        total += every_call(ast.parse(f.read_text()))
    tot["all_calls_in_source"] = total
    tot["sum_of_scopes"] = sum(tot[k] for k in ("function", "nested", "module", "class_body", "shadowed"))
    assert tot["sum_of_scopes"] == total, tot
    out = {"totals": tot}
    if "--per-node" in sys.argv:
        out["per_node"] = dict(sorted(per_node.items()))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
