"""R1-C96 — `build` never imports the target; R1-C95 — it degrades instead of crashing on foreign trees.

Design `docs/design/build_on_foreign_trees.md` (pre-registered 45592b2).
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

from codemap.diagnostics import COMPILED_MODULES_NOT_LOADED, diagnostics
from codemap.extract.griffe_extractor import extract

MARKER_SRC = '''import pathlib
pathlib.Path({marker!r}).write_text("imported")


def f():
    return 1
'''
USER = "from pkg import evil\n\n\ndef use():\n    return evil.f()\n"


def _pkg(root: Path) -> Path:
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "user.py").write_text(USER)
    return pkg


# -- D1 + D2: a sourceless .pyc is neither imported nor lost in silence -------------------

@pytest.fixture
def pyc_tree(tmp_path):
    pkg = _pkg(tmp_path)
    marker = tmp_path / "MARKER"
    src = pkg / "evil.py"
    src.write_text(MARKER_SRC.format(marker=str(marker)))
    py_compile.compile(str(src), cfile=str(pkg / "evil.pyc"), doraise=True)  # this interpreter
    src.unlink()
    return pkg, marker


def test_E1_a_sourceless_pyc_is_not_imported(pyc_tree):
    pkg, marker = pyc_tree
    graph = extract(str(pkg))
    assert not marker.exists(), "codemap imported the target: the .pyc body ran"
    assert "pkg.user.use" in graph.nodes
    assert "pkg.evil" not in graph.nodes


def test_E2_it_is_listed_and_noted(pyc_tree):
    pkg, _ = pyc_tree
    graph = extract(str(pkg))
    assert graph.provenance["inputs"]["compiled"] == ["pkg/evil.pyc"]
    d = [x for x in diagnostics(graph) if x["code"] == COMPILED_MODULES_NOT_LOADED]
    assert len(d) == 1 and d[0]["severity"] == "note" and "pkg/evil.pyc" in d[0]["message"]


def test_E1_deep_tier_does_not_import_it_either(pyc_tree):
    pytest.importorskip("jedi")
    pkg, marker = pyc_tree
    extract(str(pkg), deep=True)
    assert not marker.exists()


def _compiler():
    cc = shutil.which("cc") or shutil.which("gcc")
    inc = sysconfig.get_paths().get("include")
    if not cc or not inc or not (Path(inc) / "Python.h").is_file():
        return None
    return cc, inc


@pytest.mark.skipif(_compiler() is None, reason="needs a C compiler and Python headers")
def test_E1_a_c_extension_is_not_imported(tmp_path):
    cc, inc = _compiler()
    pkg = _pkg(tmp_path)
    marker = tmp_path / "MARKER"
    c = tmp_path / "evil.c"
    c.write_text(
        "#include <Python.h>\n#include <stdio.h>\n"
        'static struct PyModuleDef m = {PyModuleDef_HEAD_INIT, "evil", NULL, -1, NULL};\n'
        "PyMODINIT_FUNC PyInit_evil(void){FILE*f=fopen(" + f'"{marker}"' + ',"w");'
        'if(f){fputs("imported",f);fclose(f);} return PyModule_Create(&m);}\n')
    so = pkg / f"evil{sysconfig.get_config_var('EXT_SUFFIX')}"
    subprocess.run([cc, "-shared", "-fPIC", f"-I{inc}", str(c), "-o", str(so)], check=True)
    graph = extract(str(pkg))
    assert not marker.exists(), "codemap imported the target: the extension's PyInit ran"
    assert graph.provenance["inputs"]["compiled"] == [f"pkg/{so.name}"]


# -- D2: a compiled copy beside its source -------------------------------------------------

@pytest.mark.parametrize("reverse", [False, True], ids=["py-first", "pyd-first"])
def test_E3_source_wins_over_a_compiled_copy_in_either_directory_order(tmp_path, monkeypatch,
                                                                         reverse):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "md.py").write_text("def helper():\n    return 1\n\n\ndef f():\n    return helper()\n")
    (pkg / "md.cp38-win32.pyd").write_bytes(b"MZ\x90\x00\x03\xffnot text")
    real_walk = os.walk

    def walk(top, *a, **k):  # griffe's finder discovers submodules in os.walk order
        for root, dirs, files in real_walk(top, *a, **k):
            yield root, dirs, sorted(files, key=lambda n: n.endswith(".py"), reverse=not reverse)

    monkeypatch.setattr(os, "walk", walk)
    graph = extract(str(pkg))
    assert {"pkg.md.helper", "pkg.md.f"} <= set(graph.nodes)
    assert ("calls", "pkg.md.f", "pkg.md.helper") in {(e.type, e.source, e.target) for e in graph.edges}
    assert "compiled" not in graph.provenance["inputs"]


# -- D3: a base class behind an unresolvable alias ----------------------------------------

def test_E4_a_base_reexported_from_an_absent_package_does_not_crash(tmp_path):
    pkg = tmp_path / "pkg"
    (pkg / "utils").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "utils" / "__init__.py").write_text("")
    (pkg / "utils" / "file_io.py").write_text("from extlib.common.file_io import PathHandler\n")
    (pkg / "user.py").write_text("from pkg.utils.file_io import PathHandler\n\n\n"
                                 "class Mine(PathHandler):\n    def go(self):\n"
                                 "        return self.other()\n\n    def own(self):\n"
                                 "        return self.go()\n")
    graph = extract(str(pkg))
    assert "pkg.user.Mine.go" in graph.nodes
    calls = {(e.source, e.target) for e in graph.edges if e.type == "calls"}
    assert not any(s == "pkg.user.Mine.go" for s, _ in calls), "self.other() resolves to nothing"
    assert ("pkg.user.Mine.own", "pkg.user.Mine.go") in calls, "the rest of the class resolves"


# -- D4: the refusal names both shapes ----------------------------------------------------

def test_E5_the_refusal_names_the_script_layout_too(tmp_path):
    facade = tmp_path / "facade"
    facade.mkdir()
    (facade / "__init__.py").write_text("from impl.core import field\n\n__all__ = ['field']\n")
    (facade / "__init__.pyi").write_text(
        "from typing import overload\n\nfrom impl.core import field as field\n\n"
        "@overload\ndef field(name: str) -> str: ...\n@overload\ndef field(name: int) -> int: ...\n")
    with pytest.raises(ValueError) as exc:
        extract(str(facade))
    msg = str(exc.value)
    assert "facade layout" in msg and "sys.path" in msg and "R1-C94" in msg


def test_the_cli_build_exits_zero_and_prints_the_note(pyc_tree, tmp_path, capsys, monkeypatch):
    from codemap.cli import main
    pkg, marker = pyc_tree
    monkeypatch.chdir(pkg.parent)
    assert main(["build", "pkg", "-o", str(tmp_path / "g.json")]) == 0
    err = capsys.readouterr().err
    assert "[note] 1 compiled module(s) without source were not loaded: pkg/evil.pyc" in err
    assert not marker.exists()
    assert sys.modules.get("pkg.evil") is None


def test_orphan_pyc_in_pycache_is_not_listed(tmp_path):
    """A cache of a deleted module is not a module (asked by bquearch, 2026-11-10): Python does
    not import a sourceless `.pyc` from `__pycache__`, and listing it would be noise."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "live.py").write_text("def f():\n    return 1\n")
    gone = pkg / "gone.py"
    gone.write_text("X = 1\n")
    py_compile.compile(str(gone), doraise=True)    # -> pkg/__pycache__/gone.cpython-XY.pyc
    py_compile.compile(str(pkg / "live.py"), doraise=True)
    gone.unlink()
    assert any((pkg / "__pycache__").glob("gone.*.pyc"))
    graph = extract(str(pkg))
    assert "compiled" not in graph.provenance["inputs"]
    assert not [d for d in diagnostics(graph) if d["code"] == COMPILED_MODULES_NOT_LOADED]
    assert "pkg.gone" not in graph.nodes and "pkg.live.f" in graph.nodes
