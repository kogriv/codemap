"""Undecidable tail: a function is passed as an argument and called via the
parameter. A sound static analyzer cannot in general know which function
``fn`` binds to at the call site ``fn()`` — this is the higher-order ceiling.
"""


def target():
    return 1


def apply(fn):
    return fn()  # fn is target(), but only known via data-flow through the arg


def run():
    return apply(target)
