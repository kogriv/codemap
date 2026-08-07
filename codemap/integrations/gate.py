"""Opt-in gate + licensing disclaimer for external integrations (DESIGN §13.1).

Every integration is **off by default** (invariant: the core works with no external
tool). A user enables one explicitly in ``codemap.toml``::

    [integrations]
    enabled = ["graphlens", "gitnexus"]     # opt-in, not default
    acknowledged = ["gitnexus"]             # licensing notice already accepted

``enabled`` is the opt-in list (DESIGN §13.1 п.2). ``acknowledged`` records which
non-commercial notices the user has already accepted, so the disclaimer (п.3) is
shown once rather than every call. Absent config → nothing enabled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class IntegrationConfig:
    """Resolved ``[integrations]`` config — which tools are opted in / acknowledged."""

    enabled: frozenset[str] = frozenset()
    acknowledged: frozenset[str] = frozenset()

    def is_enabled(self, name: str) -> bool:
        return name in self.enabled

    def is_acknowledged(self, name: str) -> bool:
        return name in self.acknowledged


def load_config(root: str | Path = ".") -> IntegrationConfig:
    """Read ``[integrations]`` from ``codemap.toml`` under ``root`` (empty if absent).

    Uses the stdlib ``tomllib`` (3.11+). A malformed file yields an empty config
    rather than raising — a bad opt-in list must never break a plain build.
    """
    path = Path(root) / "codemap.toml"
    if not path.is_file():
        return IntegrationConfig()
    try:
        import tomllib
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ModuleNotFoundError):
        return IntegrationConfig()
    section = data.get("integrations", {})
    return IntegrationConfig(
        enabled=frozenset(section.get("enabled", []) or []),
        acknowledged=frozenset(section.get("acknowledged", []) or []),
    )
