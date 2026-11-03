# Diagnostic variant of predict_chain_calls.py used in the R1-C71 reconciliation: per node, external chain
# sites in the node's own body (not nested, not module level). Prints {node: count}.
"""Independent prediction for R1-C71, from Python semantics and the package's own source, not from codemap.

Usage: python3 -I predict_chain_calls.py <package dir>   (prints JSON)

A call site is in scope when its callee is an attribute chain rooted at a name bound by an import
(module level, or in an enclosing function), and either the chain has depth >= 2 (`a.b.f()`) or its root
is the package itself (`import pkg; pkg.f()`):
- internal root (the package, or anything inside it): the chain is followed through modules, definitions
  and re-exports (`from x import y [as z]` and `import a.b as c`, in any module, as codemap records them).
  If it lands on a function, class or method, the call edge (caller, callee) is predicted; otherwise the
  site counts as internal-unresolved.
- external root (depth >= 2): the site counts as external.

Callers are attributed as codemap attributes them: module-level functions and methods (of module-level and
nested classes) are nodes; a function nested in one is not, and its calls go to the nearest node owner;
module-level statements go to the module. Class-body statements outside methods are attributed to the
module here, an assumption to be reconciled.

Not modelled, as in codemap's fast tier: import order and shadowing.
"""
import ast
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
pkg = root.name
files = {}
for f in sorted(root.rglob("*.py")):
    p = list(f.relative_to(root.parent).with_suffix("").parts)
    files[".".join(p[:-1] if p[-1] == "__init__" else p)] = (f, p[-1] == "__init__")
mods = set(files)
trees = {m: ast.parse(f.read_text()) for m, (f, _) in files.items()}


def from_target(m, node):
    if node.level:
        parts = m.split(".") if files[m][1] else m.split(".")[:-1]
        anchor = parts[:len(parts) - (node.level - 1)]
        return ".".join(anchor + ([node.module] if node.module else []))
    return node.module or ""


def children(body):
    """Statements of a block, descending into if/try/with/for/while, not into defs."""
    for n in body:
        yield n
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for fld in ("body", "orelse", "finalbody"):
            yield from children(getattr(n, fld, None) or [])
        for h in getattr(n, "handlers", None) or []:
            yield from children(h.body)


# definitions and aliases
defs, alias = set(), {}
for m, tree in trees.items():
    def walk_defs(body, prefix):
        for n in children(body):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.add(f"{prefix}.{n.name}")
            elif isinstance(n, ast.ClassDef):
                defs.add(f"{prefix}.{n.name}")
                walk_defs(n.body, f"{prefix}.{n.name}")
    walk_defs(tree.body, m)
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            t = from_target(m, n)
            for a in n.names:
                if a.name != "*" and t:
                    alias.setdefault(f"{m}.{a.asname or a.name}", f"{t}.{a.name}")
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.asname:
                    alias.setdefault(f"{m}.{a.asname}", a.name)


def binds(m, body):
    out = {}
    for n in children(body):
        if isinstance(n, ast.Import):
            for a in n.names:
                out[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(n, ast.ImportFrom):
            t = from_target(m, n)
            for a in n.names:
                if a.name != "*" and t:
                    out[a.asname or a.name] = f"{t}.{a.name}"
    return out


def internal(t):
    return t == pkg or t.startswith(pkg + ".")


def land(path):
    seen = set()
    while path not in defs and path not in mods and path in alias and path not in seen:
        seen.add(path)
        path = alias[path]
    return path


def resolve_chain(target, parts):
    cur = land(target)
    for part in parts:
        cur = land(f"{cur}.{part}")
    return cur if cur in defs else None


own = {}
out = {"edges": set(), "internal_resolved_sites": 0, "internal_unresolved": 0, "external_sites": 0, "external_by_module": {}}


def scan(m, node, owner, env, nested=False):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scan(m, child, owner, {**env, **binds(m, child.body)}, True)   # nested: not a node
            continue
        if isinstance(child, ast.ClassDef):
            scan(m, child, owner, env, True)
            continue
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            chain, v = [child.func.attr], child.func.value
            while isinstance(v, ast.Attribute):
                chain.append(v.attr)
                v = v.value
            chain.reverse()
            if isinstance(v, ast.Name) and v.id in env:
                t = env[v.id]
                if internal(t) and (len(chain) >= 2 or t == pkg):
                    hit = resolve_chain(t, chain)
                    if hit:
                        out["edges"].add((owner, hit))
                        out["internal_resolved_sites"] += 1
                    else:
                        out["internal_unresolved"] += 1
                elif not internal(t) and len(chain) >= 2:
                    out["external_sites"] += 1
                    if not nested and owner != m:
                        own[owner] = own.get(owner, 0) + 1
                    out["external_by_module"][m] = out["external_by_module"].get(m, 0) + 1
        scan(m, child, owner, env, nested)


for m, tree in trees.items():
    modb = binds(m, tree.body)

    def walk_class(c, prefix):
        for s in c.body:
            if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
                scan(m, s, f"{prefix}.{s.name}", {**modb, **binds(m, s.body)})
            elif isinstance(s, ast.ClassDef):
                walk_class(s, f"{prefix}.{s.name}")
            else:
                scan(m, ast.Module(body=[s], type_ignores=[]), m, modb)

    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scan(m, n, f"{m}.{n.name}", {**modb, **binds(m, n.body)})
        elif isinstance(n, ast.ClassDef):
            walk_class(n, f"{m}.{n.name}")
        else:
            scan(m, ast.Module(body=[n], type_ignores=[]), m, modb)

out["edges"] = sorted(map(list, out["edges"]))
out["external_by_module"] = dict(sorted(out["external_by_module"].items()))
print(json.dumps(own, indent=1))
