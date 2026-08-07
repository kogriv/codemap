"""Integration contracts — the two deep-coupling modes that need shared infra.

DESIGN §13 / §13.1. Five integration modes exist on a depth×license gradient:

    0. reimplement (learn-and-build)  — our own code, their idea; no tool, no infra
    1. vendoring (copy source in)     — like `_scip_pb2.py`; permissive license only
    2. library embed (pip dependency) — an extractor plugin; permissive license only
    3. adapter                        — call user-installed tool, TRANSLATE its output
                                        into our neutral graph; permissive only
    4. router / passthrough           — call user-installed tool, FORWARD its answer
                                        as-is; even non-commercial OK (opt-in + notice)

Modes 0–2 reuse existing patterns (native code, vendored subpackage, `extract/`
plugin). Only **adapter** and **router** need this package: they call an external
tool the user installed and either absorb its output (adapter) or forward it
(router). The invariant (DESIGN §13): the core never depends on an external tool —
every integration is opt-in and the baseline works without it.

Two output contracts, because the modes return fundamentally different things:

  * an **adapter** yields a :class:`GraphFragment` — nodes/edges in our schema,
    tagged ``provenance: external`` + resolver name, written to a **non-canonical
    sidecar** (the canonical core graph stays deterministic — many external tools
    are not);
  * a **router** yields a :class:`RawAnswer` — the tool's answer untouched, which
    never enters the graph.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntegrationMode(str, Enum):
    """The coupling mode of an integration (the two that need this infra)."""

    ADAPTER = "adapter"  # translate the tool's output into our graph (permissive only)
    ROUTER = "router"    # forward the tool's answer as-is (any license, opt-in)


# Licenses under which we may **absorb** a tool's output into our artifact (adapter)
# or depend on it. Anything else is router-only: we forward, never incorporate.
# This is the machine-checkable half of the DESIGN §13.1 licensing policy.
_PERMISSIVE = frozenset({
    "mit", "apache-2.0", "apache 2.0", "apache", "bsd", "bsd-2-clause",
    "bsd-3-clause", "isc", "unlicense", "0bsd", "psf",
})


def is_permissive(license_id: str) -> bool:
    """True if ``license_id`` permits absorbing the tool's output (adapter-eligible).

    Normalizes case/spacing; unknown or non-commercial licenses (e.g. PolyForm
    Noncommercial) return False → such a tool may only be a :class:`IntegrationMode.ROUTER`.
    """
    return license_id.strip().lower() in _PERMISSIVE


@dataclass
class GraphFragment:
    """Adapter output — graph nodes/edges to be merged into a **non-canonical sidecar**.

    Every node/edge is stamped with provenance so it never masquerades as part of
    the deterministic core graph: ``extras.provenance = 'external'`` and
    ``extras.resolver = <tool name>``. ``deterministic`` records whether the source
    tool produces stable output — False (the common case, e.g. graphlens' SQLite)
    is why fragments live in a sidecar, not the canonical graph.
    """

    resolver: str
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    deterministic: bool = False

    def stamped(self) -> "GraphFragment":
        """Return a copy with every node/edge tagged external + resolver."""
        tag = {"provenance": "external", "resolver": self.resolver}
        nodes = [{**n, "extras": {**n.get("extras", {}), **tag}} for n in self.nodes]
        edges = [{**e, "extras": {**e.get("extras", {}), **tag}} for e in self.edges]
        return GraphFragment(self.resolver, nodes, edges, self.deterministic)

    def to_sidecar_dict(self) -> dict[str, Any]:
        """Serialize for the ``external_edges.json`` sidecar (non-canonical)."""
        f = self.stamped()
        return {
            "resolver": f.resolver,
            "deterministic": f.deterministic,
            "canonical": False,  # explicit: never part of the deterministic core graph
            "nodes": f.nodes,
            "edges": f.edges,
        }


@dataclass
class RawAnswer:
    """Router output — the external tool's answer, forwarded untouched.

    It is never parsed into our schema. ``source`` names the tool; ``disclaimer`` is
    the licensing notice shown to the user; ``payload`` is whatever the tool returned.
    """

    source: str
    payload: Any
    disclaimer: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "passthrough": True,
                "disclaimer": self.disclaimer, "payload": self.payload}


class Integration(abc.ABC):
    """One external tool, wired in adapter or router mode.

    Subclasses declare identity + the capabilities they provide and implement
    availability detection. Adapters implement :meth:`extract_fragments`; routers
    implement :meth:`route`. The registry enforces the licensing policy
    (adapters must be permissive-licensed) at registration time.
    """

    #: short, stable identifier (e.g. "graphlens", "gitnexus")
    name: str
    #: :class:`IntegrationMode`
    mode: IntegrationMode
    #: SPDX-ish license id (checked by :func:`is_permissive`)
    license: str
    #: capability keys this tool provides (e.g. ("resolve-into-deps",))
    capabilities: tuple[str, ...] = ()

    @abc.abstractmethod
    def is_available(self) -> bool:
        """True if the user has the tool installed and it is usable."""

    def disclaimer(self) -> str | None:
        """One-time licensing notice, or None for a permissive tool.

        For a non-commercial tool the notice is worded on **use**, not reselling
        (DESIGN §13.1 п.3): routing to it is only for non-commercial use.
        """
        if is_permissive(self.license):
            return None
        return (
            f"Tool '{self.name}' is licensed {self.license}. This route is for "
            f"non-commercial use only; for commercial use of codemap, do not enable "
            f"it, or obtain a commercial license from the tool's author."
        )

    # -- mode-specific surfaces (implement the one for your mode) -------------

    def extract_fragments(self, target: str, **kw: Any) -> GraphFragment:  # adapter
        raise NotImplementedError(f"{self.name} is not an adapter")

    def route(self, capability: str, question: str, **kw: Any) -> RawAnswer:  # router
        raise NotImplementedError(f"{self.name} is not a router")
