import functools

def trace(fn):
    @functools.wraps(fn)
    def inner(*a, **k):
        return fn(*a, **k)
    return inner

@trace
def traced_target():
    return _wrapped_helper()

def _wrapped_helper():
    return 3

@functools.singledispatch
def render(x):
    return str(x)

@render.register
def _render_int(x: int):
    return "int"
