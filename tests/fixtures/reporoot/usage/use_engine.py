"""Consumer (loose script, not a package) that uses the core via a re-export."""

from core import Engine  # re-export path: core.Engine -> core.engine.Engine


def scenario() -> int:
    e = Engine()
    return e.run()
