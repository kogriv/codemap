"""Sums of call-site counters by scope, from a graph JSON (the R1-C74 buckets), and an edge/node diff vs a before-graph."""
import json, sys, copy, ast, pathlib
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else None
src = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else None
keys = ("out", "resolved", "external", "unresolved", "dynamic")
by = {s: dict.fromkeys(keys, 0) for s in ("function", "nested", "module", "class_body")}; shadow = 0
for n in a["nodes"]:
    x = n.get("extras") or {}
    sc = {"function": "function", "attribute": "function", "module": "module", "class": "class_body"}.get(n["kind"])
    for k2, bucket in (("calls", sc), ("calls_nested", "nested")):
        if x.get(k2) and bucket:
            for k in keys: by[bucket][k] += x[k2].get(k, 0)
    shadow += x.get("calls_shadowed", 0)
print("  out by scope:", {s: by[s]["out"] for s in by}, "| shadowed", shadow, "| sum+shadowed", sum(by[s]["out"] for s in by) + shadow)
if b is None: sys.exit()
kk = lambda e: (e["type"], e["source"], e["target"], json.dumps(e.get("extras", {}), sort_keys=True))
eb, ea = {kk(e) for e in b["edges"]}, {kk(e) for e in a["edges"]}
kind = {n["id"]: n["kind"] for n in a["nodes"]}
added, removed = ea - eb, eb - ea
print("  edges added", len(added), "removed", len(removed), "| added all calls-from-class:", all(e[0] == "calls" and kind.get(e[1]) == "class" for e in added))
for e in sorted(removed)[:5]: print("   REMOVED", e)
def strip(n):
    n = copy.deepcopy(n); x = n.get("extras") or {}
    for k in ("calls", "calls_nested", "calls_shadowed"):
        if n["kind"] in ("module", "class") or k != "calls": x.pop(k, None)
    return json.dumps(n, sort_keys=True)
print("  nodes identical apart from the new counter keys:", sorted(map(strip, b["nodes"])) == sorted(map(strip, a["nodes"])))
if src:  # every class->target edge: the class body source contains a call whose callee text ends with the target's last name
    mods = {}
    for f in src.rglob("*.py"):
        p = list(f.relative_to(src.parent).with_suffix("").parts); mods[".".join(p[:-1] if p[-1] == "__init__" else p)] = f
    bad = 0
    for e in added:
        cls = e[1]; m = max((x for x in mods if cls.startswith(x + ".")), key=len); path = cls[len(m) + 1:].split(".")
        t = ast.parse(mods[m].read_text()); node = t
        for name in path:
            node = next(c for c in ast.walk(node) if isinstance(c, ast.ClassDef) and c.name == name)
        texts = []
        def own(nd):
            for c in ast.iter_child_nodes(nd):
                if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): continue
                if isinstance(c, ast.Call): texts.append(ast.unparse(c.func))
                own(c)
        own(node)
        last = e[2].split(".")[-1]
        if not any(tx.split(".")[-1] == last or tx == last for tx in texts): bad += 1; print("   UNVERIFIED", e[1], "->", e[2], texts[:5])
    print("  class edges verified against the class-body source:", len(added) - bad, "of", len(added))
