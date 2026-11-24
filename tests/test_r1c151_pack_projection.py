from codemap.model import Edge, Graph, Node
from codemap.query import Query
from codemap.serve.pack import build_pack


def test_seeded_pack_builds_one_directed_projection_per_request(monkeypatch):
    graph = Graph(target="pkg")
    for nid in ("pkg.seed", "pkg.dep", "pkg.sibling"):
        graph.add_node(Node(id=nid, kind="function", file="pkg/mod.py"))
    graph.add_edge(Edge("calls", "pkg.seed", "pkg.dep"))
    graph.add_edge(Edge("calls", "pkg.sibling", "pkg.dep"))
    query = Query(graph)
    build_projection = query._rank_graph
    projections = []

    def record_projection(*args, **kwargs):
        projection = build_projection(*args, **kwargs)
        projections.append(projection)
        return projection

    monkeypatch.setattr(query, "_rank_graph", record_projection)
    for request_count, direction in enumerate(("both", "uses"), start=1):
        pack = build_pack(query, budget=1000, seeds=("seed",), direction=direction)
        assert len(projections) == request_count
        assert {item["id"] for item in pack["items"]} == {"pkg.seed", "pkg.dep"}
        assert set(projections[-1].edges) == {
            ("pkg.seed", "pkg.dep"), ("pkg.sibling", "pkg.dep"),
        }

    first, second = projections
    assert first is not second
