"""R1-C55 — an override is reached through its base, so it cannot be `high`.

Found by axis B4 (`gaps/third_shape_2026-09-12.md` §S2), on Pillow: **40 of 63**
symbols graded `high` dead were `_open` implementations overriding
``ImageFile.ImageFile._open``, which the same graph records as called from
``ImageFile.__init__`` (``self._open()``). The report's wording is a statement of
fact — *"no inbound calls, references, or decorators"* — and it was false. The
data to know better was already in the graph: 191 ``inherits`` edges.

Neither codemap nor bquant carries the shape, which is why a month of dogfood on
them never produced it: measured before and after the fix, the `high` band on both
is **unchanged**, while Pillow's drops 63 → 15.

The grade drops to `low` when the base has inbound calls (something dispatches into
it) and to `medium` when the base is itself uncalled here (dead only if the base is).
Both bands are shown the shape they must reject, and the honest-nothing control below
keeps the fix from simply neutering the band: a private function that overrides
nothing and is called by nobody is still `high`.
"""

from __future__ import annotations

import pytest

from codemap.model import Edge, Graph, Node
from codemap.query import Query


def _fn(cls: str, name: str, line: int) -> Node:
    return Node(id=f"{cls}.{name}", kind="function", file="pkg/mod.py",
                visibility="private", lineno=line)


@pytest.fixture(scope="module")
def hierarchy() -> Query:
    """The Pillow shape in miniature: a called template method, three overrides.

    ``Base._open`` is called by ``Base.__init__``; ``Child`` and ``GrandChild``
    override it and are called by nobody under their own names. ``Lonely._orphan``
    overrides nothing. ``Quiet`` overrides a base method that nothing calls.
    """
    g = Graph(target="pkg")
    g.add_node(Node(id="pkg", kind="module", file="pkg/__init__.py"))
    g.add_node(Node(id="pkg.mod", kind="module", file="pkg/mod.py"))
    for cls in ("Base", "Child", "GrandChild", "Lonely", "Silent", "Quiet"):
        g.add_node(Node(id=f"pkg.mod.{cls}", kind="class", file="pkg/mod.py"))
    g.add_node(Node(id="pkg.mod.Base.__init__", kind="function", file="pkg/mod.py",
                    visibility="public", lineno=2))
    g.add_node(_fn("pkg.mod.Base", "_open", 4))
    g.add_node(_fn("pkg.mod.Child", "_open", 8))            # overrides a called base
    g.add_node(_fn("pkg.mod.GrandChild", "_open", 12))      # two levels up
    g.add_node(_fn("pkg.mod.Lonely", "_orphan", 16))        # overrides nothing
    g.add_node(_fn("pkg.mod.Silent", "_hush", 20))          # base of Quiet, uncalled
    g.add_node(_fn("pkg.mod.Quiet", "_hush", 24))           # overrides an uncalled base

    g.add_edge(Edge("inherits", "pkg.mod.Child", "pkg.mod.Base"))
    g.add_edge(Edge("inherits", "pkg.mod.GrandChild", "pkg.mod.Child"))
    g.add_edge(Edge("inherits", "pkg.mod.Quiet", "pkg.mod.Silent"))
    # the one call in the fixture: the template method, from the base constructor
    g.add_edge(Edge("calls", "pkg.mod.Base.__init__", "pkg.mod.Base._open"))
    return Query(g)


def _by_id(rows):
    return {c["id"]: c for c in rows}


def test_an_override_of_a_called_base_is_not_confidently_dead(hierarchy):
    """The shape the fix exists to reject (R1-C37), stated as the report would."""
    rows = _by_id(hierarchy.dead_code())
    child = rows["pkg.mod.Child._open"]
    assert child["confidence"] == "low", "reached by dispatch, not by name"
    assert "overrides pkg.mod.Base._open" in child["reasons"][0]
    assert "1 inbound call" in child["reasons"][0]


def test_the_walk_is_transitive(hierarchy):
    """A plugin may override its grand-parent's method — Pillow does exactly this.

    The middle link is an override too, so it carries no inbound call of its own.
    Naming *it* would report "the base is itself uncalled" while the call sits one
    level further up — so the ancestor that is actually called wins the reason.
    This case is why the first version of the fix was wrong: it stopped at the
    nearest declaration and graded a dispatched method `medium`.
    """
    row = _by_id(hierarchy.dead_code())["pkg.mod.GrandChild._open"]
    assert row["confidence"] == "low"
    assert "pkg.mod.Base._open" in row["reasons"][0], "the called ancestor is named"


def test_an_override_of_an_uncalled_base_is_medium_not_high(hierarchy):
    """Nothing calls the base either — so it is dead only if the base is, and that
    is a `medium` with the reason said out loud, not a confident `high`."""
    row = _by_id(hierarchy.dead_code())["pkg.mod.Quiet._hush"]
    assert row["confidence"] == "medium"
    assert "dead only if the base is" in row["reasons"][0]


def test_the_band_still_means_something(hierarchy):
    """Positive control: the fix must not empty the `high` band. A private function
    that overrides nothing and is called by nobody stays `high` with the old wording."""
    rows = _by_id(hierarchy.dead_code())
    lonely = rows["pkg.mod.Lonely._orphan"]
    assert lonely["confidence"] == "high"
    assert lonely["reasons"] == ["no inbound calls, references, or decorators"]
    assert rows["pkg.mod.Silent._hush"]["confidence"] == "high", "a base nobody calls"


def test_a_referenced_override_keeps_its_reference_reason(hierarchy):
    """Precedence: an actual inbound reference is better evidence than the override
    rule, and must keep naming who references it."""
    g = hierarchy.graph
    g.add_node(Node(id="pkg.mod.user", kind="function", file="pkg/mod.py",
                    visibility="public", lineno=40))
    g.add_edge(Edge("references", "pkg.mod.user", "pkg.mod.Child._open"))
    row = _by_id(Query(g).dead_code())["pkg.mod.Child._open"]
    assert row["confidence"] == "low"
    assert "referenced" in row["reasons"][0], row["reasons"]
