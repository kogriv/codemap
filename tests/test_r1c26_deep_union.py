"""R1-C26 acceptance — the deep tier is a union with the fast tier, not a replacement (issue #10).

`add_behavior` picked its resolver by tier and used it **exclusively**: with `deep=True`
every call went to jedi and the name-based resolver was never consulted. Two consequences,
both silent, both inverted (paying for the better tier and getting less):

- **On a flat layout, catastrophic.** jedi resolves `from leaf import helper` correctly — to
  `leaf.helper` — and the internal test `startswith(pkg + ".")` reads that as *external*,
  because in a flat layout the directory itself is on `sys.path` and a sibling has no
  package prefix. Measured on the reporter's target: **487 calls / 158 cross-module on
  fast, 336 / 0 on deep**. R1-C21 taught the flat-layout inference to the structural and
  fast layers; the jedi boundary was never taught it.
- **On ordinary packaged targets, small but real.** Anything jedi could not see was
  discarded rather than handed to the cheaper resolver: 5 true edges on codemap, 5 on
  bquant, mostly `self.` calls whose target lives on a base class.

After the fix, `calls(deep) ⊇ calls(fast)` on all three targets — the reporter's target 158 → 0
fast-only edges, codemap 5 → 0, bquant 5 → 1, where the one remaining difference is deep
being *more precise* (it resolves a call to the method on the class, where fast named the
module-level function).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.extract import extract
from codemap.extract.behavior import _flat_qualify

FLAT = Path(__file__).resolve().parent / "fixtures" / "flatpkg"
REF = Path(__file__).resolve().parent / "fixtures" / "refpkg"


def _calls(graph):
    return {(e.source, e.target) for e in graph.edges if e.type == "calls"}


@pytest.fixture(scope="module")
def flat_fast():
    return extract(FLAT)


@pytest.fixture(scope="module")
def flat_deep():
    return extract(FLAT, deep=True)


# -- D1: a flat sibling is internal, it just does not look it ---------------------

def test_a_flat_sibling_call_resolves_on_the_deep_tier(flat_deep):
    """`beta.doubled` calls `base_width`, imported by bare name from a sibling. The deep
    tier used to file it as external and emit nothing."""
    assert ("flatpkg.beta.doubled", "flatpkg.alpha.base_width") in _calls(flat_deep)


def test_the_edge_is_labelled_as_the_tier_that_resolved_it(flat_deep):
    """`resolution` names which tier resolved the call, not which layout the target has —
    the flat inference is already visible on the `imports` edge."""
    e = [e for e in flat_deep.edges if e.type == "calls"
         and e.target == "flatpkg.alpha.base_width"]
    assert e and e[0].extras["resolution"] == "deep"


def test_qualification_only_fires_for_a_real_sibling():
    known = {"pkg.leaf", "pkg.mid"}
    assert _flat_qualify("leaf.helper", "pkg.mid", known) == "pkg.leaf.helper"
    # `pandas.DataFrame` must never be invented into the package
    assert _flat_qualify("pandas.DataFrame", "pkg.mid", known) is None
    # a top-level module has no parent to qualify against
    assert _flat_qualify("leaf.helper", "mid", known) is None


# -- D5.2: the invariant the milestone is about ----------------------------------

@pytest.mark.parametrize("target", [FLAT, REF])
def test_deep_is_a_superset_of_fast(target):
    """The property every consumer assumes when they choose the expensive tier, and which
    did not hold: nothing the cheap tier resolves may be lost by the expensive one."""
    lost = _calls(extract(target)) - _calls(extract(target, deep=True))
    assert lost == set(), f"deep lost edges the fast tier resolved: {sorted(lost)}"


def test_deep_still_finds_more_than_fast(flat_fast, flat_deep):
    """A union, not a downgrade to the fast tier: jedi's own resolutions stay."""
    assert len(_calls(flat_deep)) >= len(_calls(flat_fast))


# -- D2/D3: when the fallback fires, and when it must not ------------------------

def test_the_fallback_fires_only_when_jedi_has_no_usable_answer(tmp_path):
    """A call jedi resolves to the stdlib must stay external — no name-based guess may
    replace a correct "not ours" with a plausible internal edge."""
    pkg = tmp_path / "extpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    # a local function named like the stdlib call target, to bait a wrong fallback
    (pkg / "mod.py").write_text(
        "import json\n\n\ndef dumps(x):\n    return x\n\n\n"
        "def go(x):\n    return json.dumps(x)\n", encoding="utf-8")
    calls = _calls(extract(pkg, deep=True))
    assert ("extpkg.mod.go", "extpkg.mod.dumps") not in calls


def test_a_jedi_answer_that_is_not_a_node_falls_back(tmp_path):
    """`self.helper()` where the method lives on the base class: jedi names it on the
    subclass, which is not a graph node, and the soundness downgrade used to drop it
    *after* the cheaper resolver was out of reach."""
    pkg = tmp_path / "inhpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "mod.py").write_text(
        "class Base:\n"
        "    def helper(self):\n"
        "        return 1\n\n\n"
        "class Child(Base):\n"
        "    def run(self):\n"
        "        return self.helper()\n", encoding="utf-8")
    calls = _calls(extract(pkg, deep=True))
    assert ("inhpkg.mod.Child.run", "inhpkg.mod.Base.helper") in calls


# -- the whole point, end to end --------------------------------------------------

def test_the_reporters_shape_resolves(tmp_path):
    """The two-file reproducer from issue #10, verbatim in shape."""
    flat = tmp_path / "flat"
    flat.mkdir()
    (flat / "leaf.py").write_text("def helper(x):\n    return x + 1\n", encoding="utf-8")
    (flat / "mid.py").write_text(
        "from leaf import helper\n\n\ndef use_both(x):\n    return helper(x)\n",
        encoding="utf-8")
    assert ("flat.mid.use_both", "flat.leaf.helper") in _calls(extract(flat, deep=True))
