"""R1-C81 — a call on a Protocol reaches its implementers; a test's chain is typed by return annotations.

Design `docs/design/protocol_dispatch.md` (pre-registered 4f0b765).
"""

from __future__ import annotations

import pytest

from codemap.extract import extract_repo
from codemap.query import Query

MENU = '''from typing import Optional, Protocol

REGISTRY = {}


class PathForecaster(Protocol):
    def fit(self, frame) -> "PathForecaster": ...

    def band(self, sub, k, *, sigma=None): ...


class Base:
    def band(self, sub, k, *, sigma=None):
        return []


class KnnA(Base):
    def fit(self, frame) -> "KnnA":
        return self


class KnnB(Base):
    def fit(self, frame) -> "KnnB":
        return self

    def band(self, sub, k, *, sigma=None):
        return [1]


class SameNamesOtherParams:
    def fit(self, data):
        return self

    def band(self, sub, k, *, sigma=None):
        return []


class Spec:
    def __init__(self, model_type="a"):
        self.model_type = model_type

    def build(self) -> PathForecaster:
        return REGISTRY[self.model_type](self)

    def maybe(self) -> Optional[PathForecaster]:
        return None

    def untyped(self):
        return KnnA()
'''

TESTS = '''from pkg.menu import KnnA, Spec


def _spec():
    return Spec(model_type="b")


def test_chain():
    fc = _spec().build().fit([1])
    assert fc.band([1], 1) is not None


def test_optional():
    Spec().maybe().band([1], 1)


def test_untyped():
    x = Spec().untyped()
    x.band([1], 1)


def test_reassigned():
    fc = Spec().build()
    fc = None
    fc.band([1], 1)


def test_direct():
    KnnA().band([1], 1)
'''


@pytest.fixture(scope="module")
def q(tmp_path_factory) -> Query:
    root = tmp_path_factory.mktemp("r1c81")
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "menu.py").write_text(MENU)
    (root / "tests").mkdir()
    (root / "tests" / "test_menu.py").write_text(TESTS)
    return Query(extract_repo(str(root / "pkg"), consumers=(str(root / "tests"),), mode="full"))


def _calls(q, res):
    return {(e.source, e.target) for e in q.graph.edges
            if e.type == "calls" and e.extras.get("resolution") == res}


P = "pkg.menu."
T = "tests.test_menu."


# -- D1 ----------------------------------------------------------------------

def test_D1_structural_implementers_match_names_and_parameters(q):
    assert q.implementers(P + "PathForecaster") == [P + "KnnA", P + "KnnB"]
    links = {(e.source, e.extras.get("via")) for e in q.graph.edges if e.type == "implements"}
    assert (P + "KnnA", "structural") in links
    # same method names, `fit(self, data)` instead of `fit(self, frame)`: not an implementer
    assert P + "SameNamesOtherParams" not in q.implementers(P + "PathForecaster")
    # Base lacks `fit`: not an implementer, though its `band` is what KnnA inherits
    assert P + "Base" not in q.implementers(P + "PathForecaster")


# -- D4 ----------------------------------------------------------------------

def test_E4_a_chain_is_typed_by_constructors_and_return_annotations(q):
    typed = _calls(q, "typed")
    assert (T + "test_chain", P + "Spec.build") in typed           # local helper → Spec
    assert (T + "test_chain", P + "PathForecaster.fit") in typed   # build() -> PathForecaster
    assert (T + "test_chain", P + "PathForecaster.band") in typed  # fc = ….fit(…): "PathForecaster"
    assert (T + "test_optional", P + "PathForecaster.band") in typed   # Optional[...] unwraps


def test_E4_nothing_is_guessed(q):
    typed = _calls(q, "typed") | _calls(q, "protocol")
    assert not any(s == T + "test_untyped" and t.endswith(".band") for s, t in typed)
    assert not any(s == T + "test_reassigned" and t.endswith(".band") for s, t in typed)


# -- D2 ----------------------------------------------------------------------

