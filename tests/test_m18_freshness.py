"""M18 acceptance — graph freshness (age in stats + rebuild recipe).

The canonical graph.json stays timestamp-free; freshness lives outside it — the file
mtime gives age, an optional sidecar records the build recipe for `codemap refresh`.
"""

from __future__ import annotations

import json
from pathlib import Path

from codemap import freshness
from codemap.extract import extract
from codemap.serve.session import Session

FIX = Path(__file__).resolve().parent / "fixtures" / "dispatchpkg"


# -- freshness module --------------------------------------------------------

def test_freshness_none_for_missing_or_unset():
    assert freshness.freshness(None) is None
    assert freshness.freshness("/no/such/graph.json") is None


def test_freshness_age_from_mtime(tmp_path):
    g = tmp_path / "graph.json"
    g.write_text("{}", encoding="utf-8")
    fr = freshness.freshness(str(g), now=1_000_000)
    assert fr["age_seconds"] >= 0
    assert isinstance(fr["built_at"], int)
    assert "rebuild" not in fr            # no sidecar → no recipe


def test_meta_roundtrip_and_rebuild_field(tmp_path):
    g = tmp_path / "graph.json"
    g.write_text("{}", encoding="utf-8")
    freshness.write_meta(str(g), argv=["build", "pkg", "-o", str(g)],
                         cwd=str(tmp_path), target="pkg")
    assert Path(freshness.meta_path(str(g))).exists()
    meta = freshness.read_meta(str(g))
    assert meta["argv"][0] == "build" and meta["target"] == "pkg"
    fr = freshness.freshness(str(g))
    assert fr["rebuild"]["argv"][0] == "build"
    assert fr["rebuild"]["cwd"] == str(tmp_path)


def test_read_meta_absent_is_none(tmp_path):
    assert freshness.read_meta(str(tmp_path / "graph.json")) is None


# -- stats integration -------------------------------------------------------

def test_stats_omits_freshness_without_graph_path():
    # in-memory graph (tests) → no freshness → stays deterministic.
    s = Session(extract(FIX))
    assert "freshness" not in s.handle({"op": "stats"})["result"]


def test_stats_reports_freshness_with_graph_path(tmp_path):
    g = tmp_path / "graph.json"
    g.write_text("{}", encoding="utf-8")
    s = Session(extract(FIX), graph_path=str(g))
    fr = s.handle({"op": "stats"})["result"]["freshness"]
    assert fr["age_seconds"] >= 0


# -- CLI: build writes sidecar, refresh replays ------------------------------

def test_build_writes_sidecar_and_refresh_replays(tmp_path):
    from codemap import cli
    out = tmp_path / "g.json"
    assert cli.main(["build", str(FIX), "-o", str(out)]) == 0
    meta = json.loads(Path(freshness.meta_path(str(out))).read_text())
    assert meta["argv"] == ["build", str(FIX), "-o", str(out)]
    assert meta["target"] == "dispatchpkg"
    # delete the graph, refresh must rebuild it from the recipe
    out.unlink()
    assert cli.main(["refresh", str(out)]) == 0
    assert out.exists()


def test_refresh_without_sidecar_errors(tmp_path):
    from codemap import cli
    with __import__("pytest").raises(SystemExit):
        cli.main(["refresh", str(tmp_path / "nope.json")])
