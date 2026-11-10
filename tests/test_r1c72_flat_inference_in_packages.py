"""R1-C72 — the flat-layout inference stays out of a package whose twins are stdlib names.

From the R1-C71 reconciliation: pytest 9.1.1 had 65 edges labelled `resolution: "flat"`
(`import warnings` → `_pytest.warnings`, `_pytest.doctest → _pytest.doctest`) in a packaged layout.
Design `docs/design/flat_inference_in_packages.md` (D1 revised before acceptance).

Pinned:
- a packaged tree with a stdlib twin gets no edge, and its call counts as external;
- with evidence of a flat directory (a bare sibling import that cannot be stdlib) the twin is
  rewritten, because a sibling shadows the stdlib there;
- a self-import is no evidence;
- the mixed R1-C21 fixture is covered by its own tests;
- two mutations, each turning a test red.
"""

from __future__ import annotations

import sys
from unittest import mock

from codemap.extract import extract
from codemap.extract import griffe_extractor as gx
from codemap.extract import gsource


def _tree(tmp_path, files: dict[str, str]):
    pkg = tmp_path / "tpkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    for name, body in files.items():
        (pkg / f"{name}.py").write_text(body)
    return extract(str(pkg))


def _imports(g, src):
    return {e.target: e.extras for e in g.edges if e.type == "imports" and e.source == src}


A = "import logging\n\n\ndef g():\n    return logging.getLogger(__name__)\n"
TWIN = "def getLogger(name):\n    return name\n"


def test_a_packaged_tree_keeps_the_stdlib_twin_out(tmp_path):
    """F3 row 1: `pkg/b.py` imports `pkg` by name; `import logging` is the standard library."""
    g = _tree(tmp_path, {"logging": TWIN, "a": A, "b": "from tpkg import a\n"})
    assert "tpkg.logging" not in _imports(g, "tpkg.a")
    assert g.nodes["tpkg.a.g"].extras["calls"].get("external") == 1
    assert not [e for e in g.edges if e.type == "calls" and e.target == "tpkg.logging.getLogger"]


def test_without_any_evidence_the_twin_is_the_stdlib_too(tmp_path):
    """F3 row 2 *as pre-registered* expected a flat edge here; under D1-revised there is no
    evidence of a flat directory (the only bare import is a stdlib name), so there is none."""
    g = _tree(tmp_path, {"logging": TWIN, "a": A})
    assert "tpkg.logging" not in _imports(g, "tpkg.a")


def test_with_evidence_of_a_flat_directory_the_sibling_shadows_the_stdlib(tmp_path):
    """`import a` in b.py can only be a sibling, so the directory is on sys.path, and there
    `import logging` in a.py reaches tpkg/logging.py — the shadowing is real, and kept."""
    g = _tree(tmp_path, {"logging": TWIN, "a": A, "b": "import a\n"})
    assert _imports(g, "tpkg.a").get("tpkg.logging") == {"resolution": "flat"}
    assert _imports(g, "tpkg.b").get("tpkg.a") == {"resolution": "flat"}


def test_a_self_import_is_no_evidence(tmp_path):
    """bquant's `indicators/library/talib.py` imports `talib` (the third-party library):
    a module importing its own bare name proves nothing about sys.path."""
    g = _tree(tmp_path, {"talib": "import talib\n\n\ndef f():\n    return talib.SMA(1)\n",
                         "logging": TWIN, "a": A})
    assert "tpkg.logging" not in _imports(g, "tpkg.a")
    assert g.nodes["tpkg.talib.f"].extras["calls"].get("external") == 1


def test_the_stdlib_list_is_what_decides():
    assert "logging" in sys.stdlib_module_names and "warnings" in sys.stdlib_module_names


# -- mutation ---------------------------------------------------------------------------

def test_mutation_without_the_stdlib_exclusion_the_twin_is_rewritten_again(tmp_path):
    """Evidence forced to "found": the R1-C21 rule as it was, and the false edge returns."""
    with mock.patch.object(gx.sys, "stdlib_module_names", frozenset()):
        g = _tree(tmp_path / "m", {"logging": TWIN, "a": A, "b": "from tpkg import a\n"})
    assert _imports(g, "tpkg.a").get("tpkg.logging") == {"resolution": "flat"}
    g = _tree(tmp_path / "r", {"logging": TWIN, "a": A, "b": "from tpkg import a\n"})
    assert "tpkg.logging" not in _imports(g, "tpkg.a")


def test_mutation_without_the_import_map_gate_the_call_is_internal_again(tmp_path):
    """D2: with the import map ungated, `logging.getLogger()` is rewritten into the package
    even though no flat edge was emitted, and it stops counting as external."""
    with mock.patch("codemap.extract.gsource.flat_inference_applies", lambda g, p: True):
        g = _tree(tmp_path / "m", {"logging": TWIN, "a": A, "b": "from tpkg import a\n"})
    assert g.nodes["tpkg.a.g"].extras["calls"].get("external", 0) == 0
    assert [e.target for e in g.edges if e.type == "calls" and e.source == "tpkg.a.g"] == \
        ["tpkg.logging.getLogger"], "the false edge into the twin"
    g = _tree(tmp_path / "r", {"logging": TWIN, "a": A, "b": "from tpkg import a\n"})
    assert g.nodes["tpkg.a.g"].extras["calls"].get("external") == 1
