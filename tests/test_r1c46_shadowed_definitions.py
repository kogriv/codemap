"""R1-C46 — a name defined twice in one scope is a finding, not a duplicate edge.

Raised by the second target (issue #16 §5): one `contains` record twice in their graph,
and behind it a method their class defined twice. Reproduced on a toy package, the
duplicate edge was the least of it — griffe keeps the last body silently, and the
behavioural walkers visited *both* bodies and attributed both to the one surviving node,
so the graph carried a `calls` edge from code that can never run. `impact` on the callee
answered "one caller"; dead-code stayed quiet.

The fixture is an **actual** duplicate (R1-C37): the first test below is red on the
undeduplicated walk by construction — there is no separate mutation to apply.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from codemap.extract import extract
from codemap.extract.behavior import _shadow_map
from codemap.extract.roots import extract_repo
from codemap.query import Query
from codemap.serve.audit import build_dead_code, render_dead_code

FIX = Path(__file__).resolve().parent / "fixtures" / "shadowpkg"


@pytest.fixture(scope="module")
def graph():
    return extract(FIX)


def _calls_from(graph, src):
    return sorted(e.target for e in graph.edges if e.type == "calls" and e.source == src)


def _first_def_line(name: str) -> int:
    tree = ast.parse((FIX / "__init__.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node.lineno
    raise AssertionError(name)


# -- the defect ---------------------------------------------------------------------------

def test_only_the_body_that_can_run_is_walked(graph):
    """Before: `Thing.get` called both `one` and `two`. `one()` never executes."""
    assert _calls_from(graph, "shadowpkg.Thing.get") == ["shadowpkg.two"]
    assert graph.nodes["shadowpkg.Thing.get"].extras["calls"]["out"] == 1


def test_the_survivor_says_what_it_shadowed(graph):
    node = graph.nodes["shadowpkg.Thing.get"]
    assert node.extras["shadows"] == [_first_def_line("get")]
    assert node.lineno > node.extras["shadows"][0], "the survivor is the later body"


def test_a_shadowed_class_is_recorded_on_the_class_node(tmp_path):
    pkg = tmp_path / "twice"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "def a():\n    return 1\n\n\ndef b():\n    return 2\n\n\n"
        "class K:\n    def m(self):\n        return a()\n\n\n"
        "class K:\n    def m(self):\n        return b()\n"
    )
    g = extract(pkg)
    assert g.nodes["twice.K"].extras["shadows"] == [9]
    assert _calls_from(g, "twice.K.m") == ["twice.b"], "the earlier class body is not walked"


# -- the exemptions (D2): re-binding idioms are not shadowing ---------------------------

@pytest.mark.parametrize("node_id", [
    "shadowpkg.parse",      # @overload before the implementation
    "shadowpkg.Box.value",  # property + setter
    "shadowpkg.render",     # singledispatch base
    "shadowpkg.maybe",      # if TYPE_CHECKING / else
])
def test_legitimate_rebinding_carries_no_shadows(graph, node_id):
    assert "shadows" not in graph.nodes[node_id].extras, node_id


def test_conditional_definitions_keep_both_bodies(graph):
    """`maybe` is defined under `if` and `else`: neither body replaces the other."""
    assert _calls_from(graph, "shadowpkg.maybe") == ["shadowpkg.one", "shadowpkg.two"]


def test_the_shadow_map_names_exactly_one_definition():
    tree = ast.parse((FIX / "__init__.py").read_text())
    skip, records, ranges = _shadow_map(tree)
    assert list(records) == [(("Thing",), "get")]
    assert len(skip) == 1 and len(ranges) == 1
    start, end = ranges[0]
    assert start == _first_def_line("get") and end >= start


# -- consumer roots: one node, one edge, and no uses from the dead body ----------------

def test_consumer_root_emits_one_contains_edge_and_no_use_from_the_dead_body(tmp_path):
    core = tmp_path / "core"
    core.mkdir()
    (core / "__init__.py").write_text("def helper_a():\n    pass\n\n\ndef helper_b():\n    pass\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_mock.py").write_text(
        "from core import helper_a, helper_b\n\n\n"
        "class Mock:\n"
        "    def get_metadata(self):\n        return helper_a()\n\n"
        "    def get_metadata(self):\n        return helper_b()\n"
    )
    g = extract_repo(core, consumers=(tests,), mode="full")
    node_id = "tests.test_mock.Mock.get_metadata"
    contains = [e for e in g.edges if e.type == "contains" and e.target == node_id]
    assert len(contains) == 1, "issue #16: the record used to appear twice"
    assert g.nodes[node_id].extras["shadows"] == [5]
    uses = sorted(e.target for e in g.edges if e.source == node_id and e.type in ("calls", "references"))
    assert uses == ["core.helper_b"], "a use inside the dead body is not a use"


# -- the surface: report dead-code, certain section ---------------------------------------

def test_report_lists_it_as_certain_not_as_a_graded_candidate(graph):
    q = Query(graph)
    listed = q.shadowed_definitions()
    assert [d["id"] for d in listed] == ["shadowpkg.Thing.get"]
    assert listed[0]["shadows"] == [_first_def_line("get")]
    data = build_dead_code(q)
    assert data["shadowed"] == listed
    assert "shadowpkg.Thing.get" not in {c["id"] for c in data["candidates"]}
    text = render_dead_code(q)
    assert "## Shadowed definitions — certain: 1" in text
    assert "`shadowpkg.Thing.get` — defined at line" in text
    assert "can never run" in text


def test_a_tree_without_a_duplicate_has_no_section():
    q = Query(extract(Path(__file__).resolve().parent / "fixtures" / "deeppkg"))
    assert q.shadowed_definitions() == []
    assert "Shadowed definitions" not in render_dead_code(q)
