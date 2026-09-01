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


def _shadow_installed_version(tmp_path, monkeypatch, version: str) -> None:
    """Make the *installed* distribution look like `version`, the way an upgrade would.

    A `dist-info` directory earlier on `sys.path` wins, so this changes what
    `importlib.metadata` answers without touching the imported module — exactly the
    asymmetry a real upgrade under a running server creates.
    """
    d = tmp_path / "site"
    (d / f"codmap-{version}.dist-info").mkdir(parents=True)
    (d / f"codmap-{version}.dist-info" / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: codmap\nVersion: {version}\n")
    monkeypatch.syspath_prepend(str(d))


def test_the_installed_side_is_read_fresh_or_there_is_nothing_to_compare(tmp_path, monkeypatch):
    """R1-C38-f1 — the defect 0.0.6 shipped, and the reason no test caught it.

    Every other test here hands `tool_drift` two versions, or forces a difference by
    patching `codemap.__version__`. Both prove the arithmetic. Neither asks the question
    the feature exists for: *can the condition arise?* It could not — `_tool_drift` read
    the installed side through `tool_version()`, which is `lru_cache`d and first called at
    import by `codemap/__init__.py`, so both sides were the same cached value forever.

    Here nothing about the process is patched. Only the installation changes, as an
    upgrade changes it, and the running server must notice.
    """
    from codemap.serve.session import Session

    assert Session._tool_drift() is None            # agreement before the "upgrade"
    _shadow_installed_version(tmp_path, monkeypatch, "9.9.9")

    d = Session._tool_drift()
    assert d is not None, "the installed version is being read from a process-lifetime cache"
    assert d["code"] == "tool_restart_needed" and d["installed"] == "9.9.9"


def test_the_build_side_stays_cached(tmp_path, monkeypatch):
    """The fix must not turn provenance into a per-call filesystem read: a build stamps
    one version into everything it writes, so `tool_version()` keeps its cache. The two
    readers exist because they answer different questions — "what was it?" and "is it
    still?" — and this is the assertion that keeps them apart."""
    from codemap.provenance import installed_version, tool_version

    before = tool_version()
    _shadow_installed_version(tmp_path, monkeypatch, "9.9.9")
    assert tool_version() == before
    assert installed_version() == "9.9.9"


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
