"""R1-C83 — the `pytest` line of a graph built elsewhere: the current directory is tried, `--source-root` is taken.

Design `docs/design/foreign_graph_paths.md` (pre-registered 8966f98).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codemap.cli import main

FOREIGN = "/srv/elsewhere/repo"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    for rel, body in {
        "pkg/__init__.py": "",
        "pkg/core.py": "def act():\n    return 1\n\n\ndef unused_thing():\n    return 2\n",
        "tests/test_a.py": "from pkg.core import act\n\n\ndef test_a():\n    assert act()\n",
    }.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    out = tmp_path / "graphs"
    out.mkdir()
    monkeypatch.chdir(repo)
    assert main(["build", "pkg", "--consumer", "tests", "--mode", "full", "-o", str(out / "g.json")]) == 0
    return tmp_path, repo, out / "g.json"


def _foreign(graph: Path, drop=False):
    meta = Path(str(graph) + ".meta.json")
    if drop:
        meta.unlink()
        return
    m = json.loads(meta.read_text())
    m["roots_base"] = FOREIGN
    meta.write_text(json.dumps(m))


def _tests(capsys, graph, *extra):
    capsys.readouterr()
    rc = main(["tests", "act", "--graph", str(graph), *extra])
    cap = capsys.readouterr()
    line = next(x for x in cap.out.splitlines() if x.startswith("pytest "))
    return rc, line, cap.err


def test_E1_foreign_sidecar_from_the_repo_root_is_not_a_false_alarm(setup, capsys):
    _, repo, g = setup
    _foreign(g)
    rc, line, err = _tests(capsys, g)
    assert rc == 0 and line == "pytest tests/test_a.py::test_a"
    assert "could not be located" not in err
    assert f"the graph was built in `{FOREIGN}`, which is not on this machine" in err


def test_E2_source_root_from_the_parent(setup, capsys, monkeypatch):
    tmp, repo, g = setup
    _foreign(g)
    monkeypatch.chdir(tmp)
    rc, line, err = _tests(capsys, g, "--source-root", "repo")
    assert line == "pytest repo/tests/test_a.py::test_a"
    assert "not found" not in err and "could not be located" not in err


def test_E3_a_wrong_source_root_is_named_and_cwd_is_not_tried(setup, capsys):
    _, repo, g = setup
    _foreign(g)
    rc, line, err = _tests(capsys, g, "--source-root", "pkg")     # cwd would have worked
    assert line == "pytest tests/test_a.py::test_a"                  # as stored, not rewritten
    assert "1 of 1 path(s) not found under `--source-root pkg`" in err


def test_E4_no_sidecar(setup, capsys, monkeypatch):
    tmp, repo, g = setup
    _foreign(g, drop=True)
    rc, line, err = _tests(capsys, g)
    assert line == "pytest tests/test_a.py::test_a" and "common directory" not in err
    monkeypatch.chdir(tmp)
    rc, line, err = _tests(capsys, g)
    assert "pass `--source-root`" in err


def test_E4_foreign_and_not_found_names_both(setup, capsys, monkeypatch):
    tmp, repo, g = setup
    _foreign(g)
    monkeypatch.chdir(tmp)
    rc, line, err = _tests(capsys, g)
    assert "could not be located" in err and f"built in `{FOREIGN}`" in err and "pass `--source-root`" in err


def test_E5_a_local_graph_from_the_parent_is_unchanged(setup, capsys, monkeypatch):
    tmp, repo, g = setup
    monkeypatch.chdir(tmp)
    rc, line, err = _tests(capsys, g)
    assert line == "pytest repo/tests/test_a.py::test_a"
    assert "could not be located" not in err and "built in" not in err


def test_E6_json_ignores_source_root(setup, capsys):
    _, repo, g = setup
    capsys.readouterr()
    main(["tests", "act", "--graph", str(g), "--format", "json"])
    a = capsys.readouterr().out
    main(["tests", "act", "--graph", str(g), "--format", "json", "--source-root", "/nowhere"])
    assert capsys.readouterr().out == a


def test_E7_report_dead_code_reads_the_whitelist_under_source_root(setup, capsys, monkeypatch):
    tmp, repo, g = setup
    (repo / "codemap.toml").write_text('[dead_code]\nwhitelist = ["pkg.core.unused_thing"]\n')
    monkeypatch.chdir(tmp)
    capsys.readouterr()
    main(["report", "dead-code", "--graph", str(g), "--format", "json"])
    without = json.loads(capsys.readouterr().out)["whitelist"]
    main(["report", "dead-code", "--graph", str(g), "--format", "json", "--source-root", "repo"])
    with_root = json.loads(capsys.readouterr().out)["whitelist"]
    assert without["patterns"] == []                       # read from cwd: no codemap.toml there
    assert with_root["patterns"] == ["pkg.core.unused_thing"]
