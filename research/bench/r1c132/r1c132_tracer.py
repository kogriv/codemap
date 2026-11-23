"""R1-C132 runtime truth: which package function calls which, observed while a project's own tests run.

A pytest plugin (``-p r1c132_tracer``, this directory on ``PYTHONPATH``), Python ≥ 3.12 (``sys.monitoring``).

Environment:
  R1C132_PKG_ROOT  absolute path of the package directory (the one codemap builds, e.g. ``src/click``)
  R1C132_OUT       where to write the JSON

What counts as a call ``F → G`` (the same attribution codemap uses, checked on a probe package):
- G is a named function of the package (module-level function or method; not a nested ``<locals>`` function,
  not a lambda, not module code). Its frame starts (``PY_START``). A generator, coroutine or async generator
  is taken at the call instruction instead (``CALL``): its frame first runs in whoever iterates it, so the frame
  above it then is the consumer, not the caller.
- F is found from the nearest package frame above G's, after at most ``MAX_EXTERNAL`` frames of code outside
  the package (``functools``, ``contextlib`` …). A test function, pytest or more external frames than that
  end the walk: G was called from outside.
  - A named package function or module code is F.
  - A nested function, lambda or generator expression is attributed lexically, to the named function it is
    defined in, as codemap does, whether or not that function is still on the stack: a closure a factory
    returned, a generator expression consumed by the caller, a lambda passed elsewhere.
  - Except a wrapper: a nested frame that holds G itself as a value (``fn`` in a decorator's wrapper) calls
    it on behalf of whoever called the wrapper, so the walk goes on up the stack to that named function.
- ``via`` records what was skipped: 1 = a nested function of F itself (lexical, codemap sees it as F),
  2 = a wrapper of another function, 4 = external frames.
- A construction yields ``F → class`` with flag 8, since codemap points a construction at the class: seen at
  the call instruction (``CALL`` with a package class as the callable — this catches dataclasses and classes
  without a Python ``__init__``) and at a started ``__init__`` whose caller is not the same object's
  ``__init__`` (``super().__init__()`` is a call, not a construction). A call site stays on while it calls
  classes or generator functions, foreign ones too: a name a test monkeypatched, ``contextlib``'s one site
  that starts every ``@contextmanager``. A site is switched off at its first event only when that callable is
  a builtin type, a C callable or a plain Python function — a site that later calls a package class or
  generator from there is missed.

Lines executed in package files are recorded once each (``LINE``, then disabled) — the precision side uses them.
"""

from __future__ import annotations

import inspect
import json
import os
import sys
from collections import Counter
from types import FunctionType, MethodType

MAX_EXTERNAL = 3
ROOT = os.path.realpath(os.environ["R1C132_PKG_ROOT"])
BASE = os.path.dirname(ROOT)
PKG = os.path.basename(ROOT)
OUT = os.environ["R1C132_OUT"]

mon = sys.monitoring
TOOL = 4
E = mon.events

_info: dict = {}          # code -> None (external) | (id, nested, owner, kind, file)
edges: Counter = Counter()  # (caller, callee, via) -> count
lines: dict[str, set[int]] = {}
started: Counter = Counter()


def _code_info(code):
    try:
        return _info[code]
    except KeyError:
        pass
    r = None
    fn = code.co_filename
    if fn.endswith(".py"):
        real = os.path.realpath(fn)
        if real.startswith(ROOT + os.sep):
            parts = os.path.relpath(real, BASE)[:-3].split(os.sep)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            mod = ".".join(parts)
            q = code.co_qualname
            if q == "<module>":
                r = (mod, False, mod, "module", os.path.relpath(real, BASE))
            elif not code.co_flags & inspect.CO_OPTIMIZED:     # a class body: runs once, is not a function
                r = (f"{mod}.{q}", False, f"{mod}.{q}", "class", os.path.relpath(real, BASE))
            else:
                head, sep, _ = q.partition(".<locals>")
                r = (f"{mod}.{head}", bool(sep), f"{mod}.{head}", "func", os.path.relpath(real, BASE))
    _info[code] = r
    return r


def _holds(fr, target) -> bool:
    """Does this frame hold the callee itself as a value — a wrapper's ``fn``?"""
    if target is None:
        return False
    try:
        values = list(fr.f_locals.values())
    except Exception:  # noqa: BLE001 - a probe never breaks the tests it watches
        return False
    for v in values:                  # by exact type: no attribute lookup, so no user __getattr__ runs here
        if type(v) is MethodType:
            v = v.__func__
        if v is target or (type(v) is FunctionType and v.__code__ is target):
            return True
    return False


