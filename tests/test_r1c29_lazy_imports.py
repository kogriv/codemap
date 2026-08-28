"""R1-C29 acceptance — a function-local import is a dependency, and a cycle has two kinds.

From [issue #11](https://github.com/kogriv/codemap/issues/11), filed off a second real
target: `report architecture` printed *"none — import graph is acyclic"* while the tree
had two cycles, both closed by an import written inside a function. The import map was
module-level only — an omission recorded about the *extractor* and never about the
*consumers*, who turned it into a property claim.

The reporter's framing is the reason this is not a minor recall bug:

    a function-local import is what developers use to break a cycle, so the edges the
    tool cannot see are exactly the edges most likely to close one — the blind spot is
    anti-correlated with the question.

Two things are asserted here, and they pull in opposite directions on purpose:

- the lazy edge must be **in** the graph (it is a real dependency: coupling, orphans,
  dependents all want it), and
- it must **not** turn into an import-cycle report (a lazy import is how that failure is
  prevented; counting it would report the fix as the bug).

Measured on the benchmark target when this landed: 1 eager cycle, 40 closed only by a
lazy import — 41 total against an independently computed AST truth set of 41, exactly.
"""

from __future__ import annotations

import json

import pytest

from codemap.extract import extract
from codemap.query import Query
from codemap.serve.architecture import build_architecture, render_architecture
from codemap.serve.audit import render_dependencies


def _pkg(tmp_path, files: dict[str, str]):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    for name, src in files.items():
        (pkg / name).write_text(src)
    return pkg


@pytest.fixture
def lazy_cycle(tmp_path):
    """`a` imports `b` at module level; `b` imports `a` inside a function — the classic
    cycle-break. Eagerly acyclic, mutually dependent."""
    return _pkg(tmp_path, {
        "a.py": "from pkg.b import beta\n\n\ndef alpha():\n    return beta()\n",
        "b.py": "def beta():\n    from pkg.a import alpha\n    return alpha\n",
    })


# -- the edge exists, and it says how it is reached --------------------------

def test_a_function_local_import_produces_an_edge(lazy_cycle):
    g = extract(str(lazy_cycle))
    edges = {(e.source, e.target): e.extras for e in g.edges if e.type == "imports"}
    assert ("pkg.b", "pkg.a") in edges, "the lazy import was invisible before R1-C29"
    assert edges[("pkg.b", "pkg.a")]["scope"] == "function"
    # …and an ordinary import is not mislabelled as one.
    assert "scope" not in edges[("pkg.a", "pkg.b")]


def test_the_edge_counts_as_a_dependency(lazy_cycle):
    """It is a real dependency: `b` cannot ship without `a`, lazily or not."""
    q = Query(extract(str(lazy_cycle)))
    assert "pkg.a" in q.dependencies("pkg.b")
    assert "pkg.b" in q.dependents("pkg.a")


def test_a_pair_imported_both_ways_keeps_the_eager_label(tmp_path):
    """A module-level import wins over a lazy one for the same pair — the edge says how
    the dependency is reached at its earliest, not how it appears last in the walk."""
    pkg = _pkg(tmp_path, {
        "a.py": "x = 1\n",
        "b.py": ("from pkg.a import x\n\n\ndef f():\n"
                 "    from pkg.a import x as y\n    return y\n"),
    })
    edges = {(e.source, e.target): e.extras
             for e in extract(str(pkg)).edges if e.type == "imports"}
    assert "scope" not in edges[("pkg.b", "pkg.a")]


def test_class_body_imports_are_not_treated_as_lazy(tmp_path):
    """A class-body import runs at import time, so it is eager — and griffe already has
    it. Mislabelling it would move a real import-order risk out of the cycle report."""
    pkg = _pkg(tmp_path, {
        "a.py": "x = 1\n",
        "b.py": "class C:\n    from pkg.a import x\n",
    })
    edges = {(e.source, e.target): e.extras
             for e in extract(str(pkg)).edges if e.type == "imports"}
    assert ("pkg.b", "pkg.a") in edges
    assert "scope" not in edges[("pkg.b", "pkg.a")]


# -- but it is not an import-time cycle --------------------------------------

def test_the_lazy_cycle_is_reported_separately_not_as_an_import_cycle(lazy_cycle):
    q = Query(extract(str(lazy_cycle)))
    assert q.import_cycles() == [], "a lazy import prevents the import-time failure"
    assert [sorted(c) for c in q.lazy_import_cycles()] == [["pkg.a", "pkg.b"]]


def test_an_eager_cycle_is_still_an_import_cycle(tmp_path):
    pkg = _pkg(tmp_path, {
        "a.py": "from pkg.b import beta\n",
        "b.py": "from pkg.a import alpha\n",
    })
    q = Query(extract(str(pkg)))
    assert [sorted(c) for c in q.import_cycles()] == [["pkg.a", "pkg.b"]]
    assert q.lazy_import_cycles() == [], "an eager cycle is not also a lazy one"


