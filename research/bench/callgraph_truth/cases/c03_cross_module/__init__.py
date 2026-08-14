"""Decidable: caller in one module calls a function imported from a sibling."""

from c03_cross_module.other import helper


def run():
    return helper()
