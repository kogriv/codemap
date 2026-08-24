"""R1-C22 acceptance — references the source shows and the graph missed, issue #7.

`report dead-code` graded a private function **high** ("no inbound calls, references, or
decorators") while its name sat two lines below the definition. Measured across two real
packages, 20 of 51 high candidates were false, from three distinct forms — and each
package exhibited only two of them, so one dogfood target could not have found this:

- **① function-as-value** — a dict entry, a `default=` callback. No edge existed: `calls`
  covers the callee position only.
- **② module-level call** — `add_behavior` walked named functions, so import-time
  statements were never visited at all.
- **③ call inside a nested def** — the whole closure was dropped (`not a definition
  node`), and every call inside it with it.

② and ③ are missing **`calls`** edges, so this was never only a dead-code report bug:
`impact`, `callers` and `flows` were reading a call graph with import-time work and
closure bodies cut out. The grader is deliberately untouched — `_grade_dead` already
demotes on any inbound edge, so modelling the references fixes the report by itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.extract import extract
from codemap.query import Query

FIX = Path(__file__).resolve().parent / "fixtures" / "refpkg"
CODEMAP = Path(__file__).resolve().parents[1] / "codemap"


@pytest.fixture(scope="module")
def g():
    return extract(FIX)


def _edges(graph, etype, source=None, target=None):
    return [e for e in graph.edges if e.type == etype
            and (source is None or e.source == source)
            and (target is None or e.target == target)]


# -- ① function as a value ----------------------------------------------------

def test_dict_value_is_a_reference(g):
    """`PANELS = {"a": _panel_a}` at module level — the form issue #7 reports."""
    e = _edges(g, "references", "refpkg.panels", "refpkg.panels._panel_a")
    assert e and e[0].extras["resolution"] == "name"


def test_keyword_value_is_a_reference(g):
    """`json.dumps(obj, default=_json_default)` — named inside a function, not called."""
    e = _edges(g, "references", "refpkg.panels.dump", "refpkg.panels._json_default")
    assert e and e[0].extras["resolution"] == "name"


def test_annotation_is_labelled_apart(g):
    """A type annotation is a real reference too, but it means a *contract*, not a
    dispatch — so it is labelled `annotation`, not blurred into the value form."""
    e = _edges(g, "references", "refpkg.panels.render", "refpkg.panels.Report")
    assert e and e[0].extras["resolution"] == "annotation"


def test_callee_position_stays_a_call_not_a_reference(g):
    """`render(kind, 1)` is a call; it must not also produce a value-reference."""
    assert _edges(g, "calls", "refpkg.app.start", "refpkg.panels.render")
    assert not _edges(g, "references", "refpkg.app.start", "refpkg.panels.render")


def test_no_self_reference(g):
    """Recursion by name says nothing about whether anyone else uses the function."""
    assert not [e for e in g.edges if e.type == "references" and e.source == e.target]


def test_reference_targets_are_definitions_only(g):
    """Only functions/classes — a name-load of a constant is not a dependency worth an
    edge, and emitting one would inflate every impact answer."""
    kinds = {g.nodes[e.target].kind for e in g.edges
             if e.type == "references" and e.target in g.nodes}
    assert kinds <= {"function", "class"}


# -- ② module-level calls -----------------------------------------------------

def test_module_level_call_is_recorded(g):
    """`_register()` at the bottom of boot.py — import-time work, previously invisible
    to the entire call graph, not just to dead-code."""
    e = _edges(g, "calls", "refpkg.boot", "refpkg.boot._register")
    assert e and e[0].extras["resolution"] == "module"


def test_module_level_call_makes_it_a_caller(g):
    """…and it reaches the query surface, so `callers` answers truthfully."""
    assert "refpkg.boot" in Query(g).callers("refpkg.boot._register")


# -- ③ calls inside nested defs -----------------------------------------------

def test_nested_call_is_attributed_to_the_nearest_definition(g):
    """The closure in `make_worker` is not a graph node, but its call is real. It is
    attributed to the innermost definition that *does* exist, and flagged as such —
    the call's existence is certain, only its source node is approximate."""
    e = _edges(g, "calls", "refpkg.panels.make_worker", "refpkg.panels._dispatched")
    assert e and e[0].extras.get("via") == "nested"


