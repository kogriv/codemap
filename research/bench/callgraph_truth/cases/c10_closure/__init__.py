"""Decidable: a nested inner function calls a module-level helper by name.
The inner closure is not a graph definition node, so the resolvable edge is
from the enclosing function ``outer`` to ``helper``.
"""


def helper():
    return 1


def outer():
    def inner():
        return helper()
    return inner()
