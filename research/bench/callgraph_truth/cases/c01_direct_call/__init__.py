"""Decidable: module-level function calls another by name."""


def a():
    return b()


def b():
    return 1
