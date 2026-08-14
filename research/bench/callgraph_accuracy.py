#!/usr/bin/env python3
"""Call-graph accuracy against hand-labeled ground truth (R1-C13, part a).

Why not PyCG as the oracle: PyCG 0.0.8 — the reference academic Python call-graph
tool — does not run on Python 3.12 (its import-hook machinery collides with the
modern stdlib; see research/tools/pycg.md). Rather than treat a second imperfect
static tool as truth, this harness uses a small **hand-labeled** micro-suite
(cases/) whose true call edges we KNOW, and measures codemap's extractor against
it — a reproducible, deterministic oracle with no third-party dependency.

Each case is a tiny package under cases/<name>/; expected.json labels, per case,
the call edges a sound analyzer should emit ('expected', tagged with the cheapest
tier that resolves them), the statically-UNDECIDABLE true relationships that
define the honest recall ceiling ('ceiling'), and the relationships codemap does
not model by design ('limitation'). See expected.json's _README.

Metrics per tier (fast = stdlib-ast, deep = jedi type inference):
  precision       = TP / (TP + FP)     — are the emitted edges correct?
  recall_decidable= TP / |expected|    — did we get the statically-decidable edges?
  recall_overall  = TP / |all true|    — the honest number: decidable + ceiling +
                                          limitation in the denominator (the gap
                                          is the price of Python's dynamism)
  phantom         = emitted edges whose target is not a graph node (soundness)

Usage:
  python research/bench/callgraph_accuracy.py            # human table
  python research/bench/callgraph_accuracy.py --json     # machine JSON
  python research/bench/callgraph_accuracy.py --check    # assert invariants (CI/tests)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from codemap.extract import extract  # noqa: E402

_CASES = _HERE / "callgraph_truth" / "cases"
_LABELS = _HERE / "callgraph_truth" / "expected.json"
_TIERS = ("fast", "deep")


def _emitted(case: str, deep: bool) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """(edges, phantom_edges) as (src, tgt) suffixes relative to the case package."""
    g = extract(str(_CASES / case), deep=deep)
    nodes = set(g.nodes)
    pre = case + "."
    edges, phantom = set(), set()
    for e in g.edges:
        if e.type != "calls":
            continue
        pair = (e.source[len(pre):] if e.source.startswith(pre) else e.source,
                e.target[len(pre):] if e.target.startswith(pre) else e.target)
        edges.add(pair)
        if e.target not in nodes:
            phantom.add(pair)
    return edges, phantom


def _expected(spec: dict, tier: str) -> set[tuple[str, str]]:
    """Expected edges applicable at this tier (fast-min always; deep-min on deep)."""
    out = set()
    for src, tgt, min_tier in spec.get("expected", []):
        if min_tier == "fast" or tier == "deep":
            out.add((src, tgt))
    return out


def _pairs(spec: dict, key: str) -> set[tuple[str, str]]:
    return {(s, t) for s, t in spec.get(key, [])}


def score_case(case: str, spec: dict, tier: str) -> dict:
    deep = tier == "deep"
    emitted, phantom = _emitted(case, deep)
    expected = _expected(spec, tier)
    ceiling = _pairs(spec, "ceiling")
    limitation = _pairs(spec, "limitation")
    # all expected across both tiers — a deep-only edge seen on fast is a bonus, not an FP
    expected_any = {(s, t) for s, t, _ in spec.get("expected", [])}

    tp = emitted & expected
    fp = {e for e in emitted
          if e not in expected_any and e not in ceiling and e not in limitation}
    fn = expected - emitted
    all_true = expected | ceiling | limitation

    return {
        "case": case,
        "tier": tier,
        "difficulty": spec.get("difficulty", ""),
        "tp": len(tp), "fp": len(fp), "fn": len(fn),
        "expected": len(expected), "all_true": len(all_true),
        "phantom": len(phantom),
        "precision": (len(tp) / (len(tp) + len(fp))) if (tp or fp) else None,
        "recall_decidable": (len(tp) / len(expected)) if expected else None,
        "recall_overall": (len(tp) / len(all_true)) if all_true else None,
        "fp_edges": sorted(fp), "fn_edges": sorted(fn), "phantom_edges": sorted(phantom),
    }


def run() -> dict:
    labels = {k: v for k, v in json.loads(_LABELS.read_text()).items()
              if not k.startswith("_")}
    rows = []
    for case in sorted(labels):
        for tier in _TIERS:
            rows.append(score_case(case, labels[case], tier))
    agg = {}
    for tier in _TIERS:
        trows = [r for r in rows if r["tier"] == tier]
        tp = sum(r["tp"] for r in trows)
        fp = sum(r["fp"] for r in trows)
        exp = sum(r["expected"] for r in trows)
        allt = sum(r["all_true"] for r in trows)
        agg[tier] = {
            "tp": tp, "fp": fp,
            "expected": exp, "all_true": allt,
            "phantom": sum(r["phantom"] for r in trows),
            "precision": (tp / (tp + fp)) if (tp + fp) else None,
            "recall_decidable": (tp / exp) if exp else None,
            "recall_overall": (tp / allt) if allt else None,
        }
    return {"rows": rows, "aggregate": agg}


def _pct(x) -> str:
    return "  n/a " if x is None else f"{100 * x:5.1f}%"


def _print_human(res: dict) -> None:
    print("codemap call-graph accuracy vs hand-labeled ground truth\n")
    print(f"{'case':22} {'tier':4}  {'P':>6} {'R-dec':>6} {'R-all':>6} "
          f"{'TP':>2} {'FP':>2} {'FN':>2} {'phan':>4}  difficulty")
    print("-" * 88)
    for r in res["rows"]:
        print(f"{r['case']:22} {r['tier']:4}  {_pct(r['precision'])} "
              f"{_pct(r['recall_decidable'])} {_pct(r['recall_overall'])} "
              f"{r['tp']:>2} {r['fp']:>2} {r['fn']:>2} {r['phantom']:>4}  {r['difficulty']}")
    print("-" * 88)
    for tier in _TIERS:
        a = res["aggregate"][tier]
        print(f"{'AGGREGATE':22} {tier:4}  {_pct(a['precision'])} "
              f"{_pct(a['recall_decidable'])} {_pct(a['recall_overall'])} "
              f"{a['tp']:>2} {a['fp']:>2} {'':>2} {a['phantom']:>4}")
    print("\nR-dec = recall over statically-decidable edges (the bug metric).")
    print("R-all = recall over ALL true edges incl. undecidable ceiling (the honest metric).")
    print("phan  = edges pointing at a non-node target (soundness signal).")
    # surface findings
    findings = [(r["case"], r["tier"], r["fp_edges"], r["phantom_edges"])
                for r in res["rows"] if r["fp"] or r["phantom"]]
    if findings:
        print("\nFindings (imperfections the suite deliberately surfaces):")
        for case, tier, fps, phans in findings:
            bits = []
            if fps:
                bits.append(f"FP={fps}")
            if phans:
                bits.append(f"phantom={phans}")
            print(f"  - {case} [{tier}]: {'; '.join(bits)}")


def _check(res: dict) -> int:
    """Assert the invariants the honest-ceiling story rests on. Exit 0 / 1."""
    a = res["aggregate"]
    problems = []
    # deep tier must be sound on the decidable set: no false edges, all decidable edges found
    if a["deep"]["precision"] != 1.0:
        problems.append(f"deep precision {a['deep']['precision']} != 1.0 (a wrong edge slipped in)")
    if a["deep"]["recall_decidable"] != 1.0:
        problems.append(f"deep recall_decidable {a['deep']['recall_decidable']} != 1.0 "
                        f"(a statically-decidable edge was missed)")
    # deep tier must not emit phantom edges (fast may, and we document it)
    if a["deep"]["phantom"] != 1:
        problems.append(f"deep phantom count {a['deep']['phantom']} != 1 "
                        f"(expected exactly the documented c10 closure phantom)")
    # the honest ceiling must be strictly below 1.0 (undecidable edges exist and are unmet)
    if not (a["deep"]["recall_overall"] < 1.0):
        problems.append("deep recall_overall is not < 1.0 — the ceiling demo is broken")
    if problems:
        print("CHECK FAILED:")
        for p in problems:
            print("  -", p)
        return 1
    print("CHECK OK — deep tier sound on decidable set; ceiling < 100% as designed.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit machine JSON")
    ap.add_argument("--check", action="store_true", help="assert invariants, exit nonzero on failure")
    args = ap.parse_args(argv)
    res = run()
    if args.json:
        print(json.dumps(res, indent=2))
        return 0
    if args.check:
        return _check(res)
    _print_human(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
