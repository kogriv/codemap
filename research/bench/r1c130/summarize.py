"""Render measurements and check sample coverage for R1-C130."""

import argparse
import gzip
import json
import math
import statistics
from collections import Counter
from pathlib import Path

from measure import PROJECTS

WARM = ("stats", "search", "impact0", "impact40", "impact_full", "pack_global", "pack_seed")


def p95(values):
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def median(rows, key):
    return statistics.median(row[key] for row in rows)


def format_ms(value):
    return f"{value:,.2f}"


def cell(rows, key="wall_ms"):
    if not rows:
        return "—"
    values = [row[key] for row in rows]
    tail = p95(values) if len(values) >= 20 else max(values)
    return f"{format_ms(statistics.median(values))} / {format_ms(tail)}"


def table(headers, rows):
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        print("| " + " | ".join(str(value) for value in row) + " |")
    print()


def mode_counts(rows):
    return ", ".join(f"{mode}×{n}" for mode, n in Counter(row["mode"] for row in rows).items()) or "—"


def mem(rows):
    return f"{max(row['hwm_kib'] for row in rows) / 1024:.1f}" if rows else "—"


def cpu(rows):
    if not rows:
        return "—"
    seconds = [row["user_s"] + row["sys_s"] if "user_s" in row else row["cpu_s"]
               for row in rows]
    return f"{statistics.median(seconds):.2f}"


def fs_io(rows):
    if not rows or "fs_in" not in rows[0]:
        return "—"
    return f"{median(rows, 'fs_in'):g}/{median(rows, 'fs_out'):g}"


