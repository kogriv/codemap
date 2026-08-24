"""All three reference forms the graph used to miss (R1-C22), plus a genuinely dead one."""

import json


class Report:
    """Referenced only as a type annotation — a contract, not a dispatch."""


def _panel_a(v):
    return v


def _json_default(o):
    return str(o)


def _dispatched():
    """Called only from inside a closure — the nested-def form."""
    return 1


def _really_dead(x):
    """Nothing names this anywhere."""
    return x


PANELS = {"a": _panel_a}          # function as a value, at module level


def render(kind, v) -> Report:    # `Report` here is an annotation reference
    return PANELS[kind](v)


def dump(obj):
    return json.dumps(obj, default=_json_default)   # function as a keyword value


def make_worker():
    def worker():                 # not a definition node — its calls used to vanish
        return _dispatched()
    return worker
