"""R1-C72 prediction, from the package source (AST) and the BEFORE graph.
A binding is shadow-qualified when a module binds a name by a bare absolute import (`import X`, `from X import Y`)
whose head X is not the package, and `<importer's parent>.X` is a module of the package (the flat rule fires).
The package is 'packaged' if any module imports another of its modules by package-qualified or relative name.
Predicted, for a packaged package: every edge labelled resolution=flat disappears; every other edge from a module
into a twin module `<parent>.X` disappears iff that module reaches the twin only through a shadow-qualified binding
(no qualified/relative import of the twin, and no non-flat imports edge to it in the before graph)."""
import ast, json, sys, pathlib
root = pathlib.Path(sys.argv[1]); pkg = root.name; g = json.load(open(sys.argv[2]))
mods = {}
for f in sorted(root.rglob("*.py")):
    p = list(f.relative_to(root.parent).with_suffix("").parts); mods[".".join(p[:-1] if p[-1] == "__init__" else p)] = f
packaged = False; twins = {}
for m, f in mods.items():
    t = ast.parse(f.read_text()); parent = m.rsplit(".", 1)[0] if "." in m else None
    for n in ast.walk(t):
        if isinstance(n, ast.ImportFrom) and (n.level or (n.module or "").split(".")[0] == pkg): packaged = True
        if isinstance(n, ast.Import) and any(a.name.split(".")[0] == pkg for a in n.names): packaged = True
        heads = []
        if isinstance(n, ast.Import): heads = [a.name.split(".")[0] for a in n.names]
        elif isinstance(n, ast.ImportFrom) and not n.level and n.module: heads = [n.module.split(".")[0]]
        for h in heads:
            if h != pkg and parent and f"{parent}.{h}" in mods: twins.setdefault(m, set()).add(f"{parent}.{h}")
flat = [e for e in g["edges"] if (e.get("extras") or {}).get("resolution") == "flat"]
nonflat_imp = {(e["source"], e["target"]) for e in g["edges"] if e["type"] == "imports" and (e.get("extras") or {}).get("resolution") != "flat"}
def mod_of(i):
    best = None
    for m in mods:
        if (i == m or i.startswith(m + ".")) and (best is None or len(m) > len(best)): best = m
    return best
derived = []
for e in g["edges"]:
    if e in flat or e["type"] in ("imports", "contains"): continue
    sm, tm = mod_of(e["source"]), mod_of(e["target"])
    if sm in twins and tm in twins[sm] and (sm, tm) not in nonflat_imp and (e.get("extras") or {}).get("resolution") != "flat":
        derived.append([e["type"], e["source"], e["target"]])
print(json.dumps({"packaged": packaged, "twin_bindings": {k: sorted(v) for k, v in sorted(twins.items())},
                  "flat_edges": sorted([e["type"], e["source"], e["target"]] for e in flat),
                  "flat_public_exports": sum(1 for e in flat if e["type"] == "export" and (e.get("extras") or {}).get("public")),
                  "derived_edges": sorted(derived)}, indent=1))
