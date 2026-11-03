"""Per node: twin-rooted call sites and twin-rooted non-call attribute sites in the node's own body (AST),
against the measured deltas of extras.calls.external and extras.attr_access.out."""
import ast, json, sys, pathlib
root = pathlib.Path(sys.argv[1]); tw = json.load(open(sys.argv[2])); b, a = (json.load(open(x)) for x in sys.argv[3:5])
pkg = root.name
mods = {}
for f in sorted(root.rglob("*.py")):
    p = list(f.relative_to(root.parent).with_suffix("").parts); mods[".".join(p[:-1] if p[-1] == "__init__" else p)] = f
calls, attrs = {}, {}
for m, bound in tw["bindings"].items():
    t = ast.parse(mods[m].read_text())
    def own(fn, nid):
        def walk(n):
            for c in ast.iter_child_nodes(n):
                if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)) and not isinstance(c, ast.Lambda):
                    continue
                if isinstance(c, ast.Call):
                    v = c.func
                    while isinstance(v, ast.Attribute): v = v.value
                    if isinstance(v, ast.Name) and v.id in bound: calls[nid] = calls.get(nid, 0) + 1
                if isinstance(c, ast.Attribute) and isinstance(c.value, ast.Name) and c.value.id in bound \
                        and not (isinstance(n, ast.Call) and n.func is c):
                    attrs[nid] = attrs.get(nid, 0) + 1
                walk(c)
        walk(fn)
    def cls(c, prefix):
        defs = {}
        def collect(body):
            for s in body:
                if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)): defs[s.name] = s
                elif isinstance(s, ast.ClassDef): cls(s, f"{prefix}.{s.name}")
                elif isinstance(s, ast.If): collect(s.body); collect(s.orelse)
        collect(c.body)
        for name, s in defs.items(): own(s, f"{prefix}.{name}")
    for n in t.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)): own(n, f"{m}.{n.name}")
        elif isinstance(n, ast.ClassDef): cls(n, f"{m}.{n.name}")
        elif isinstance(n, ast.If):
            last = {}
            for s in n.body + n.orelse:
                if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)): last[s.name] = s
            for name, s in last.items(): own(s, f"{m}.{name}")
ex = lambda g, k, f: {n["id"]: ((n.get("extras") or {}).get(k) or {}).get(f, 0) for n in g["nodes"]}
eb, ea = ex(b, "calls", "external"), ex(a, "calls", "external")
ab, aa = ex(b, "attr_access", "out"), ex(a, "attr_access", "out")
dc = {i: ea.get(i, 0) - eb.get(i, 0) for i in set(eb) | set(ea) if ea.get(i, 0) != eb.get(i, 0)}
da = {i: ab.get(i, 0) - aa.get(i, 0) for i in set(ab) | set(aa) if ab.get(i, 0) != aa.get(i, 0)}
print("calls: predicted sites", sum(calls.values()), "measured external delta", sum(dc.values()))
for i in sorted(set(calls) | set(dc)):
    if calls.get(i, 0) != dc.get(i, 0): print("   calls mismatch", i, "predicted", calls.get(i, 0), "measured", dc.get(i, 0))
print("attr_access.out: measured drop", sum(da.values()), "| twin-rooted attribute expressions in own bodies (incl. call callees)", sum(attrs.values()))
for i in sorted(set(attrs) | set(da)):
    if attrs.get(i, 0) != da.get(i, 0): print("   attr mismatch", i, "predicted", attrs.get(i, 0), "measured", da.get(i, 0))
