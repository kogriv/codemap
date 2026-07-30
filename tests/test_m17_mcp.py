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
from codemap.serve.mcp_server import MCP_TOOLS, build_mcp_server
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
