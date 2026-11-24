"""R1-C137…C146, acceptance of the warm graph and the MCP transport."""

import asyncio
import io
import json
import sys
from pathlib import Path

import pytest

from codemap import store
from codemap.cli import _recipe_problem, main
from codemap.freshness import meta_path
from codemap.model import ANSWER_FORMAT, Edge, Graph, Node
from codemap.serve import session as session_module
from codemap.serve.server import serve_stdio
from codemap.serve.session import Session


def ask(session, op, **args):
    return session.handle({"op": op, "args": args})


@pytest.fixture
def snapshot(tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    src = package / "__init__.py"
    src.write_text("def f():\n    return 1\n")
    graph = tmp_path / "graph.json"
    assert main(["build", str(package), "-o", str(graph)]) == 0
    return src, graph, Session(store.load(graph), source_root=str(tmp_path), graph_path=str(graph),
                               currency_ttl=3600)


def test_limits_and_json_stdio(snapshot):
    _, _, session = snapshot
    for op, args, field in (
        ("search", {"term": "f"}, "limit"),
        ("impact", {"symbol": "f"}, "limit"),
        ("call_contract", {"symbol": "f", "full": True}, "limit"),
        ("tests", {"symbol": "f"}, "cap"),
        ("covers", {"test": "f"}, "cap"),
        ("semantic", {"query": "f"}, "limit"),
    ):
        args[field] = -1
        error = ask(session, op, **args)
        assert not error["ok"] and error["error_kind"] == "invalid_argument"
        assert error["answer_format"] == ANSWER_FORMAT and "currency" in error
    output = io.StringIO()
    serve_stdio(session, io.StringIO('{"op":"search","args":{"term":"f","limit":0}}\n'), output)
    reply = json.loads(output.getvalue())
    assert reply["result"] == []
    assert reply["limit"] == {"applied": 0, "returned": 0, "total": 1, "truncated": True}


def test_strict_check_uses_one_fresh_currency(snapshot):
    src, graph, session = snapshot
    assert ask(session, "stats")["currency"]["status"] == "current"
    absent = ask(session, "check", require_contract=True)
    assert absent["outcome"] == "verdict" and not absent["result"]["ok"]
    assert absent["result"]["refused"] == ["contract_required"]
    (src.parents[1] / "codemap.toml").write_text("[architecture]\nno_cycles = true\n")
    assert ask(session, "check", require_contract=True, require_current=True)["result"]["ok"]
    Path(meta_path(str(graph))).unlink()
    fallback = ask(session, "check", require_current=True)
    assert fallback["result"]["ok"] and fallback["currency"] == fallback["result"]["graph_currency"]
    src.write_text("\n" + src.read_text())
    behind = ask(session, "check", require_current=True)
    assert not behind["result"]["ok"] and behind["currency"]["status"] == "behind"
    unknown = ask(Session(Graph("pkg")), "check", require_current=True)
    assert not unknown["result"]["ok"] and unknown["result"]["refused"] == ["current_graph_required"]


def test_source_checks_file_even_when_currency_is_cached(snapshot):
    src, graph, session = snapshot
    first = ask(session, "source", symbol="pkg.f")
    assert first["result"]["status"] == "verified" and "def f" in first["result"]["code"]
    assert ask(session, "source", symbol="pkg")["result"]["status"] == "no_span"
    src.write_text("# inserted\n" + src.read_text())
    cached = ask(session, "source", symbol="pkg.f")
    assert cached["currency"]["status"] == "current"
    assert cached["result"]["status"] == "behind" and cached["result"]["code"] is None
    assert main(["build", str(src.parent), "-o", str(graph)]) == 0
    assert ask(session, "source", symbol="pkg.f")["result"]["status"] == "behind"
    assert ask(session, "reload")["result"]["reloaded"]
    assert ask(session, "source", symbol="pkg.f")["result"]["status"] == "verified"
    legacy = Session(store.load(graph), source_root=str(src.parents[1]))
    assert ask(legacy, "source", symbol="pkg.f")["result"]["status"] == "unverified"
    sidecar = Path(meta_path(str(graph)))
    meta = json.loads(sidecar.read_text())
    meta["scope"]["files"][0]["sha256"] = "0" * 64
    sidecar.write_text(json.dumps(meta))
    invalid = Session(store.load(graph), source_root=str(src.parents[1]), graph_path=str(graph))
    assert ask(invalid, "source", symbol="pkg.f")["result"]["status"] == "unverified"


def test_stage_publishes_refreshable_recipes(snapshot, monkeypatch):
    src, graph, _ = snapshot
    stage = graph.with_name("graph.next.json")
    for flags in ([], ["--incremental"]):
        if flags:
            stage.write_bytes(graph.read_bytes())
            Path(meta_path(str(stage))).write_bytes(Path(meta_path(str(graph))).read_bytes())
        assert main(["build", str(src.parent), *flags, "-o", str(stage),
                     "--recipe-output", str(graph)]) == 0
        stage.replace(graph)
        Path(meta_path(str(stage))).replace(meta_path(str(graph)))
        recipe = json.loads(Path(meta_path(str(graph))).read_text())["argv"]
        assert recipe[recipe.index("-o") + 1] == str(graph)
        assert ("--incremental" in recipe) == bool(flags)
        assert main(["refresh", str(graph)]) == 0
    from codemap import atomic

    final_sidecar = Path(meta_path(str(graph)))
    published = graph.read_bytes(), final_sidecar.read_bytes()
    recipe = json.loads(published[1])
    recipe["argv"] += ["--recipe-output", str(stage)]
    assert _recipe_problem(recipe, str(graph))
    write = atomic.write_text

    def fail_stage_recipe(path, content):
        if str(path) == meta_path(str(stage)):
            raise OSError("fixture metadata write failure")
        return write(path, content)

    monkeypatch.setattr(atomic, "write_text", fail_stage_recipe)
    assert main(["build", str(src.parent), "-o", str(stage),
                 "--recipe-output", str(graph)]) == 2
    assert (graph.read_bytes(), final_sidecar.read_bytes()) == published


def test_equal_counts_and_failed_index_on_reload(snapshot, monkeypatch):
    src, path, session = snapshot
    src.write_text("def g():\n    return 1\n")
    assert main(["build", str(src.parent), "-o", str(path)]) == 0
    query = session.query
    graph = session.graph
    with monkeypatch.context() as patch:
        def fail(_):
            raise RuntimeError("fixture indexing failure")
        patch.setattr(session_module, "Query", fail)
        assert not ask(session, "reload")["result"]["reloaded"]
        assert session.query is query and session.graph is graph
    changed = ask(session, "reload")["result"]
    assert changed["before"] == changed["after"] and changed["changed"]
    assert not ask(session, "reload")["result"]["changed"]


def test_structured_and_text_mcp_stdio(snapshot):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    src, graph, _ = snapshot

    async def check():
        server = StdioServerParameters(command=sys.executable, args=[
            "-m", "codemap", "serve", "--graph", str(graph), "--source-root",
            str(src.parents[1]), "--mcp",
        ])
        async with stdio_client(server) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                assert len(tools) == 29
                assert all(tool.output_schema and tool.annotations for tool in tools.values())
                assert tools["search"].input_schema["properties"]["limit"]["minimum"] == 0
                assert tools["reload"].annotations.read_only_hint is False
                assert tools["semantic_search"].annotations.open_world_hint
                for name, args, expected in [
                    ("search", {"term": "f", "limit": 0}, "ok"),
                    ("search", {"term": "f", "kind": "typo"}, "error"),
                    ("resolve", {"name": "missing"}, "not_found"),
                    ("pack", {"seeds": ["missing"]}, "refused"),
                    ("check", {"require_contract": True}, "verdict"),
                ]:
                    response = await client.call_tool(name, args)
                    assert response.structured_content == json.loads(response.content[0].text)
                    assert response.structured_content["outcome"] == expected
                    assert response.is_error == (expected == "error")
                    if name == "check":
                        assert not response.structured_content["result"]["ok"]
                negative = await client.call_tool("search", {"term": "f", "limit": -1})
                assert negative.is_error and negative.structured_content["error_kind"] == "invalid_argument"

    asyncio.run(asyncio.wait_for(check(), 15))


def test_locate_and_resolution(snapshot):
    _, _, session = snapshot
    assert not ask(session, "locate", file="pkg/__init__.py")["ok"]
    assert not ask(session, "locate", file="pkg/__init__.py", lines=[2, 1])["ok"]
    assert ask(session, "locate", file="pkg/__init__.py", line=1)["result"]["symbol"] == "pkg.f"
    assert ask(session, "resolve", name="missing")["resolved"]["found"] is False
    graph = Graph("pkg")
    for name in ("pkg.one.run", "pkg.two.run"):
        graph.add_node(Node(name, "function"))
    assert ask(Session(graph), "impact", symbol="run")["resolved"]["alternatives"] == list(graph.nodes)


def test_hotspot_totals_and_single_impact_walk(monkeypatch):
    graph = Graph("pkg")
    for i in range(16):
        name = f"pkg.f{i}"
        graph.add_node(Node(name, "function", extras={"complexity": {"cc": 8, "mi": 10, "sloc": 9}}))
        graph.add_edge(Edge("calls", "pkg.f0", name))
    session = Session(graph)
    hotspots = ask(session, "architecture")["result"]["hotspots"]
    assert len(hotspots["complex_functions"]) == 15
    assert hotspots["selection"]["totals"]["complex_functions"] == 16
    seen = []
    original = session.query.impact

    def impact(*args, **kwargs):
        seen.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(session.query, "impact", impact)
    compact = ask(session, "impact", symbol="pkg.f1", limit=0)
    full = ask(session, "impact", symbol="pkg.f1", limit=0, full=True)
    assert seen == ["pkg.f1", "pkg.f1"]
    assert compact["result"]["impact"][0]["refs"] == [] and "markdown" not in compact["result"]
    assert full["limit"]["applied"] is None and full["result"]["markdown"]


def test_uncertainty_and_local_file_contract(snapshot):
    _, graph, session = snapshot
    unknown = ask(session, "callers", symbol="pkg.f")["epistemic"]
    heuristic = Graph("pkg")
    heuristic.add_node(Node("pkg.f", "function"))
    heuristic.add_edge(Edge("calls", "pkg.dispatch", "pkg.f", {"resolution": "registry-candidate"}))
    candidates = Session(heuristic)
    broad = ask(candidates, "callers", symbol="pkg.f")["epistemic"]
    exact = ask(candidates, "callers", symbol="pkg.f", min_confidence="exact")["epistemic"]
    assert broad["may_miss"] and broad["may_include_candidates"] and exact["may_miss"]
    assert unknown["may_miss"] and "may_include_candidates" not in unknown
    assert "may_include_candidates" not in exact
    assert ask(session, "tests", symbol="pkg.f")["epistemic"]["test_evidence"] == "static_reachability"
    assert ask(session, "diff", base=str(graph))["result"]["summary"]["breaking_total"] == 0
    assert ask(session, "semantic", query="unused")["result"]["resolver"] is None
