"""R1-C136 controlled graph comparison on the retained public R1-C132 traces."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import signal
import subprocess
import sys
from collections import Counter
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(BENCH / name) for name in ("r1c132", "r1c130")]
from compare import compare, explicit_pairs, grades
from measure import pressure, timed


PROJECTS = {
    "click": ("cf19179e8e2fd54c601378cec9e0d21bb12b6fb1", "src/click", 646),
    "rich": ("6ac483cbea39cab124dfd3483bba70ffafb71050", "rich", 1240),
    "jinja": ("15206881c006c79667fe5154fe80c01c65410679", "src/jinja2", 1476),
}
HOLDOUT = ("6389612fd1ee1bd93579eed5026e8fd471d04abd", "src/werkzeug", None)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call_routes(graph, *, omit_override=False):
    return {(edge["source"], edge["target"], edge["extras"].get("resolution"))
            for edge in graph["edges"] if edge["type"] == "calls"
            and (not omit_override or edge["extras"].get("resolution") != "override")}


def read(path):
    return json.loads(path.read_text())


def run_build(work, project_dir, package, destination, candidate, deep):
    source = str(work / "candidate")
    env = ["env", f"PYTHONPATH={source}"] if candidate else ["env", "-u", "PYTHONPATH"]
    args = [*env, sys.executable, "-m", "codemap", "build", package, "-o", destination]
    if deep:
        args += ["--deep", "--repeat", "2"]
    usage, _ = timed(args, project_dir, destination.with_suffix(".out"), timeout=300)
    return {**usage, "graph_sha256": digest(destination)}


def metrics(report):
    explicit = report["recall"]["explicit"]
    by_outcome = report["precision"]["outcomes"]
    confirmed = by_outcome.get("confirmed", 0)
    contradicted = by_outcome.get("contradicted", 0)
    return {"pairs": explicit["pairs"], "found": explicit["found"],
            "recall_pct": 100 * explicit["found"] / explicit["pairs"],
            "decided_precision_pct": 100 * confirmed / (confirmed + contradicted),
            "precision_outcomes": by_outcome, "callers_complete": report["callers_complete"]}


def summarize_case(paths, traces, src, holdout=None):
    ordinary = {name: read(paths[(name, False)]) for name in ("baseline", "candidate")}
    left = call_routes(ordinary["baseline"])
    right = call_routes(ordinary["candidate"], omit_override=True)
    fast = {"parity": left == right, "base_routes": len(left), "preserved_routes": len(right),
            "missing": sorted(left - right)[:12], "extra": sorted(right - left)[:12],
            "candidate_routes": len(call_routes(ordinary["candidate"]) - right)}

    candidate = read(paths[("candidate", True)])
    overrides = [edge for edge in candidate["edges"]
                 if edge["type"] == "calls" and edge["extras"].get("resolution") == "override"]
    ablated = paths[("candidate", True)].with_name("ablated-deep.json")
    candidate["edges"] = [edge for edge in candidate["edges"]
                          if edge["type"] != "calls" or edge["extras"].get("resolution") != "override"]
    ablated.write_text(json.dumps(candidate, sort_keys=True))
    base_report = compare(str(paths[("baseline", True)]), traces, str(src))
    before = compare(str(ablated), traces, str(src))
    after = compare(str(paths[("candidate", True)]), traces, str(src))
    assert before["recall"]["explicit"]["pairs"] == after["recall"]["explicit"]["pairs"]
    existing_pairs = {(source, target) for source, target, _ in call_routes(candidate)}
    override_pairs = {(e["source"], e["target"]) for e in overrides}
    new = override_pairs - existing_pairs
    outcomes = Counter(after["edge_outcomes"][f"{source} -> {target}"] for source, target in new)
    base, m0, m1 = (metrics(report) for report in (base_report, before, after))
    outcome = {"fast": fast, "baseline_deep": base, "ablated_deep": m0, "candidate_deep": m1,
               "override_edges": len(overrides), "override_pairs": len(override_pairs),
               "novel_pairs": len(new), "novel_outcomes": dict(outcomes),
               "recall_delta_pp": m1["recall_pct"] - m0["recall_pct"],
               "precision_drop_pp": m0["decided_precision_pct"] - m1["decided_precision_pct"]}
    if holdout:
        baseline = str(paths[("baseline", True)])
        t1, t2 = (explicit_pairs(baseline, path) for path in traces)
        outcome["holdout"] = {**holdout, "trace_explicit_union": len(t1 | t2),
                              "trace_explicit_difference": len(t1 ^ t2),
                              "functions": base_report["functions"],
                              "functions_started": base_report["functions_started"],
                              "novel_decided": outcomes["confirmed"] + outcomes["contradicted"]}
    return outcome


def trace_control(project):
    runs = {}
    for mode in ("plain", "traced1", "traced2"):
        status = int((project / f"status-{mode}.txt").read_text())
        summary = (project / f"pytest-{mode}.txt").read_text().splitlines()[-1]
        counts = re.findall(r"(\d+) (passed|skipped|failed|errors?|xfailed|xpassed)\b", summary)
        runs[mode] = {"status": status, "counts": {name: int(count) for count, name in counts}}
    plain = runs["plain"]
    return {"runs": runs, "equivalent": plain["status"] == 0 and bool(plain["counts"].get("passed"))
            and all(run == plain for run in runs.values()),
            "python": (project / "trace-python.txt").read_text().strip(),
            "dependencies": (project / "trace-deps.txt").read_text().splitlines()}


def main(work, trace_home, holdout=None):
    out = work / os.environ.get("R1C136_RUN", "run")
    out.mkdir()
    affinity = sorted(os.sched_getaffinity(0))
    assert len(affinity) == 2, affinity
    assert grades().get("override") == "heuristic"
    assert importlib.metadata.version("codmap") == "0.0.50"
    projects = [(name, trace_home / name, target) for name, target in PROJECTS.items()]
    control = None
    if holdout is not None:
        control = trace_control(holdout)
        if not control["equivalent"]:
            raise ValueError(f"Werkzeug plain/traced test runs differ: {control['runs']}")
        projects.append(("werkzeug", holdout, HOLDOUT))
    outcomes = {}
    with (out / "samples.jsonl").open("w", buffering=1) as raw:
        def emit(phase, **row):
            raw.write(json.dumps({"phase": phase, **row}, sort_keys=True) + "\n")

        emit("host", affinity=affinity, python=platform.python_version(),
             versions={name: importlib.metadata.version(name) for name in
                       ("codmap", "griffe", "jedi", "networkx")},
             wheel_sha256=(work / "wheel.sha256").read_text().split()[0],
             candidate_patch_sha256=digest(work / "r1c136.patch"),
             pressure=pressure())
        for name, project, (revision, package_name, expected_pairs) in projects:
            checkout = project / "src"
            observed = subprocess.check_output(["git", "-C", checkout, "rev-parse", "HEAD"],
                                               text=True).strip()
            assert observed == revision, (name, observed)
            subprocess.run(["git", "-C", checkout, "diff", "--quiet", "HEAD", "--", package_name],
                           check=True)
            package = checkout / package_name
            traces = tuple(project / f"trace{i}.json" for i in (1, 2))
            case = out / name
            case.mkdir()
            paths = {}
            for deep in (False, True):
                tier = "deep" if deep else "fast"
                for variant in ("baseline", "candidate"):
                    print(f"{name}: {variant} {tier}", flush=True)
                    path = case / f"{variant}-{tier}.json"
                    paths[(variant, deep)] = path
                    usage = run_build(work, project, package, path, variant == "candidate", deep)
                    emit("build", project=name, variant=variant, tier=tier, **usage)
            outcome = summarize_case(paths, traces, package.parent, control if name == "werkzeug" else None)
            pair_counts = {outcome[key]["pairs"] for key in
                           ("baseline_deep", "ablated_deep", "candidate_deep")}
            assert len(pair_counts) == 1 and (expected_pairs is None or expected_pairs in pair_counts), (
                name, pair_counts, expected_pairs)
            outcomes[name] = outcome
            emit("case", project=name, revision=revision,
                 traces_sha256=[digest(p) for p in traces], **outcome)
            print(f"{name}: recall {outcome['recall_delta_pp']:+.2f} pp, "
                  f"precision drop {outcome['precision_drop_pp']:+.2f} pp", flush=True)
        original = [outcomes[name] for name in PROJECTS]
        pass_recall = sum(o["recall_delta_pp"] >= 5 - 1e-9 for o in original) >= 2
        pass_precision = all(o["precision_drop_pp"] <= 3 + 1e-9 for o in original)
        pass_parity = all(o["fast"]["parity"] for o in original)
        decision = {"pass_recall": pass_recall, "pass_precision": pass_precision,
                    "pass_fast_parity": pass_parity,
                    "promote": pass_recall and pass_precision and pass_parity}
        if holdout is not None:
            extra = outcomes["werkzeug"]
            after = extra["candidate_deep"]
            pass_holdout = extra["fast"]["parity"] and all(
                after["recall_pct"] >= extra[control]["recall_pct"] - 1e-9
                and after["decided_precision_pct"] >= extra[control]["decided_precision_pct"] - 3 - 1e-9
                for control in ("baseline_deep", "ablated_deep"))
            decision["pass_holdout"] = pass_holdout
            decision["promote"] = decision["promote"] and pass_holdout
        emit("end", **decision, pressure=pressure())
        (out / "decision.json").write_text(json.dumps(decision, indent=2) + "\n")
        print(json.dumps(decision), flush=True)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.default_int_handler)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("trace_home", type=Path)
    parser.add_argument("--holdout", type=Path)
    args = parser.parse_args()
    main(args.work.resolve(), args.trace_home.resolve(), args.holdout and args.holdout.resolve())
