"""R1-C72: twin bindings and the call sites that go through them, from the package source only.
A twin binding: a bare absolute import (`import X[.y]`, `from X[.y] import Z`) whose head X is not the package while
`<importer parent>.X` is a module of the package — the flat rule rewrites it into the package.
Sites: calls whose callee is rooted at a name bound that way (any depth), split into node-own bodies (counted in
extras.calls) and the rest (module level / nested: edges only)."""
import ast, json, sys, pathlib
root = pathlib.Path(sys.argv[1]); pkg = root.name
mods = {}
for f in sorted(root.rglob("*.py")):
    p = list(f.relative_to(root.parent).with_suffix("").parts); mods[".".join(p[:-1] if p[-1] == "__init__" else p)] = f
out = {"bindings": {}, "sites_counted": 0, "sites_uncounted": 0, "sites_by_module": {}}
for m, f in mods.items():
    t = ast.parse(f.read_text()); parent = m.rsplit(".", 1)[0] if "." in m else None
    bound = {}
    for n in ast.walk(t):
        if isinstance(n, ast.Import):
            for a in n.names:
                h = a.name.split(".")[0]
                if h != pkg and parent and f"{parent}.{h}" in mods: bound[a.asname or h] = f"{parent}.{h}"
        elif isinstance(n, ast.ImportFrom) and not n.level and n.module:
            h = n.module.split(".")[0]
            if h != pkg and parent and f"{parent}.{h}" in mods:
                for a in n.names:
                    if a.name != "*": bound[a.asname or a.name] = f"{parent}.{n.module}.{a.name}"
    if not bound: continue
    out["bindings"][m] = bound
    counted = set()
    for n in t.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)): counted.add(n)
        elif isinstance(n, ast.ClassDef):
            st = [n]
            while st:
                c = st.pop()
                for s in c.body:
                    if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)): counted.add(s)
                    elif isinstance(s, ast.ClassDef): st.append(s)
        elif isinstance(n, ast.If):
            for s in n.body + n.orelse:
                if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)): counted.add(s)
    par = {}
    for x in ast.walk(t):
        for c in ast.iter_child_nodes(x): par[c] = x
    for n in ast.walk(t):
        if not isinstance(n, ast.Call): continue
        v = n.func
        while isinstance(v, ast.Attribute): v = v.value
        if not (isinstance(v, ast.Name) and v.id in bound): continue
        p, owner = par.get(n), None
        while p is not None and not isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)): p = par.get(p)
        key = "sites_counted" if p in counted else "sites_uncounted"
        out[key] += 1; out["sites_by_module"][m] = out["sites_by_module"].get(m, 0) + 1
print(json.dumps(out, indent=1, sort_keys=True))
