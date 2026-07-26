"""main() builds an Engine as a LOCAL variable and calls a method on it.

Fast tier: `e.run()` is an x.foo() on a local — unresolved.
Deep tier: jedi infers e: Engine, resolves to deeppkg.core.Engine.run.
"""
from deeppkg.core import Engine


def main() -> int:
    e = Engine()          # local variable
    return e.run()        # the tail: only the deep tier cracks this
