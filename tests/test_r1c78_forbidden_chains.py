"""R1-C78 — `forbidden` with `indirect = true`: no chain of imports from one layer to another.

Design `docs/design/forbidden_chains.md` (acceptance pre-registered in 312c104, oracle in e466ee1).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codemap import arch
from codemap.cli import main
from codemap.extract import extract, extract_repo
from codemap.query import Query
from codemap.serve.check import build_check

CHAIN = '[architecture]\nforbidden = [{from = "data", to = "analysis", indirect = true}]\n'
DIRECT = '[architecture]\nforbidden = [{from = "data", to = "analysis"}]\n'


def _pkg(root: Path, files: dict[str, str]) -> Path:
    pkg = root / "pkg"
    for rel, src in {"__init__.py": "", **files}.items():
        p = pkg / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        for parent in p.relative_to(pkg).parents:
            init = pkg / parent / "__init__.py"
            if not init.exists():
                init.write_text("")
        p.write_text(src)
    return pkg


def _check(tmp_path: Path, files: dict[str, str], toml: str, capsys) -> tuple[int, str]:
    pkg = _pkg(tmp_path, files)
    (tmp_path / "codemap.toml").write_text(toml)
    rc = main(["check", "--build", str(pkg), "--root", str(tmp_path)])
    return rc, capsys.readouterr().out


BASE = {
    "data/d.py": "from pkg.core import c\n",
    "core/c.py": "from pkg.analysis import a\n",
    "analysis/a.py": "X = 1\n",
}


def test_A1_a_two_hop_chain_breaks_an_indirect_item_and_not_a_direct_one(tmp_path, capsys):
    rc, out = _check(tmp_path, BASE, CHAIN, capsys)
    assert rc == 2, out
    assert "`data` must not reach `analysis`, directly or through other modules: 1 module(s)" in out
    assert "- `pkg.core.c` → `pkg.analysis.a`" in out                       # the entry edge
    assert "- `pkg.data.d` → `pkg.core.c` → `pkg.analysis.a`" in out        # its witness
    rc, out = _check(tmp_path, BASE, DIRECT, capsys)
    assert rc == 0 and "forbidden (1)" in out, out                           # direct: unchanged


@pytest.mark.parametrize("middle", [
    "def f():\n    from pkg.analysis import a\n    return a\n",
    "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from pkg.analysis import a\n",
], ids=["function-local", "type-checking"])
def test_A2_every_import_scope_carries_a_chain(tmp_path, capsys, middle):
    rc, out = _check(tmp_path, {**BASE, "core/c.py": middle}, CHAIN, capsys)
    assert rc == 2 and "`pkg.data.d` → `pkg.core.c` → `pkg.analysis.a`" in out, out


def test_A3_a_chain_through_an_undeclared_layer(tmp_path, capsys):
    files = {"data/d.py": "from pkg.utils import u\n", "utils/u.py": "from pkg.analysis import a\n",
             "analysis/a.py": "X = 1\n"}
    toml = '[architecture]\nlayers = ["analysis", "data"]\n' + CHAIN.split("\n", 1)[1]
    rc, out = _check(tmp_path, files, toml, capsys)
    assert rc == 2, out
    assert "`layered`" not in out                                     # the stack alone sees nothing
    assert "`pkg.data.d` → `pkg.utils.u` → `pkg.analysis.a`" in out, out


def test_A4_a_consumer_root_does_not_create_a_chain(tmp_path):
    # Vacuous by construction, and asserted as such: codemap's graph has no edge from core into a
    # consumer root (even `import helper` with `tests/helper.py` present is not resolved), so no
    # chain can pass through one and the `root_of == "core"` filter in `_forbidden_chain` is
    # defensive. What is pinned here is the property the filter relies on.
    pkg = _pkg(tmp_path, {"data/d.py": "import helper\n", "analysis/a.py": "Y = 1\n"})
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "helper.py").write_text("from pkg.analysis import a\n")
    (tests / "test_x.py").write_text("from pkg.data import d\nfrom pkg.analysis import a\n")
    (tmp_path / "codemap.toml").write_text(CHAIN)
    q = Query(extract_repo(str(pkg), consumers=(str(tests),), mode="full"))
    ig = q.import_graph
    assert any(q.root_of(u) != "core" for u, _ in ig.edges())               # consumers are in the graph
    assert not any(q.root_of(u) == "core" and q.root_of(v) != "core" for u, v in ig.edges())
    assert arch.check_contract(q, arch.load_contract(tmp_path)) == []


def test_A5_the_shortest_then_smallest_witness_and_a_stable_answer(tmp_path, capsys):
    files = {
        "data/a.py": "from pkg.core import z\n",              # data.a → core.z → core.m → analysis.t (3)
        "data/b.py": "from pkg.core import y\n",              # data.b → core.y → core.m → analysis.t (3)
        "data/c.py": "from pkg.core import m\n",              # data.c → core.m → analysis.t (2) ← shortest
        "core/z.py": "from pkg.core import m\n",
        "core/y.py": "from pkg.core import m\n",
        "core/m.py": "from pkg.analysis import t\n",
        "analysis/t.py": "T = 1\n",
    }
    rc, out = _check(tmp_path, files, CHAIN, capsys)
    assert rc == 2 and "3 module(s) of `data` reach it" in out, out
    assert "- `pkg.data.c` → `pkg.core.m` → `pkg.analysis.t`" in out, out
    files2 = {**files, "data/c.py": "X = 1\n"}                 # two chains of 3: a < b
    rc, out1 = _check(tmp_path, files2, CHAIN, capsys)
    assert "- `pkg.data.a` → `pkg.core.z` → `pkg.core.m` → `pkg.analysis.t`" in out1, out1
    rc, out2 = _check(tmp_path, files2, CHAIN, capsys)
    assert out1 == out2


@pytest.mark.parametrize("value, rc_want", [('"yes"', 2), ("false", 0)])
def test_A6_indirect_is_a_boolean(tmp_path, capsys, value, rc_want):
    toml = f'[architecture]\nforbidden = [{{from = "data", to = "analysis", indirect = {value}}}]\n'
    rc, out = _check(tmp_path, BASE, toml, capsys)
    assert rc == rc_want, out
    if rc_want == 2:
        assert "`forbidden[0]`: `indirect` must be true or false" in out
    else:
        assert "forbidden (1)" in out                       # false is the same as absent


def test_the_structured_answer_carries_entry_edges_and_witnesses(tmp_path):
    pkg = _pkg(tmp_path, BASE)
    (tmp_path / "codemap.toml").write_text(CHAIN)
    c = arch.load_contract(tmp_path)
    q = Query(extract(str(pkg)))
    payload = build_check(q, c, arch.check_contract(q, c))
    (v,) = payload["violations"]
    assert payload["ok"] is False and v["rule"] == "forbidden"
    assert v["edges"] == [["pkg.core.c", "pkg.analysis.a"]]
    assert v["modules"] == ["`pkg.data.d` → `pkg.core.c` → `pkg.analysis.a`"]
    json.dumps(payload)
