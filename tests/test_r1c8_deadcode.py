"""R1-C8 acceptance — dead-code confidence + whitelist.

codemap's cross-root graph lets it *grade* an uncalled-private-function candidate
instead of listing flat: **high** (no inbound edge or hook), **medium** (a decorator
/ registry may invoke it implicitly), **low** (something references it → likely
alive). Plus a whitelist (exact id / glob) and a `min_confidence` floor. Tests pin
the grading, the provenance reasons, the whitelist, the filter, and back-compat.
"""

from __future__ import annotations

import pytest

from codemap.model import Edge, Graph, Node
from codemap.query import Query
from codemap.serve.audit import load_dead_code_whitelist, render_dead_code


@pytest.fixture(scope="module")
def graded() -> Query:
    """A graph with one candidate per confidence tier + the exclusions."""
    g = Graph(target="pkg")
    g.add_node(Node(id="pkg", kind="module", file="pkg/__init__.py"))
    g.add_node(Node(id="pkg.mod", kind="module", file="pkg/mod.py"))
    mk = lambda name, **kw: Node(id=f"pkg.mod.{name}", kind="function",
                                 file="pkg/mod.py", visibility="private", **kw)
    g.add_node(mk("_high", lineno=1))                                   # → high
    g.add_node(mk("_deco", lineno=5, decorators=["app.route"]))         # → medium (decorated)
    g.add_node(mk("_reg", lineno=9, extras={"registry": {"key": "z"}}))  # → medium (registered)
    g.add_node(mk("_ref", lineno=13))                                   # → low (referenced)
    g.add_node(mk("_called", lineno=17))                                # excluded (has caller)
    g.add_node(Node(id="pkg.mod.public_fn", kind="function", file="pkg/mod.py",
                    visibility="public", lineno=21))                    # excluded (public)
    g.add_node(mk("__hidden__", lineno=25))                             # excluded (dunder)
    g.add_node(Node(id="pkg.other", kind="function", file="pkg/mod.py",
                    visibility="public", lineno=30))
    # a reference (not a call) → _ref is likely alive; a call → _called is not dead
    g.add_edge(Edge("references", "pkg.other", "pkg.mod._ref"))
    g.add_edge(Edge("calls", "pkg.other", "pkg.mod._called"))
    return Query(g)


def _by_id(rows):
    return {c["id"]: c for c in rows}


# -- grading ------------------------------------------------------------------

def test_confidence_tiers(graded):
    rows = _by_id(graded.dead_code())
    assert rows["pkg.mod._high"]["confidence"] == "high"
    assert rows["pkg.mod._deco"]["confidence"] == "medium"
    assert rows["pkg.mod._reg"]["confidence"] == "medium"
    assert rows["pkg.mod._ref"]["confidence"] == "low"


def test_exclusions(graded):
    ids = set(_by_id(graded.dead_code()))
    assert "pkg.mod._called" not in ids       # has a resolved caller
    assert "pkg.mod.public_fn" not in ids     # public, not private
    assert "pkg.mod.__hidden__" not in ids    # dunder


def test_reasons_are_provenance(graded):
    rows = _by_id(graded.dead_code())
    assert rows["pkg.mod._high"]["reasons"] == ["no inbound calls, references, or decorators"]
    assert any("decorated by @route" in r for r in rows["pkg.mod._deco"]["reasons"])
    assert any("registered as 'z'" in r for r in rows["pkg.mod._reg"]["reasons"])
    assert any("referenced (references) by core×1" in r for r in rows["pkg.mod._ref"]["reasons"])


def test_sorted_most_confident_first(graded):
    order = [c["confidence"] for c in graded.dead_code()]
    ranks = {"high": 2, "medium": 1, "low": 0}
    assert order == sorted(order, key=lambda c: -ranks[c])


# -- whitelist + min_confidence ----------------------------------------------

def test_whitelist_exact_and_glob(graded):
    ids = set(_by_id(graded.dead_code(whitelist=("pkg.mod._high", "pkg.mod._re*"))))
    assert "pkg.mod._high" not in ids                 # exact
    assert "pkg.mod._ref" not in ids and "pkg.mod._reg" not in ids  # glob _re*
    assert "pkg.mod._deco" in ids                     # untouched


def test_min_confidence_filters(graded):
    ids = set(_by_id(graded.dead_code(min_confidence="high")))
    assert ids == {"pkg.mod._high"}
    med_up = {c["confidence"] for c in graded.dead_code(min_confidence="medium")}
    assert med_up == {"high", "medium"}               # low dropped


def test_dead_symbols_backcompat(graded):
    # thin wrapper: ids of every candidate (any confidence), unfiltered
    assert graded.dead_symbols() == sorted(
        c["id"] for c in graded.dead_code())
    assert "pkg.mod._high" in graded.dead_symbols()


# -- render + whitelist loader ------------------------------------------------

def test_render_groups_and_counts(graded):
    out = render_dead_code(graded)
    assert "### high (1)" in out and "### medium (2)" in out and "### low (1)" in out
    assert "`pkg.mod._high`" in out


def test_render_respects_min_confidence(graded):
    out = render_dead_code(graded, min_confidence="high")
    assert "### high (1)" in out
    assert "### medium" not in out and "### low" not in out
    assert "min-confidence: high" in out


def test_whitelist_loader(tmp_path):
    (tmp_path / "codemap.toml").write_text(
        '[dead_code]\nwhitelist = ["a.b._x", "pkg.*._debug"]\n', encoding="utf-8")
    assert load_dead_code_whitelist(str(tmp_path)) == ("a.b._x", "pkg.*._debug")
    assert load_dead_code_whitelist(str(tmp_path / "nope")) == ()   # absent → empty
    assert load_dead_code_whitelist(None) == ()
