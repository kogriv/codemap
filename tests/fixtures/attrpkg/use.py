"""Consumers: construction kwargs, ClassName.field, obj.field on a local, method call."""

from attrpkg.models import Config


def make():
    return Config(width=5, height=6)      # construction kwargs -> writes width, height


def use_class():
    return Config.width                   # ClassName.field -> read (class)


def use_local():
    c = make()
    total = c.width + c.height            # obj.field reads -> deep tier only
    c.height = 99                         # obj.field write -> deep tier only
    return total


def call_method():
    c = make()
    return c.area()                       # method call -> a `calls` edge, NOT `accesses`
