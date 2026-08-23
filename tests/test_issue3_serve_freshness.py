"""Issue #3 — a served graph must not report itself fresh while it's stale.

The MCP/serve session caches the graph it loaded at start; `stats.freshness` used to
be computed from the on-disk file's mtime, so after an external rebuild it reported the
NEW file's age while every query answered from the OLD in-memory snapshot — active false
reassurance. These tests pin: (1) `stats` describes the served graph and flags on-disk
divergence; (2) `reload` picks up the rebuilt artifact without a restart.
"""

from __future__ import annotations

import os
from pathlib import Path

from codemap import freshness, store
from codemap.extract import extract
from codemap.serve.session import Session

FIX = Path(__file__).resolve().parent / "fixtures"
SMALL = FIX / "flowpkg"      # few nodes
BIG = FIX / "attrpkg"        # more nodes/edges — a clearly different graph


# -- freshness() unit ---------------------------------------------------------

def test_freshness_describes_served_not_disk(tmp_path):
    g = tmp_path / "graph.json"
    g.write_text("{}", encoding="utf-8")
    os.utime(g, (1000, 1000))  # on-disk mtime = 1000
    # served snapshot is OLDER than the on-disk file (an external rebuild happened).
    fr = freshness.freshness(str(g), now=1000, served_mtime=900)
    assert fr["built_at"] == 900              # reports the SERVED graph, not the file
    assert fr["stale"] is True
    assert fr["on_disk_built_at"] == 1000
    assert "reload" in fr["reason"]


def test_freshness_not_stale_when_served_matches_disk(tmp_path):
    g = tmp_path / "graph.json"
    g.write_text("{}", encoding="utf-8")
    os.utime(g, (1000, 1000))
    fr = freshness.freshness(str(g), now=1000, served_mtime=1000)
    assert "stale" not in fr


def test_freshness_flags_disappeared_artifact(tmp_path):
    fr = freshness.freshness(str(tmp_path / "gone.json"), now=1000, served_mtime=900)
    assert fr["stale"] is True and "gone" in fr["reason"]


# -- serve integration --------------------------------------------------------

def _save(graph, path, mtime):
    store.save(graph, path)
    os.utime(path, (mtime, mtime))


def test_stats_flags_stale_after_external_rebuild(tmp_path):
    g = tmp_path / "graph.json"
    _save(extract(SMALL), g, 1000)
    s = Session(extract(SMALL), graph_path=str(g))  # served snapshot at mtime 1000
    assert "stale" not in s.handle({"op": "stats"})["result"]["freshness"]

    # an external rebuild overwrites the artifact with a different graph, newer mtime.
    _save(extract(BIG), g, 2000)
    fr = s.handle({"op": "stats"})["result"]["freshness"]
    assert fr["stale"] is True                 # no longer silently "fresh"
    assert fr["on_disk_built_at"] == 2000


def test_reload_picks_up_the_rebuilt_graph(tmp_path):
    g = tmp_path / "graph.json"
    _save(extract(SMALL), g, 1000)
    s = Session(extract(SMALL), graph_path=str(g))
    small_nodes = len(s.graph.nodes)

    _save(extract(BIG), g, 2000)
    res = s.handle({"op": "reload"})["result"]
    assert res["reloaded"] is True and res["changed"] is True
    assert res["after"]["nodes"] != small_nodes
    # after reload the server answers from the new graph, and stats is no longer stale.
    assert len(s.graph.nodes) == res["after"]["nodes"]
    assert "stale" not in s.handle({"op": "stats"})["result"]["freshness"]


def test_reload_noop_for_in_memory_build():
    s = Session(extract(SMALL))  # no graph_path (started from --build)
    res = s.handle({"op": "reload"})["result"]
    assert res["reloaded"] is False and "restart" in res["reason"]
