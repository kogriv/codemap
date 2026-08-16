"""R1-C4 acceptance — per-function complexity metrics.

codemap computes cyclomatic complexity, Halstead volume, a Maintainability Index
and physical SLOC per function in the behavioural AST pass (source-only, stdlib-only,
deterministic). These tests pin the cyclomatic decision-point counting (incl. the
nested-def boundary), the MI range/monotonicity, and the wiring into node extras,
Query.hotspots (both axes), and the query dossier.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from codemap.extract import extract
from codemap.extract.behavior import (
    _complexity, _cyclomatic, _halstead_volume, _maintainability,
)
from codemap.query import Query
from codemap.serve.session import build_query_result

CORE = Path(__file__).resolve().parent / "fixtures" / "reporoot" / "core"


def _fn(code: str):
    return ast.parse(code).body[0]


# -- cyclomatic decision points -----------------------------------------------

def test_cc_trivial():
    assert _cyclomatic(_fn("def f():\n    return 1\n")) == 1


def test_cc_if_elif_else():
    code = ("def f(x):\n"
            "    if x == 1:\n        return 1\n"
            "    elif x == 2:\n        return 2\n"
            "    else:\n        return 3\n")
    assert _cyclomatic(_fn(code)) == 3          # if + elif


def test_cc_boolop():
    assert _cyclomatic(_fn("def f(a, b, c):\n    return a and b and c\n")) == 3  # +2


def test_cc_loops_and_excepts():
    code = ("def f(items):\n"
            "    for i in items:\n"
            "        while i:\n            i -= 1\n"
            "    try:\n        pass\n"
            "    except ValueError:\n        pass\n"
            "    except KeyError:\n        pass\n")
    assert _cyclomatic(_fn(code)) == 5          # for + while + 2 excepts


def test_cc_comprehension_and_ternary():
    assert _cyclomatic(_fn("def f(xs):\n    return [x for x in xs if x > 0 if x < 9]\n")) == 4
    assert _cyclomatic(_fn("def f(x):\n    return 1 if x else 2\n")) == 2


def test_cc_match():
    code = ("def f(x):\n"
            "    match x:\n"
            "        case 1:\n            return 1\n"
            "        case 2:\n            return 2\n"
            "        case _:\n            return 3\n")
    assert _cyclomatic(_fn(code)) == 4          # three cases


def test_cc_excludes_nested_def():
    code = ("def outer(x):\n"
            "    def inner(y):\n"
            "        if y:\n            return 1\n"
            "        return 0\n"
            "    if x:\n        return inner(x)\n"
            "    return 0\n")
    # only outer's own `if x` counts; inner's `if y` is a separate node's complexity
    assert _cyclomatic(_fn(code)) == 2


# -- Halstead + MI ------------------------------------------------------------

def test_halstead_volume_zero_and_positive():
    assert _halstead_volume(_fn("def f():\n    return 1\n")) == 0.0   # no operators/names
    assert _halstead_volume(_fn("def f(a, b):\n    return a + b * a\n")) > 0.0


def test_mi_range_and_monotonicity():
    simple = _complexity(_fn("def f():\n    return 1\n"))
    complex_code = ("def g(a, b, c, d):\n" + "".join(
        f"    if a == {i} and b > {i} or c < {i}:\n        d += {i}\n" for i in range(15)))
    hard = _complexity(_fn(complex_code))
    assert 0.0 <= hard["mi"] <= 100.0 and 0.0 <= simple["mi"] <= 100.0
    assert simple["mi"] > hard["mi"]            # simpler code is more maintainable
    assert hard["cc"] > simple["cc"]


def test_complexity_dict_shape():
    m = _complexity(_fn("def f(x):\n    if x:\n        return 1\n    return 0\n"))
    assert set(m) == {"cc", "volume", "sloc", "mi"}
    assert m["cc"] == 2 and m["sloc"] == 4


# -- wiring: node extras, determinism -----------------------------------------

def test_extraction_populates_complexity():
    g = extract(CORE)
    run = g.nodes["core.engine.Engine.run"]
    assert run.extras["complexity"]["cc"] >= 1
    assert "mi" in run.extras["complexity"]


def test_extraction_deterministic():
    a = extract(CORE).nodes["core.engine.Engine.run"].extras["complexity"]
    b = extract(CORE).nodes["core.engine.Engine.run"].extras["complexity"]
    assert a == b


# -- wiring: hotspots (both axes) ---------------------------------------------

def test_hotspots_carries_complexity():
    q = Query(extract(CORE))
    hs = q.hotspots(min_methods=1, min_cc=1)
    assert "complex_functions" in hs
    # god classes now expose the complexity axis
    for g in hs["god_classes"]:
        assert "total_cc" in g and "max_cc" in g
    # Engine.run should surface as a complex function at min_cc=1
    assert any(f["id"].endswith("Engine.run") for f in hs["complex_functions"])
    # each complex-function entry is well-formed and above threshold
    for f in hs["complex_functions"]:
        assert f["cc"] >= 1 and 0.0 <= f["mi"] <= 100.0


def test_hotspots_min_cc_threshold():
    q = Query(extract(CORE))
    # a high threshold drops the tiny fixture functions
    assert q.hotspots(min_cc=99)["complex_functions"] == []


# -- wiring: query dossier ----------------------------------------------------

def test_dossier_carries_complexity():
    q = Query(extract(CORE))
    dossier = build_query_result(q, "run")
    fn = dossier["functions"]["core.engine.Engine.run"]
    assert fn["complexity"] is not None and "cc" in fn["complexity"]
