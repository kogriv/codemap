"""External-tool integration layer (DESIGN §13 / §13.1).

The opt-in adapter/router framework over third-party code-analysis tools. The core
never depends on it — an integration is only reached when a user opts in
(``codemap.toml``) and the tool is installed. See :mod:`codemap.integrations.base`
for the five-mode model and the two output contracts.

Concrete integrations register themselves on import (P2 gitnexus router, P3
graphlens adapter); importing this package must have no external side effects.
"""

from __future__ import annotations

from .base import (
    GraphFragment,
    Integration,
    IntegrationMode,
    RawAnswer,
    is_permissive,
)
from .gate import IntegrationConfig, load_config
from .registry import (
    all_integrations,
    get,
    register,
    resolve,
    unregister,
)

# Import concrete integrations so they self-register (dict inserts only — no I/O;
# availability/subprocess calls happen lazily at resolve/route time). DESIGN §13.1.
from . import gitnexus as _gitnexus  # noqa: E402,F401

__all__ = [
    "GraphFragment",
    "Integration",
    "IntegrationMode",
    "RawAnswer",
    "is_permissive",
    "IntegrationConfig",
    "load_config",
    "all_integrations",
    "get",
    "register",
    "resolve",
    "unregister",
]
