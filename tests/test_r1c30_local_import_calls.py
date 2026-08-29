"""R1-C30 acceptance — the fast tier resolves a call through a function-local import.

The remainder of [issue #11](https://github.com/kogriv/codemap/issues/11). R1-C29 taught
the **import map** to see an import written inside a function; the **call** layer was left
as it was, and the split was measurable on the reporter's own three-file example:

    def go(x):
        from leaf import helper
        return helper(x)

`--deep` produced `calls go -> leaf.helper`; the default fast tier produced nothing. So the
asymmetry the reporter read as "the tool can see it, the map cannot" was true of deep and
false of fast, where both halves were blind — and fast is the default tier, and the one the
`codemap watch` loop runs.

The awkward half of this feature is the constraint, not the recall. A local import binds a
name in **one** scope; folding these into the module map would resolve `helper(x)` in a
sibling function that never imported it — the false-edge shape we hold against tools that
walk name-matched call edges. Every test below that asserts a *missing* edge is that
constraint, and they are the ones worth keeping.

Measured when this landed, against the previous commit's deep tier as an independent
reference: +24 `calls` edges on bquant and +60 on codemap itself, **84 of 84 confirmed by
jedi**, none lost. The deep∖fast gap narrowed 600 → 576 and 225 → 165.
"""

from __future__ import annotations

import pytest

from codemap.extract import extract


def _calls(graph):
    return {(e.source, e.target) for e in graph.edges if e.type == "calls"}


def _pkg(tmp_path, files: dict[str, str]):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    for name, src in files.items():
        (pkg / name).write_text(src)
    return pkg


@pytest.fixture
def issue_example(tmp_path):
    """The reporter's shape: one function imports locally and calls; a sibling function
    calls the same bare name **without** importing it."""
    return _pkg(tmp_path, {
        "leaf.py": "def helper(x):\n    return x + 1\n",
        "user.py": (
            "def go(x):\n"
            "    from pkg.leaf import helper\n"
            "    return helper(x)\n"
            "\n\n"
            "def elsewhere(x):\n"
            "    return helper(x)\n"        # never imported here
        ),
    })


# -- the edge exists, on the tier that is actually the default ---------------

def test_the_fast_tier_resolves_the_call(issue_example):
    assert ("pkg.user.go", "pkg.leaf.helper") in _calls(extract(str(issue_example)))


def test_the_deep_tier_still_does_too(issue_example):
    """Pinned because the fix works by *widening the name map the fast resolver sees*,
    which deep also falls back to (R1-C26). A regression that broke the map would show
    up on both tiers at once, and one of them was already green."""
    assert ("pkg.user.go", "pkg.leaf.helper") in _calls(extract(str(issue_example), deep=True))


def test_the_call_is_counted_as_resolved_not_unresolved(issue_example):
    g = extract(str(issue_example))
    assert g.nodes["pkg.user.go"].extras["calls"]["resolved"] == 1
    assert g.nodes["pkg.user.go"].extras["calls"]["unresolved"] == 0


def test_the_edge_is_labelled_imported_like_any_other_import(issue_example):
    """No new resolution label: the name *was* imported, the import was just written
    lower down. A new label would make every consumer ask what it means."""
    edge = next(e for e in extract(str(issue_example)).edges
                if e.type == "calls" and e.source == "pkg.user.go")
    assert edge.extras["resolution"] == "imported"


# -- the constraint: one function's import is not another's ------------------

def test_a_sibling_function_does_not_inherit_the_import(issue_example):
    """The whole reason the map is per-function. `elsewhere` calls `helper` and never
    imported it — resolving that would be a false edge bought with the same recall."""
    assert ("pkg.user.elsewhere", "pkg.leaf.helper") not in _calls(extract(str(issue_example)))


def test_the_sibling_call_stays_honestly_unresolved(issue_example):
    g = extract(str(issue_example))
    assert g.nodes["pkg.user.elsewhere"].extras["calls"]["unresolved"] == 1


def test_a_class_body_import_is_not_visible_in_a_method(tmp_path):
    """Python's own rule: class scope is not visible inside its methods. The import is
    still a real eager dependency and the import graph records it (R1-C29) — it is only
    the *call* resolution that must not use it."""
    pkg = _pkg(tmp_path, {
        "leaf.py": "def helper(x):\n    return x\n",
        "user.py": (
            "class C:\n"
            "    from pkg.leaf import helper\n"
            "\n"
            "    def run(self, x):\n"
            "        return helper(x)\n"     # NameError at runtime, not an edge
        ),
    })
    assert ("pkg.user.C.run", "pkg.leaf.helper") not in _calls(extract(str(pkg)))


# -- lexical scoping, where Python really does inherit -----------------------

