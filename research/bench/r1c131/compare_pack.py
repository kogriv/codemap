"""Compare the two R1-C131 follow-ups on the same published graph."""

import hashlib
import json
import math
import os
import platform
import signal
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "r1c130"))
from measure import MCP, pressure, proc_sample, process


VARIANTS = ("baseline", "page", "projection", "combined")
ANCHOR = "_pytest.fixtures.FixtureRequest.getfixturevalue"
GRAPH_SHA = "87d408f8cec849a72150d7d0e497c92ba09165ee56d60057ed9dc15af70b43e5"


def direct_checks(path):
    import codemap
    from codemap.query import Query
    from codemap.serve.pack import build_pack
    from codemap.store import load

    q = Query(load(path))
    original = q._rank_graph
    calls = 0

    def projection(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    q._rank_graph = projection
    cases = [
        {},
        {"seeds": [ANCHOR], "direction": "uses"},
        {"seeds": [ANCHOR], "direction": "both"},
        {"seeds": [ANCHOR], "direction": "both"},
        {"seeds": ["__init__"], "direction": "both"},
        {"seeds": [ANCHOR, ANCHOR, "r1c131_missing"]},
        {"seeds": ["r1c131_missing"]},
        {"seeds": [ANCHOR], "root": "core"},
        {"seeds": [ANCHOR], "root": "testing"},
        {"seeds": ["src/_pytest/fixtures.py"], "direction": "uses"},
    ]
    values, counts = [], []
    for args in cases:
        before = calls
        values.append(build_pack(q, budget=2000, **args))
        counts.append(calls - before)
    values.append(build_pack(q, budget=0, seeds=[ANCHOR]))
    assert values[4]["seeds"]["requested"][0]["ambiguous"], "ambiguous control failed"
    assert values[6]["status"] == "refused", "unknown seed control failed"
    ranks = [q.rank(**args) for args in cases]
    ranks.append(q.rank(edge_types=("calls",), root="core"))
    return {"values": values, "ranks": ranks, "counts": counts, "module": codemap.__file__}


def env_for(work, variant):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    if variant != "baseline":
        env["PYTHONPATH"] = str(work / variant)
    return env


@contextmanager
def server(repo, graph, work, variant):
    args = [sys.executable, "-m", "codemap", "serve", "--mcp", "--graph", graph,
            "--source-root", repo]
    with (work / f"{variant}-mcp.log").open("wb") as stderr:
        with process(args, cwd=repo, env=env_for(work, variant),
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr) as child:
            client = MCP(child)
            protocol = client.initialize()
            yield client, protocol


def choose_seeds(data):
    eligible = sorted(node["id"] for node in data["nodes"]
                      if node["kind"] in ("module", "class", "function")
                      and node["extras"].get("root", "core") == "core"
                      and node["id"] != ANCHOR)
    seeds = [ANCHOR, *(eligible[round(i * (len(eligible) - 1) / 30)] for i in range(31))]
    assert len(set(seeds)) == 32
    return seeds


def variant_quantiles(rows):
    values = sorted(row["wall_ms"] for row in rows)
    assert len(values) == 32
    return {"p50_ms": median(values), "p95_ms": values[math.ceil(.95 * len(values)) - 1]}


def run(work, repo, graph):
    sha = hashlib.sha256(graph.read_bytes()).hexdigest()
    assert sha == GRAPH_SHA, sha
    cpus = sorted(os.sched_getaffinity(0))
    assert len(cpus) == 2, cpus
    seeds = choose_seeds(json.loads(graph.read_text()))
    with (work / "samples.jsonl").open("w", buffering=1) as raw:
        def record(phase, **row):
            raw.write(json.dumps({"phase": phase, **row}, sort_keys=True) + "\n")

        record("host", graph_sha256=sha, affinity=cpus,
               python=platform.python_version(), pressure=pressure())
        expected = None
        for variant in VARIANTS:
            direct = subprocess.check_output([sys.executable, __file__, "--direct", graph],
                                             cwd=repo, env=env_for(work, variant), timeout=60)
            result = json.loads(direct)
            if variant != "baseline":
                assert Path(result["module"]).is_relative_to(work / variant), variant
            counts = result["counts"]
            assert counts[0] == counts[6] == 1, (variant, counts)
            seeded_count = 1 if variant in ("projection", "combined") else 3
            assert counts[1:5] == [seeded_count] * 4, (variant, counts)
            signature = json.dumps([result["values"], result["ranks"]],
                                   ensure_ascii=False, sort_keys=True)
            if expected is None:
                expected = signature
            assert signature == expected, f"Direct rank/pack parity: {variant}"
            record("parity", variant=variant, projection_counts=counts,
                   result_sha256=hashlib.sha256(signature.encode()).hexdigest())
        print("Direct rank and pack parity passed for all variants", flush=True)

        groups = {}
        with ExitStack() as scopes:
            clients = {}
            for variant in VARIANTS:
                client, protocol = scopes.enter_context(server(repo, graph, work, variant))
                clients[variant] = client
                record("startup", variant=variant, protocol=protocol)
            for route in ("both", "uses", "global"):
                print(f"MCP {route}: interleaved variants, one request in flight", flush=True)
                values = {variant: [] for variant in VARIANTS}
                warm_args = {"budget": 2000} if route == "global" else {
                    "budget": 2000, "direction": route, "seeds": [seeds[0]]}
                for client in clients.values():
                    client.call("pack", warm_args)
                for i, seed in enumerate(seeds):
                    args = {"budget": 2000} if route == "global" else {
                        "budget": 2000, "direction": route, "seeds": [seed]}
                    offset = i % len(VARIANTS)
                    expected_pack = None
                    for variant in VARIANTS[offset:] + VARIANTS[:offset]:
                        reply, sample = clients[variant].call("pack", args)
                        if expected_pack is None:
                            expected_pack = reply["result"]
                        assert reply["result"] == expected_pack, (route, seed, variant)
                        values[variant].append(sample)
                        record("mcp", route=route, variant=variant, i=i+1,
                               seed=None if route == "global" else seed, **sample)
                groups[route] = {v: variant_quantiles(rows) for v, rows in values.items()}
            for variant, client in clients.items():
                record("resident", variant=variant, **proc_sample(client.child.pid))

        baseline = groups["both"]["baseline"]["p95_ms"]
        passes = {}
        for variant in VARIANTS[1:]:
            saving = baseline - groups["both"][variant]["p95_ms"]
            passes[variant] = saving >= 50 or saving >= .20 * baseline
        if passes["page"] and passes["projection"] and passes["combined"]:
            selected = "combined"
        elif passes["page"] or passes["projection"]:
            eligible = (v for v in ("page", "projection") if passes[v])
            selected = min(eligible, key=lambda v: groups["both"][v]["p95_ms"])
        else:
            selected = "baseline"
        outcome = {"groups": groups, "passes": passes, "selected": selected}
        record("end", **outcome, pressure=pressure())
        (work / "decision.json").write_text(json.dumps(outcome, indent=2) + "\n")
        print(json.dumps(outcome), flush=True)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.default_int_handler)
    if sys.argv[1] == "--direct":
        print(json.dumps(direct_checks(Path(sys.argv[2])), ensure_ascii=False, sort_keys=True))
    else:
        run(*(Path(p).resolve() for p in sys.argv[1:]))