def test_a_longer_cycle_whose_lazy_edge_closes_it_is_enumerated(tmp_path):
    """Three modules, the lazy import at the far end — the shape both audit scripts lost.

    The reporter of #11 verified the fix on their tree and found codemap reporting **three**
    cycles where their issue had claimed two. Their scan collected DFS back-edges instead
    of enumerating simple cycles, so a 3-node cycle was swallowed once its nodes were
    coloured; ours mis-anchored relative imports. Two independent scripts written to audit
    a tool, both less careful than the tool, on the same day. This test pins the property
    that made codemap right here: every elementary cycle, not one representative per
    strongly-connected blob.
    """
    pkg = _pkg(tmp_path, {
        "a.py": "from pkg.b import beta\n\n\ndef alpha():\n    return 1\n",
        "b.py": "from pkg.c import gamma\n\n\ndef beta():\n    return gamma()\n",
        "c.py": "def gamma():\n    from pkg.a import alpha\n    return alpha()\n",
        # a second, shorter cycle sharing a node — both must be reported, not one.
        "d.py": "from pkg.a import alpha\n\n\ndef delta():\n    return alpha()\n",
        "e.py": ("from pkg.d import delta\n\n\ndef eps():\n"
                 "    return delta()\n"),
    })
    (tmp_path / "pkg" / "a.py").write_text(
        "from pkg.b import beta\n\n\ndef alpha():\n"
        "    from pkg.e import eps\n    return eps()\n")
    q = Query(extract(str(pkg)))
    assert q.import_cycles() == [], "every cycle here is closed by a lazy import"
    found = {frozenset(c) for c in q.lazy_import_cycles()}
    assert frozenset({"pkg.a", "pkg.b", "pkg.c"}) in found
    assert frozenset({"pkg.a", "pkg.d", "pkg.e"}) in found, (
        "a second cycle sharing a node was swallowed — this is back-edge collection, "
        "not simple-cycle enumeration")


def test_import_map_is_emitted_even_when_nothing_is_lazy(tmp_path):
    """The R1-C28 rule, applied to a second kind of partiality: a reader must never have
    to tell "no lazy imports here" from "this build did not look for them"."""
    pkg = _pkg(tmp_path, {"a.py": "x = 1\n", "b.py": "from pkg.a import x\n"})
    im = Query(extract(str(pkg))).import_map()
    assert im == {"module_level": 1, "function_local": 0}


# -- and no consumer states acyclicity as a property -------------------------

def test_architecture_never_claims_acyclic(lazy_cycle):
    md = render_architecture(Query(extract(str(lazy_cycle))))
    assert "acyclic" not in md, "a partial map cannot support a property claim"
    assert "none found in the eager import graph" in md
    assert "function-local import(s)" in md
    assert "Dependency cycles closed only by a function-local import: 1" in md


def test_dependencies_report_never_claims_acyclic(lazy_cycle):
    md = render_dependencies(Query(extract(str(lazy_cycle))))
    assert "acyclic" not in md
    assert "close through a lazy import" in md


def test_architecture_payload_carries_both_kinds_and_the_counts(lazy_cycle):
    a = build_architecture(Query(extract(str(lazy_cycle))))
    assert a["cycles"] == []
    assert [sorted(c) for c in a["lazy_cycles"]] == [["pkg.a", "pkg.b"]]
    assert a["import_map"] == {"module_level": 1, "function_local": 1}


def test_no_renderer_states_acyclicity_anywhere(tmp_path):
    """The guard: grep the shipped renderers for the affirmative word.

    The defect was never in one report — it was one sentence copied into three. A new
    consumer of `import_cycles` inherits the same temptation, so the rule is enforced on
    the source rather than on three assertions that would each need remembering.
    """
    import ast
    from pathlib import Path
    import codemap
    root = Path(codemap.__file__).parent
    offenders = []
    for py in sorted(root.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        # Docstrings are prose about the code and may name the word freely; what must not
        # exist is a string the tool *prints*.
        docstrings = {id(ast.get_docstring(n, clean=False) and n.body[0].value)
                      for n in ast.walk(tree)
                      if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                        ast.AsyncFunctionDef))}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in docstrings or "acyclic" not in node.value:
                continue
            offenders.append(f"{py.relative_to(root)}:{node.lineno}: {node.value[:70]}")
    assert not offenders, (
        "a renderer states acyclicity as a property over a map that cannot prove it:\n"
        + "\n".join(offenders))


# -- the real target, which is what made this worth fixing -------------------

def test_the_benchmark_target_is_no_longer_answered_at_one_cycle():
    """Guard on the finding itself, on codemap's own tree rather than a fixture.

    codemap has no eager cycle and (at the time of writing) no lazy one either, so what
    is asserted here is the part that would silently regress: that the lazy imports are
    *seen*. 38 of them, from 100 module-level ones, on this repository.
    """
    from pathlib import Path
    import codemap
    q = Query(extract(str(Path(codemap.__file__).parent)))
    im = q.import_map()
    assert im["function_local"] > 0, "the extractor stopped seeing function-local imports"
    assert im["module_level"] > im["function_local"]
