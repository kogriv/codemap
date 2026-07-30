"""M16 acceptance — architecture overview (A9 dogfood F18–F21).

The architect's global view: layers + direction/violations (F18), coupling
Ca/Ce/instability (F19), god-objects & call-hubs (F20), synthesized into one report
(F21). All over existing import/calls/contains/provenance — no schema change.
Fixtures: dispatchpkg (multiple modules, classes, import edges).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.extract import extract
from codemap.query import Query
from codemap.serve.architecture import build_architecture, render_architecture
from codemap.serve.session import Session

DISPATCH = Path(__file__).resolve().parent / "fixtures" / "dispatchpkg"


@pytest.fixture(scope="module")
def q():
    return Query(extract(DISPATCH))


# -- F18: layers -------------------------------------------------------------

def test_layers_shape(q):
    lay = q.layers()
    assert set(lay) == {"layers", "edges", "violations"}
    # dispatchpkg is flat → each module is its own layer.
    assert "base" in lay["layers"]
    assert isinstance(lay["violations"], list)


def test_layer_violation_is_mutual_dependency():
    # a↔b mutual import must be flagged order-free; a→b alone must not.
    from codemap.model import Graph, Node, Edge
    g = Graph(target="pkg")
    for m in ("pkg.a.x", "pkg.b.y", "pkg.c.z"):
        g.add_node(Node(id=m, kind="module"))
    g.add_edge(Edge("imports", "pkg.a.x", "pkg.b.y"))
    g.add_edge(Edge("imports", "pkg.b.y", "pkg.a.x"))  # mutual a↔b
    g.add_edge(Edge("imports", "pkg.c.z", "pkg.a.x"))  # one-way c→a
    lay = Query(g).layers()
    assert lay["violations"] == [["a", "b"]]


# -- F19: coupling -----------------------------------------------------------

def test_coupling_metrics(q):
    rows = q.coupling()
    assert rows and set(rows[0]) == {"module", "ca", "ce", "instability"}
    # registry is imported by factory + impls → afferent coupling > 0, stable.
    reg = next((r for r in rows if r["module"].endswith(".registry")), None)
    assert reg and reg["ca"] >= 1
    for r in rows:
        assert 0.0 <= r["instability"] <= 1.0


# -- F20: hotspots -----------------------------------------------------------

def test_hotspots_shape_and_pervasive_flag(q):
    hs = q.hotspots(min_methods=1)
    assert "god_classes" in hs and "call_hubs" in hs
    # Alpha/Beta each have a `run` method → surface as (tiny) god candidates.
    assert any(g["class"].endswith("Alpha") for g in hs["god_classes"])
    for h in hs["call_hubs"]:
        assert set(h) == {"id", "degree", "pervasive"}


# -- F21: synthesis ----------------------------------------------------------

def test_build_architecture_has_all_sections(q):
    a = build_architecture(q)
    assert set(a) == {"target", "cycles", "layers", "coupling", "hotspots"}
    assert a["target"] == "dispatchpkg"


def test_render_architecture_markdown(q):
    md = render_architecture(q)
    assert "# Architecture overview" in md
    assert "## Layers" in md
    assert "## Coupling" in md


def test_architecture_op_and_report():
    s = Session(extract(DISPATCH))
    r = s.handle({"op": "architecture"})
    assert r["ok"]
    assert "layers" in r["result"]
    rep = s.handle({"op": "report", "args": {"kind": "architecture"}})
    assert rep["ok"]
    assert "Architecture overview" in rep["result"]["markdown"]
