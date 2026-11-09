"""R1-C91 — every route the extractor emits is graded; a graph from a newer codemap says so.

Design `docs/design/route_vocabulary_drift.md` (pre-registered 66feb01).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codemap import model, store
from codemap.cli import main
from codemap.diagnostics import GRAPH_FROM_NEWER_TOOL, diagnostics, newer_tool_diagnostic
from codemap.extract import extract_repo
from codemap.query import Query
from codemap.serve.session import Session

FILES = {
    "pkg/__init__.py": "",
    "pkg/core.py": "def act():\n    return 1\n",
    "tests/test_a.py": ("from pkg.core import act\n\n\n"
                        "def _helper():\n    return act()\n\n\n"
                        "def test_through_helper():\n    assert _helper() == 1\n\n\n"
                        "HOOKS = [_helper]\n"),
}


def _write(root: Path):
    for rel, body in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


def _build(root: Path):
    return extract_repo(str(root / "pkg"), consumers=(str(root / "tests"),), mode="full")


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    _write(root)
    return root


def _local(graph):
    return {(e.type, e.source, e.target) for e in graph.edges
            if e.extras.get("resolution") == "local"}


# -- D1 -------------------------------------------------------------------------------------

def test_E1_local_routes_are_graded_exact_and_survive_min_confidence(repo):
    graph = _build(repo)
    local = _local(graph)
    helper = "tests.test_a._helper"
    assert ("calls", "tests.test_a.test_through_helper", helper) in local
    assert ("references", "tests.test_a", helper) in local, "the fixture must name it uncalled"
    for e in graph.edges:
        if e.extras.get("resolution") == "local":
            assert model.confidence_of(e) == "exact"
    q = Query(graph)
    assert "unknown" not in q.confidence_map()["by_grade"]
    assert "tests.test_a.test_through_helper" in q.callers(helper, min_confidence="exact")


# -- D2 -------------------------------------------------------------------------------------

def test_E5_a_builder_refuses_a_route_its_table_does_not_know(repo, monkeypatch):
    for key in (("calls", "local"), ("references", "local")):
        monkeypatch.delitem(model.RESOLUTIONS, key)
    with pytest.raises(KeyError, match="local"):
        _build(repo)


# -- D3 -------------------------------------------------------------------------------------

def _stamped(graph, version):
    graph.provenance = {**graph.provenance,
                        "tool": {**(graph.provenance.get("tool") or {}), "version": version}}
    return graph


def test_E3_a_newer_builder_is_named(repo):
    graph = _stamped(_build(repo), "99.0.0")
    d = newer_tool_diagnostic(graph, running="0.0.35")
    assert d["code"] == GRAPH_FROM_NEWER_TOOL and d["severity"] == "warning"
    assert d["built_by"] == "99.0.0" and d["running"] == "0.0.35" and d["unrecognised"] == {}
    assert "99.0.0 or newer" in d["message"]
    assert any(x["code"] == GRAPH_FROM_NEWER_TOOL for x in diagnostics(graph))


def test_E3_unknown_routes_are_listed_with_counts(repo):
    graph = _build(repo)
    e = next(e for e in graph.edges if e.extras.get("resolution") == "imported")
    e.extras["resolution"] = "future"
    d = newer_tool_diagnostic(graph, running="0.0.35")
    assert d["unrecognised"] == {f"{e.type}:future": 1}
    assert "rebuild it with this codemap" in d["message"], "not newer: the remedy is a rebuild"


def test_unknown_routes_fire_without_a_running_version(repo):
    graph = _build(repo)
    next(e for e in graph.edges if e.extras.get("resolution")).extras["resolution"] = "future"
    assert newer_tool_diagnostic(graph, running="")["unrecognised"]


def test_E2_an_older_or_equal_graph_with_known_routes_is_silent(repo):
    graph = _build(repo)
    for v in ("0.0.1", "0.0.35"):
        assert newer_tool_diagnostic(_stamped(graph, v), running="0.0.35") is None


def test_the_running_version_compares_by_number_not_by_string(repo):
    graph = _stamped(_build(repo), "0.0.100")
    assert newer_tool_diagnostic(graph, running="0.0.99") is not None
    assert newer_tool_diagnostic(_stamped(graph, "0.0.9"), running="0.0.10") is None


def test_stats_carries_it(repo, tmp_path):
    graph = _stamped(_build(repo), "99.0.0")
    out = Session(graph).handle({"op": "stats"})
    codes = [d["code"] for d in out["result"].get("diagnostics", [])]
    assert GRAPH_FROM_NEWER_TOOL in codes


# -- D4 -------------------------------------------------------------------------------------

def test_E3_cold_cli_read_warns_once_and_keeps_stdout(repo, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(repo)
    g = tmp_path / "g.json"
    assert main(["build", "pkg", "--consumer", "tests", "--mode", "full", "-o", str(g)]) == 0
    capsys.readouterr()
    assert main(["query", "act", "--graph", str(g)]) == 0
    plain = capsys.readouterr()
    assert "graph_from_newer_tool" not in plain.err and "built by codemap" not in plain.err

    data = json.loads(g.read_text())
    data["provenance"]["tool"]["version"] = "99.0.0"
    g.write_text(json.dumps(data))
    assert main(["query", "act", "--graph", str(g)]) == 0
    stamped = capsys.readouterr()
    lines = [ln for ln in stamped.err.splitlines() if "built by codemap 99.0.0" in ln]
    assert len(lines) == 1 and lines[0].startswith("[warning]")
    assert stamped.out == plain.out
