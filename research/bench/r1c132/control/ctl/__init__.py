"""R1-C132 control package: every shape of call the tracer must attribute the way codemap does."""

import contextlib
import functools

def g():
    return 1

def h(x):
    return x

class C:
    def __init__(self):
        self.v = g()
    def m(self):
        return h(self.v)

class D(C):
    pass

def deco(fn):
    @functools.wraps(fn)
    def wrapper(*a):
        return fn(*a)
    return wrapper

@deco
def decorated():
    return g()

def outer():
    def inner():
        return h(2)
    lam = lambda: g()
    xs = [h(i) for i in range(2)]
    return inner() + lam() + D().m() + decorated() + sorted([1], key=h)[0]


class A:
    def run(self):
        return 1


class B:
    def run(self):
        return 2


def pick(flag=False):
    a = A()
    if flag:
        return B().run()
    return a.run()


class E(C):
    def __init__(self):
        super().__init__()


def make_e():
    return E()


def only_a():
    return A().run()


def never_called():
    return h(3)


def gen():
    yield h(4)


def use_gen():
    return gen()


class G:
    def items(self):
        yield 1


def make_rule():
    def rule():
        return h(5)            # runs later, from run_rules: still make_rule's call, as codemap reads it
    return rule


def make_rule_with(obj):
    def rule():
        return h(5) if obj is not None else 0     # the closure holds an object a lookup would break on
    return rule


def run_rules(rules):
    return [r() for r in rules]


def lazy_h():
    return (h(i) for i in range(2))   # a generator expression: runs where it is consumed


@contextlib.contextmanager
def cm():
    yield h(6)


def use_cm():
    with cm() as v:            # started at contextlib's one call site, which foreign context managers share
        return v


class Err(Exception):
    pass


def raise_err():
    raise Err()                # the same call site first meets a class a test patched in
