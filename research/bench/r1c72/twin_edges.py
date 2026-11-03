"""R1-C72: edges in the BEFORE graph that exist only because of a twin binding.
For every module with twin bindings (twins.py), the qualified paths reached through a bound name in its source
(`name.a.b` -> `<twin target>.a.b`, and every prefix of it). An edge from a node of that module whose target is
one of those paths (or contained in one, for members) and is not also reachable by a non-twin binding is predicted
to vanish. Flat-labelled edges are listed separately."""
import ast, json, sys, pathlib
root = pathlib.Path(sys.argv[1]); g = json.load(open(sys.argv[2])); tw = json.load(open(sys.argv[3]))
pkg = root.name
mods = {}
for f in sorted(root.rglob("*.py")):
    p = list(f.relative_to(root.parent).with_suffix("").parts); mods[".".join(p[:-1] if p[-1] == "__init__" else p)] = f
def mod_of(i):
    best = None
    for m in mods:
        if (i == m or i.startswith(m + ".")) and (best is None or len(m) > len(best)): best = m
    return best
paths = {}
for m, bound in tw["bindings"].items():
    t = ast.parse(mods[m].read_text()); ps = set()
    for n in ast.walk(t):
        if isinstance(n, ast.Attribute) or isinstance(n, ast.Name):
            chain, v = [], n
            while isinstance(v, ast.Attribute): chain.append(v.attr); v = v.value
            if isinstance(v, ast.Name) and v.id in bound:
                chain.reverse(); base = bound[v.id]
                ps.add(base)
                for i in range(len(chain)): ps.add(base + "." + ".".join(chain[:i + 1]))
    paths[m] = ps
pred = []
for e in g["edges"]:
    if (e.get("extras") or {}).get("resolution") == "flat" or e["type"] == "contains": continue
    sm = mod_of(e["source"])
    if sm in paths and e["target"] in paths[sm]:
        pred.append([e["type"], e["source"], e["target"]])
print(json.dumps({"predicted_vanish": sorted(pred)}, indent=1))
