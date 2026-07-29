"""Callers exercising positional / keyword / multi-site / splat shapes."""

from argpkg.api import configure


def one_positional():
    return configure("a")


def two_sites_here():
    x = configure("b")            # site 1
    y = configure("c", mode="x")  # site 2 — adds a kwarg
    return x, y


def splatted(args):
    return configure(*args)       # arity unknown -> splat
