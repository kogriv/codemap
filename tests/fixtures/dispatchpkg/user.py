"""Consumer: bind a strategy on self, call it later (the bquant pattern)."""

from dispatchpkg.factory import create_thing


class Worker:
    def __init__(self, name):
        self.thing = create_thing(name)  # non-literal -> family candidates

    def work(self) -> int:
        return self.thing.run()          # bridged to {Alpha,Beta}.run


def direct_literal() -> int:
    return create_thing('alpha').run()   # literal key -> exact Alpha
