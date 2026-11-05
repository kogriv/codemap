"""R1-C84 — a `--consumer` / `--docs` root that is not a directory is refused, not skipped.

Design `docs/design/missing_roots.md` (pre-registered 0e2a9c1).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from codemap import cli
from codemap.cli import main
from codemap.extract import extract_repo


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    for rel, body in {
        "pkg/__init__.py": "",
        "pkg/core.py": "def act():\n    return 1\n",
        "tests/test_a.py": "from pkg.core import act\n\n\ndef test_a():\n    assert act()\n",
        "examples/ex.py": "from pkg.core import act\n\nact()\n",
    }.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    (tmp_path / "empty").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _build(*extra) -> int:
    return main(["build", "pkg", "-o", "g.json", "--mode", "full", *extra])


def test_E1_missing_consumer_exits_2_and_leaves_the_graph_alone(repo, capsys):
    assert _build("--consumer", "tests") == 0
    before = Path("g.json").read_bytes()
    capsys.readouterr()
    assert _build("--consumer", "nope") == 2
    err = capsys.readouterr().err
    assert "error: `--consumer nope`: no such directory" in err
    assert Path("g.json").read_bytes() == before


def test_E2_a_list_in_one_string_gets_the_split_command(repo, capsys):
    assert _build("--consumer", "tests,examples") == 2
    err = capsys.readouterr().err
    assert "looks like a list; pass the flag once per root: `--consumer tests --consumer examples`" in err
    assert _build("--consumer", "tests,nope") == 2
    err = capsys.readouterr().err
    assert "no such directory" in err and "looks like a list" not in err


def test_E3_missing_docs_and_a_file_as_root(repo, capsys):
    assert _build("--docs", "nope") == 2
    assert "error: `--docs nope`: no such directory" in capsys.readouterr().err
    assert _build("--consumer", "pkg/core.py") == 2
    assert "error: `--consumer pkg/core.py`: not a directory" in capsys.readouterr().err


def test_E3_every_problem_is_named_not_just_the_first(repo, capsys):
    assert _build("--consumer", "tests", "--consumer", "nope1", "--docs", "nope2") == 2
    err = capsys.readouterr().err
    assert "`--consumer nope1`" in err and "`--docs nope2`" in err


def test_E4_scope_and_watch_refuse_the_same_way(repo, capsys):
    assert main(["scope", "pkg", "--consumer", "nope", "--no-git"]) == 2
    assert "`--consumer nope`: no such directory" in capsys.readouterr().err
    assert main(["watch", "pkg", "-o", "w.json", "--consumer", "nope"]) == 2
    assert "`--consumer nope`: no such directory" in capsys.readouterr().err
    assert not Path("w.json").exists()


def test_E4_refresh_names_a_root_deleted_since_the_build(repo, capsys, monkeypatch):
    assert _build("--consumer", "tests", "--consumer", "examples") == 0
    shutil.rmtree(repo / "examples")
    capsys.readouterr()
    assert main(["refresh", str(repo / "g.json")]) == 2
    assert "`--consumer examples`: no such directory" in capsys.readouterr().err


def test_E4_watch_reports_a_refused_rebuild_as_failed(repo, capsys, monkeypatch):
    # a root deleted while watching: _cmd_build returns 2 instead of raising
    monkeypatch.setattr(cli, "_cmd_build", lambda a: 2)
    seen = {}

    class Poller:
        QUICK_MAX = 1

        def __init__(self, probe, rebuild, **kw):
            seen["rebuild"] = rebuild

        def run(self, *a, **kw):
            seen["result"] = seen["rebuild"]("sid-x")

    monkeypatch.setattr("codemap.watch.DebouncedPoller", Poller)
    monkeypatch.setattr(cli, "_watch_start_is_stale", lambda out, sid: False)
    main(["watch", "pkg", "-o", "w.json", "--consumer", "tests"])
    assert seen["result"] is False
    assert "rebuild FAILED" in capsys.readouterr().err


def test_E5_refused_before_the_core_is_extracted(repo, capsys, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("core extracted before the roots were checked")
    monkeypatch.setattr("codemap.extract.roots.extract", boom)
    monkeypatch.setattr(cli, "extract_repo", lambda *a, **kw: boom())
    assert _build("--deep", "--consumer", "nope") == 2
    assert "no such directory" in capsys.readouterr().err


def test_E6_the_library_refuses_too(repo):
    with pytest.raises(ValueError, match="`--consumer nope`: no such directory"):
        extract_repo("pkg", consumers=("tests", "nope"))
    with pytest.raises(ValueError, match="`--docs README.md`: not a directory"):
        Path("README.md").write_text("x\n")
        extract_repo("pkg", docs=("README.md",))


def test_E7_an_empty_directory_is_still_a_legal_root(repo):
    assert _build("--consumer", "empty") == 0
    assert _build("--consumer", "tests", "--docs", "empty") == 0
