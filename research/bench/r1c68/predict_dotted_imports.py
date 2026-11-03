"""Independent prediction for R1-C68 from Python semantics, not from codemap code.
For each module of a package: module-level plain `import P.x.y` (no `as`) -> the module P.x.y depends on.
Predicted NEW edges: (src, containing module of target) for such imports, at module level incl. try/if (not TYPE_CHECKING),
where no other module-level import form in the same file already names that module.
Predicted REMOVED edges: (src, P) where P is only bound by dotted imports (no `import P`, no `from P import <name defined in P/__init__>`)."""
import ast, sys, pathlib, json
root = pathlib.Path(sys.argv[1]); pkg = root.name
mods = {}
for f in sorted(root.rglob("*.py")):
    rel = f.relative_to(root.parent).with_suffix("")
    parts = list(rel.parts); parts = parts[:-1] if parts[-1] == "__init__" else parts
    mods[".".join(parts)] = f
def containing(t):
    while t and t not in mods: t = t.rpartition(".")[0]
    return t or None
def is_tc(n):
    t = n.test
    return (isinstance(t, ast.Name) and t.id == "TYPE_CHECKING") or (isinstance(t, ast.Attribute) and t.attr == "TYPE_CHECKING")

def scan(m, f):
    st = {"dotted": set(), "plain_root": False, "other": set()}
    def walk(nodes, tc):
        for n in nodes:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(n, ast.If) and is_tc(n):
                walk(n.body, True); walk(n.orelse, tc); continue
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.name == pkg and a.asname is None:
                        st["plain_root"] = True
                    elif a.name.startswith(pkg + ".") and a.asname is None and not tc:
                        st["dotted"].add(a.name)
                    elif a.name.startswith(pkg + "."):
                        st["other"].add(containing(a.name))
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module and (n.module == pkg or n.module.startswith(pkg + ".")):
                for a in n.names:
                    st["other"].add(containing(f"{n.module}.{a.name}"))
            for fld in ("body", "orelse", "handlers", "finalbody"):
                walk(getattr(n, fld, None) or [], tc)
    walk(ast.parse(f.read_text()).body, False)
    return st

new, removed = set(), set()
for m, f in mods.items():
    st = scan(m, f)
    for d in st["dotted"]:
        t = containing(d)
        if t and t != m and t not in st["other"]:
            new.add((m, t))
    if st["dotted"] and not st["plain_root"] and pkg not in st["other"] and m != pkg:
        removed.add((m, pkg))
print(json.dumps({"new": sorted(new), "removed": sorted(removed)}, indent=1))
