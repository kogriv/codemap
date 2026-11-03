"""Every ast.Call in a package, by the scope that runs it. Independent of codemap.

Usage: python3 -I call_scopes.py <package dir> [--per-node]   (prints JSON)

Scopes, matching how codemap attributes code:
- function   : the own body of a definition node, meaning a module-level function or a method of a
               (nested) module-level class. Its decorators, defaults and annotations are included, since
               they are children of the def node, as in codemap's `_own_nodes`. When one name is
               defined twice at one level, the last definition is the node (R1-C46).
- shadowed   : every call in a definition replaced by a later one of the same name at the same level.
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


def scan(path, module_id, tot, per_node):
    tree = ast.parse(path.read_text())

    def define(stmts, prefix, scope_for_other):
        defs, other = level(stmts)
        for kind, node in other:
            tot[scope_for_other] += head_calls(kind, node)
        last = {}
        for d in defs:
            last[d.name] = d
        for d in defs:
            if last[d.name] is not d:
                tot["shadowed"] += every_call(d)
                continue
            nid = f"{prefix}.{d.name}"
            if isinstance(d, DEFS):
                k = own_calls(d)
                tot["function"] += k
                per_node[nid] = k
                for inner in nested_defs(d):
                    tot["nested"] += every_call(inner)
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
