"""P1 acceptance — the integration core (registry + gate + contracts).

Exercises the shared adapter/router infra with in-test fakes (no external tools):
licensing policy enforcement, opt-in gating, capability-first resolution, and the
two output contracts. DESIGN §13.1.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codemap.integrations import (
    GraphFragment,
    Integration,
    IntegrationConfig,
    IntegrationMode,
    RawAnswer,
    is_permissive,
    load_config,
)
from codemap.integrations import registry


# -- fakes -------------------------------------------------------------------

class FakeAdapter(Integration):
    name = "fake-adapter"
    mode = IntegrationMode.ADAPTER
    license = "MIT"
    capabilities = ("resolve-into-deps",)

    def __init__(self, available: bool = True) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def extract_fragments(self, target, **kw) -> GraphFragment:
        return GraphFragment(
            resolver=self.name,
            edges=[{"type": "calls_external", "source": "pkg.f", "target": "numpy.mean"}],
        )


class FakeRouter(Integration):
    name = "fake-router"
    mode = IntegrationMode.ROUTER
    license = "PolyForm-Noncommercial-1.0.0"
    capabilities = ("semantic-search",)

    def is_available(self) -> bool:
        return True

    def route(self, capability, question, **kw) -> RawAnswer:
        return RawAnswer(source=self.name, payload={"hits": [question]},
                         disclaimer=self.disclaimer())


@pytest.fixture(autouse=True)
def _clean_registry():
    """Each test starts with an empty registry (module-global otherwise leaks)."""
    for i in list(registry.all_integrations()):
        registry.unregister(i.name)
    yield
    for i in list(registry.all_integrations()):
        registry.unregister(i.name)


# -- licensing policy (the machine-checked half of §13.1) --------------------

def test_permissive_classifier():
    assert is_permissive("MIT")
    assert is_permissive("apache-2.0")
    assert not is_permissive("PolyForm-Noncommercial-1.0.0")
    assert not is_permissive("GPL-3.0")


def test_registry_rejects_noncommercial_adapter():
    # An adapter absorbs output into our artifact → must be permissive (§13.1).
    class BadAdapter(FakeAdapter):
        name = "bad"
        license = "PolyForm-Noncommercial-1.0.0"

    with pytest.raises(ValueError, match="non-permissive"):
        registry.register(BadAdapter())


def test_registry_allows_noncommercial_router():
    # A router only forwards → any license is fine (opt-in + disclaimer).
    registry.register(FakeRouter())
    assert registry.get("fake-router") is not None


# -- opt-in gate -------------------------------------------------------------

def test_disabled_by_default():
    registry.register(FakeRouter())
    # No config → nothing enabled → capability resolves to nothing.
    assert registry.resolve("semantic-search", config=IntegrationConfig()) is None


def test_enabled_resolves():
    registry.register(FakeRouter())
    cfg = IntegrationConfig(enabled=frozenset({"fake-router"}))
    got = registry.resolve("semantic-search", config=cfg)
    assert got is not None and got.name == "fake-router"


def test_unavailable_tool_does_not_resolve():
    registry.register(FakeAdapter(available=False))
    cfg = IntegrationConfig(enabled=frozenset({"fake-adapter"}))
    assert registry.resolve("resolve-into-deps", config=cfg) is None


def test_resolution_requires_matching_capability():
    registry.register(FakeRouter())
    cfg = IntegrationConfig(enabled=frozenset({"fake-router"}))
    assert registry.resolve("resolve-into-deps", config=cfg) is None


def test_resolution_is_deterministic_by_name():
    # Two enabled providers of the same capability → the name-sorted first wins.
    class A(FakeRouter):
        name = "aaa"
        capabilities = ("semantic-search",)

    class B(FakeRouter):
        name = "bbb"
        capabilities = ("semantic-search",)

    registry.register(B())
    registry.register(A())
    cfg = IntegrationConfig(enabled=frozenset({"aaa", "bbb"}))
    assert registry.resolve("semantic-search", config=cfg).name == "aaa"


# -- config loading ----------------------------------------------------------

def test_load_config_absent(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.enabled == frozenset() and cfg.acknowledged == frozenset()


def test_load_config_reads_toml(tmp_path):
    (tmp_path / "codemap.toml").write_text(
        '[integrations]\nenabled = ["gitnexus"]\nacknowledged = ["gitnexus"]\n',
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg.is_enabled("gitnexus")
    assert cfg.is_acknowledged("gitnexus")


def test_load_config_malformed_is_empty(tmp_path):
    (tmp_path / "codemap.toml").write_text("not = valid = toml =", encoding="utf-8")
    assert load_config(tmp_path).enabled == frozenset()


# -- output contracts --------------------------------------------------------

def test_graph_fragment_stamps_provenance():
    frag = FakeAdapter().extract_fragments("pkg").stamped()
    e = frag.edges[0]
    assert e["extras"]["provenance"] == "external"
    assert e["extras"]["resolver"] == "fake-adapter"


def test_fragment_sidecar_is_non_canonical():
    d = FakeAdapter().extract_fragments("pkg").to_sidecar_dict()
    assert d["canonical"] is False           # never part of the deterministic core
    assert d["deterministic"] is False       # graphlens-class tools aren't stable
    assert json.dumps(d)                      # serializable for the sidecar file


def test_raw_answer_marks_passthrough_and_disclaimer():
    ans = FakeRouter().route("semantic-search", "where is X").to_dict()
    assert ans["passthrough"] is True         # never claims to be graph data
    assert ans["source"] == "fake-router"
    assert "non-commercial" in ans["disclaimer"]


def test_permissive_router_has_no_disclaimer():
    class MitRouter(FakeRouter):
        name = "mit-router"
        license = "MIT"

    assert MitRouter().disclaimer() is None
