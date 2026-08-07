"""R1-C18 acceptance — module communities + call flows (built on our own graph).

Inspired by the GitNexus разбор (Leiden clusters + flow tracing); computed
natively and deterministically. Two import clusters + a call chain give precise
control; also smoked on the CLI and serve.
"""

from __future__ import annotations

from codemap import store
from codemap.cli import main
from codemap.model import Edge, Graph, Node
from codemap.query import Query
from codemap.serve.session import Session
from codemap.serve.subsystems import render_communities, render_flows


def _mod(g: Graph, nid: str) -> None:
    g.add_node(Node(id=nid, kind="module", extras={"root": "core"}))


def _imports(g: Graph, src: str, tgt: str) -> None:
    g.add_edge(Edge(type="imports", source=src, target=tgt))


def _two_clusters() -> Graph:
    """Two import triangles (layers a, b) joined by one bridge edge."""
    g = Graph(target="pkg")
    a = ["pkg.a.m1", "pkg.a.m2", "pkg.a.m3"]
    b = ["pkg.b.n1", "pkg.b.n2", "pkg.b.n3"]
    for m in a + b:
        _mod(g, m)
    for trio in (a, b):
        _imports(g, trio[0], trio[1])
        _imports(g, trio[1], trio[2])
        _imports(g, trio[2], trio[0])
    _imports(g, "pkg.a.m1", "pkg.b.n1")  # bridge
    return g


def _call_chain() -> Graph:
    g = Graph(target="pkg")
    for n in "EFGH":
        g.add_node(Node(id=f"pkg.{n}", kind="function", extras={"root": "core"}))
    g.add_edge(Edge(type="calls", source="pkg.E", target="pkg.F"))  # d1
    g.add_edge(Edge(type="calls", source="pkg.F", target="pkg.G"))  # d2
    g.add_edge(Edge(type="calls", source="pkg.G", target="pkg.H"))  # d3
    return g


# -- communities -------------------------------------------------------------

def test_communities_split_two_clusters():
    comms = Query(_two_clusters()).communities()
    assert len(comms) == 2
    labels = {c["label"] for c in comms}
    assert labels == {"a", "b"}
    for c in comms:
        assert c["size"] == 3
        assert all(m.startswith(f"pkg.{c['label']}.") for m in c["modules"])


def test_communities_deterministic():
    g = _two_clusters()
    assert Query(g).communities() == Query(g).communities()


def test_communities_empty_without_import_edges():
    g = Graph(target="pkg")
    g.add_node(Node(id="pkg.solo", kind="module", extras={"root": "core"}))
    assert Query(g).communities() == []


# -- flows -------------------------------------------------------------------

def test_entry_points_are_call_forest_roots():
    assert Query(_call_chain()).entry_points() == ["pkg.E"]  # only E has no callers


def test_flow_forward_by_distance():
    f = Query(_call_chain()).flow("pkg.E", max_depth=3)
    assert f["reached"] == 3
    assert f["max_depth"] == 3
    dists = {(e["source"], e["target"]): e["distance"] for e in f["edges"]}
    assert dists == {("pkg.E", "pkg.F"): 1, ("pkg.F", "pkg.G"): 2, ("pkg.G", "pkg.H"): 3}


def test_flow_depth_bounded():
    f = Query(_call_chain()).flow("pkg.E", max_depth=1)
    assert f["reached"] == 1 and f["max_depth"] == 1


def test_flow_leaf_symbol():
    f = Query(_call_chain()).flow("pkg.H")
    assert f["edges"] == [] and f["reached"] == 0


# -- rendering ---------------------------------------------------------------

def test_render_communities_markdown():
    md = render_communities(Query(_two_clusters()))
    assert "Subsystems" in md and "3 modules" in md


def test_render_flows_entry_summary_and_symbol():
    q = Query(_call_chain())
    overview = render_flows(q)                       # no symbol → entry points
    assert "entry points" in overview and "pkg.E" in overview
    detail = render_flows(q, "E", depth=3)           # symbol → forward chain
    assert "reaches 3" in detail and "pkg.E → pkg.F" in detail


# -- CLI + serve -------------------------------------------------------------

def test_cli_report_communities_and_flows(tmp_path, capsys):
    gpath = tmp_path / "imports.json"
    store.save(_two_clusters(), str(gpath))
    assert main(["report", "communities", "--graph", str(gpath)]) == 0
    assert "Subsystems" in capsys.readouterr().out

    fpath = tmp_path / "calls.json"
    store.save(_call_chain(), str(fpath))
    assert main(["report", "flows", "--graph", str(fpath), "--symbol", "E",
                 "--depth", "3"]) == 0
    assert "reaches 3" in capsys.readouterr().out


def test_serve_ops_communities_and_flows():
    s = Session(_call_chain())
    assert s.handle({"op": "communities", "args": {}})["ok"]
    env = s.handle({"op": "flows", "args": {"symbol": "E", "depth": 3}})
    assert env["ok"] and env["result"]["reached"] == 3
    eps = s.handle({"op": "flows", "args": {}})
    assert eps["result"]["entry_points"] == ["pkg.E"]
