"""A live class and a `@deprecated` one — the deprecation-detection target.

griffe reads decorators statically (it never imports this), and codemap flags a
symbol deprecated when any decorator's last component is ``deprecated`` — so a bare
``@deprecated`` marker is enough; no runtime decorator is needed.
"""

from typing import Any


def deprecated(obj: Any) -> Any:
    """No-op stand-in so the fixture is valid Python (griffe parses, never imports)."""
    return obj


class LiveThing:
    """A current, supported class."""

    def run(self) -> int:
        return 1


@deprecated
class OldThing:
    """A deprecated class — kept for the deprecation-detection acceptance."""

    def run(self) -> int:
        return 0
