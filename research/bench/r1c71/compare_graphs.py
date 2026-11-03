"""Compare two graphs for R1-C71: edges by type, nodes outside extras.calls, sums of calls counters; and the
new calls edges against the independent prediction (predicted pairs minus those already present before)."""
import json, sys, copy
b, a = (json.load(open(p)) for p in sys.argv[1:3])
pred = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else None
k = lambda e: (e["type"], e["source"], e["target"], json.dumps(e.get("extras", {}), sort_keys=True))
eb, ea = {k(e) for e in b["edges"]}, {k(e) for e in a["edges"]}
def strip(n):
    n = copy.deepcopy(n); n.get("extras", {}).pop("calls", None); return json.dumps(n, sort_keys=True)
print("  nodes identical outside extras.calls:", sorted(map(strip, b["nodes"])) == sorted(map(strip, a["nodes"])))
types = sorted({e[0] for e in eb | ea})
for t in types:
    plus, minus = {e for e in ea - eb if e[0] == t}, {e for e in eb - ea if e[0] == t}
    if plus or minus: print(f"  {t}: +{len(plus)} -{len(minus)}")
def sums(g):
    s = {}
    for n in g["nodes"]:
        for kk, v in (n.get("extras", {}).get("calls") or {}).items(): s[kk] = s.get(kk, 0) + v
    return s
sb, sa = sums(b), sums(a)
print("  calls counters delta:", {kk: sa.get(kk, 0) - sb.get(kk, 0) for kk in sorted(set(sb) | set(sa)) if sa.get(kk, 0) != sb.get(kk, 0)})
new_pairs = {(e[1], e[2]) for e in ea - eb if e[0] == "calls"}
gone_pairs = {(e[1], e[2]) for e in eb - ea if e[0] == "calls"}
changed = new_pairs & gone_pairs      # same pair, extras changed (callsites count etc.)
if pred is not None:
    before_pairs = {(e[1], e[2]) for e in eb if e[0] == "calls"}
    p = {tuple(x) for x in pred["edges"]}
    expect_new = p - before_pairs
    print(f"  predicted pairs {len(p)}, already present before {len(p & before_pairs)}, expected new {len(expect_new)}")
    print(f"  new pairs {len(new_pairs - gone_pairs)}; extras-changed pairs {len(changed)}; removed pairs {len(gone_pairs - new_pairs)}")
    for x in sorted(expect_new - new_pairs): print("   MISSING (predicted, not produced):", *x)
    for x in sorted((new_pairs - gone_pairs) - expect_new): print("   EXTRA (produced, not predicted):", *x)
    for x in sorted(changed): print("   extras changed:", *x)
    for x in sorted(gone_pairs - new_pairs): print("   REMOVED:", *x)
