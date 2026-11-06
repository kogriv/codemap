"""R1-C85 — every served answer says whether its graph matches the tree.

Design `docs/design/mcp_graph_currency.md` (pre-registered 79a7fd2).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap import store
from codemap.cli import main
from codemap.extract import extract
from codemap.serve.session import Session


@pytest.fixture
def built(tmp_path, monkeypatch):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text("def f():\n    return 1\n")
    monkeypatch.chdir(tmp_path)
    g = tmp_path / "g.json"
    assert main(["build", "pkg", "-o", str(g)]) == 0
    return tmp_path, g


def _session(g, ttl=10.0):
    return Session(store.load(str(g)), graph_path=str(g), currency_ttl=ttl)


def _edit(root):
    (root / "pkg" / "m.py").write_text("def f():\n    return 2\n")


def test_E1_every_envelope_carries_currency(built):
    root, g = built
    s = _session(g, ttl=0)
    for op, args in (("stats", {}), ("search", {"term": "f"}), ("query", {"name": "f"})):
        env = s.handle({"op": op, "args": args})
        assert env["ok"] and env["currency"]["status"] == "current", (op, env.get("currency"))
    _edit(root)
    c = s.handle({"op": "search", "args": {"term": "f"}})["currency"]
    assert c["status"] == "behind" and c["changed"] == 1 and "rebuild" in c["hint"]


def test_E1_an_in_process_build_is_unknown_with_a_reason(built):
    root, _ = built
    s = Session(extract(str(root / "pkg")))
    c = s.handle({"op": "stats"})["currency"]
    assert c["status"] == "unknown" and "in-process build" in c["reason"]


def test_E2_the_check_is_cached_for_the_ttl(built):
    _, g = built
    s = _session(g, ttl=10)
    for _ in range(5):
        s.handle({"op": "search", "args": {"term": "f"}})
    assert s._currency_checks == 1
    s0 = _session(g, ttl=0)
    for _ in range(3):
        s0.handle({"op": "search", "args": {"term": "f"}})
    assert s0._currency_checks == 3


def test_E2_a_cached_answer_states_its_age(built):
    _, g = built
    c = _session(g).handle({"op": "search", "args": {"term": "f"}})["currency"]
    assert c["checked_seconds_ago"] == 0


def test_E3_reload_drops_the_cache(built):
    root, g = built
    s = _session(g, ttl=3600)
    assert s.handle({"op": "stats"})["currency"]["status"] == "current"
    _edit(root)
    assert s.handle({"op": "stats"})["currency"]["status"] == "current"   # cached, by design
    assert main(["build", "pkg", "-o", str(g)]) == 0
    s.handle({"op": "reload"})
    assert s.handle({"op": "stats"})["currency"]["status"] == "current"
    _edit(root)        # same content as the rebuild: still current; now change it again
    (root / "pkg" / "m.py").write_text("def f():\n    return 3\n")
    s.handle({"op": "reload"})                 # the graph on disk is the older one
    assert s.handle({"op": "stats"})["currency"]["status"] == "behind"


def test_D3_stats_shows_currency_beside_freshness(built):
    _, g = built
    r = _session(g).handle({"op": "stats"})["result"]
    assert "freshness" in r and r["currency"]["status"] == "current"


def test_E4_a_cold_cli_read_warns_when_behind(built, capsys):
    root, g = built
    capsys.readouterr()
    assert main(["query", "f", "--graph", str(g)]) == 0
    before = capsys.readouterr()
    assert before.err == ""
    _edit(root)
    assert main(["query", "f", "--graph", str(g)]) == 0
    after = capsys.readouterr()
    assert after.out == before.out
    assert "[warning]" in after.err and "behind its source tree" in after.err and "1 changed" in after.err


def test_E4_check_keeps_its_own_line_and_gets_no_second_warning(built, capsys):
    root, g = built
    _edit(root)
    capsys.readouterr()
    main(["check", "--graph", str(g)])
    assert "[warning]" not in capsys.readouterr().err


def test_D1_it_is_the_served_graph_that_is_judged_not_the_file_on_disk(built):
    """Edit, rebuild on disk, no reload: the file matches the tree, the served graph does not."""
    root, g = built
    s = _session(g, ttl=0)
    _edit(root)
    assert main(["build", "pkg", "-o", str(g)]) == 0
    assert s.handle({"op": "stats"})["currency"]["status"] == "behind"
