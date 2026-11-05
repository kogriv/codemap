"""R1-C77 — the gate probe battery: the questions asked of import-linter, asked of `codemap check`.

Design `docs/design/gate_probe_battery.md` (predictions pre-registered in 312c104). One fixture, `gp` with
layers `high > mid > low`; every probe is a fresh copy with one change. A probe whose answer is a defect is
`xfail(strict=True)` against the *right* answer, with the number of its fix, so fixing it turns this red
until the mark comes off.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from codemap.cli import main

LAYERS = '[architecture]\nlayers = ["high", "mid", "low"]\n'
UP = "from gp.high import h\n"


@pytest.fixture(scope="module")
def base(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("r1c77") / "proj"
    gp = root / "gp"
    for d in ("", "high", "mid", "low"):
        (gp / d).mkdir(parents=True, exist_ok=True)
        (gp / d / "__init__.py").write_text("")
    (gp / "high" / "h.py").write_text("from gp.mid import m\n\nclass X:\n    pass\n")
    (gp / "mid" / "m.py").write_text("from gp.low import l\n")
    (gp / "low" / "l.py").write_text("Y = 1\n")
    (root / "codemap.toml").write_text(LAYERS)
    return root


def _copy(base: Path, tmp_path: Path) -> Path:
    dst = tmp_path / "proj"
    shutil.copytree(base, dst)
    return dst


def _run(root: Path, capsys, *extra) -> tuple[int, str]:
    rc = main(["check", "--build", str(root / "gp"), "--root", str(root), *extra])
    return rc, capsys.readouterr().out


# -- import shapes: the change is in gp/low/l.py unless the probe says otherwise -------------------

SHAPES = {
    "P0": ("low/l.py", UP),
    "P1": ("low/l.py", "def f():\n    from gp.high import h\n    return h\n"),
    "P2": ("low/l.py", "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from gp.high import h\n"),
    "P3": ("low/l.py", "import gp.high.h\n"),
    "P4": ("low/__init__.py", "from ..high import h\n"),
    "P5": ("low/l.py", "from gp import high\n"),
    "P6": ("low/l.py", "from .. import high\n"),
    "P7": ("low/l.py", "import gp.high.h as hh\n"),
    "P8": ("low/l.py", "from gp.high.h import *\n"),
    "P9": ("low/l.py", "try:\n    from gp.high import h\nexcept ImportError:\n    h = None\n"),
    "P10": ("low/l.py", "class K:\n    from gp.high import h\n"),
    "P11": ("low/l.py", "import sys\nif sys.version_info >= (3, 8):\n    from gp.high import h\n"),
    "P12": ("low/l.py", "class K:\n    def m(self):\n        def inner():\n"
                        "            from gp.high import h\n            return h\n        return inner\n"),
    "P13": ("low/l.py", "import gp.high\n\ndef f():\n    return gp.high.h.X\n"),
}


def test_P0c_control_clean_tree_is_satisfied(base, tmp_path, capsys):
    rc, out = _run(_copy(base, tmp_path), capsys)
    assert rc == 0 and "Contract satisfied" in out, out


@pytest.mark.parametrize("probe", sorted(SHAPES, key=lambda p: int(p[1:])))
def test_an_upward_import_is_caught_in_every_shape(base, tmp_path, capsys, probe):
    root = _copy(base, tmp_path)
    rel, src = SHAPES[probe]
    (root / "gp" / rel).write_text(src)
    rc, out = _run(root, capsys)
    assert rc == 2, f"{probe}: {out}"
    # Which edge, not only whether (the C11 lesson): from gp.low, into gp.high.
    assert "`layered`" in out and "- `gp.low" in out and "` → `gp.high" in out, f"{probe}: {out}"


def test_P14_a_dynamic_import_is_a_documented_limit(base, tmp_path, capsys):
    root = _copy(base, tmp_path)
    (root / "gp" / "low" / "l.py").write_text('import importlib\nh = importlib.import_module("gp.high.h")\n')
    rc, out = _run(root, capsys)
    assert rc == 0, out          # a static tool cannot see it; import-linter is blind to it too


# -- contract shapes -------------------------------------------------------------------------------

def _with(base, tmp_path, toml: str, src: str | None = UP, rel: str = "low/l.py") -> Path:
    root = _copy(base, tmp_path)
    (root / "codemap.toml").write_text(toml)
    if src is not None:
        (root / "gp" / rel).write_text(src)
    return root


REFUSED = {
    "C1": (LAYERS + "exhaustiv = true\n", ["unknown key `exhaustiv`", "did you mean `exhaustive`"]),
    "C3": ('[architecture]\nforbidden = [{from = "low", too = "high"}]\n', ["unknown key(s) `too`", "missing `to`"]),
    "C6": (LAYERS + 'exhaustive = "maybe"\n', ["`exhaustive` must be true or false"]),
    "C8": ('[architectur]\nlayers = ["high", "mid", "low"]\n', ["`[architectur]`"]),
    "C9": ('[architecture]\nforbidden = {from = "low", to = "high"}\n', ["`forbidden` must be a list"]),
    "C10": ('[architecture]\nLayers = ["high", "mid", "low"]\n', ["unknown key `Layers`", "did you mean `layers`"]),
    "C15": ('[architecture]\nforbidden = [{from = "low", to = "high", indirect = true}]\n', ["unknown key(s) `indirect`"]),
}


@pytest.mark.parametrize("probe", sorted(REFUSED, key=lambda p: int(p[1:])))
def test_a_malformed_contract_is_refused(base, tmp_path, capsys, probe):
    toml, heard = REFUSED[probe]
    rc, out = _run(_with(base, tmp_path, toml), capsys)
    assert rc == 2 and "nothing was enforced" in out, f"{probe}: {out}"
    for line in heard:
        assert line in out, f"{probe}: {line!r} not in {out}"


def test_C2_exhaustive_names_an_undeclared_layer(base, tmp_path, capsys):
    root = _with(base, tmp_path, LAYERS + "exhaustive = true\n", src=None)
    (root / "gp" / "extra").mkdir()
    (root / "gp" / "extra" / "__init__.py").write_text("")
    rc, out = _run(root, capsys)
    assert rc == 2 and "`exhaustive`" in out and "- extra" in out, out


def test_C4_a_misspelled_forbidden_layer_is_inert_and_disclosed(base, tmp_path, capsys):
    toml = '[architecture]\nforbidden = [{from = "low", to = "hihg"}]\n'
    rc, out = _run(_with(base, tmp_path, toml), capsys)
    assert rc == 0, out                                     # R1-C62: inert by design ...
    assert "forbidden (1 declared, 0 applicable)" in out and "`hihg`" in out, out   # ... and said


def test_C4b_no_phantom_rules_makes_it_a_failure(base, tmp_path, capsys):
    toml = '[architecture]\nforbidden = [{from = "low", to = "hihg"}]\nno_phantom_rules = true\n'
    rc, out = _run(_with(base, tmp_path, toml), capsys)
    assert rc == 2 and "`no_phantom_rules`" in out and "hihg" in out, out


def test_C5_a_misspelled_layer_is_inert_and_disclosed(base, tmp_path, capsys):
    toml = '[architecture]\nlayers = ["hihg", "mid", "low"]\n'
    rc, out = _run(_with(base, tmp_path, toml), capsys)
    assert rc == 0, out
    assert "layered (3 declared, 2 applicable)" in out and "`hihg`" in out, out


def test_C7_no_contract_passes_unless_required(base, tmp_path, capsys):
    root = _copy(base, tmp_path)
    (root / "codemap.toml").unlink()
    (root / "gp" / "low" / "l.py").write_text(UP)
    rc, out = _run(root, capsys)
    assert rc == 0 and "No `[architecture]` contract found" in out, out
    with pytest.raises(SystemExit, match="no \\[architecture\\] contract found"):
        _run(root, capsys, "--require-contract")


def test_C11_a_repeated_layer_is_refused(base, tmp_path, capsys):
    # R1-C79. First run (73a757e): exit 2, but for the wrong edge. The second `high` overwrote the first in
    # `rank`, the legal `gp.high.h → gp.mid.m` was named as the violation and the real upward
    # `gp.mid.m → gp.high.h` was not. An exit-code-only assertion passed on it.
    toml = '[architecture]\nlayers = ["high", "mid", "high", "low"]\n'
    rc, out = _run(_with(base, tmp_path, toml, src="from gp.high import h\n", rel="mid/m.py"), capsys)
    assert rc == 2 and "nothing was enforced" in out and "`layers` repeats `high`" in out, out


def test_C12_an_empty_layers_list(base, tmp_path, capsys):
    rc, out = _run(_with(base, tmp_path, "[architecture]\nlayers = []\n"), capsys)
    assert rc == 0 and "No `[architecture]` contract found" in out, out


def test_C13_a_same_layer_forbidden_item_is_refused(base, tmp_path, capsys):
    rc, out = _run(_with(base, tmp_path, '[architecture]\nforbidden = [{from = "low", to = "low"}]\n',
                         src=None), capsys)
    assert rc == 2 and "`from` and `to` are both `low`" in out, out


def test_C14_an_independent_group_naming_one_layer_twice_is_refused(base, tmp_path, capsys):
    rc, out = _run(_with(base, tmp_path, '[architecture]\nindependent = [["low", "low"]]\n', src=None), capsys)
    assert rc == 2 and "`independent[0]` repeats `low`" in out, out


# -- graph and invocation --------------------------------------------------------------------------

def test_G1_a_stale_graph_fails_unless_allowed(base, tmp_path, capsys):
    root = _copy(base, tmp_path)
    graph = tmp_path / "g.json"
    assert main(["build", str(root / "gp"), "--out", str(graph)]) == 0
    capsys.readouterr()
    (root / "gp" / "low" / "l.py").write_text(UP)
    rc = main(["check", "--graph", str(graph), "--root", str(root)])
    out = capsys.readouterr().out
    assert rc == 2 and "behind its source tree" in out, out
    rc = main(["check", "--graph", str(graph), "--root", str(root), "--allow-stale"])
    out = capsys.readouterr().out
    assert rc == 0 and "behind its source tree" in out, out          # G1b


def test_G2_a_build_path_that_does_not_exist(tmp_path, capsys):
    missing = tmp_path / "nope"
    try:
        rc = main(["check", "--build", str(missing), "--root", str(tmp_path)])
    except SystemExit as e:
        rc = e.code
    captured = capsys.readouterr()
    assert rc not in (0, None), captured
    assert "nope" in (captured.out + captured.err + str(rc)), captured


def test_G3_a_root_without_a_contract_names_where_it_looked(base, tmp_path, capsys):
    root = _copy(base, tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    rc = main(["check", "--build", str(root / "gp"), "--root", str(elsewhere)])
    out = capsys.readouterr().out
    assert rc == 0 and str(elsewhere.resolve() / "codemap.toml") in out, out