def test_D2_a_protocol_call_fans_out_to_each_implementers_method(q):
    fan = _calls(q, "protocol")
    assert (T + "test_chain", P + "KnnB.band") in fan
    assert (T + "test_chain", P + "Base.band") in fan              # KnnA's inherited band
    assert (T + "test_chain", P + "KnnB.fit") in fan and (T + "test_chain", P + "KnnA.fit") in fan
    assert not any(t.startswith(P + "SameNamesOtherParams") for _, t in fan)


# -- D3 ----------------------------------------------------------------------

def test_D3_a_test_reached_only_through_the_fan_out_is_low(q):
    r = q.tests_for(P + "KnnB.band")
    rows = {t["id"]: t["confidence"] for t in r["tests"]}
    assert rows == {T + "test_chain": "low", T + "test_optional": "low"}
    assert r["confidence"] == "low"
    assert any("dispatch over-approximation" in c for c in r["caveats"])


def test_D3_an_exact_path_keeps_its_confidence(q):
    # test_direct calls KnnA().band → Base.band exactly; test_chain reaches it only by the fan-out
    r = q.tests_for(P + "Base.band")
    rows = {t["id"]: t["confidence"] for t in r["tests"]}
    assert rows[T + "test_direct"] == "high" and rows[T + "test_chain"] == "low"
    assert r["confidence"] == "high"


def test_E2_shape_the_method_behind_build_is_no_longer_unknown(q):
    assert q.tests_for(P + "KnnB.fit")["confidence"] != "unknown"


def test_D2_core_callers_fan_out_in_a_single_package_build(tmp_path):
    """No consumer roots: the fan-out must come from the core pipeline itself (deep tier,
    where jedi resolves `spec.build().band(...)` to the Protocol method)."""
    from codemap.extract import extract
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "menu.py").write_text(
        MENU + "\n\ndef evaluate(spec: Spec, df):\n    return spec.build().fit(df).band(df, 1)\n")
    g = extract(str(tmp_path / "pkg"), deep=True)
    fan = {(e.source, e.target) for e in g.edges
           if e.type == "calls" and e.extras.get("resolution") == "protocol"}
    assert (P + "evaluate", P + "KnnB.band") in fan


# -- R1-C88: a method outside the Protocol --------------------------------------

def test_R1C88_a_method_outside_the_protocol_fans_out_to_those_that_have_it(tmp_path):
    root = tmp_path
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "menu.py").write_text(
        MENU + "\n\nclass KnnC(Base):\n    def fit(self, frame) -> 'KnnC':\n        return self\n\n"
        "    def member_values(self, q, k):\n        return []\n\n\n"
        "class KnnD(KnnC):\n    def fit(self, frame) -> 'KnnD':\n        return self\n\n\n"
        "def _knnb_member_values(self, q, k):\n    return []\n\n\nKnnB.member_values = _knnb_member_values\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_m.py").write_text(
        "from pkg.menu import Spec, KnnA\n\n\n"
        "def test_outside():\n    fc = Spec().build().fit([1])\n    fc.member_values(1, 3)\n\n\n"
        "def test_nobody_has_it():\n    Spec().build().nothing_like_this()\n\n\n"
        "def test_concrete_missing():\n    KnnA().member_values(1, 3)\n")
    q = Query(extract_repo(str(root / "pkg"), consumers=(str(root / "tests"),), mode="full"))
    fan = {(s.rsplit(".", 1)[1], t) for s, t in _calls(q, "protocol") if s.startswith("tests.")}
    assert ("test_outside", P + "KnnC.member_values") in fan
    # KnnC defines it and KnnD inherits it (one method, one edge); KnnA/KnnB do not have it
    # as a method in the graph (KnnB's is a module-level assignment), so they get nothing
    assert {t for s, t in fan if s == "test_outside" and t.endswith(".member_values")} == {
        P + "KnnC.member_values"}
    assert P + "KnnD" in q.implementers(P + "PathForecaster")
    assert not any(s in ("test_nobody_has_it", "test_concrete_missing") for s, _ in fan)
    r = q.tests_for(P + "KnnC.member_values")
    assert {t["id"]: t["confidence"] for t in r["tests"]} == {"tests.test_m.test_outside": "low"}
