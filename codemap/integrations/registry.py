"""Integration registry — register tools, resolve a capability to a live one.

DESIGN §13.1. The registry is where the licensing policy is machine-enforced: an
**adapter** (which absorbs the tool's output into our artifact) must be permissive-
licensed; a **router** (which only forwards) may be any license. Registration of a
non-permissive adapter is a programming error and raises.

Resolution is **capability-first** (the chosen UX, DESIGN §13.1 decision): a caller
asks for a capability ("semantic-search", "resolve-into-deps"), and the registry
returns an integration that (a) provides it, (b) is opted-in via config, and (c) is
actually installed. The concrete tool stays hidden behind the capability.
"""

from __future__ import annotations

from .base import Integration, IntegrationMode, is_permissive
from .gate import IntegrationConfig, load_config

_REGISTRY: dict[str, Integration] = {}


def register(integration: Integration) -> Integration:
    """Register an integration, enforcing the DESIGN §13.1 licensing policy.

    Raises ``ValueError`` if an adapter is not permissive-licensed (adapters absorb
    output into our artifact → MIT/Apache only; a non-commercial tool can only be a
    router). Idempotent-friendly: re-registering the same name overwrites.
    """
    if (integration.mode is IntegrationMode.ADAPTER
            and not is_permissive(integration.license)):
        raise ValueError(
            f"adapter '{integration.name}' has non-permissive license "
            f"{integration.license!r}: a tool whose output we absorb must be "
            f"MIT/Apache-class (DESIGN §13.1); use router mode instead."
        )
    _REGISTRY[integration.name] = integration
    return integration


def unregister(name: str) -> None:
    _REGISTRY.pop(name, None)


def get(name: str) -> Integration | None:
    return _REGISTRY.get(name)


def all_integrations() -> list[Integration]:
    return [_REGISTRY[n] for n in sorted(_REGISTRY)]


def resolve(capability: str, *, config: IntegrationConfig | None = None,
            root: str = ".") -> Integration | None:
    """Return an enabled + installed integration providing ``capability``, or None.

    Capability-first dispatch: the tool is picked for the caller. Requires all three
    gates — provides the capability, opted-in (``config.enabled``), and
    ``is_available()`` — so the core degrades cleanly when nothing satisfies them.
    Deterministic tie-break by name.
    """
    cfg = config if config is not None else load_config(root)
    for integ in all_integrations():  # sorted by name → deterministic pick
        if (capability in integ.capabilities
                and cfg.is_enabled(integ.name)
                and integ.is_available()):
            return integ
    return None
