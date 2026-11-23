"""R1-C132 harness controls: the runtime truth and the comparison are themselves checked before they judge.

Design and pre-registered expectations: research/bench/r1c132/DESIGN.md. C1 — the tracer attributes every call
shape of the control package the way codemap does (nested functions and lambdas to the enclosing function, a
decorator's wrapper as `wrapper`, a construction to the class, `super().__init__()` as a call). C2 — the
comparison can say "contradicted": a planted false edge whose every site ran is caught, and an edge whose site
did not run is not judged.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.version_info < (3, 12), reason="sys.monitoring needs Python 3.12")

HERE = Path(__file__).resolve().parent.parent / "research/bench/r1c132"
CONTROL = HERE / "control"
sys.path.insert(0, str(HERE))

EXPECTED = {
    ("ctl", "ctl.deco", "direct", False),                    # applied as a decorator at import
    ("ctl.C.__init__", "ctl.g", "direct", False),
    ("ctl.C.m", "ctl.h", "direct", False),
    ("ctl.decorated", "ctl.g", "direct", False),
    ("ctl.outer", "ctl.C.__init__", "direct", False),
    ("ctl.outer", "ctl.C.m", "direct", False),
    ("ctl.outer", "ctl.D", "direct", True),                  # D() — construction, pointed at the class
    ("ctl.outer", "ctl.decorated", "wrapper", False),        # through deco's wrapper
    ("ctl.outer", "ctl.g", "nested", False),                 # from a lambda inside outer
    ("ctl.outer", "ctl.h", "direct", False),                 # comprehension (inlined), sorted(key=h)
    ("ctl.outer", "ctl.h", "nested", False),                 # from inner()
    ("ctl.make_e", "ctl.E", "direct", True),
    ("ctl.make_e", "ctl.E.__init__", "direct", False),
    ("ctl.E.__init__", "ctl.C.__init__", "direct", False),   # super().__init__(): a call, not a construction
    ("ctl.pick", "ctl.A", "direct", True),                   # A has no __init__: seen at the call instruction
    ("ctl.pick", "ctl.A.run", "direct", False),
    ("ctl.only_a", "ctl.A", "direct", True),
    ("ctl.only_a", "ctl.A.run", "direct", False),
}


@pytest.fixture(scope="module")
def trace(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("r1c132") / "trace.json"
    env = {**os.environ, "R1C132_PKG_ROOT": str(CONTROL / "ctl"), "R1C132_OUT": str(out),
           "PYTHONPATH": os.pathsep.join([str(HERE), str(CONTROL)]), "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "r1c132_tracer", "-p", "no:cacheprovider",
                        "tests"], cwd=CONTROL, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return out


def test_c1_the_tracer_attributes_calls_the_way_codemap_does(trace):
    from compare import via_name
    got = {(c, g, via_name(v), bool(v & 8)) for c, g, v, _ in json.loads(trace.read_text())["edges"]}
    assert got == EXPECTED, (sorted(got - EXPECTED), sorted(EXPECTED - got))


def _graph(tmp_path: Path, deep: bool) -> Path:
    from codemap import store
    from codemap.extract import extract
    g = extract(str(CONTROL / "ctl"), deep=deep)
    out = tmp_path / ("deep.json" if deep else "fast.json")
    store.save(g, str(out))
    return out


def test_c2_a_planted_false_edge_is_contradicted_and_an_unrun_site_is_not_judged(trace, tmp_path):
    from compare import compare
    path = _graph(tmp_path, deep=False)
    g = json.loads(path.read_text())
    for src, dst in (("ctl.only_a", "ctl.B.run"), ("ctl.never_called", "ctl.g")):
        g["edges"].append({"type": "calls", "source": src, "target": dst, "extras": {"resolution": "module"}})
    path.write_text(json.dumps(g))
    r = compare(str(path), str(trace), str(CONTROL))
    assert ["ctl.only_a", "ctl.B.run", "module"] in r["contradicted"]
    assert ["ctl.never_called", "ctl.g", "module"] not in r["contradicted"]   # its site never ran: not judged
    assert r["precision"]["outcomes"]["contradicted"] == 1


def test_c2b_on_the_control_package_codemap_is_judged_without_a_contradiction(trace, tmp_path):
    from compare import compare
    for deep in (False, True):
        r = compare(str(_graph(tmp_path, deep)), str(trace), str(CONTROL))
        assert r["contradicted"] == [], (deep, r["contradicted"])
        assert r["recall"]["explicit"]["pairs"] == 14    # 18 observed: minus the decorator, a pair seen two
                                                         # ways, two __init__ standing behind a construction
