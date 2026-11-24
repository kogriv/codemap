"""R1-C131 timing, attribution and isolated per-snapshot cache prototypes."""

import cProfile
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import pstats
import signal
import subprocess
import sys
import time
import tracemalloc
from collections import Counter
from contextlib import ExitStack
from functools import lru_cache, wraps
from itertools import combinations
from pathlib import Path
from unittest.mock import patch

from codemap import query as query_module
from codemap.model import Graph, Node
from codemap.query import RANKED_KINDS, Query
from codemap.serve import pack as pack_module
from codemap.store import load

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "r1c130"))
from measure import PROJECTS, pressure, scope_args, serve, timed


CASES = {"more-itertools": "fast", "rich": "deep", "pytest": "deep"}
ROUTES = ("global", "uses", "both")
STRATEGIES = ("uncached", "projection", "rank")
EDGE_TYPES = query_module._RANK_EDGE_TYPES
BUDGET = 2000
SAMPLES = 20


def measure(call):
    cpu_start = time.process_time_ns()
    wall_start = time.perf_counter_ns()
    value = call()
    return value, {"wall_ms": (time.perf_counter_ns() - wall_start) / 1e6,
                   "cpu_ms": (time.process_time_ns() - cpu_start) / 1e6}


def route_args(seed, route):
    return {} if route == "global" else {"seeds": (seed,), "direction": route}


class Spans:
    """Record exclusive wall times even when profiled functions nest."""

    def __init__(self):
        self.stack = []
        self.ns = Counter()
        self.calls = Counter()

    def wrap(self, stage, call):
        @wraps(call)
        def wrapped(*args, **kwargs):
            start = time.perf_counter_ns()
            self.stack.append(0)
            try:
                return call(*args, **kwargs)
            finally:
                duration = time.perf_counter_ns() - start
                self.ns[stage] += duration - self.stack.pop()
                self.calls[stage] += 1
                if self.stack:
                    self.stack[-1] += duration
        return wrapped

    def row(self, call, top):
        bindings = (
            (Query, "_rank_graph", "projection"), (Query, "rank", "rank_other"),
            (Query, "_expand_seeds", "rank_seed_expansion"),
            (Query, "seed_resolution", "seed_resolution"),
            (Query, "reachable_from", "reachability"),
            (query_module, "_pagerank", "pagerank"),
            (pack_module, "_coverage", "coverage"), (pack_module, "_item_text", "item_render"),
        )
        with ExitStack() as scopes:
            for owner, name, stage in bindings:
                scopes.enter_context(patch.object(owner, name, self.wrap(stage, getattr(owner, name))))
            result = (self.wrap("pack_other", call) if top == "pack" else call)()
        return result, {"stage_ms": {key: ns / 1e6 for key, ns in self.ns.items()},
                        "stage_calls": dict(self.calls)}


def function_profile(call):
    profiler = cProfile.Profile()
    profiler.runcall(call)
    stats = pstats.Stats(profiler)
    entries = []
    for (file, line, fn), (primitive, total, own, inclusive, _) in stats.stats.items():
        entries.append({"file": Path(file).name, "line": line, "function": fn, "calls": total,
                        "primitive": primitive, "self_ms": own * 1000, "cumulative_ms": inclusive * 1000})
    return {"profile_total_ms": stats.total_tt * 1000,
            "top_self": sorted(entries, key=lambda row: -row["self_ms"])[:16],
            "top_cumulative": sorted(entries, key=lambda row: -row["cumulative_ms"])[:16]}


def attach_cache(q, strategy):
    if strategy == "projection":
        original = q._rank_graph
        cached = lru_cache(maxsize=8)(original)

        def projection(edge_types=EDGE_TYPES, root=None):
            return cached(tuple(sorted(set(edge_types))), root)

        q._rank_graph = projection
        return cached
    if strategy == "rank":
        original = q.rank

        @lru_cache(maxsize=32)
        def cached(seeds, edge_types, root, direction):
            return original(seeds=seeds, edge_types=edge_types, root=root, direction=direction)

        def rank(*, seeds=(), edge_types=EDGE_TYPES, root=None, direction="uses"):
            return dict(cached(tuple(seeds or ()), tuple(sorted(set(edge_types))), root, direction))

        q.rank = rank
        return cached
    return None


def cache_info(cache):
    return cache.cache_info()._asdict() if cache else {"hits": 0, "misses": 0, "maxsize": 0, "currsize": 0}


