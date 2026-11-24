"""Validate the R1-C131 matrix and render reproducible Markdown tables."""

import gzip
import json
import math
import sys
from collections import Counter
from pathlib import Path
from statistics import median


PROJECTS = ("more-itertools", "rich", "pytest")
ROUTES = ("global", "uses", "both")
STRATEGIES = ("uncached", "projection", "rank")


def table(headers, rows):
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        print("| " + " | ".join(map(str, row)) + " |")
    print()


def stats(rows, key="wall_ms"):
    values = sorted(r[key] for r in rows)
    upper = values[math.ceil(.95 * len(values)) - 1] if len(values) >= 20 else values[-1]
    return f"{median(values):.2f} / {upper:.2f}"


def summarize(rows):
    def pick(phase, **filters):
        return [r for r in rows if r["phase"] == phase
                and all(r.get(key) == value for key, value in filters.items())]

    def exact(phase, n, **filters):
        group = pick(phase, **filters)
        assert len(group) == n, (phase, filters, len(group), n)
        if group and "i" in group[0]:
            assert sorted(r["i"] for r in group) == list(range(1, n + 1)), (phase, filters)
        return group

    host, = exact("host", 1)
    exact("end", 1)
    print(f"Python {host['python']}, Linux {host['kernel']}, affinity "
          f"`{','.join(map(str, host['affinity']))}`. "
          + ", ".join(f"{k} {v}" for k, v in host["packages"].items()) + ".\n")
    graphs = [exact("graph", 1, project=p)[0] for p in PROJECTS]
    exact("mcp_start", 3)
    table(("Project", "Tier", "Nodes", "Edges", "Graph MiB", "Build wall s"), (
        (r["project"], r["tier"], r["nodes"], r["edges"], f"{r['graph_bytes']/2**20:.2f}",
         f"{r['wall_ms']/1000:.2f}") for r in graphs
    ))

    print("### Baseline and stage attribution\n")
    print("Baseline time is median / nearest-rank P95 in ms, n=20. The MCP/direct pack "
          "difference is the difference of medians from separate processes.\n")
    baseline_rows, stages, hotspots = [], [], []
    for project in PROJECTS:
        exact("project_end", 1, project=project)
        for route in ROUTES:
            views = {case: exact("baseline", 20, project=project, route=route, case=case)
                     for case in ("rank", "pack", "mcp")}
            delta = median(r["wall_ms"] for r in views["mcp"]) - median(r["wall_ms"] for r in views["pack"])
            baseline_rows.append((project, route, stats(views["rank"]), stats(views["pack"]),
                                  stats(views["mcp"]), f"{delta:.2f}",
                                  f"{median(r['wire_bytes'] for r in views['mcp']):,.0f}"))
            for case in ("rank", "pack"):
                group = exact("attribution", 3, project=project, route=route, case=case)
                medians = {key: median(r["stage_ms"].get(key, 0) for r in group)
                           for key in set().union(*(r["stage_ms"] for r in group))}
                totals = [sum(r["stage_ms"].values()) for r in group]
                share = median((r["stage_ms"].get("pagerank", 0) + r["stage_ms"].get("projection", 0))
                               / total for r, total in zip(group, totals))
                builds = {r["stage_calls"]["projection"] for r in group}
                stages.append((project, route, case, "/".join(map(str, sorted(builds))),
                               f"{100*share:.1f}%", f"{median(totals):.2f} / {max(totals):.2f}",
                               ", ".join(f"{k} {v:.2f}" for k, v in
                                         sorted(medians.items(), key=lambda a: (-a[1], a[0])))))
            profile, = exact("cprofile", 1, project=project, route=route)
            leaders = ", ".join(f"{f['function']} {f['self_ms']:.1f}"
                                for f in profile["top_self"][:4])
            hotspots.append((project, route, f"{profile['profile_total_ms']:.1f}", leaders))
    assert len(pick("baseline")) == 540
    table(("Project", "Route", "Direct rank", "Direct pack", "MCP pack", "MCP − direct P50", "Reply bytes P50"),
          baseline_rows)
    print("Exclusive instrumented stages in ms, n=3. Projection count is per call. "
          "`pack_other` includes sorting, token estimates and selection. `rank_other` includes "
          "reversal and score finalization when applicable.\n")
    table(("Project", "Route", "Case", "Projections", "Projection + PageRank", "P50 / max", "Stage medians"),
          stages)
    table(("Project", "Route", "cProfile total ms", "Top self time functions, ms"), hotspots)

    print("### Isolated cache experiments on pytest/deep\n")
    stream_rows = []
    for distinct in (24, 12, 3):
        uncached = None
        for method in STRATEGIES:
            samples = exact("stream", 24, distinct=distinct, strategy=method)
            summary, = exact("stream_cache", 1, distinct=distinct, strategy=method)
            hits, misses = (sum(r[k] for r in samples) for k in ("hits", "misses"))
            assert hits == summary["hits"] and misses == summary["misses"]
            tail = sorted(r["wall_ms"] for r in samples)[math.ceil(.95 * len(samples)) - 1]
            if method == "uncached":
                uncached = tail
            delta = uncached - tail
            stream_rows.append((distinct, 24 - distinct, method, f"{hits}/{hits + misses}" if hits+misses else "—",
                                summary["currsize"], stats(samples), f"{delta:.2f} ({100*delta/uncached:.1f}%)"))
    table(("Distinct rank keys", "Repeat requests", "Strategy", "Lookup hits", "Entries",
           "P50 / P95 ms", "P95 saved ms (%)"), stream_rows)
    cold = {method: exact("cold", 12, strategy=method) for method in STRATEGIES}
    base = median(r["wall_ms"] for r in cold["uncached"])
    table(("Cold strategy", "P50 / max ms", "Median overhead"), (
        (method, stats(group), f"{100*(median(r['wall_ms'] for r in group)/base - 1):+.1f}%")
        for method, group in cold.items()
    ))
    memory = pick("memory")
    assert Counter(r["strategy"] for r in memory) == {"projection": 2, "rank": 3}
    table(("Strategy", "Entries", "Retained MiB", "Peak traced MiB"), (
        (r["strategy"], r["entries"], f"{r['retained_bytes']/2**20:.2f}", f"{r['peak_bytes']/2**20:.2f}")
        for r in memory
    ))
    controls = exact("control", 2)
    assert all(r["package_checks"] == 5 and r["variant_keys"] and r["mutable_result"]
               and r["new_snapshot"] for r in controls)
    print("Exact output, argument variants, caller mutation and new-snapshot controls passed.")


if __name__ == "__main__":
    source = Path(sys.argv[1])
    opener = gzip.open if source.suffix == ".gz" else open
    with opener(source, "rt", encoding="utf-8") as stream:
        summarize([json.loads(line) for line in stream])
