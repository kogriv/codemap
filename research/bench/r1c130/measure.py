"""Collect R1-C130 measurements under the CPU affinity of the caller (Linux)."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import select
import signal
import subprocess as sp
import sys
import time
from contextlib import contextmanager
from pathlib import Path

PROJECTS = {
    "more-itertools": ("4aeb4338ae1407d8da9723e86da99efeb446f719", "more_itertools", (),
                       "more_itertools/recipes.py", "more_itertools.recipes.flatten"),
    "rich": ("6ac483cbea39cab124dfd3483bba70ffafb71050", "rich", (),
             "rich/style.py", "rich.console.Console.print"),
    "pytest": ("3d10b5148e03eb82b3ee29181dbdc73cf82699e2", "src/_pytest",
               ("src/pytest", "testing", "scripts"), "src/_pytest/timing.py",
               "_pytest.fixtures.FixtureRequest.getfixturevalue"),
}
EDIT = b"\n\ndef r1c130_benchmark_marker():\n    return 130\n"
MARKER = "r1c130_benchmark_marker"
CLI = Path(sys.executable).with_name("codemap")
CLOCK_TICKS = os.sysconf("SC_CLK_TCK")
INC = re.compile(r"\[incremental\] (\w+): (\d+) module\(s\) recomputed(?: \((.*)\))?")
LOAD = """
import json, sys, time
from codemap.store import load_snapshot
from codemap.serve.session import Session
start = time.perf_counter_ns()
graph, mtime = load_snapshot(sys.argv[1])
s = Session(graph, graph_path=sys.argv[1], served_mtime=mtime)
print(json.dumps({"load_ms": (time.perf_counter_ns()-start)/1e6, "nodes": len(s.graph.nodes)}))
"""


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def elapsed(start):
    return (time.perf_counter_ns() - start) / 1e6


def git(repo, *argv):
    return sp.check_output(["git", "-C", repo, *argv], text=True).strip()


def sidecar(graph):
    return graph.with_suffix(".json.meta.json")


def marker_ids(data):
    return [node["id"] for node in data["nodes"] if node["id"].endswith("." + MARKER)]


def core_edge_digest(data):
    core = {node["id"] for node in data["nodes"]
            if (node.get("extras") or {}).get("root", "core") == "core"}
    edges = [(e["source"], e["target"], e["extras"]) for e in data["edges"]
             if e["type"] == "calls" and e["source"] in core and e["target"] in core]
    return hashlib.sha256(json.dumps(edges, sort_keys=True).encode()).hexdigest()


@contextmanager
def process(args, **kwargs):
    child = sp.Popen(args, start_new_session=True, **kwargs)
    try:
        yield child
    finally:
        if child.stdin:
            child.stdin.close()
        try:
            # MCP exits on EOF; watcher and timed-command timeouts need a group stop.
            if child.stdin is None and child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
            child.wait(timeout=3)
        except sp.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
        if child.stdout:
            child.stdout.close()


def timed(args, cwd, output, timeout=900):
    usage = output.with_suffix(".time")
    stderr = output.with_suffix(".err")
    cmd = ["/usr/bin/time", "-o", usage, "-f", "%U %S %M %I %O", *args]
    with output.open("wb") as out, stderr.open("wb") as err:
        start = time.perf_counter_ns()
        with process(cmd, cwd=cwd, stdout=out, stderr=err) as child:
            # Wait on the kernel's exit event. Popen.wait(timeout) polls in userspace
            # and can add roughly 50 ms to short measurements on Linux.
            pidfd = os.pidfd_open(child.pid)
            try:
                if not select.select([pidfd], [], [], timeout)[0]:
                    raise sp.TimeoutExpired(cmd, timeout)
                code = child.wait()
            finally:
                os.close(pidfd)
        wall_ms = elapsed(start)
    message = stderr.read_text(errors="replace").strip()
    check(code == 0, f"{args[1]} rc={code}: {message[-2000:]}")
    user, system, rss, inputs, outputs = usage.read_text().strip().split()
    return {"wall_ms": wall_ms, "user_s": float(user), "sys_s": float(system),
            "hwm_kib": int(rss), "fs_in": int(inputs), "fs_out": int(outputs)}, message


def proc_sample(pid):
    root = Path("/proc") / str(pid)
    fields = (root / "stat").read_text().rsplit(")", 1)[1].split()
    status = {}
    for line in (root / "status").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in {"VmRSS", "VmHWM"}:
            status[key] = int(value.split()[0])
    io = {}
    for line in (root / "io").read_text().splitlines():
        key, value = line.split(":")
        if key in {"rchar", "wchar", "read_bytes", "write_bytes"}:
            io[key] = int(value)
    return {"cpu_s": sum(map(int, fields[11:15])) / CLOCK_TICKS,
            "cpu_self_s": sum(map(int, fields[11:13])) / CLOCK_TICKS,
            "rss_kib": status["VmRSS"], "hwm_kib": status["VmHWM"], **io}


class MCP:
    def __init__(self, child):
        self.child = child
        self.id = 0
        self.pending = b""

    def send(self, method, params, message_id=None):
        body = {"jsonrpc": "2.0", "method": method, "params": params}
        if message_id is not None:
            body["id"] = message_id
        self.child.stdin.write(json.dumps(body).encode() + b"\n")
        self.child.stdin.flush()

    def request(self, method, params, timeout=60):
        self.id += 1
        start = time.perf_counter_ns()
        deadline = time.monotonic() + timeout
        self.send(method, params, self.id)
        fd = self.child.stdout.fileno()
        while True:
            while b"\n" not in self.pending:
                remaining = max(0, deadline - time.monotonic())
                if not remaining or not select.select([fd], [], [], remaining)[0]:
                    raise TimeoutError(f"MCP timeout: {method} {params}")
                chunk = os.read(fd, 65536)
                check(chunk, f"MCP EOF for {method}")
                self.pending += chunk
            raw, self.pending = self.pending.split(b"\n", 1)
            wall = elapsed(start)
            message = json.loads(raw)
            if "id" not in message:
                continue
            check(message["id"] == self.id and "result" in message, str(message)[:1500])
            return message["result"], {"wall_ms": wall, "wire_bytes": len(raw) + 1}

    def initialize(self):
        answer, _ = self.request("initialize", {
            "protocolVersion": "2025-11-25",
            "clientInfo": {"name": "r1c130", "version": "1"},
            "capabilities": {},
        })
        self.send("notifications/initialized", {})
        return answer["protocolVersion"]

    def call(self, name, arguments, *, current=True, outcome="ok"):
        result, sample = self.request("tools/call", {"name": name, "arguments": arguments})
        body = result["structuredContent"]
        check(body["answer_format"] == 13 and not result.get("isError"), str(body)[:1000])
        check(body == json.loads(result["content"][0]["text"]), "structured/text mismatch")
        check(outcome is None or body["outcome"] == outcome, str(body)[:1000])
        check(not current or body["currency"]["status"] == "current", str(body["currency"]))
        return body, {**sample, "currency_age_s": body["currency"].get("checked_seconds_ago"),
                      "outcome": body["outcome"], "limit": body.get("limit")}


@contextmanager
def serve(repo, graph, log, *flags):
    args = [CLI, "serve", "--graph", graph, "--mcp", "--source-root", repo, *flags]
    with log.open("wb") as stderr:
        start = time.perf_counter_ns()
        with process(args, cwd=repo, stdin=sp.PIPE, stdout=sp.PIPE, stderr=stderr) as child:
            client = MCP(child)
            protocol = client.initialize()
            ready = elapsed(start)
            yield client, {"wall_ms": ready, "protocol": protocol, **proc_sample(child.pid)}


def scope_args(core, consumers):
    return [core, *(item for path in consumers for item in ("--consumer", path)),
            *(("--mode", "full") if consumers else ())]


def graph_record(graph, data):
    meta = json.loads(sidecar(graph).read_text())
    return {"graph_bytes": graph.stat().st_size, "meta_bytes": sidecar(graph).stat().st_size,
            "nodes": len(data["nodes"]), "edges": len(data["edges"]),
            "schema": data["codemap_schema"], "scope": meta["scope"]["profile"],
            "source_verified": meta.get("source_verified"),
            "behavior": data["provenance"].get("behavior")}


def builds(repo, roots, edited, tier, dest, emit, samples):
    flags = ["--deep", "--repeat", "1"] if tier == "deep" else []
    base = [CLI, "build", *roots, *flags]
    for i in range(1, 4):
        graph = dest / f"full-{i}.json"
        row, _ = timed([*base, "-o", graph], repo, dest / f"build-{i}.out")
        data = json.loads(graph.read_text())
        check(data["codemap_schema"] == "0.13" and not marker_ids(data), "bad full baseline")
        check(data["provenance"]["tier"] == tier, "declared tier mismatch")
        emit("full", i=i, **row, **graph_record(graph, data))
    baseline = json.loads(sidecar(graph).read_text())["scope"]["scope_id"]
    original = edited.read_bytes()
    expected = core_edge_digest(data)
    for variant, count in (("edit", samples), ("noop", 5)):
        for i in range(1, count + 1):
            marker = variant == "edit" and i % 2 == 1
            if variant == "edit":
                edited.write_bytes(original + EDIT if marker else original)
            before = (graph.stat().st_mtime_ns, graph.stat().st_size)
            before_bytes = graph.read_bytes() if variant == "noop" else None
            row, stderr = timed([*base, "-o", graph, "--incremental"],
                                repo, dest / f"{variant}-{i}.out")
            decision = INC.search(stderr)
            check(decision, f"missing incremental mode: {stderr}")
            mode, affected, reason = decision.groups()
            after_bytes = graph.read_bytes()
            data = json.loads(after_bytes)
            restored = json.loads(sidecar(graph).read_text())["scope"]["scope_id"] == baseline
            stable = before == (graph.stat().st_mtime_ns, graph.stat().st_size)
            edges_equal = core_edge_digest(data) == expected if not marker and tier == "fast" else None
            emit(variant, i=i, mode=mode, affected=int(affected), reason=reason,
                 marker=marker_ids(data), scope_restored=restored, artifact_unchanged=stable,
                 graph_bytes_equal=before_bytes == after_bytes if before_bytes is not None else None,
                 core_calls_equal=edges_equal, **row)
            check(bool(marker_ids(data)) == marker and restored != marker, "edit not reflected")
            # A parity failure is a product finding. Keep recording timings with
            # the divergence flagged so it cannot masquerade as a valid control.
            if variant == "noop":
                check(mode == "unchanged" and int(affected) == 0, f"no-op mode was {mode}")
    return graph


def mcp_measure(repo, graph, symbol, dest, emit, samples):
    for i in range(1, 4):
        row, _ = timed([sys.executable, "-c", LOAD, graph], repo, dest / f"load-{i}.out", 60)
        load = json.loads((dest / f"load-{i}.out").read_text())
        emit("load", i=i, **row, **load)
        with serve(repo, graph, dest / f"mcp-{i}.log") as (mcp, start):
            emit("mcp_start", i=i, **start)
            if i < 3:
                continue
            result, _ = mcp.request("tools/list", {})
            check(all(t.get("outputSchema") for t in result["tools"]), "missing MCP output schema")
            resolved, _ = mcp.call("resolve", {"name": symbol})
            check(resolved["result"]["id"] == symbol, str(resolved))
            ops = [
                ("stats", "stats", {}),
                ("search", "search", {"term": symbol.rsplit(".", 1)[-1]}),
                ("impact0", "impact", {"symbol": symbol, "limit": 0}),
                ("impact40", "impact", {"symbol": symbol}),
                ("impact_full", "impact", {"symbol": symbol, "full": True}),
                ("pack_global", "pack", {}),
                ("pack_seed", "pack", {"seeds": [symbol]}),
            ]
            for case, operation, args in ops:
                mcp.call(operation, args)
                for j in range(1, samples + 1):
                    _, row = mcp.call(operation, args)
                    emit("mcp", case=case, i=j, **row)
            emit("mcp_resident", **proc_sample(mcp.child.pid))


def watch_measure(repo, roots, graph, edited, dest, emit, seconds, samples):
    with serve(repo, graph, dest / "fresh.log", "--currency-ttl", "0") as (mcp, _):
        mcp.call("stats", {})
        for i in range(1, samples + 1):
            _, row = mcp.call("stats", {})
            emit("mcp", case="stats_forced", i=i, **row)
    original = edited.read_bytes()
    source_log = dest / "watch-source.log"
    server_log = dest / "watch-mcp.log"
    try:
        with source_log.open("wb") as log, process(
            [CLI, "watch", *roots, "-o", graph], cwd=repo, stdout=sp.DEVNULL, stderr=log
        ) as watcher, serve(repo, graph, server_log, "--watch", "--currency-ttl", "0") as (mcp, _):
            mcp.call("stats", {})
            deadline = time.monotonic() + 30
            while "(poll " not in source_log.read_text(errors="replace"):
                check(watcher.poll() is None and time.monotonic() < deadline, "watch not ready")
                time.sleep(0.1)
            time.sleep(2)
            artifacts = (graph, sidecar(graph))
            before_artifacts = [p.stat().st_mtime_ns for p in artifacts]
            pids = {"source": watcher.pid, "artifact": mcp.child.pid}
            before = {name: proc_sample(pid) for name, pid in pids.items()}
            start = time.perf_counter_ns()
            time.sleep(seconds)
            window = elapsed(start)
            after = {name: proc_sample(pid) for name, pid in pids.items()}
            stable = before_artifacts == [p.stat().st_mtime_ns for p in artifacts]
            for name, snapshot in after.items():
                delta = {key: value - before[name][key] for key, value in snapshot.items()
                         if key not in {"rss_kib", "hwm_kib"}}
                emit("watch_idle", case=name, wall_ms=window, artifact_unchanged=stable,
                     **delta, rss_kib=snapshot["rss_kib"], hwm_kib=snapshot["hwm_kib"])
            check(stable, "watch regenerated the graph at idle")
            data = json.loads(graph.read_text())
            check(not marker_ids(data), "watch baseline already contains marker")
            edited.write_bytes(original + EDIT)
            start = time.perf_counter_ns()
            tries = 0
            while elapsed(start) < 120_000:
                tries += 1
                reply, _ = mcp.call("resolve", {"name": MARKER}, current=False, outcome=None)
                if reply["outcome"] == "ok" and reply["currency"]["status"] == "current":
                    emit("watch_edit", wall_ms=elapsed(start), tries=tries,
                         symbol=reply["result"]["id"], currency=reply["currency"]["status"],
                         rebuild_log=[line.replace(str(graph), graph.name) for line in
                                      source_log.read_text(errors="replace").splitlines()
                                      if line.startswith("[watch]") and "rebuilt in" in line],
                         reload_log=[line.replace(str(graph), graph.name) for line in
                                     server_log.read_text(errors="replace").splitlines()
                                     if line.startswith("[watch] reloaded")])
                    return
                time.sleep(0.25)
            raise TimeoutError("watch never served the edited symbol")
    finally:
        edited.write_bytes(original)


def pressure():
    return {kind: (Path("/proc/pressure") / kind).read_text().strip()
            for kind in ("cpu", "io", "memory")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--projects", nargs="+", choices=PROJECTS, default=list(PROJECTS))
    parser.add_argument("--tiers", nargs="+", choices=("fast", "deep"), default=("fast", "deep"))
    parser.add_argument("--output", type=Path, help="new output directory, absolute or relative to work")
    parser.add_argument("--smoke", action="store_true", help="two repeats, three seconds idle")
    args = parser.parse_args()
    work = args.work.resolve()
    samples = 2 if args.smoke else 20
    out = work / (args.output or ("smoke" if args.smoke else "run"))
    out.mkdir()
    cpus = sorted(os.sched_getaffinity(0))
    check(len(cpus) <= 2, f"expected at most 2 allowed CPUs, got {cpus}")
    with (out / "samples.jsonl").open("w", buffering=1) as output:
        def emit(phase, **row):
            output.write(json.dumps({"phase": phase, **row}, sort_keys=True) + "\n")

        emit("host", protocol="smoke" if args.smoke else "full", cpus=cpus,
             kernel=platform.release(), python=platform.python_version(),
             versions={p: importlib.metadata.version(p) for p in
                       ("codmap", "mcp", "griffe", "jedi", "networkx")},
             installed=sorted((dist.metadata["Name"], dist.version)
                              for dist in importlib.metadata.distributions()),
             wheel_sha256=(work / "wheel.sha256").read_text().split()[0],
             filesys=sp.check_output(["findmnt", "-no", "FSTYPE", "-T", work], text=True).strip(),
             pressure=pressure(), load=os.getloadavg())
        errors = 0
        for project in args.projects:
            commit, core, consumers, target, symbol = PROJECTS[project]
            repo = work / "repos" / project
            check(git(repo, "rev-parse", "HEAD") == commit, f"{project} commit mismatch")
            check(not git(repo, "status", "--porcelain"), f"{project} dirty before benchmark")
            edited = repo / target
            original = edited.read_bytes()
            roots = scope_args(core, consumers)
            for tier in args.tiers:
                def record(phase, **row):
                    emit(phase, project=project, tier=tier, **row)

                dest = out / f"{project}-{tier}"
                dest.mkdir()
                print(f"{project} {tier}: full + incremental", flush=True)
                record("series_start", commit=commit, core=core, consumers=consumers,
                       symbol=symbol, pressure=pressure(), load=os.getloadavg())
                try:
                    graph = builds(repo, roots, edited, tier, dest, record, samples)
                    print(f"{project} {tier}: load + MCP", flush=True)
                    mcp_measure(repo, graph, symbol, dest, record, samples)
                    if tier == "fast":
                        print(f"{project} {tier}: watch", flush=True)
                        watch_measure(repo, roots, graph, edited, dest, record,
                                      3 if args.smoke else 15, samples)
                except Exception as exc:
                    errors += 1
                    record("failure", error=type(exc).__name__, detail=str(exc).replace(str(work), "$RUN"))
                    print(f"{project} {tier}: {exc}", file=sys.stderr, flush=True)
                finally:
                    if edited.read_bytes() != original:
                        edited.write_bytes(original)
                record("series_end", pressure=pressure(), load=os.getloadavg())
            check(not git(repo, "status", "--porcelain"), f"{project} dirty after benchmark")
        emit("end", failures=errors, pressure=pressure(), load=os.getloadavg())
    return min(errors, 1)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.default_int_handler)
    raise SystemExit(main())
