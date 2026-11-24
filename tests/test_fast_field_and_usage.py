"""R1-C147/C148. Synthetic consumer feedback and negative controls."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codemap import store
from codemap.cli import main
from codemap.devkit.usage import count, render
from codemap.extract import extract, extract_repo
from codemap.model import confidence_of
from codemap.query import Query


FIELD_SOURCE = (Path(__file__).parent / "fixtures/annotated_fields/__init__.py").read_text()


def _package(root, source):
    package = root / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(source)
    return package


@pytest.mark.parametrize("mode", ["thin", "full"])
def test_fast_field_call_is_not_dead(tmp_path, mode, capsys):
    package = _package(tmp_path, FIELD_SOURCE)
    consumer = tmp_path / "tests"
    consumer.mkdir()
    graph = extract_repo(package, consumers=(consumer,), mode=mode)
    query = Query(graph)
    assert query.callers("pkg.Worker._work") == ["pkg.Task.execute"]
    assert query.callers("pkg.Worker._work", min_confidence="exact") == []
    high = {row["id"] for row in query.dead_code(min_confidence="high")}
    assert "pkg.Worker._work" not in high
    assert {"pkg.Worker._unused", "pkg.Other._work"} <= high
    edge = next(edge for edge in graph.edges if edge.type == "calls" and edge.target == "pkg.Worker._work")
    assert edge.extras["resolution"] == "annotated-field" and edge.extras["callsites"] == 1
    assert confidence_of(edge) == "inferred"
    artifact = tmp_path / "graph.json"
    store.save(graph, artifact)
    assert main(["report", "dead-code", "--graph", str(artifact), "--public",
                 "--min-confidence", "high", "--format", "json"]) == 0
    rows = json.loads(capsys.readouterr().out)["candidates"]
    assert {row["id"] for row in rows} == high


def test_fast_field_accepts_explicit_forward_ref(tmp_path):
    source = FIELD_SOURCE.replace("worker: Worker", 'worker: "Worker"')
    graph = extract(_package(tmp_path, source))
    assert Query(graph).callers("pkg.Worker._work") == ["pkg.Task.execute"]


def test_exact_route_wins_when_both_sites_call_the_same_method(tmp_path):
    source = FIELD_SOURCE.replace("return self._worker._work(1)",
                                  "self._worker._work(1)\n        return Worker._work(self._worker, 2)")
    graph = extract(_package(tmp_path, source))
    assert Query(graph).callers("pkg.Worker._work", min_confidence="exact") == ["pkg.Task.execute"]
    edge = next(edge for edge in graph.edges if edge.type == "calls" and edge.target == "pkg.Worker._work")
    assert edge.extras["callsites"] == 2 and edge.extras["resolution"] == "module"


@pytest.mark.parametrize("source", [
    FIELD_SOURCE.replace("worker: Worker", "worker: Worker | None"),
    FIELD_SOURCE.replace("from __future__ import annotations", ""),
    FIELD_SOURCE.replace("        self._worker = worker", "        worker = Other()\n        self._worker = worker"),
    FIELD_SOURCE.replace("    def execute", "    def replace(self):\n        self._worker = Other()\n\n    def execute"),
    FIELD_SOURCE.replace("    def execute", '    def replace(self):\n        setattr(self, "_worker", Other())\n\n    def execute'),
    FIELD_SOURCE.replace("return self._worker._work(1)", "return (lambda self: self._worker._work(1))(Other())"),
])
def test_fast_field_does_not_guess_conflicting_types(tmp_path, source):
    graph = extract(_package(tmp_path, source))
    assert not Query(graph).callers("pkg.Worker._work")
    assert not any(edge.extras.get("resolution") == "annotated-field" for edge in graph.edges)


def _transcript(path, uses):
    now = datetime.now(timezone.utc).isoformat()
    records = [{"type": "assistant", "timestamp": now, "message": {"content": [
        {"type": "tool_use", "id": str(i), "name": name, "input": {"command": command}}
        for i, name, command in uses
    ]}}]
    path.write_text("\n".join(json.dumps(record) for record in records))


def test_usage_cli_without_mcp(tmp_path, capsys):
    _transcript(tmp_path / "s.jsonl", [
        (1, "Bash", "codemap query Task"),
        (2, "Bash", "rg Task"),
        (1, "Bash", "codemap query Task"),
    ])
    report = count(tmp_path, 2)
    assert report["codemap_total"] == 0 and report["codemap_cli_total"] == 1
    assert report["grep_total"] == 1
    assert report["share"]["numerator"] == 1 and report["share"]["denominator"] == 2
    assert "50 %" in render(report)
    assert "MCP + CLI + grep" in render(report)
    assert main(["devkit", "usage", "--transcripts", str(tmp_path), "--days", "2", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out) == report


def test_usage_cli_program_positions_and_mixed_commands(tmp_path):
    _transcript(tmp_path / "s.jsonl", [
        (1, "Bash", "cd source\n./.venv/bin/codemap build pkg | rg graph"),
        (2, "Bash", "python3.12 -I -m codemap check"),
        (3, "Bash", "uv run --with codmap codemap query Task; codemap report dead-code"),
        (4, "Bash", 'printf "%s" "; codemap review"'),
        (5, "Bash", "echo codemap refresh"),
        (6, "Bash", "python -c 'print(\"codemap\")'"),
        (7, "mcp__codemap__stats", ""),
        (8, "Grep", ""),
        (9, "Bash", "# codemap query Task\nrg Task"),
        (10, "Bash", '"./virtual env/bin/codemap" stats'),
        (11, "Bash", "command -v codemap"),
        (12, "Bash", "cat <<'EOF'\ncodemap query Task\nEOF"),
        (13, "Bash", r"printf %s \; codemap"),
        (14, "Bash", "((codemap + 1))"),
        (15, "Bash", "python --version -m codemap"),
        (16, "Bash", "cd source # change directory\nenv PYTHONPATH=. codemap stats"),
    ])
    report = count(tmp_path, 2)
    assert report["codemap"] == {"stats": 1} and report["codemap_total"] == 1
    assert report["codemap_cli_total"] == 5 and report["grep_total"] == 3
    assert report["share"]["numerator"] == 6 and report["share"]["denominator"] == 9
