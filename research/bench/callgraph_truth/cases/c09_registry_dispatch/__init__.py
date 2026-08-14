"""Design-boundary: dispatch through a string-keyed registry. ``REGISTRY[key]()``
is not an import-time call edge — it is a *bridged* seam. codemap models these
via its registry-bridging pass (M7), not as a resolved ``calls`` edge, so the
call-graph edge run→build_a is deliberately absent here (the bridge is a
separate, honestly-labeled channel).
"""


def build_a():
    return 1


def build_b():
    return 2


REGISTRY = {"a": build_a, "b": build_b}


def run(key):
    return REGISTRY[key]()  # resolved via the registry, not a direct call
