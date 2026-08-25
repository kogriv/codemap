"""A hand-built world with known distances — the acceptance depends on them."""


def entry(x):
    return _mid(x)


def _mid(x):
    return _leaf(x)


def _leaf(x):
    return _beyond(x)


def _beyond(x):
    return x


def orphan():
    """Reached by no test at all."""
    return 1


class Engine:
    def run(self):
        return _mid(1)
