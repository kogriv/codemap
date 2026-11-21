"""R1-C112: score each tool's dead-code list against rust-analyzer's references (recipe_rust.md D7, E10, E11).

    python research/tools/_rust/score_dead.py <planted checkout> <refs.json> <plants.json> name=dead.json ...

Each reported item falls in exactly one class, checked in this order:
- `unresolved`  no declaration of that name within 3 lines of the reported line (closures, generated names);
- `entry`       a `#[test]`/`#[bench]` function, or `main`: nothing calls it by design;
- `trait_impl`  a method of `impl Trait for Type`: it cannot be deleted while the impl stands;
- `alive`       referenced from production code, outside `use` statements: a **false death**;
- `test_only`   referenced only from tests;
- `reexported`  referenced only by `use`/`pub use` lines: public surface, not a use;
- `cfg_variant` no reference, and a twin of the same name sits in the same item (a `#[cfg(windows)]` variant is
                inactive for rust-analyzer here): alive on another platform;
- `unused`      no reference at all: a true candidate (in a library crate it may still be public API).
`false_death_rate` = alive / (items − unresolved). The plants are reported by name for each tool.
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path


USE = re.compile(r"^\s*(pub(\([^)]*\))?\s+)?use\b")


def in_use_tree(lines: list[str], i: int) -> bool:
    """Whether line i (0-based) is part of a `use` statement, single- or multi-line."""
    for j in range(i, max(-1, i - 20), -1):
        line = lines[j]
        if USE.match(line):
            return True
        if j != i and (";" in line or not line.strip() or line.rstrip().endswith("}")):
            return False
    return False


def real_refs(root: Path, refs: list[str], cache: dict) -> list[str]:
    out = []
    for ref in refs:
        f, ln = ref.rsplit(":", 1)
        if f not in cache:
            cache[f] = (root / f).read_text(encoding="utf-8").splitlines()
        if not in_use_tree(cache[f], int(ln) - 1):
            out.append(ref)
    return out


def classify(root: Path, r: dict, cache: dict) -> str:
    if "error" in r:
        return "unresolved"
    f = r["file"]
    if f not in cache:
        cache[f] = (root / f).read_text(encoding="utf-8").splitlines()
    lines = cache[f]
    i = r["decl_line"] - 1
    above = " ".join(lines[max(0, i - 3):i])
    if re.search(r"#\[(test|bench)\]|#\[\w+::test", above) or r["name"] == "main":
        return "entry"
    if r["trait_impl"]:
        return "trait_impl"
    prod, test = real_refs(root, r["refs_prod"], cache), real_refs(root, r["refs_test"], cache)
    if prod:
        return "alive"
    if test:
        return "test_only"
    if r["refs_prod"] or r["refs_test"]:
        return "reexported"
    return "cfg_variant" if r.get("cfg_variants") else "unused"


def main(argv):
    root = Path(argv[1]).resolve()
    refs = {(r["file"], r["line"], r["name"]): r for r in json.loads(Path(argv[2]).read_text())}
    plants = json.loads(Path(argv[3]).read_text())["dead"]
    cache: dict = {}
    out = {}
    for spec in argv[4:]:
        name, path = spec.split("=", 1)
        items = json.loads(Path(path).read_text())
        seen = {(x["file"], x["line"], x["name"]) for x in items}
        classes = collections.Counter()
        alive_sample = []
        for k in sorted(seen):
            c = classify(root, refs[k], cache)
            classes[c] += 1
            if c == "alive" and len(alive_sample) < 8:
                alive_sample.append(f"{k[0]}:{k[1]} {k[2]} ← {real_refs(root, refs[k]['refs_prod'], cache)[0]}")
        resolved = len(seen) - classes["unresolved"]
        reported = {k[2] for k in seen}
        out[name] = {"items": len(seen), "classes": dict(sorted(classes.items())),
                     "false_death_rate": round(classes["alive"] / resolved, 3) if resolved else None,
                     "alive_sample": alive_sample,
                     "plants": {p: {"truth": t, "reported_dead": p in reported} for p, t in plants.items()}}
    json.dump(out, sys.stdout, indent=1, sort_keys=True)
    print()


if __name__ == "__main__":
    main(sys.argv)
