"""R1-C118 — dead-code: bound-method callbacks, test calls through a module, public functions said aloud.

Expectations E1–E6 are in BACKLOG.md (R1-C118), written before the change. E1–E5 fail on 0.0.42.
"""

from __future__ import annotations

import json
from pathlib import Path

from codemap.extract import extract_repo
from codemap.query import Query
from codemap.serve.audit import build_dead_code, render_dead_code

W = '''class Bus:
    def on(self, name, fn):
        self.fn = fn


def run(fn, *, prepare=None):
    return fn, prepare


class Worker:
    def __init__(self):
        self.bus = Bus()

    def start(self):
        self.bus.on("x", self._on_attached)
        run(len, prepare=self._migrate)
        self._called()

    def _on_attached(self, ev):
        return ev

    def _migrate(self):
        return 1

    def _called(self):
        return 0

    def _nobody(self):
        return 3


def _only_tests(x):
    return x


def public_unused():
    return 2


def public_tested():
    return 4


def main():
    Worker().start()
'''
TEST = '''from pkg import w


def test_it():
    assert w._only_tests(1) == 1
    assert w.public_tested() == 4
'''


def _q(tmp_path: Path) -> Query:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/__init__.py").write_text("")
    (tmp_path / "pkg/w.py").write_text(W)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_w.py").write_text(TEST)
    return Query(extract_repo(str(tmp_path / "pkg"), consumers=[str(tmp_path / "tests")]))


def test_e1_a_bound_method_handed_on_is_referenced_not_dead(tmp_path):
    by = {c["id"]: c for c in _q(tmp_path).dead_code()}
    for name in ("_on_attached", "_migrate"):
        c = by[f"pkg.w.Worker.{name}"]
        assert c["confidence"] == "low" and "referenced (references) by core" in c["reasons"][0], c
    assert by["pkg.w.Worker._nobody"]["confidence"] == "high"   # control: nothing names it
    assert "pkg.w.Worker._called" not in by                    # control: called, never a candidate


def test_e2_e3_a_test_call_through_a_module_is_an_edge_and_is_named(tmp_path):
    q = _q(tmp_path)
    assert "pkg.w._only_tests" not in {c["id"] for c in q.dead_code()}
    outside = {c["id"]: c for c in q.called_only_from_outside()}
    assert outside["pkg.w._only_tests"]["roots"] == {"tests": 1}
    md = render_dead_code(q)
    assert "## Called only from outside the package: 1 private function(s)" in md
    assert "- `pkg.w._only_tests` (private) — tests×1" in md
    assert "And 1 public function(s) reached only from outside" in md      # public_tested, hidden by default
    assert "`pkg.w.public_tested` (public)" in render_dead_code(q, public=True)


def test_e4_public_functions_are_counted_by_default_and_listed_on_request(tmp_path):
    q = _q(tmp_path)
    md = render_dead_code(q)
    assert "Not judged: 2 public module-level function(s) have no inbound edge" in md
    assert "`codemap report dead-code --public`" in md
    assert "public_unused" not in md
    full = render_dead_code(q, public=True)
    assert "## Uncalled public functions (module level): 2" in full
    assert "- `pkg.w.public_unused` [high]" in full and "- `pkg.w.main` [high]" in full
    assert "public_tested" not in full.split("## Uncalled public functions")[1]


def test_e5_json_carries_the_same(tmp_path):
    q = _q(tmp_path)
    out = build_dead_code(q)
    assert out["uncalled_public"] == {"count": 2, "listed": False}
    assert [c["id"] for c in out["called_only_from_outside"]] == ["pkg.w._only_tests", "pkg.w.public_tested"]
    listed = build_dead_code(q, public=True)["uncalled_public"]
    assert [c["id"] for c in listed["candidates"]] == ["pkg.w.main", "pkg.w.public_unused"]
    json.dumps(out)
