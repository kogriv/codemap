"""R1-C64 — a dependency that answers wrongly is not the same as one that is absent.

griffe and jedi were only ever checked by `import` succeeding. That catches the loud failure and
misses the quiet one: a jedi that stopped resolving does not break a build — `_resolve_jedi`
reads any exception as `unresolved` — it turns every deep call into a fast-tier one. Measured
on a real 89-module tree with `jedi.Script` answering nothing: the deep build exited 0, and its
`calls` and `accesses` equalled the fast tier's to the edge while the graph still said
`tier: deep`.

The probe is `jg doctor`'s shape (research/tools/jevgrep.md, S2): a synthetic input with a
known answer, one fact per dependency, through the real pipeline. This file is also the suite
half of the fix: CI installs without a lock file, so a new jedi or griffe meets this test on the
first push after its release. Design: `docs/design/dependency_probe.md`.
"""

from __future__ import annotations

import sys

import pytest

from codemap.cli import main
from codemap.extract import extract
from codemap.extract.probe import ABSENT, ERROR, NOT_RUN, OK, WRONG, holds, run_probes, write_probe


class _SilentScript:
    """A jedi that imports, constructs and answers every question with nothing."""

    def __init__(self, *args, **kwargs):
        pass

    def goto(self, *args, **kwargs):
        return []

    def infer(self, *args, **kwargs):
        return []


def _status(report) -> dict:
    return {r["dependency"]: r["status"] for r in report["probes"]}


@pytest.fixture()
def silent_jedi(monkeypatch):
    import jedi
    monkeypatch.setattr(jedi, "Script", _SilentScript)


# -- the suite half: the installed dependencies still answer correctly --------------------

def test_the_installed_dependencies_answer_the_probe():
    """If this goes red after a dependency upgrade, the upgrade broke resolution — read the
    versions in the report before reading anything else."""
    report = run_probes()
    assert _status(report) == {"griffe": OK, "jedi": OK}, report
    assert report["ok"] is True


def test_the_fast_tier_cannot_answer_the_jedi_question(tmp_path):
    """Control: the jedi fact must be one only jedi supplies, or the probe passes without it."""
    pkg = write_probe(tmp_path)
    assert not holds(extract(str(pkg)), "jedi")
    assert holds(extract(str(pkg), deep=True), "jedi")


def test_the_jedi_fact_is_the_edge_jedi_resolved_not_any_such_edge(tmp_path):
    """If a cheaper resolver ever learned this call, the edge would exist with another route
    and the probe must still ask for jedi's — shown the edge it must reject (R1-C37)."""
    from codemap.model import Edge
    graph = extract(str(write_probe(tmp_path)))
    graph.add_edge(Edge("calls", "codemap_probe.app.main", "codemap_probe.core.Engine.run",
                        extras={"resolution": "imported"}))
    assert not holds(graph, "jedi")


# -- the four outcomes ----------------------------------------------------------------------

def test_a_jedi_that_answers_nothing_is_wrong_not_absent(silent_jedi):
    report = run_probes()
    assert _status(report) == {"griffe": OK, "jedi": WRONG}
    assert report["ok"] is False
    jedi_row = report["probes"][1]
    assert "codemap_probe.core.Engine.run" in jedi_row["detail"]
    assert jedi_row["version"], "the version is the first thing a reader needs"


def test_a_jedi_that_cannot_be_imported_is_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "jedi", None)        # `import jedi` → ImportError
    report = run_probes()
    assert _status(report) == {"griffe": OK, "jedi": ABSENT}
    assert "not importable" in report["probes"][1]["detail"]


def test_a_griffe_that_resolves_aliases_wrongly_is_wrong(monkeypatch):
    import griffe
    original = griffe.Alias.__init__

    def misdirected(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.target_path = "elsewhere." + self.name

    monkeypatch.setattr(griffe.Alias, "__init__", misdirected)
    report = run_probes()
    assert _status(report)["griffe"] == WRONG
    assert _status(report)["jedi"] == OK, "one wrong dependency must not be blamed on the other"


def test_a_failed_structural_pass_leaves_jedi_unknown(monkeypatch):
    """jedi's probe stands on griffe's structure; without it the deep answer means nothing."""
    import codemap.extract as ex

    def broken(*args, **kwargs):
        raise RuntimeError("structural pass failed")

    monkeypatch.setattr(ex, "extract", broken)
    report = run_probes()
    assert _status(report) == {"griffe": ERROR, "jedi": NOT_RUN}
    assert "RuntimeError" in report["probes"][0]["detail"]


# -- the command --------------------------------------------------------------------------

def test_doctor_exits_zero_when_every_probe_holds(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "griffe" in out and "jedi" in out and "WRONG" not in out


def test_doctor_exits_one_and_names_the_wrong_answer(silent_jedi, capsys):
    assert main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "WRONG" in out and "codemap_probe.core.Engine.run" in out


def test_doctor_json_is_structured(silent_jedi, capsys):
    import json
    assert main(["doctor", "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert _status(report) == {"griffe": OK, "jedi": WRONG}
