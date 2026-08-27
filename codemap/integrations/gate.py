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

from codemap.tomlio import read_toml


@dataclass
class IntegrationConfig:
    """Resolved ``[integrations]`` config — which tools are opted in / acknowledged.

    ``error`` carries the reason ``codemap.toml`` could not be read, if it could not be
    (R1-C27). Nothing is enabled either way — the opt-in invariant is not weakened by a
    read failure — but a user who wrote an opt-in list and got a typo deserves to hear
    that, rather than watch the integration quietly stay off.
    """

    enabled: frozenset[str] = frozenset()
    acknowledged: frozenset[str] = frozenset()
    error: str | None = None

    def is_enabled(self, name: str) -> bool:
        return name in self.enabled

    def is_acknowledged(self, name: str) -> bool:
        return name in self.acknowledged


def load_config(root: str | Path = ".") -> IntegrationConfig:
    """Read ``[integrations]`` from ``codemap.toml`` under ``root`` (empty if absent).

    A malformed file yields an empty config rather than raising — a bad opt-in list must
    never break a plain build — but the reason travels back in ``error`` instead of being
    indistinguishable from "no config" (R1-C27).
    """
    data, error = read_toml(Path(root) / "codemap.toml")
    if error:
        return IntegrationConfig(error=error)
    section = data.get("integrations", {})
    return IntegrationConfig(
        enabled=frozenset(section.get("enabled", []) or []),
        acknowledged=frozenset(section.get("acknowledged", []) or []),
    )
