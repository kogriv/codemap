"""Import-time work: the call the behavior pass never walked."""

from panels import _really_dead   # noqa: F401  (flat import, fixture is a package too)


def _register():
    return "registered"


_register()                        # module-level call
