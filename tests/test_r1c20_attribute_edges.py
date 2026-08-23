"""R1-C20 acceptance — attribute-access edges (`accesses`), issue #1.

`impact` on a class field used to return `refs: []` / `risk: "none"` — an affirmative
"nothing depends on this" — because attribute nodes had no inbound edges. This pass
emits `accesses` edges (function → attribute, read/write) so field blast-radius is real,
and reports `risk: "unknown"` (not `none`) for a field with no modelled accessor.

Fixture ``attrpkg``: a dataclass (`self.` reads/writes + a property that must NOT be
modelled as an attribute) and consumers (construction kwargs, `ClassName.field`,
`obj.field` on a local — deep tier only, and a method call — the calls layer, not this).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.extract import extract
from codemap.model import EDGE_TYPES, SCHEMA_VERSION
from codemap.query import Query

FIX = Path(__file__).resolve().parent / "fixtures" / "attrpkg"

WIDTH = "attrpkg.models.Config.width"
HEIGHT = "attrpkg.models.Config.height"
DEPTH = "attrpkg.models.Config.depth"
DIAGONAL = "attrpkg.models.Config.diagonal"


@pytest.fixture(scope="module")
def g():
    return extract(FIX)  # fast tier (ast)


@pytest.fixture(scope="module")
def q(g):
    return Query(g)


def _accesses(g):
    return [e for e in g.edges if e.type == "accesses"]


# -- vocabulary / schema ------------------------------------------------------

def test_accesses_is_declared():
    assert "accesses" in EDGE_TYPES
    assert tuple(map(int, SCHEMA_VERSION.split("."))) >= (0, 11)


# -- fast tier: the three static forms ---------------------------------------

def test_self_read_and_write(q):
    assert "attrpkg.models.Config.area" in q.readers(WIDTH)     # self.width read
    assert "attrpkg.models.Config.reset" in q.writers(WIDTH)    # self.width = 0


def test_construction_kwargs_are_writes(q):
    # Config(width=5, height=6) -> writes to both fields (D3).
    assert "attrpkg.use.make" in q.writers(WIDTH)
    assert "attrpkg.use.make" in q.writers(HEIGHT)


def test_classname_field_is_a_read(q):
    assert "attrpkg.use.use_class" in q.readers(WIDTH)          # Config.width


def test_resolution_labels(g):
    labels = {(e.source.rsplit(".", 1)[-1], e.target.rsplit(".", 1)[-1]):
              e.extras["resolution"] for e in _accesses(g)}
    assert labels[("area", "width")] == "self"
    assert labels[("make", "width")] == "construct"
    assert labels[("use_class", "width")] == "class"


# -- soundness gates ----------------------------------------------------------

def test_method_call_is_not_an_attribute_edge(g):
    # c.area() is a call, handled by the behavioral layer — never an `accesses` edge.
    assert not any(e.source == "attrpkg.use.call_method" for e in _accesses(g))


def test_property_read_is_captured(g):
    # griffe models `@property` as an *attribute* node, and `self.diagonal` is read
    # like a field — so `accesses` correctly captures it. This is the ONLY layer that
    # can (a property read has no `()` call), so excluding it would recreate the
    # honesty gap for properties. `perimeter` reads `self.diagonal`.
    assert g.nodes[DIAGONAL].kind == "attribute"
    assert any(e.source == "attrpkg.models.Config.perimeter" and e.target == DIAGONAL
               for e in _accesses(g))


def test_obj_field_on_local_needs_deep_tier(g):
    # On the fast tier, `c.width` on a local yields no edge (no false precision).
    assert not any(e.source == "attrpkg.use.use_local" for e in _accesses(g))


def test_every_accesses_target_is_a_real_attribute(g):
    for e in _accesses(g):
        node = g.nodes.get(e.target)
        assert node is not None and node.kind == "attribute"  # never an edge to nothing


# -- impact integration + honesty (P0) ---------------------------------------

def test_field_impact_is_no_longer_empty(q):
    rep = q.impact(WIDTH)
    assert rep["refs"], "attribute impact must span accesses edges"
    assert rep["risk"] != "none"


def test_unaccessed_field_reports_unknown_not_none(q):
    rep = q.impact(DEPTH)                    # depth is never read/written
    assert not rep["refs"]
    assert rep["risk"] == "unknown"
    assert "lower bound" in rep["risk_reason"]


def test_function_with_no_refs_stays_none(q):
    # the honesty override is attribute-scoped — a function's empty impact is real.
    rep = q.impact("attrpkg.use.call_method")
    assert rep["risk"] == "none"
    assert "risk_reason" not in rep


def test_impact_risk_kind_gate():
    assert Query._impact_risk(0, 0, 0) == "none"
    assert Query._impact_risk(0, 0, 0, kind="attribute") == "unknown"
    assert Query._impact_risk(0, 0, 0, kind="function") == "none"


# -- coverage counter ---------------------------------------------------------

def test_attr_access_counts_recorded(g):
    area = g.nodes["attrpkg.models.Config.area"]
    assert area.extras["attr_access"]["resolved"] >= 2   # self.width + self.height


# -- deep tier: obj.field on a typed local -----------------------------------

def test_deep_tier_resolves_obj_field():
    g = extract(FIX, deep=True)
    q = Query(g)
    # c = make(); c.width / c.height read, c.height = 99 write — jedi types the local.
    assert "attrpkg.use.use_local" in q.readers(WIDTH)
    assert "attrpkg.use.use_local" in q.writers(HEIGHT)
    assert any(e.extras["resolution"] == "deep" for e in _accesses(g))