def summarize(rows, samples):
    def pick(phase, tier=None, case=None):
        return [r for r in rows if r["phase"] == phase
                and (tier is None or r.get("tier") == tier)
                and (case is None or r.get("case") == case)]

    hosts = pick("host")
    if not hosts:
        raise ValueError("Missing host record")
    host = hosts[0]
    print(f"Python {host['python']}, Linux {host['kernel']}, {host['filesys']}, CPU affinity "
          f"`{','.join(map(str, host['cpus']))}`. "
          + ", ".join(f"{k} {v}" for k, v in host["versions"].items()) + ".\n")

    errors = []
    print("### Scope and graph size\n")
    summaries = []
    data = {}
    for project in PROJECTS:
        for tier in ("fast", "deep"):
            subset = [r for r in rows if r.get("project") == project and r.get("tier") == tier]

            def select_rows(phase, case=None):
                return [r for r in subset if r["phase"] == phase
                        and (case is None or r.get("case") == case)]

            full = select_rows("full")
            edit = select_rows("edit")
            noop = select_rows("noop")
            load = select_rows("load")
            starts = select_rows("mcp_start")
            idle = select_rows("watch_idle")
            watch_edit = select_rows("watch_edit")
            resident = select_rows("mcp_resident")
            warm = {op: select_rows("mcp", op) for op in WARM}
            forced = select_rows("mcp", "stats_forced")
            for case, group, expected in [
                ("full", full, 3), ("edit", edit, samples), ("noop", noop, 5),
                ("load", load, 3), ("mcp_start", starts, 3), ("mcp_resident", resident, 1),
                ("watch_idle", idle, 2 if tier == "fast" else 0),
                ("watch_edit", watch_edit, 1 if tier == "fast" else 0),
                ("stats_forced", forced, samples if tier == "fast" else 0),
                *((case, group, samples) for case, group in warm.items()),
            ]:
                if len(group) != expected:
                    errors.append(f"{project}/{tier}/{case}: {len(group)}/{expected}")
                elif group and all("i" in row for row in group):
                    if sorted(row["i"] for row in group) != list(range(1, expected + 1)):
                        errors.append(f"{project}/{tier}/{case}: mixed or duplicate sample indices")
            data[(project, tier)] = (full, edit, noop, load, starts, idle, watch_edit,
                                     resident, warm, forced)
            if full:
                row = full[-1]
                scope = row["scope"]
                summaries.append([project, tier, scope["file_count"], scope["loc_total"],
                                  f"{scope['total_bytes']/2**20:.2f}", row["nodes"], row["edges"],
                                  f"{row['graph_bytes']/2**20:.2f}", f"{row['meta_bytes']/2**10:.1f}"])
    table(("Project", "Tier", "Files", "Lines", "Input MiB", "Nodes", "Edges",
           "Graph MiB", "Sidecar KiB"), summaries)

    print("### Build and startup\n")
    print("Times in ms. Cells show median / P95 for n≥20, median / maximum otherwise. "
          "Full samples are listed in run order. CPU and filesystem I/O counters are medians, "
          "RSS is maximum KiB converted to MiB.\n")
    for project, tier in data:
        full, edit, noop, load, starts, idle, watch_edit, resident, warm, forced = data[(project, tier)]
        print(f"**{project}, {tier}.** Full runs (ms): "
              + ", ".join(format_ms(row["wall_ms"]) for row in full) + ".\n")
        table(("Phase", "n", "Wall ms", "CPU s", "Peak MiB", "FS in/out", "Modes"), [
            (phase, len(group), cell(group), cpu(group), mem(group), fs_io(group), mode)
            for phase, group, mode in (("Full", full, "—"), ("Edited", edit, mode_counts(edit)),
                                      ("Unchanged", noop, mode_counts(noop)),
                                      ("Load + index", load, "—"), ("MCP initialize", starts, "—"))
        ])
        if load:
            print(f"Internal graph load + index median / max: {cell(load, 'load_ms')} ms.\n")
        if noop:
            byte_equal = sum(row["graph_bytes_equal"] for row in noop)
            touches = sum(not row["artifact_unchanged"] for row in noop)
            print(f"No-op control: {byte_equal}/{len(noop)} graph payloads byte-identical, "
                  f"artifact metadata touched on {touches}/{len(noop)} calls.\n")
        reverted = [row for row in edit if row["core_calls_equal"] is not None]
        if reverted:
            equal = sum(row["core_calls_equal"] for row in reverted)
            print(f"Reverted fast core calls matched the full graph in {equal}/{len(reverted)} samples.\n")

    print("### Warm MCP STDIO\n")
    print("Each cell is median / P95 wall time (ms). Wire size is median / maximum "
          "in bytes, including both output representations.\n")
    warm_rows = []
    for (project, tier), (_, _, _, _, _, _, _, resident, warm, forced) in data.items():
        if resident:
            print(f"- {project}/{tier} warm resident RSS "
                  f"{resident[0]['rss_kib']/1024:.1f} MiB, peak ({mem(resident)} MiB).")
        for op, group in list(warm.items()) + ([("stats_forced", forced)] if tier == "fast" else []):
            if group:
                warm_rows.append((project, tier, op, len(group), cell(group),
                                  f"{median(group, 'wire_bytes'):,.0f} / "
                                  f"{max(row['wire_bytes'] for row in group):,}"))
    print()
    table(("Project", "Tier", "Operation", "n", "Wall ms", "Wire bytes"), warm_rows)

    print("### Watch\n")
    idle_rows = []
    for (project, tier), (_, _, _, _, _, idle, edits, _, _, _) in data.items():
        for row in idle:
            idle_rows.append((project, row["case"], f"{row['wall_ms']/1000:.2f}",
                              f"{100_000*row['cpu_s']/row['wall_ms']:.2f}",
                              f"{row['rss_kib']/1024:.1f}", f"{row['hwm_kib']/1024:.1f}",
                              f"{row['rchar']:,}/{row['wchar']:,}",
                              f"{row['read_bytes']:,}/{row['write_bytes']:,}"))
        for row in edits:
            print(f"- {project}: save to current MCP answer {row['wall_ms']/1000:.2f} s "
                  f"({row['tries']} probes).")
    print()
    table(("Project", "Watcher", "Window s", "CPU % of one core", "RSS MiB", "Peak MiB",
           "Logical bytes r/w", "Physical bytes r/w"), idle_rows)

    failures = pick("failure")
    if not pick("end"):
        errors.append("No end marker")
    print(f"Recorded failures: {len(failures)}.\n")
    for row in failures:
        print(f"- {row['project']}/{row['tier']}: {row['error']}: {row['detail']}")
    if errors:
        print("\nIncomplete sample groups:\n")
        print("\n".join(f"- {error}" for error in errors))
    return bool(errors or failures)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("samples", type=Path)
    parser.add_argument("--repeats", type=int, default=20)
    args = parser.parse_args()
    open_file = gzip.open if args.samples.suffix == ".gz" else open
    with open_file(args.samples, "rt", encoding="utf-8") as stream:
        raise SystemExit(summarize([json.loads(line) for line in stream], args.repeats))
