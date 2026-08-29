"""Decidable: the callee is imported *inside* the calling function (R1-C30, issue #11).

The construct a developer reaches for to break an import cycle, so a tool blind to it is
blind exactly where the cycle question is asked. The second function is the guard: it calls
the same bare name and never imports it, so a resolver that merged the local import into the
module map — buying recall the cheap way — would emit an edge that is not here.
"""

from c11_local_import.leaf import other


def go(x):
    from c11_local_import.leaf import helper
    return helper(x)


def elsewhere(x):
    return helper(x)          # never imported here: NameError at runtime, not an edge


def module_level(x):
    return other(x)           # ordinary module-level import, for contrast