def input_keys(graph, seed):
    candidates = sorted(n.id for n in graph.nodes.values()
                        if n.kind in RANKED_KINDS and n.extras.get("root", "core") == "core"
                        and n.id != seed)
    step = max(1, len(candidates) // 32)
    chosen = [seed, *candidates[::step]][:32]
    assert len(chosen) == 32
    return [route_args(name, "both" if index % 2 == 0 else "uses")
            for index, name in enumerate(chosen)]


def run_baselines(repo, artifact, graph, seed, log, emit):
    q = Query(graph)
    with serve(repo, artifact, log) as (mcp, startup):
        emit("mcp_start", **startup)
        for route in ROUTES:
            args = route_args(seed, route)
            rank = lambda: q.rank(**args)
            pack = lambda: pack_module.build_pack(q, budget=BUDGET, **args)
            expected_rank, expected_pack = rank(), pack()
            assert expected_rank and expected_pack["items"], route
            reply, _ = mcp.call("pack", {"budget": BUDGET, **args})
            assert reply["result"] == expected_pack, f"MCP parity: {route}"
            for case, operation, expected in (("rank", rank, expected_rank), ("pack", pack, expected_pack)):
                for i in range(1, SAMPLES + 1):
                    result, row = measure(operation)
                    assert result == expected, (route, case, i)
                    emit("baseline", route=route, case=case, i=i, **row)
            for i in range(1, SAMPLES + 1):
                reply, row = mcp.call("pack", {"budget": BUDGET, **args})
                assert reply["result"] == expected_pack, (route, i)
                emit("baseline", route=route, case="mcp", i=i, **row)
            for case, operation, expected in (("rank", rank, expected_rank), ("pack", pack, expected_pack)):
                for i in range(1, 4):
                    result, row = Spans().row(operation, case)
                    assert result == expected, (route, case, i)
                    emit("attribution", route=route, case=case, i=i, **row)
            emit("cprofile", route=route, **function_profile(pack))


def stream_trial(graph, keys, emit):
    for distinct in (24, 12, 3):
        requests = [
            {**keys[i % distinct], "budget": (1200, BUDGET)[(i + i // distinct) % 2]}
            for i in range(24)
        ]
        answers = []
        for strategy in STRATEGIES:
            q = Query(graph)
            cache = attach_cache(q, strategy)
            for i, args in enumerate(requests, 1):
                before = cache_info(cache)
                result, row = measure(lambda: pack_module.build_pack(q, **args))
                after = cache_info(cache)
                assert "error" not in result, (distinct, strategy, i)
                if strategy == "uncached":
                    answers.append(result)
                else:
                    assert result == answers[i - 1], (distinct, strategy, i)
                emit("stream", strategy=strategy, distinct=distinct, i=i,
                     rank_key_repeated=i > distinct, hits=after["hits"] - before["hits"],
                     misses=after["misses"] - before["misses"], **row)
            emit("stream_cache", strategy=strategy, distinct=distinct, **cache_info(cache))


def cold_trial(graph, keys, emit):
    for i, args in enumerate([{}, *keys[:11]], 1):
        expected = None
        for strategy in STRATEGIES:
            q = Query(graph)
            cache = attach_cache(q, strategy)
            result, row = measure(lambda: pack_module.build_pack(q, budget=BUDGET, **args))
            if strategy == "uncached":
                expected = result
            else:
                assert result == expected, (strategy, i)
            emit("cold", strategy=strategy, i=i, **row, **cache_info(cache))


def retained_allocations(graph, keys, emit):
    projection_keys = []
    for size in range(len(EDGE_TYPES), 0, -1):
        projection_keys.extend(combinations(sorted(EDGE_TYPES), size))
        if len(projection_keys) >= 8:
            break
    for strategy, capacity in (("projection", 8), ("rank", 32)):
        q = Query(graph)
        gc.collect()
        tracemalloc.start()
        cache = attach_cache(q, strategy)
        for i in range(capacity):
            if strategy == "projection":
                q._rank_graph(edge_types=projection_keys[i])
            else:
                q.rank(**keys[i])
            if i + 1 in (1, 8, capacity):
                gc.collect()
                retained, peak = tracemalloc.get_traced_memory()
                emit("memory", strategy=strategy, entries=i + 1, retained_bytes=retained,
                     peak_bytes=peak, **cache_info(cache))
        tracemalloc.stop()


def controls(graph, seed, emit):
    baseline = Query(graph)
    checks = [
        {"budget": BUDGET},
        {"budget": 1000, "seeds": (seed,), "direction": "uses"},
        {"budget": BUDGET, "seeds": (seed,), "direction": "both", "root": "core"},
        {"budget": BUDGET, "seeds": (seed,), "direction": "both", "root": "testing"},
        {"budget": BUDGET, "seeds": ("r1c131_no_such_seed",)},
    ]
    expected = [pack_module.build_pack(baseline, **args) for args in checks]
    marker = "r1c131_snapshot_marker"
    for strategy in ("projection", "rank"):
        q = Query(graph)
        cache = attach_cache(q, strategy)
        assert [pack_module.build_pack(q, **args) for args in checks] == expected
        expected_rank = baseline.rank(edge_types=("calls",), root="core")
        assert q.rank(edge_types=("calls",), root="core") == expected_rank
        assert cache_info(cache)["currsize"] > 0
        scores = q.rank()
        scores.clear()
        assert q.rank() == baseline.rank(), "caller mutated future scores"
        snapshot = Graph.from_dict(graph.to_dict())
        snapshot.add_node(Node(id=marker, kind="function"))
        new_query = Query(snapshot)
        fresh = attach_cache(new_query, strategy)
        assert cache_info(fresh)["currsize"] == 0
        assert marker in new_query.rank() and marker not in q.rank()
        emit("control", strategy=strategy, package_checks=len(checks), variant_keys=True,
             mutable_result=True, new_snapshot=True)


def prepare_graph(work, name, tier, out):
    commit, core, consumers, _, seed = PROJECTS[name]
    repo = work / "repos" / name
    observed = subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip()
    assert commit == observed
    artifact = out / f"{name}.json"
    cli = Path(sys.executable).with_name("codemap")
    flags = ("--deep", "--repeat", "1") if tier == "deep" else ()
    row, _ = timed([cli, "build", *scope_args(core, consumers), *flags, "-o", artifact],
                   repo, out / f"{name}-build.out")
    graph = load(artifact)
    assert graph.provenance["tier"] == tier and graph.provenance["tool"]["version"] == "0.0.49"
    assert seed in graph.nodes
    return repo, artifact, graph, seed, dict(row, revision=commit, seed=seed,
        graph_bytes=artifact.stat().st_size, nodes=len(graph.nodes), edges=len(graph.edges),
        scope_id=graph.provenance["scope_id"], artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())


def main(work):
    out = work / os.environ.get("R1C131_RUN", "run")
    out.mkdir()
    cpus = sorted(os.sched_getaffinity(0))
    assert len(cpus) == 2, cpus
    env = {name: importlib.metadata.version(name) for name in
           ("codmap", "mcp", "griffe", "jedi", "networkx")}
    assert env["codmap"] == "0.0.49"
    with (out / "samples.jsonl").open("w", buffering=1) as raw:
        def emit(phase, **row):
            raw.write(json.dumps({"phase": phase, **row}, sort_keys=True) + "\n")

        emit("host", affinity=cpus, python=platform.python_version(), kernel=platform.release(),
             packages=env, wheel_sha256=(work / "wheel.sha256").read_text().split()[0],
             installed=sorted((dist.metadata["Name"], dist.version)
                              for dist in importlib.metadata.distributions()),
             load=os.getloadavg(), pressure=pressure())
        for name, tier in CASES.items():
            def record(phase, **row):
                emit(phase, project=name, tier=tier, **row)

            print(f"{name}/{tier}: build", flush=True)
            repo, artifact, graph, seed, meta = prepare_graph(work, name, tier, out)
            record("graph", **meta)
            print(f"{name}/{tier}: baseline + attribution", flush=True)
            run_baselines(repo, artifact, graph, seed, out / f"{name}-mcp.log", record)
            if name == "pytest":
                keys = input_keys(graph, seed)
                print("pytest/deep: cache parity, streams and cold cost", flush=True)
                controls(graph, seed, record)
                stream_trial(graph, keys, record)
                cold_trial(graph, keys, record)
                print("pytest/deep: retained allocations", flush=True)
                retained_allocations(graph, keys, record)
            record("project_end", load=os.getloadavg(), pressure=pressure())
        emit("end", load=os.getloadavg(), pressure=pressure())


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.default_int_handler)
    main(Path(sys.argv[1]).resolve())
