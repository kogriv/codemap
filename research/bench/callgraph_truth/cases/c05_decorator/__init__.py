"""Partly decidable: a decorated function. The definition-site call
``deco(worker)`` is decidable; whether a *call to* ``worker`` dispatches through
the wrapper is a resolution nuance most static tools flatten.
"""


def deco(fn):
    def wrapper(*a, **k):
        return fn(*a, **k)
    return wrapper


@deco
def worker():
    return 1


def run():
    return worker()
