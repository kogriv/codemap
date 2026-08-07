"""R1-C19 acceptance — transitive impact depth histogram + risk triage.

The transitive BFS already existed (M6.6); this adds the depth histogram
(`by_distance`/`max_distance`), a heuristic `risk` label built on our own graph
(from the GitNexus разбор, no external dep), and `--depth` on the CLI.
"""

from __future__ import annotations

import json
from pathlib import Path

from codemap import store
from codemap.cli import main
from codemap.model import Edge, Graph, Node
from codemap.query import Query
from codemap.serve.impact import render_impact


def _fn(g: Graph, nid: str, root: str = "core") -> None:
    g.add_node(Node(id=nid, kind="function", extras={"root": root}))


def _calls(g: Graph, src: str, tgt: str) -> None:
    g.add_edge(Edge(type="calls", source=src, target=tgt))


def _chain() -> Graph:
    """A <- B <- C <- D (each calls the previous) — a 3-deep inbound chain to A."""
    g = Graph(target="pkg")
    for n in "ABCD":
        _fn(g, f"pkg.{n}")
    _calls(g, "pkg.B", "pkg.A")   # distance 1
    _calls(g, "pkg.C", "pkg.B")   # distance 2
    _calls(g, "pkg.D", "pkg.C")   # distance 3
    return g


# -- depth histogram ---------------------------------------------------------

def test_by_distance_histogram_full_depth():
    rep = Query(_chain()).impact("pkg.A", depth=3)
    assert rep["by_distance"] == {1: 1, 2: 1, 3: 1}
    assert rep["max_distance"] == 3


def test_depth_limits_the_bfs():
    rep = Query(_chain()).impact("pkg.A", depth=1)
    assert rep["by_distance"] == {1: 1}          # only direct callers
    assert rep["max_distance"] == 1
    assert len(rep["refs"]) == 1


def test_isolated_symbol_has_no_risk():
    g = Graph(target="pkg")
    _fn(g, "pkg.lonely")
    rep = Query(g).impact("pkg.lonely")
    assert rep["by_distance"] == {} and rep["max_distance"] == 0
    assert rep["risk"] == "none"


# -- risk heuristic (breadth × reach × root-spread) --------------------------

def test_risk_low_narrow_direct_single_root():
    assert Query._impact_risk(breadth=2, reach=1, roots=1) == "low"


def test_risk_medium_by_breadth_reach_or_rootspread():
    assert Query._impact_risk(6, 1, 1) == "medium"    # breadth >= 5
    assert Query._impact_risk(3, 2, 1) == "medium"    # transitive reach >= 2
    assert Query._impact_risk(3, 1, 2) == "medium"    # spans 2 provenance roots


def test_risk_high_by_breadth_rootspread_or_deep_breadth():
    assert Query._impact_risk(30, 1, 1) == "high"     # broad
    assert Query._impact_risk(4, 1, 4) == "high"      # spans 4 roots (core+tests+docs+…)
    assert Query._impact_risk(15, 3, 1) == "high"     # broad AND deep


def test_risk_rises_with_root_spread_on_real_graph():
    # Same symbol referenced from 2 roots → medium (root-spread signal, codemap's
    # provenance differentiator).
    g = Graph(target="pkg")
    _fn(g, "pkg.core_fn")
    _fn(g, "pkg.caller1", root="core")
    _fn(g, "tests.caller2", root="tests")
    _calls(g, "pkg.caller1", "pkg.core_fn")
    _calls(g, "tests.caller2", "pkg.core_fn")
    rep = Query(g).impact("pkg.core_fn")
    assert set(rep["by_root"]) == {"core", "tests"}
    assert rep["risk"] == "medium"


# -- rendering ---------------------------------------------------------------

def test_render_shows_risk_and_histogram():
    md = render_impact(Query(_chain()), "A", depth=3)
    assert "Risk: LOW" in md or "Risk: MEDIUM" in md  # 3-deep single-root chain
    assert "depth reached 3" in md
    assert "d1×1" in md and "d3×1" in md


# -- CLI ---------------------------------------------------------------------

def test_cli_report_impact_depth_flag(tmp_path, capsys):
    gpath = tmp_path / "g.json"
    store.save(_chain(), str(gpath))
    assert main(["report", "impact", "--graph", str(gpath), "--symbol", "A",
                 "--depth", "1"]) == 0
    out = capsys.readouterr().out
    assert "depth reached 1" in out                  # depth flag respected


def test_serve_impact_carries_depth_fields():
    from codemap.serve.session import Session
    env = Session(_chain()).handle({"op": "impact", "args": {"symbol": "A", "depth": 3}})
    assert env["ok"]
    entry = env["result"]["impact"][0]
    assert entry["max_distance"] == 3
    assert entry["risk"] in {"low", "medium", "high"}
    # JSON round-trips (int distance keys become strings — expected).
    assert json.loads(json.dumps(entry))["by_distance"]
