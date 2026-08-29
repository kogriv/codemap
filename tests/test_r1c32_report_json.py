"""R1-C32 — `report --format json` returns the report, not the graph (#14).

Reported by the second target while measuring documentation coverage: they asked for
`report api-surface --format json`, parsed it without error, and got the whole graph.
Three different report kinds produced **byte-identical** output, because the format branch
sat above the dispatch on `args.kind` and the kind was never read.

Their framing is the reason this is a defect and not a missing feature:

    Отказа нет, есть подмена: хорошо оформленный не тот ответ… Молчаливая выдача графа хуже
    отказа: она проходит проверку «ответ получен».

That is the same family as the two fixed the day before — `✅ Contract satisfied` over a
partial judgement, `pytest <path>` for a path that does not exist. An answer shaped exactly
like the right one, which is what stops the reader from checking.

Every kind the CLI accepts now has a structured form. The tests below are mostly one line
each on purpose: what is worth pinning is that the kind *reaches* the output at all.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from codemap.extract import extract
from codemap.store import save

_KINDS = ["api-surface", "dependencies", "dead-code", "behavior", "architecture",
          "communities"]


@pytest.fixture(scope="module")
def graph_file(tmp_path_factory):
    pkg = tmp_path_factory.mktemp("src") / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "inner.py").write_text(
        '"""Inner."""\n\n\ndef helper(x):\n    """Add one."""\n    return x + 1\n'
        "\n\ndef _unused():\n    return 0\n")
    (pkg / "user.py").write_text(
        '"""User."""\n\nfrom pkg.inner import helper\n\n\ndef go(x):\n'
        '    """Call it."""\n    return helper(x)\n')
    out = tmp_path_factory.mktemp("out") / "g.json"
    save(extract(str(pkg)), str(out))
    return str(out)


def _report(graph_file, kind, *extra):
    r = subprocess.run([sys.executable, "-m", "codemap.cli", "report", kind,
                        "--graph", graph_file, "--format", "json", *extra],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.parametrize("kind", _KINDS)
def test_the_payload_is_the_report_not_the_graph(graph_file, kind):
    payload = _report(graph_file, kind)
    assert payload["kind"] == kind
    assert "nodes" not in payload and "codemap_schema" not in payload


def test_two_kinds_do_not_produce_the_same_bytes(graph_file):
    """The symptom that made it obvious: `args.kind` was never read on this path."""
    a = _report(graph_file, "api-surface")
    b = _report(graph_file, "dead-code")
    assert a != b


@pytest.mark.parametrize("kind", _KINDS)
def test_markdown_still_renders(graph_file, kind):
    r = subprocess.run([sys.executable, "-m", "codemap.cli", "report", kind,
                        "--graph", graph_file, "--format", "markdown"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("#")


# -- each form carries what its markdown says -------------------------------

def test_api_surface_carries_symbols_with_their_signatures(graph_file):
    """The reporter's own use: measuring documentation coverage without parsing prose."""
    payload = _report(graph_file, "api-surface")
    symbols = {s["id"]: s for m in payload["modules"] for s in m["symbols"]}
    assert symbols["pkg.inner.helper"]["doc"] == "Add one."
    assert symbols["pkg.inner.helper"]["kind"] == "function"
    assert payload["totals"]["symbols"] == len(symbols)


def test_dead_code_carries_graded_candidates(graph_file):
    payload = _report(graph_file, "dead-code")
    assert "pkg.inner._unused" in {c["id"] for c in payload["candidates"]}
    assert set(payload["totals"]) == {"high", "medium", "low"}


def test_dependencies_keeps_the_two_kinds_of_cycle_apart(graph_file):
    """R1-C29's distinction is not a rendering flourish — it survives into the data."""
    payload = _report(graph_file, "dependencies")
    assert payload["import_cycles"] == []
    assert payload["lazy_import_cycles"] == []
    assert payload["import_map"]["module_level"] >= 1


def test_behavior_carries_the_call_site_aggregate(graph_file):
    payload = _report(graph_file, "behavior")
    assert payload["call_sites"]["resolved"] >= 1
    assert payload["calls_edges"]["total"] >= 1


def test_impact_reports_every_definition_the_name_matched(graph_file):
    """A short name can name more than one definition; the markdown form prints all of
    them, so the json form returns all of them rather than picking."""
    payload = _report(graph_file, "impact", "--symbol", "helper")
    assert payload["matched"] == ["pkg.inner.helper"]
    assert payload["reports"][0]["id"] == "pkg.inner.helper"
    assert payload["reports"][0]["refs"]


def test_an_unknown_symbol_answers_with_an_empty_match(graph_file):
    """Parity with the markdown form, which prints "_No definition found_" and exits 0:
    the name resolving to nothing is an answer, not a usage error."""
    r = subprocess.run([sys.executable, "-m", "codemap.cli", "report", "impact",
                        "--graph", graph_file, "--format", "json",
                        "--symbol", "nope_not_here"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and json.loads(r.stdout)["matched"] == []