def _caller_of(fr, target=None):
    """The named package function (or module / class-body code) a call from frame ``fr`` belongs to, and how
    it was reached. ``target`` is the callee (its code, or the class constructed) — to tell a wrapper."""
    ext = 0
    owners = []                       # owners of the wrapper frames skipped on the way
    while fr is not None:
        c2 = _code_info(fr.f_code)
        if c2 is None:
            ext += 1
            if ext > MAX_EXTERNAL:
                return None, 0
        elif c2[1]:
            if not owners and not _holds(fr, target):
                return c2[2], (4 if ext else 0) | 1     # lexical: the function the nested code is defined in
            owners.append(c2[2])
        else:
            via = 4 if ext else 0
            if owners:
                via |= 1 if all(o == c2[0] for o in owners) else 2
            return c2[0], via
        fr = fr.f_back
    return None, 0


#: a generator, coroutine or async generator starts running at its first ``next``/``send``/``await`` — in the
#: consumer's frame, not the caller's — so its call is taken at the call instruction instead (``_on_call``)
_LAZY = inspect.CO_GENERATOR | inspect.CO_COROUTINE | inspect.CO_ASYNC_GENERATOR | inspect.CO_ITERABLE_COROUTINE


def _on_start(code, offset):
    ci = _code_info(code)
    if ci is None or ci[1] or ci[3] != "func":
        return mon.DISABLE            # outside the package, nested, module or class-body code: never a callee
    callee = ci[0]
    if code.co_flags & _LAZY:
        started[callee] += 1
        return None                   # its caller is recorded where it was called
    frame = sys._getframe(1)
    started[callee] += 1
    caller, via = _caller_of(frame.f_back, code)
    if caller is None:
        return None                   # called from a test, from pytest, or through too much foreign code
    edges[(caller, callee, via)] += 1
    if code.co_name == "__init__":
        try:
            me = frame.f_locals.get("self")
            parent = frame.f_back
            if parent is not None and parent.f_code.co_name == "__init__" and parent.f_locals.get("self") is me:
                return None           # super().__init__() / Base.__init__(self): a call, not a construction
            cls = type(me)
            if cls.__module__ == PKG or cls.__module__.startswith(PKG + "."):
                edges[(caller, f"{cls.__module__}.{cls.__qualname__}", via | 8)] += 1
        except Exception:  # noqa: BLE001 - a probe never breaks the tests it watches
            pass
    return None


def _on_call(code, offset, callable_, arg0):
    """A call instruction. A package class called here is a construction, whatever its __init__ is (generated
    by dataclasses, inherited from outside, absent); a package generator or coroutine function called here is
    its call. A site stays on while it calls classes or generator functions (see the module docstring)."""
    if isinstance(callable_, type):
        mod = getattr(callable_, "__module__", "") or ""
        if not (mod == PKG or mod.startswith(PKG + ".")):
            return mon.DISABLE if mod == "builtins" else None
        caller, via = _caller_of(sys._getframe(1), callable_)
        if caller is not None:
            edges[(caller, f"{mod}.{callable_.__qualname__}", via | 8)] += 1
        return None
    fn = getattr(callable_, "__func__", callable_)          # a bound method calls its function
    fcode = getattr(fn, "__code__", None)
    if fcode is None or not fcode.co_flags & _LAZY:
        return mon.DISABLE
    ci = _code_info(fcode)
    if ci is None or ci[1] or ci[3] != "func":
        return None
    caller, via = _caller_of(sys._getframe(1), fcode)
    if caller is not None:
        edges[(caller, ci[0], via)] += 1
    return None


def _on_line(code, line):
    ci = _code_info(code)
    if ci is not None:
        lines.setdefault(ci[4], set()).add(line)
    return mon.DISABLE


def _dump():
    mon.set_events(TOOL, 0)
    data = {
        "package_root": ROOT,
        "python": sys.version.split()[0],
        "edges": sorted([c, g, v, n] for (c, g, v), n in edges.items()),
        "started": dict(sorted(started.items())),
        "lines": {f: sorted(ls) for f, ls in sorted(lines.items())},
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def pytest_configure(config):
    mon.use_tool_id(TOOL, "r1c132")
    mon.register_callback(TOOL, E.PY_START, _on_start)
    mon.register_callback(TOOL, E.LINE, _on_line)
    mon.register_callback(TOOL, E.CALL, _on_call)
    mon.set_events(TOOL, E.PY_START | E.LINE | E.CALL)


def pytest_unconfigure(config):
    _dump()
    mon.free_tool_id(TOOL)
