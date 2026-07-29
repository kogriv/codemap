"""The Protocol the registered things structurally satisfy (never inherited)."""

from typing import Protocol


class ThingProtocol(Protocol):
    """Contract every registered thing implements — by structure, not inheritance."""

    def run(self) -> int:
        ...
