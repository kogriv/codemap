"""M17 acceptance — MCP adapter over the warm serve surface.

The MCP adapter is a thin wrapper: each op → one MCP tool that calls
``Session.handle`` and returns its envelope. mcp is an optional dependency, so the
whole module skips when it is not installed (FOSS checkout without the extra).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="optional 'mcp' extra not installed")

from codemap.extract import extract
from codemap.serve.mcp_server import (
    MCP_TOOLS,
    _cap_list,
    _compact_impact,
    build_mcp_server,
)
from codemap.serve.session import Session

DISPATCH = Path(__file__).resolve().parent / "fixtures" / "dispatchpkg"


def _server():
    return build_mcp_server(Session(extract(DISPATCH)))


def _call(server, name, args):
    """Call a tool and return the parsed envelope dict from its text content."""
    res = asyncio.run(server.call_tool(name, args))
    assert res.is_error is False
    return json.loads(res.content[0].text)


def test_all_ops_registered_as_tools():
    tools = asyncio.run(_server().list_tools())
    assert sorted(t.name for t in tools) == sorted(MCP_TOOLS)


def test_every_tool_has_description():
    # a good MCP tool is self-documented — the LLM picks tools by description.
    tools = asyncio.run(_server().list_tools())
    assert all((t.description or "").strip() for t in tools)


def test_search_tool_routes_to_handle():
    env = _call(_server(), "search", {"term": "Alpha"})
    assert env["ok"] is True
    assert any(r["id"].endswith("Alpha") for r in env["result"])


def test_query_tool_dossier():
    env = _call(_server(), "query", {"name": "ThingProtocol"})
    assert env["ok"] is True
    assert env["result"]["matches"]


def test_ambiguity_signal_survives_the_adapter():
    # F14: a bare ambiguous name ('run' is in Alpha, Beta, Protocol) must carry the
    # resolved.ambiguous warning through the MCP layer, not answer silently.
    env = _call(_server(), "callers", {"symbol": "run"})
    assert env["ok"] is True
    assert env["resolved"]["ambiguous"] is True


def test_bad_args_do_not_crash_the_tool():
    # Session.handle never raises → the tool returns an error envelope, not a fault.
    env = _call(_server(), "query", {"name": "does_not_exist_xyz"})
    assert env["ok"] is True          # query of an unknown name is a valid empty result
    assert env["result"]["matches"] == []


def test_architecture_tool():
    env = _call(_server(), "architecture", {})
    assert env["ok"] is True
    assert "layers" in env["result"]


# -- F22: compact MCP payloads ----------------------------------------------

def test_compact_impact_drops_markdown_and_caps_refs():
    refs = [{"source": f"s{i}"} for i in range(50)]
    env = {"ok": True, "result": {"symbol": "X", "markdown": "…big…",
                                  "impact": [{"refs": refs, "by_root": {"core": 50}}]}}
    out = _compact_impact(env, limit=10)
    entry = out["result"]["impact"][0]
    assert "markdown" not in out["result"]           # duplicate rendering dropped
    assert len(entry["refs"]) == 10                    # flat list capped
    assert entry["refs_total"] == 50                   # total preserved
    assert entry["by_root"] == {"core": 50}            # counts stay complete


def test_cap_list_truncates_with_total():
    env = {"ok": True, "result": [{"caller": f"c{i}"} for i in range(40)],
           "resolved": {"ambiguous": False}}
    out = _cap_list(env, limit=15)
    assert len(out["result"]) == 15
    # R1-C28: was `shown`/`total`, emitted only on truncation — now the shared `limit`
    # block, emitted always, so one vocabulary covers every limited surface.
    assert out["limit"] == {"applied": 15, "returned": 15,
                            "total": 40, "truncated": True}
    assert out["resolved"] == {"ambiguous": False}     # envelope extras preserved


def test_compact_helpers_passthrough_on_error():
    err = {"ok": False, "error": "boom"}
    assert _compact_impact(err, 10) is err
    assert _cap_list(err, 10) is err


def test_impact_tool_compact_by_default_full_on_request():
    s = _server()
    default = _call(s, "impact", {"symbol": "ThingProtocol"})
    assert "markdown" not in default["result"]         # compact default
    full = _call(s, "impact", {"symbol": "ThingProtocol", "full": True})
    assert "markdown" in full["result"]                # full keeps markdown
