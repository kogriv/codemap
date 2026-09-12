"""R1-C58 — cycles were counted by the piece, and pieces are combinatorial.

Found by axis B4 (`gaps/third_shape_2026-09-12.md` §S3/§S4). Three trees of comparable
size, the same command:

    codemap  52 modules → 0 / 0 / 0
    bquant   92 modules → 0 / 9 / —
    _pytest  78 modules → 1080 / 95 001 / 464 109, a 1632-line report in 10.3 s

Those are not large numbers, they are combinatorial ones: two mutually-dependent modules
make one cycle, and a third in the same knot multiplies the paths through it. The reader's
action is the same either way — break the knot — so the unit of the answer is now the knot
(a strongly connected component), with **one example cycle** each.

What must not be lost with the count is the property issue #11 was about: nothing is
swallowed. Two loops sharing a module are two problems, and a module inside a cycle must
never be missing from the answer. That is carried by the tangle's membership and by its
**cycle rank** — the number of independent loops, `E - V + 1`, which is linear to compute
and does not explode (the 19-module tangle in `_pytest` has 57, against 1080 simple cycles).

D4 in the same pass: a layer is the first path segment under the root, so a package with no
subpackages has one layer per module. Pillow printed "Layers (105)" over 105 modules and
presented it as an architectural overview.

Design: `docs/design/cycle_tangles.md`.
"""

from __future__ import annotations

import pytest

from codemap import arch
from codemap.extract import extract
from codemap.query import Query
from codemap.serve.architecture import build_architecture, render_architecture

# a → b → c → a and a → d → e → a: two loops sharing one module, all eager
KNOT = {
    "a.py": "from pkg.b import beta\nfrom pkg.d import delta\n\n\ndef alpha():\n    return 1\n",
    "b.py": "from pkg.c import gamma\n\n\ndef beta():\n    return gamma()\n",
    "c.py": "from pkg.a import alpha\n\n\ndef gamma():\n    return alpha()\n",
    "d.py": "from pkg.e import eps\n\n\ndef delta():\n    return eps()\n",
    "e.py": "from pkg.a import alpha\n\n\ndef eps():\n    return alpha()\n",
    # a module outside the knot, so "everything is tangled" cannot pass by accident
    "f.py": "from pkg.a import alpha\n\n\ndef phi():\n    return alpha()\n",
}
FLAT = {"one.py": "from pkg.two import t\n", "two.py": "t = 1\n"}
NESTED = {"sub/__init__.py": "", "sub/one.py": "from pkg.other.two import t\n",
          "other/__init__.py": "", "other/two.py": "t = 1\n"}


def _pkg(root, files, name="pkg"):
    pkg = root / name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    for rel, body in files.items():
        path = pkg / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return pkg


@pytest.fixture(scope="module")
def knot(tmp_path_factory):
    return Query(extract(str(_pkg(tmp_path_factory.mktemp("r1c58"), KNOT))))


# -- D1: the unit is the tangle ---------------------------------------------------------

def test_one_knot_is_one_answer(knot):
    tangles = knot.import_tangles()
    assert len(tangles) == 1
    assert tangles[0]["modules"] == ["pkg.a", "pkg.b", "pkg.c", "pkg.d", "pkg.e"]
    assert "pkg.f" not in tangles[0]["modules"], "a module that only imports in is not in"


def test_the_independent_loops_are_counted(knot):
    """The part of the old count worth keeping: two loops sharing a module are two."""
    assert knot.import_tangles()[0]["loops"] == 2


def test_one_example_cycle_per_tangle(knot):
    cycles = knot.import_cycles()
    assert len(cycles) == 1, "one representative, not every simple cycle"
    cyc = cycles[0]
    assert set(cyc) <= set(knot.import_tangles()[0]["modules"])
    assert len(set(cyc)) == len(cyc), "an example cycle does not repeat a module"


def test_the_example_is_a_real_cycle(knot):
    """Cheap to state, easy to get wrong: consecutive modules must really import."""
    edges = {(e.source, e.target) for e in knot.graph.edges if e.type == "imports"}
    cyc = knot.import_cycles()[0]
    for src, dst in zip(cyc, cyc[1:] + cyc[:1]):
        assert (src, dst) in edges, f"{src} does not import {dst}"


def test_a_tree_without_a_knot_reports_none(tmp_path):
    q = Query(extract(str(_pkg(tmp_path, FLAT))))
    assert q.import_tangles() == [] and q.import_cycles() == []


# -- D2: the three classes still partition ----------------------------------------------

def test_the_classes_stay_disjoint(knot):
    sets = [{frozenset(t["modules"]) for t in kind}
            for kind in (knot.import_tangles(), knot.lazy_import_tangles(),
                         knot.type_only_import_tangles())]
    assert not (sets[0] & sets[1]) and not (sets[0] & sets[2]) and not (sets[1] & sets[2])


def test_the_gate_reports_one_violation_per_tangle(knot):
    v = arch.check_contract(knot, arch.ArchitectureContract(no_cycles=True))
    assert len(v) == 1 and v[0].rule == "no_cycles"
    assert "1 import tangle(s), 5 module(s)" in v[0].summary
    assert len(v[0].modules) == 1, "one line, not one per simple cycle"
    assert "tangle of 5" in v[0].modules[0]


def test_the_report_says_what_it_does_not_report(knot):
    md = render_architecture(knot)
    assert "5 module(s), 2 independent loop(s)" in md
    assert "combinatorial" in md, "the reader is told the simple-cycle count is withheld"
    assert "tangle" in md


# -- D4: a flat package says its layers are degenerate -----------------------------------

def test_a_flat_package_declares_that_layer_means_module(tmp_path):
    q = Query(extract(str(_pkg(tmp_path, FLAT))))
    md = render_architecture(q)
    assert "**layer = module** here" in md
    assert "### Inter-layer dependencies" not in md, \
        "the inter-layer view would repeat the import graph edge for edge"


def test_a_nested_package_keeps_the_layer_view(tmp_path):
    """The control: where layers mean something, nothing changes."""
    q = Query(extract(str(_pkg(tmp_path, NESTED))))
    md = render_architecture(q)
    assert "**layer = module** here" not in md
    assert "### Inter-layer dependencies" in md


# -- the structured payload carries both --------------------------------------------------

def test_the_payload_carries_tangles_and_examples(knot):
    a = build_architecture(knot)
    assert a["tangles"] and a["cycles"]
    assert a["tangles"][0]["size"] == 5 and a["tangles"][0]["loops"] == 2
    assert len(a["cycles"]) == len(a["tangles"]), "one example per tangle"
