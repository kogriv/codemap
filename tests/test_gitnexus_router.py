"""P2 acceptance — GitNexus router (DESIGN §13.1, mode 4).

The router mechanism is tested with the subprocess monkeypatched (no 1.7 GB Node
install): registration under the licensing policy, argv construction, answer
wrapping, graceful degrade, and the `codemap route` CLI. A live end-to-end call is
gated on `gitnexus` actually being installed.
"""

from __future__ import annotations

import json

import pytest

from codemap.integrations import gitnexus, registry
from codemap.integrations.base import IntegrationMode, RawAnswer


def test_gitnexus_registered_as_router():
    g = registry.get("gitnexus")
    assert g is not None
    assert g.mode is IntegrationMode.ROUTER
    # Non-commercial → router-only was accepted by the registry (adapter would raise).
    assert "Noncommercial" in g.license
    assert set(g.capabilities) == {"semantic-search", "flow-narrative", "community-clusters"}


def test_argv_per_capability():
    g = gitnexus.GitNexusRouter()
    assert g._argv("semantic-search", "how are zones detected", ["gitnexus"]) == [
        "gitnexus", "search", "how are zones detected", "--json"]
    assert g._argv("community-clusters", "", ["gitnexus"]) == [
        "gitnexus", "check", "--clusters", "--json"]


def test_argv_carries_npx_launcher():
    # the launcher (global bin vs `npx …`) is prepended verbatim; the tail is identical.
    g = gitnexus.GitNexusRouter()
    launcher = ["npx", "--no-install", "gitnexus"]
    assert g._argv("semantic-search", "zones", launcher) == [
        "npx", "--no-install", "gitnexus", "search", "zones", "--json"]


def test_launcher_prefers_global_binary(monkeypatch):
    monkeypatch.setattr(gitnexus, "which", lambda b: "/usr/bin/gitnexus")
    assert gitnexus.GitNexusRouter()._launcher() == ["gitnexus"]


def test_launcher_falls_back_to_npx(monkeypatch):
    # global gitnexus absent, but npx present → serve a local `npm install gitnexus`.
    monkeypatch.setattr(gitnexus, "which", lambda b: None if b == "gitnexus" else "/usr/bin/npx")
    assert gitnexus.GitNexusRouter()._launcher() == ["npx", "--no-install", "gitnexus"]


def test_launcher_none_when_neither_present(monkeypatch):
    monkeypatch.setattr(gitnexus, "which", lambda b: None)
    g = gitnexus.GitNexusRouter()
    assert g._launcher() is None
    assert g.is_available() is False
    # route degrades cleanly — no launcher → payload None, never a crash or a download.
    assert g.route("semantic-search", "zones").payload is None


def test_route_wraps_answer_with_disclaimer(monkeypatch):
    monkeypatch.setattr(gitnexus, "run_json", lambda argv, **kw: {"hits": ["z"]})
    ans = gitnexus.GitNexusRouter().route("semantic-search", "zones")
    assert isinstance(ans, RawAnswer)
    d = ans.to_dict()
    assert d["passthrough"] is True           # never claims to be our graph data
    assert d["payload"] == {"hits": ["z"]}    # forwarded untouched
    assert "non-commercial" in d["disclaimer"]


def test_route_degrades_when_tool_fails(monkeypatch):
    # run_json returns None on any failure → payload None, no crash.
    monkeypatch.setattr(gitnexus, "run_json", lambda argv, **kw: None)
    ans = gitnexus.GitNexusRouter().route("semantic-search", "zones")
    assert ans.payload is None


def test_route_rejects_unknown_capability():
    with pytest.raises(ValueError, match="does not provide"):
        gitnexus.GitNexusRouter().route("call-contract", "x")


def test_is_available_reflects_binary(monkeypatch):
    monkeypatch.setattr(gitnexus, "which", lambda b: None)
    assert gitnexus.GitNexusRouter().is_available() is False
    monkeypatch.setattr(gitnexus, "which", lambda b: "/usr/bin/gitnexus")
    assert gitnexus.GitNexusRouter().is_available() is True


# -- CLI ---------------------------------------------------------------------

def test_cli_route_errors_when_not_enabled(tmp_path, capsys):
    from codemap.cli import main
    # No codemap.toml → gitnexus not opted in → clean error, not a crash.
    with pytest.raises(SystemExit):
        main(["route", "semantic-search", "zones", "--root", str(tmp_path)])


def test_cli_route_forwards_when_enabled(tmp_path, monkeypatch, capsys):
    from codemap.cli import main
    (tmp_path / "codemap.toml").write_text(
        '[integrations]\nenabled = ["gitnexus"]\nacknowledged = ["gitnexus"]\n',
        encoding="utf-8")
    monkeypatch.setattr(gitnexus, "which", lambda b: "/usr/bin/gitnexus")
    monkeypatch.setattr(gitnexus, "run_json", lambda argv, **kw: {"hits": ["Z"]})
    rc = main(["route", "semantic-search", "zones", "--root", str(tmp_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["source"] == "gitnexus" and out["payload"] == {"hits": ["Z"]}


def test_cli_route_shows_disclaimer_when_unacknowledged(tmp_path, monkeypatch, capsys):
    from codemap.cli import main
    (tmp_path / "codemap.toml").write_text(
        '[integrations]\nenabled = ["gitnexus"]\n', encoding="utf-8")  # no acknowledged
    monkeypatch.setattr(gitnexus, "which", lambda b: "/usr/bin/gitnexus")
    monkeypatch.setattr(gitnexus, "run_json", lambda argv, **kw: {"ok": 1})
    main(["route", "semantic-search", "zones", "--root", str(tmp_path)])
    assert "non-commercial" in capsys.readouterr().err   # notice on stderr