def test_nested_attribution_does_not_duplicate_a_direct_call(g):
    """A pair the owner already calls directly must not gain a second, weaker copy —
    that would double-count in every degree and hub metric."""
    pairs = [(e.source, e.target) for e in g.edges if e.type == "calls"]
    assert len(pairs) == len(set(pairs))


# -- the payoff: the `high` band -----------------------------------------------

def test_only_the_genuinely_dead_function_is_high(g):
    dc = {c["id"]: c["confidence"] for c in Query(g).dead_code()}
    assert dc.get("refpkg.panels._really_dead") == "high"
    for live in ("refpkg.panels._panel_a", "refpkg.panels._json_default"):
        assert dc.get(live) == "low", f"{live} should be demoted, got {dc.get(live)}"


def test_the_called_ones_are_not_candidates_at_all(g):
    """`_dispatched` and `_register` now have inbound *calls*, so they leave the
    candidate set entirely rather than merely being demoted."""
    ids = {c["id"] for c in Query(g).dead_code()}
    assert "refpkg.panels._dispatched" not in ids
    assert "refpkg.boot._register" not in ids


def test_the_demotion_names_who_references_it(g):
    """`low` is only useful if the reader can check it — the reason must say who."""
    c = next(c for c in Query(g).dead_code() if c["id"] == "refpkg.panels._panel_a")
    assert c["reasons"] and "referenced" in c["reasons"][0]


# -- dogfood regression --------------------------------------------------------

def test_codemap_no_longer_calls_its_own_dispatch_table_dead():
    """codemap graded 13 of its own `_cmd_*` handlers `high` — they are values in the
    CLI dispatch table. Its own package is the regression guard for form ①."""
    dc = {c["id"]: c["confidence"] for c in Query(extract(CODEMAP)).dead_code()}
    cmds = [i for i in dc if i.startswith("codemap.cli._cmd_")]
    assert cmds and all(dc[i] != "high" for i in cmds)


# -- R1-C22-f1: over-attribution, the mirror of the above (issue #9) -----------

SHADOWS = "refpkg.shadows"


@pytest.mark.parametrize("func,shadowed", [
    ("by_assign", "_shadowed_assign"),      # x = 1  — binds for the whole scope
    ("by_param", "_shadowed_param"),        # a parameter of the same name
    ("by_loop", "_shadowed_loop"),          # for-target
    ("by_with", "_shadowed_with"),          # with ... as
    ("by_except", "_shadowed_except"),      # except ... as
    ("by_nested", "_shadowed_nested"),      # a nested def of the same name
])
def test_a_local_binding_is_not_a_reference(g, func, shadowed):
    """Python binds per *scope*: once a name is bound anywhere in a function, every read
    of it there is the local. Attributing that read to a module-level function of the same
    name invents a reference — and hides a dead function in `low` (issue #9)."""
    assert not _edges(g, "references", f"{SHADOWS}.{func}", f"{SHADOWS}.{shadowed}")


def test_shadowed_functions_stay_high(g):
    """The consequence that matters: they are as dead as their unshadowed twins."""
    dc = {c["id"]: c["confidence"] for c in Query(g).dead_code()}
    for name in ("_shadowed_assign", "_shadowed_param", "_shadowed_loop",
                 "_shadowed_with", "_shadowed_except", "_shadowed_nested"):
        assert dc.get(f"{SHADOWS}.{name}") == "high", name


def test_global_declaration_opts_back_out(g):
    """`global x` says the name *is* the module binding — not a local shadow."""
    assert _edges(g, "references", f"{SHADOWS}.by_global", f"{SHADOWS}._rebound_global")


def test_a_local_import_does_not_count_as_shadowing(g):
    """An import binds the name to the symbol it imports — the very thing an edge records.
    Treating it as a shadow dropped a real edge on bquant
    (`register_builtin_indicators → IndicatorFactory`, imported inside its own body)."""
    from codemap.extract.behavior import _local_bindings
    import ast
    src = (FIX / "shadows.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "by_local_import")
    assert "_json_default" not in _local_bindings(fn)


def test_module_scope_rebinding_is_not_shadowing(g):
    """At module level a rebinding is the *same* symbol, so the dispatch table in
    panels.py must keep its edges — the suppression is function-scope only."""
    assert _edges(g, "references", "refpkg.panels", "refpkg.panels._panel_a")
