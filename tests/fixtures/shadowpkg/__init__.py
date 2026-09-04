"""R1-C46 fixture: a name defined twice in one scope, and the idioms that only look like it.

`Thing.get` is the real thing — the second body silently replaces the first, so a
graph that walks both attributes a call to `one` to code that can never run. The four
blocks after it are legitimate re-bindings (overload, property accessor, singledispatch
registration, conditional definition) and must produce no `shadows` at all.
"""
from functools import singledispatch
from typing import TYPE_CHECKING, overload


def one():
    return 1


def two():
    return 2


class Thing:
    def get(self):
        return one()   # SHADOWED — can never run

    def get(self):
        return two()


@overload
def parse(x: int) -> int: ...
@overload
def parse(x: str) -> str: ...
def parse(x):
    return one()


class Box:
    @property
    def value(self):
        return one()

    @value.setter
    def value(self, v):
        two()


@singledispatch
def render(x):
    return one()


@render.register
def _(x: int):
    return two()


if TYPE_CHECKING:
    def maybe():
        return one()
else:
    def maybe():
        return two()
