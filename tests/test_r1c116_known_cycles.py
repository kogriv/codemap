"""R1-C116 — the cycle ratchet: known cycles by their modules, a new or grown one fails `check`.

Expectations E1–E6 are in BACKLOG.md (R1-C116), written before the code. The fixture has the shape of a
consumer's verified case: a known pair that grew into four modules, two unlisted pairs, a listed triple, and a
cycle closed only under TYPE_CHECKING.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

from codemap import arch
from codemap.cli import main
from codemap.extract import extract
from codemap.query import Query
from codemap.serve.check import build_check, render_check

LAZY = "def f():\n    from pkg import {0}\n    return {0}\n"
EAGER = "import pkg.{0}\n"
TREE = {
    "pkg/__init__.py": "",
    # the known pair (x, y), grown: x → y (eager), y ⇢ z, z → w, w ⇢ x
    "pkg/x.py": EAGER.format("y"), "pkg/y.py": LAZY.format("z"),
    "pkg/z.py": EAGER.format("w"), "pkg/w.py": LAZY.format("x"),
    # two pairs nobody listed
    "pkg/c.py": EAGER.format("d"), "pkg/d.py": LAZY.format("c"),
    "pkg/e.py": EAGER.format("f"), "pkg/f.py": LAZY.format("e"),
    # the listed triple
    "pkg/t1.py": EAGER.format("t2"), "pkg/t2.py": EAGER.format("t3"), "pkg/t3.py": LAZY.format("t1"),
    # closed only under TYPE_CHECKING
    "pkg/g.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from pkg import h\n",
    "pkg/h.py": EAGER.format("g"),
}
KNOWN = '''[architecture]
known_lazy_cycles = [
  ["pkg.x", "pkg.y"],
  ["pkg.t1", "pkg.t2", "pkg.t3"],
]
known_type_only_cycles = [
  ["pkg.g", "pkg.h"],
]
'''


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return root


def _q(root: Path) -> Query:
    return Query(extract(str(root / "pkg")))


def _contract(text: str) -> arch.ArchitectureContract:
    return arch.parse_contract(tomllib.loads(text).get("architecture", {}))


def test_e1_known_pass_new_and_grown_fail(tmp_path):
    root = _tree(tmp_path, TREE)
    q, c = _q(root), _contract(KNOWN)
    vs = arch.check_contract(q, c)
    assert [v.rule for v in vs] == ["no_lazy_cycles"]
    lines = vs[0].modules
    assert vs[0].summary.startswith("3 new tangle(s)")
    grown = [ln for ln in lines if "pkg.w" in ln]
    assert len(grown) == 1 and "grew from the known (pkg.x, pkg.y)" in grown[0]
    assert sum("pkg.c" in ln for ln in lines) == 1 and sum("pkg.e" in ln for ln in lines) == 1
    assert not any("pkg.t1" in ln for ln in lines)          # the listed triple passes
    md = render_check(q, c, vs)
    assert "no_lazy_cycles" in md


def test_e2_e3_after_the_ratchet_green_then_a_new_cycle_red(tmp_path):
    root = _tree(tmp_path, TREE)
    (root / "codemap.toml").write_text("[architecture]\nno_lazy_cycles = false\n")
    graph = root / "g.json"
    subprocess.run([sys.executable, "-m", "codemap", "build", "pkg", "-o", str(graph)], cwd=root, check=True,
                   capture_output=True)
    assert main(["devkit", "ratchet", "--root", str(root), "--graph", str(graph), "--cycles"]) == 0
    text = (root / "codemap.toml").read_text()
    assert "# >>> codemap-devkit cycles v" in text
    c = arch.load_contract(root)
    assert c.error is None and c.no_lazy_cycles and len(c.known_lazy_cycles) == 4
    q = _q(root)
    assert arch.check_contract(q, c) == []                                   # E2
    assert "no_lazy_cycles (4 known)" in render_check(q, c, [])
    _tree(root, {"pkg/m.py": EAGER.format("n"), "pkg/n.py": LAZY.format("m")})   # E3: a new pair
    vs = arch.check_contract(_q(root), c)
    lazy = [v for v in vs if v.rule == "no_lazy_cycles"]
    assert len(lazy) == 1 and "1 new tangle(s)" in lazy[0].summary


def test_e4_a_broken_cycle_is_a_note_and_tighten_removes_it(tmp_path):
    root = _tree(tmp_path, TREE)
    (root / "codemap.toml").write_text("[architecture]\n")
    graph = root / "g.json"

    def build():
        subprocess.run([sys.executable, "-m", "codemap", "build", "pkg", "-o", str(graph)], cwd=root,
                       check=True, capture_output=True)
    build()
    assert main(["devkit", "ratchet", "--root", str(root), "--graph", str(graph), "--cycles"]) == 0
    (root / "pkg/d.py").write_text("def f():\n    return 1\n")               # the (c, d) cycle is gone
    c, q = arch.load_contract(root), _q(root)
    assert arch.check_contract(q, c) == []
    md = render_check(q, c, [])
    assert "1 known cycle group(s) no longer hold a tangle" in md and "pkg.c, pkg.d" in md
    assert build_check(q, c, [])["known_stale"] == {"known_lazy_cycles": [["pkg.c", "pkg.d"]]}
    build()
    assert main(["devkit", "ratchet", "--root", str(root), "--graph", str(graph), "--tighten"]) == 0
    c = arch.load_contract(root)
    assert frozenset({"pkg.c", "pkg.d"}) not in c.known_lazy_cycles and len(c.known_lazy_cycles) == 3


def test_e4b_a_split_cycle_stays_known(tmp_path):
    root = _tree(tmp_path, TREE)
    c = _contract('[architecture]\nknown_lazy_cycles = [["pkg.c", "pkg.d", "pkg.e", "pkg.f", '
                  '"pkg.x", "pkg.y", "pkg.z", "pkg.w", "pkg.t1", "pkg.t2", "pkg.t3"]]\n')
    assert arch.check_contract(_q(root), c) == []   # four tangles, each inside the one listed group


def test_e5_the_schema_names_each_bad_list():
    for body, expect in [
        ('known_lazy_cycles = [["pkg.a"]]', "`known_lazy_cycles[0]` must be a list of at least 2"),
        ('known_lazy_cycles = [["pkg.a", "pkg.b", "pkg.a"]]', "`known_lazy_cycles[0]` repeats `pkg.a`"),
        ('known_type_only_cycles = [["a", "b"], ["b", "a"]]', "`known_type_only_cycles[1]` repeats an earlier"),
        ('known_lazy_cycles = "pkg.a"', "`known_lazy_cycles` must be a list of lists"),
        ('known_lazy_cyles = []', "did you mean `known_lazy_cycles`"),
    ]:
        c = _contract("[architecture]\n" + body + "\n")
        assert c.error and expect in c.error, (body, c.error)


def test_e6_without_the_new_keys_nothing_changes(tmp_path):
    root = _tree(tmp_path, TREE)
    q = _q(root)
    c = _contract("[architecture]\nno_lazy_cycles = true\nno_type_only_cycles = true\n")
    vs = arch.check_contract(q, c)
    assert [v.rule for v in vs] == ["no_lazy_cycles", "no_type_only_cycles"]
    assert vs[0].summary.startswith("4 tangle(s)") and "new" not in vs[0].summary
    assert not any("grew from" in m for v in vs for m in v.modules)
    out = build_check(q, c, vs)
    assert "known_stale" not in out


def test_a_list_alone_is_a_contract_and_names_its_gate(tmp_path):
    root = _tree(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "x = 1\n"})
    q = _q(root)
    for key, rule in (("known_lazy_cycles", "no_lazy_cycles"), ("known_type_only_cycles", "no_type_only_cycles")):
        c = _contract(f"[architecture]\n{key} = []\n")
        assert not c.is_empty() and c.error is None
        md = render_check(q, c, arch.check_contract(q, c))
        assert f"Rules enforced: {rule} (0 known)." in md, md
