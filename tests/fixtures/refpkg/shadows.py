"""Local bindings that merely *share a name* with a module-level function (R1-C22-f1).

Python binds per scope: once a name is bound anywhere in a function, every read of it in
that function is the local one — so none of these are references to the functions above.
"""

from panels import _panel_a  # noqa: F401  (flat-layout sibling import, exercised elsewhere)


def _shadowed_assign(x):
    return x


def _shadowed_param(x):
    return x


def _shadowed_loop(x):
    return x


def _shadowed_with(x):
    return x


def _shadowed_except(x):
    return x


def _shadowed_nested(x):
    return x


def _rebound_global(x):
    return x


def by_assign():
    _shadowed_assign = 1
    return _shadowed_assign


def by_param(_shadowed_param):
    return _shadowed_param


def by_loop(items):
    for _shadowed_loop in items:
        print(_shadowed_loop)


def by_with(ctx):
    with ctx as _shadowed_with:
        return _shadowed_with


def by_except():
    try:
        pass
    except ValueError as _shadowed_except:
        return _shadowed_except


def by_nested():
    def _shadowed_nested():
        return 2
    return _shadowed_nested


def by_global():
    global _rebound_global      # opts back out: this *is* the module binding
    _rebound_global = 1
    return _rebound_global


def by_local_import():
    """A local import binds the name to the symbol it *imports* — the very thing an edge
    would record — so it must not count as shadowing the way an assignment does.

    (Whether such a name resolves at all is a separate, pre-existing matter: it depends on
    griffe's module import map, which records some function-local imports and not others.)
    """
    from .panels import _json_default
    return _json_default
