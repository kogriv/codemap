"""R1-C80 — `tests` through a helper in the test module; the answer names the next band.

Design `docs/design/tests_through_helpers.md` (pre-registered e666077, corrected before code in 3247be6).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.cli import main
from codemap.extract import extract_repo
from codemap.query import Query

FILES = {
    "pkg/__init__.py": "",
    "pkg/core.py": "def act():\n    return 1\n\n\ndef wrap():\n    return act()\n",
    "tests/test_a.py": (
        "from pkg.core import act, wrap\n\n\n"
        "def _helper():\n    return act()\n\n\n"
        "def _outer():\n    return _helper()\n\n\n"
        "def test_direct():\n    assert act() == 1\n\n\n"
        "def test_through_helper():\n    assert _helper() == 1\n\n\n"
        "def test_through_two_helpers():\n    assert _outer() == 1\n\n\n"
        "def test_nested():\n    def one():\n        return _helper()\n    assert one() == 1\n\n\n"
        "def test_far():\n    assert wrap() == 1\n\n\n"
        "def test_recursive_helper_is_not_a_self_edge():\n    pass\n"
    ),
    "tests/helpers.py": "from pkg.core import act\n\n\ndef shared():\n    return act()\n",
}


def _repo(root: Path, files=FILES, mode="full") -> Query:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return Query(extract_repo(str(root / "pkg"), consumers=(str(root / "tests"),), mode=mode))


@pytest.fixture(scope="module")
def q(tmp_path_factory) -> Query:
    return _repo(tmp_path_factory.mktemp("r1c80"))


def _edges(q, etype=None):
    return {(e.source, e.target, e.extras.get("resolution")) for e in q.graph.edges
            if e.type != "contains" and (etype is None or e.type == etype)}


def test_D0_a_test_calling_its_modules_helper_is_an_edge(q):
    es = _edges(q, "calls")
    assert ("tests.test_a.test_through_helper", "tests.test_a._helper", "local") in es
    assert ("tests.test_a._outer", "tests.test_a._helper", "local") in es
    assert ("tests.test_a.test_nested.one", "tests.test_a._helper", "local") in es
    # every local edge stays inside the consumer root
    for src, tgt, res in _edges(q):
        if res == "local":
            assert q.root_of(src) == "tests" and q.root_of(tgt) == "tests"


def test_D0_not_in_thin_mode_and_not_for_imported_names(tmp_path):
    thin = _repo(tmp_path / "thin", mode="thin")
    assert not any(r == "local" for *_, r in _edges(thin))
    files = {**FILES, "tests/test_b.py": ("from pkg.core import act\n\n\ndef act_local():\n    return act()\n\n\n"
                                          "def test_b():\n    assert act() == 1\n")}
    full = _repo(tmp_path / "full", files)
    assert ("tests.test_b.test_b", "pkg.core.act", "imported") in _edges(full, "calls")


def test_E1_tests_through_helpers_are_in_the_nearest_band(q):
    r = q.tests_for("pkg.core.act")
    got = {t["id"] for t in r["tests"]}
    assert r["distance"] == 1
    assert got == {"tests.test_a.test_direct", "tests.test_a.test_through_helper",
                   "tests.test_a.test_through_two_helpers", "tests.test_a.test_nested"}
    assert "tests.helpers.shared" not in got            # not a test, and helpers.py is not collected


def test_E7_next_band_is_named_and_null_when_there_is_none(q):
    r = q.tests_for("pkg.core.act")
    assert r["next_band"] == {"distance": 2, "count": 1}                  # test_far, through wrap
    assert "nearest band at distance 1; looked up to depth 3 for more" in r["caveats"]
    assert q.tests_for("pkg.core.wrap")["next_band"] is None


def test_E8_all_bands_is_the_union_with_distances_and_is_stable(q):
    r = q.tests_for("pkg.core.act", all_bands=True)
    rows = {(t["id"], t["distance"]) for t in r["tests"]}
    assert ("tests.test_a.test_far", 2) in rows and ("tests.test_a.test_direct", 1) in rows
    assert r["total"] == 5 and r["total_at_distance"] == 4
    assert r == q.tests_for("pkg.core.act", all_bands=True)


def test_E9_covers_reaches_through_a_helper_at_distance_one(q):
    r = q.covers("tests.test_a.test_through_helper")
    assert {"id": "pkg.core.act", "distance": 1} in r["symbols"]
    r = q.covers("tests.test_a.test_through_two_helpers")
    assert {"id": "pkg.core.act", "distance": 1} in r["symbols"]


def test_the_cli_names_the_next_band_and_lists_all_bands(tmp_path, capsys):
    from codemap import store
    q = _repo(tmp_path)
    g = tmp_path / "g.json"
    store.save(q.graph, str(g))
    assert main(["tests", "act", "--graph", str(g)]) == 0
    out = capsys.readouterr().out
    assert "… 1 more test(s) at distance 2 — `--all-bands` lists them" in out
    assert main(["tests", "act", "--graph", str(g), "--all-bands"]) == 0
    out = capsys.readouterr().out
    assert "test_far   (distance 2)" in out and "more test(s)" not in out


def test_E9_covers_enters_a_nested_helper(q):
    assert {"id": "pkg.core.act", "distance": 1} in q.covers("tests.test_a.test_nested")["symbols"]