def test_a_closure_sees_the_enclosing_function_import(tmp_path):
    """A nested `def` is not a definition node, so its calls are attributed to the nearest
    definition that is (R1-C22 D3) — but it does see the outer function's name."""
    pkg = _pkg(tmp_path, {
        "leaf.py": "def helper(x):\n    return x\n",
        "user.py": (
            "def outer(x):\n"
            "    from pkg.leaf import helper\n"
            "\n"
            "    def inner(y):\n"
            "        return helper(y)\n"
            "    return inner(x)\n"
        ),
    })
    assert ("pkg.user.outer", "pkg.leaf.helper") in _calls(extract(str(pkg)))


def test_a_method_of_a_class_defined_inside_a_function_sees_it_too(tmp_path):
    pkg = _pkg(tmp_path, {
        "leaf.py": "def helper(x):\n    return x\n",
        "user.py": (
            "def build(x):\n"
            "    from pkg.leaf import helper\n"
            "\n"
            "    class C:\n"
            "        def run(self, y):\n"
            "            return helper(y)\n"
            "    return C\n"
        ),
    })
    assert ("pkg.user.build", "pkg.leaf.helper") in _calls(extract(str(pkg)))


# -- the import forms, each resolved the way the module-level map resolves it -

def test_a_relative_local_import_resolves(tmp_path):
    pkg = _pkg(tmp_path, {
        "leaf.py": "def helper(x):\n    return x\n",
        "user.py": "def go(x):\n    from .leaf import helper\n    return helper(x)\n",
    })
    assert ("pkg.user.go", "pkg.leaf.helper") in _calls(extract(str(pkg)))


def test_an_aliased_module_import_resolves(tmp_path):
    pkg = _pkg(tmp_path, {
        "leaf.py": "def helper(x):\n    return x\n",
        "user.py": "def go(x):\n    import pkg.leaf as lf\n    return lf.helper(x)\n",
    })
    assert ("pkg.user.go", "pkg.leaf.helper") in _calls(extract(str(pkg)))


def test_a_flat_sibling_import_resolves(tmp_path):
    """`from leaf import helper` — the bare-sibling form that only resolves because the
    directory itself is on `sys.path` (R1-C21). The local map runs it through the same
    qualifier the module-level map uses, so the two cannot drift apart."""
    pkg = _pkg(tmp_path, {
        "leaf.py": "def helper(x):\n    return x\n",
        "user.py": "def go(x):\n    from leaf import helper\n    return helper(x)\n",
    })
    assert ("pkg.user.go", "pkg.leaf.helper") in _calls(extract(str(pkg)))


def test_a_local_import_shadows_the_module_level_one(tmp_path):
    """Two definitions of `helper`; the module imports one at the top and the function
    imports the other in its body. Python binds the local one inside that function."""
    pkg = _pkg(tmp_path, {
        "a.py": "def helper(x):\n    return x\n",
        "b.py": "def helper(x):\n    return x\n",
        "user.py": (
            "from pkg.a import helper\n"
            "\n\n"
            "def go(x):\n"
            "    from pkg.b import helper\n"
            "    return helper(x)\n"
            "\n\n"
            "def plain(x):\n"
            "    return helper(x)\n"
        ),
    })
    calls = _calls(extract(str(pkg)))
    assert ("pkg.user.go", "pkg.b.helper") in calls
    assert ("pkg.user.go", "pkg.a.helper") not in calls
    assert ("pkg.user.plain", "pkg.a.helper") in calls   # module-level map, untouched


def test_a_local_star_import_binds_nothing_guessable(tmp_path):
    """`from x import *` inside a function binds names we cannot enumerate statically.
    The dependency is on the `imports` edge (R1-C23); the call stays unresolved rather
    than being guessed onto a plausible target."""
    pkg = _pkg(tmp_path, {
        "leaf.py": "def helper(x):\n    return x\n",
        "user.py": "def go(x):\n    from pkg.leaf import *\n    return helper(x)\n",
    })
    assert ("pkg.user.go", "pkg.leaf.helper") not in _calls(extract(str(pkg)))


# -- a locally imported symbol used as a *value* -----------------------------

def test_a_locally_imported_function_passed_as_a_value_is_referenced(tmp_path):
    """R1-C22 D1 reads the same name map, so the dispatch-table case follows for free —
    and it matters for dead-code, which counts references."""
    pkg = _pkg(tmp_path, {
        "leaf.py": "def helper(x):\n    return x\n",
        "user.py": "def go(items):\n    from pkg.leaf import helper\n    return map(helper, items)\n",
    })
    refs = {(e.source, e.target) for e in extract(str(pkg)).edges if e.type == "references"}
    assert ("pkg.user.go", "pkg.leaf.helper") in refs
