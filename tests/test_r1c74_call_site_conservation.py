"""R1-C74 — every call site is counted somewhere, and the counts add up to the source.

Design `docs/design/call_site_conservation.md`. `extras.calls` counted function bodies only, while
`report behavior` printed the sum as the package's resolution: module-level code and nested functions
made edges and appeared in no count, and class bodies were walked by nobody at all.

Pinned:
- C1: each scope is counted on its node;
- a class-body call is an edge from the class;
- conservation against an AST count of the fixture, shadowed bodies named;
- the report names the parts;
- a mutation (class bodies unwalked) turning a test red; the module counter is shown by reverting the code.
"""

from __future__ import annotations

import ast
from unittest import mock

import pytest

from codemap.extract import behavior
from codemap.extract import extract
from codemap.query import Query
from codemap.serve.audit import build_behavior, call_sites_by_scope, render_behavior

SRC = '''import functools


def helper(x=None):
    return 1


def deco(f):
    return f


def replaced():
    return helper(), helper()


def replaced():
    return 0


class Base:
    pass


def make_base():
    return Base


class K(make_base()):
    x = helper()
    y = [helper() for _ in range(2)]

    @deco
    def method(self):
        return helper()


Y = helper()


def outer():
    def inner():
        return helper()

    class Local:
        z = helper()

    f = lambda: helper()
    return inner, Local, f


@functools.lru_cache(maxsize=helper())
def own(a=helper()):
    return helper()
'''


@pytest.fixture(scope="module")
def g(tmp_path_factory):
    pkg = tmp_path_factory.mktemp("r1c74") / "cpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text(SRC)
    return extract(str(pkg))


def _calls(g, nid, key="calls"):
    return g.nodes[nid].extras.get(key, {}).get("out")


def test_c1_each_scope_is_counted_on_its_node(g):
    assert _calls(g, "cpkg.m") == 1, "Y = helper()"
    # bases + 2 statements (one comprehension: helper() and range())
    assert _calls(g, "cpkg.m.K") == 4
    # decorator + its argument + default + body
    assert _calls(g, "cpkg.m.own") == 4
    # inner's call, Local's body, the lambda's call (lambda is own body, not nested)
    assert _calls(g, "cpkg.m.outer", "calls_nested") == 2
    assert _calls(g, "cpkg.m.outer") == 1, "helper() in the lambda: a lambda is own body"


def test_a_class_body_call_is_an_edge_from_the_class(g):
    targets = {e.target for e in g.edges if e.type == "calls" and e.source == "cpkg.m.K"}
    assert {"cpkg.m.helper", "cpkg.m.make_base"} <= targets


def test_conservation_against_the_source(g):
    total = sum(isinstance(n, ast.Call) for n in ast.walk(ast.parse(SRC)))
    sites = call_sites_by_scope(g)
    assert sites["shadowed_not_walked"] == 2, "the first `replaced` body"
    assert sites["all"]["out"] + sites["shadowed_not_walked"] == total


def test_the_report_names_the_parts(g):
    out = render_behavior(Query(g))
    assert "in function bodies" in out and "at module level" in out and "in class bodies" in out
    assert "not walked" in out
    b = build_behavior(Query(g))["call_sites"]
    assert set(b["by_scope"]) == {"function", "nested", "module", "class_body"}


# -- mutation ---------------------------------------------------------------------------

def test_mutation_without_class_bodies_conservation_breaks(tmp_path):
    pkg = tmp_path / "cpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text(SRC)
    total = sum(isinstance(n, ast.Call) for n in ast.walk(ast.parse(SRC)))
    with mock.patch.object(behavior, "_process_class_bodies", lambda *a, **k: None):
        gm = extract(str(pkg))
    s = call_sites_by_scope(gm)
    assert s["all"]["out"] + s["shadowed_not_walked"] < total
    assert not [e for e in gm.edges if e.type == "calls" and e.source == "cpkg.m.K"]



def test_a_nested_namesake_of_a_method_is_not_the_method(tmp_path):
    """Found by the conservation check on pytest: `def getfixturedefs` nested in a method of
    `FixtureManager` became the method `FixtureManager.getfixturedefs`, because a node id sees
    only the class chain. Its calls and edges went to a namesake that never makes them."""
    pkg = tmp_path / "npkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text(
        "def target():\n    return 1\n\n\nclass M:\n    def lookup(self):\n        return 0\n\n"
        "    def closure(self):\n        def lookup(x):\n            return target()\n        return lookup\n")
    gm = extract(str(pkg))
    calls = {(e.source, e.target, e.extras.get("via")) for e in gm.edges if e.type == "calls"}
    assert calls == {("npkg.m.M.closure", "npkg.m.target", "nested")}
    assert gm.nodes["npkg.m.M.lookup"].extras["calls"]["out"] == 0


def test_two_standing_bodies_of_one_node_add_up(tmp_path):
    """A name defined in both branches of an `if` keeps both bodies walked (R1-C46); their
    counts used to be overwritten by the last one, so the first body counted nowhere."""
    pkg = tmp_path / "bpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text(
        "import sys\n\n\ndef h():\n    return 1\n\n\nif sys.platform == 'win32':\n"
        "    def f():\n        return h(), h()\nelse:\n    def f():\n        return h()\n")
    gm = extract(str(pkg))
    assert gm.nodes["bpkg.m.f"].extras["calls"]["out"] == 3
