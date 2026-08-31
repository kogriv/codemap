"""R1-C38 — a warm server holds a graph *and* code, and only one of them reloads.

Measured, not imagined. While closing an unrelated debt — "the MCP path for the new
fields was exercised through `Session.handle`, not through a live agent" — the live check
was run: the bquant graph was rebuilt with 0.0.5 and `reload` picked it up, 4656 → 4743
nodes, the schema-mismatch diagnostic gone. The dossier came back **without `signature`**,
which the rebuilt artifact plainly contained.

Nothing was broken. The server process had been started before R1-C33 landed, so it was
running the old `build_query_result` over a new graph, and no part of the answer said so.
`reload` refreshes the artifact; nothing refreshes the code.

`stats` already separates the graph's schema from the running tool's (R1-C25). This is the
same separation one level up, and it is only observable because the version comes from the
installed metadata, read at call time, while the code was loaded at import: when those two
disagree, a restart is pending. `reload` carries the diagnostic too — the op whose name
promises freshness owes the caller the half it cannot deliver.
"""

from __future__ import annotations

from codemap.serve.session import tool_drift


def test_agreement_is_silent():
    assert tool_drift("0.0.5", "0.0.5") is None


def test_a_process_older_than_what_is_installed_says_restart():
    d = tool_drift("0.0.4", "0.0.5")
    assert d["code"] == "tool_restart_needed" and d["severity"] == "warning"
    assert d["running"] == "0.0.4" and d["installed"] == "0.0.5"
    assert "restart" in d["message"]


def test_it_names_reload_as_the_thing_that_will_not_help():
    """The whole point: the user's next move would otherwise be `reload`, again."""
    assert "reload" in tool_drift("0.0.4", "0.0.5")["consequence"]


def test_the_other_direction_is_reported_too():
    """A process newer than the installed distribution is equally a mismatch — saying
    nothing about it would be guessing which direction is the interesting one."""
    d = tool_drift("0.0.6", "0.0.5")
    assert d is not None and d["running"] == "0.0.6" and d["installed"] == "0.0.5"


def test_an_unknown_version_is_not_a_drift():
    """Not installed, or a version we could not read, is silence — not a warning invented
    out of an absent answer."""
    assert tool_drift(None, "0.0.5") is None
    assert tool_drift("0.0.5", None) is None
    assert tool_drift(None, None) is None


def test_stats_and_reload_carry_it_when_it_applies(tmp_path, monkeypatch):
    import codemap
    from codemap.extract import extract
    from codemap.serve.session import Session
    from codemap.store import save

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text("def f():\n    return 1\n")
    out = tmp_path / "g.json"
    graph = extract(str(pkg))
    save(graph, str(out))

    s = Session(graph, graph_path=str(out))
    monkeypatch.setattr(codemap, "__version__", "0.0.0-old", raising=False)
    codes = {d["code"] for d in s.handle({"op": "stats", "args": {}})["result"].get("diagnostics", [])}
    assert "tool_restart_needed" in codes
    reload_out = s.handle({"op": "reload", "args": {}})["result"]
    assert any(d["code"] == "tool_restart_needed" for d in reload_out.get("diagnostics", []))
