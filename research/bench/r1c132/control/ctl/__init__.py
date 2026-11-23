"""R1-C132 control package: every shape of call the tracer must attribute the way codemap does."""

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
