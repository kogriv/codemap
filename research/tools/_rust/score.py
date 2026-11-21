"""R1-C111: score a tool's answers on ripgrep against the Rust truth (docs/design/recipe_rust.md D3).

    python research/tools/_rust/score.py <tool answers.json> <ripgrep checkout>

A tool adapter writes answers in one normalized shape:

    {"tool": ..., "version": ...,
     "r1": {name: ["file:line", ...]},                     # definitions of the bare name
     "r2": {symbol: [{"file", "name", "line"}, ...]},      # caller functions of the target
     "r3": {symbol: [{"file", "name", "line"}, ...]},      # callers at depth 1 or 2 (union)
     "r4": ["file -> file", ...],                          # `use` edges between source files
     "r5": {trait: ["TypeName", ...]}}                     # implementing types

Matching rules, the same for every tool:
- a definition or a caller matches the truth when the file is the same and the line is within 3 (attributes and
  doc comments move a reported start line); each truth item matches at most once;
- R4 compares module-level edges after mapping both sides to *file modules*: the truth's inline modules
  (`mod tests { }`) fold into their file, and a tool's file edges map to the file's module path;
- R5 compares the implementing type's base name (`StandardSink<'p, 's, M, W>` → `StandardSink`,
  `&'a mut S` → `S`, `Box<S>` → `Box`).
A missing question is reported as not answered, never as zero.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOL = 3


def prf(tp: int, n_tool: int, n_truth: int) -> dict:
    p = tp / n_tool if n_tool else None
    r = tp / n_truth if n_truth else None
    return {"tp": tp, "tool": n_tool, "truth": n_truth,
            "precision": round(p, 3) if p is not None else None, "recall": round(r, 3) if r is not None else None}


def match_sites(truth: list[tuple[str, int]], tool: list[tuple[str, int]]) -> int:
    used, tp = set(), 0
    for f, line in tool:
        best = None
        for i, (tf, tl) in enumerate(truth):
            if i in used or tf != f or abs(tl - line) > TOL:
                continue
            if best is None or abs(tl - line) < abs(truth[best][1] - line):
                best = i
        if best is not None:
            used.add(best)
            tp += 1
    return tp


def caller_key(cid: str) -> tuple[str, int]:
    # truth id: "file::detail::name@line"
    file = cid.split("::", 1)[0]
    return file, int(cid.rsplit("@", 1)[1])


def base_type(text: str) -> str:
    t = re.sub(r"^&('\w+\s+)?(mut\s+)?", "", text.strip())
    return re.split(r"[<\s]", t, 1)[0]


def file_modules(root: Path) -> dict[str, str]:
    """file path → module path, from cargo metadata targets (lib and the rg binary)."""
    meta = json.loads(subprocess.run(["cargo", "metadata", "--no-deps", "--format-version", "1"], cwd=root,
                                     capture_output=True, text=True, check=True).stdout)
    out = {}
    for p in meta["packages"]:
        for t in p["targets"]:
            if not ({"lib", "bin"} & set(t["kind"])) or ("bin" in t["kind"] and t["name"] != "rg"):
                continue
            crate = t["name"].replace("-", "_")
            src = Path(t["src_path"])
            base = src.parent
            for f in base.rglob("*.rs"):
                rel = f.relative_to(base)
                parts = list(rel.with_suffix("").parts)
                if parts[-1] in ("mod", "lib", "main") or f == src:
                    parts = parts[:-1]
                out[str(f.relative_to(root))] = "::".join([crate, *parts])
    return out


def main(argv):
    answers = json.loads(Path(argv[1]).read_text())
    root = Path(argv[2]).resolve()
    truth = json.loads((HERE / "truth_ra.json").read_text())
    tmod = json.loads((HERE / "truth_modules.json").read_text())
    res: dict = {"tool": answers.get("tool"), "version": answers.get("version"), "tree": truth["tree"]["commit"]}

    # R1
    if "r1" in answers:
        res["r1"] = {}
        for name, t in truth["r1"].items():
            tr = [(h.split("::")[0].rsplit(":", 1)[0], int(h.split("::")[0].rsplit(":", 1)[1])) for h in t["definitions"]]
            to = [(x.rsplit(":", 1)[0], int(x.rsplit(":", 1)[1])) for x in answers["r1"].get(name, [])]
            res["r1"][name] = prf(match_sites(tr, to), len(to), len(tr))
    # R2, R3
    for q in ("r2", "r3"):
        if q not in answers:
            continue
        res[q] = {}
        for sym, t in truth["r2"].items():
            if t.get("kind") == "macro":
                if q == "r3":
                    continue
                tr = [(s.rsplit(":", 1)[0], int(s.rsplit(":", 1)[1])) for s in t["sites"]]
                to = [(c["file"], c["line"]) for c in answers[q].get(sym, [])]
            else:
                ids = [c["caller"] for c in t["callers"]]
                strict_ids = [i for i in ids if i not in set(t.get("via_impl", []))]
                if q == "r3":
                    ids = sorted(set(ids) | {x for v in truth["r3"].get(sym, {}).values() for x in v})
                tr = [caller_key(i) for i in ids]
                to = [(c["file"], c["line"]) for c in answers[q].get(sym, [])]
            # A caller listed once per call site is still one caller.
            to = sorted(set(to))
            if sym not in answers[q]:
                res[q][sym] = {"answered": False, "truth": len(tr)}
                continue
            res[q][sym] = prf(match_sites(tr, to), len(to), len(tr))
            if q == "r2" and t.get("kind") != "macro" and len(strict_ids) != len(ids):
                st = [caller_key(i) for i in strict_ids]
                res[q][sym]["strict"] = prf(match_sites(st, to), len(to), len(st))
    # R4
    if "r4" in answers:
        fm = file_modules(root)
        mods = set(fm.values())

        def fold(m: str) -> str | None:
            parts = m.split("::")
            for i in range(len(parts), 0, -1):
                if "::".join(parts[:i]) in mods:
                    return "::".join(parts[:i])
            return None

        tr = set()
        for e in tmod["edges"]:
            a, b = (fold(x) for x in e.split(" -> "))
            if a and b and a != b:
                tr.add((a, b))
        to = set()
        unmapped = 0
        for e in answers["r4"]:
            fa, fb = e.split(" -> ")
            a, b = fm.get(fa), fm.get(fb)
            if a is None or b is None:
                unmapped += 1
                continue
            if a != b:
                to.add((a, b))
        roots = {m for m in mods if "::" not in m}
        tr_nr = {e for e in tr if e[1] not in roots}
        to_nr = {e for e in to if e[1] not in roots}
        res["r4"] = prf(len(tr & to), len(to), len(tr)) | {"unmapped_tool_edges": unmapped,
                                                            "without_crate_root_targets": prf(len(tr_nr & to_nr), len(to_nr), len(tr_nr)),
                                                            "missed_sample": sorted(f"{a} -> {b}" for a, b in tr - to)[:10],
                                                            "extra_sample": sorted(f"{a} -> {b}" for a, b in to - tr)[:10]}
    # R5
    if "r5" in answers:
        res["r5"] = {}
        for trait, lines in truth["r5"].items():
            tr = []
            for s in lines:
                f, ln = s.rsplit(":", 1)
                text = (root / f).read_text(encoding="utf-8").splitlines()[int(ln) - 1]
                m = re.search(r"\bfor\s+(.+?)\s*(where|\{|$)", text)
                tr.append(base_type(m.group(1)) if m else "?")
            to = [base_type(x) for x in answers["r5"].get(trait, [])]
            tp = sum(min(tr.count(x), to.count(x)) for x in set(to))
            res["r5"][trait] = prf(tp, len(to), len(tr)) | {"truth_types": sorted(tr), "tool_types": sorted(to)}
    json.dump(res, sys.stdout, indent=1, sort_keys=True)
    print()


if __name__ == "__main__":
    main(sys.argv)
