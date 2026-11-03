"""R1-C71 — the fast tier follows a call through an attribute chain rooted at an import.

From the failed expectation E6 of R1-C68: `import pkg.analysis.b` + `pkg.analysis.b.f()` gave no edge,
while `from pkg.analysis import b` + `b.f()` did. Design `docs/design/attribute_chain_calls.md`.

Pinned: every C1 row (fast tier), the preserved `dynamic` answer for a chain that lands on no
definition, and three mutations (hop following, root equality, external chains). Each mutation turns
a test red.
"""

from __future__ import annotations

from unittest import mock

import pytest

from codemap.extract import behavior
from codemap.extract import extract

B = ("def f():\n    return 1\n\n\nclass K:\n    @staticmethod\n    def m():\n        return 2\n\n\n"
     "registry = {}\n")


def _build(tmp_path, imp: str, call: str, analysis_init: str = ""):
    pkg = tmp_path / "pkg"
    for d in (pkg, pkg / "core", pkg / "analysis"):
        d.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("def top():\n    return 0\n")
    (pkg / "core" / "__init__.py").write_text("")
    (pkg / "analysis" / "__init__.py").write_text(analysis_init)
    (pkg / "analysis" / "b.py").write_text(B)
    (pkg / "core" / "a.py").write_text(f"{imp}\n\n\ndef g():\n    return {call}\n")
    g = extract(str(pkg))
    edges = sorted(e.target for e in g.edges if e.type == "calls" and e.source == "pkg.core.a.g")
    counts = {k: v for k, v in g.nodes["pkg.core.a.g"].extras["calls"].items() if v and k != "out"}
    return edges, counts


ROWS = [
    ("dotted", "import pkg.analysis.b", "pkg.analysis.b.f()", "", ["pkg.analysis.b.f"], {"resolved": 1}),
    ("as", "import pkg.analysis as pa", "pa.b.f()", "", ["pkg.analysis.b.f"], {"resolved": 1}),
    ("from-module", "from pkg import analysis", "analysis.b.f()", "", ["pkg.analysis.b.f"], {"resolved": 1}),
    ("method", "import pkg.analysis.b", "pkg.analysis.b.K.m()", "", ["pkg.analysis.b.K.m"], {"resolved": 1}),
    ("object", "import pkg.analysis.b", "pkg.analysis.b.registry.get(1)", "", [], {"unresolved": 1}),
    ("object-dynamic", "import pkg.analysis.b", 'pkg.analysis.b.registry.get("k")', "", [], {"dynamic": 1}),
    ("reexport", "import pkg.analysis", "pkg.analysis.f()", "from .b import f\n", ["pkg.analysis.b.f"], {"resolved": 1}),
    ("root-chain", "import pkg", "pkg.analysis.b.f()", "", ["pkg.analysis.b.f"], {"resolved": 1}),
    ("root", "import pkg", "pkg.top()", "", ["pkg.top"], {"resolved": 1}),
    ("external", "import os.path", 'os.path.join("a")', "", [], {"external": 1}),
    ("control", "from pkg.analysis import b", "b.f()", "", ["pkg.analysis.b.f"], {"resolved": 1}),
]


@pytest.mark.parametrize("imp, call, init, edges, counts",
                         [r[1:] for r in ROWS], ids=[r[0] for r in ROWS])
def test_each_c1_row(tmp_path, imp, call, init, edges, counts):
    assert _build(tmp_path, imp, call, init) == (edges, counts)


# -- C7 mutation ------------------------------------------------------------------------

def test_mutation_without_hop_following_the_chain_is_lost(tmp_path):
    """D1. Make every hop answer "no definition here", and the dotted row loses its edge."""
    with mock.patch.object(behavior, "_follow_reexport", lambda t, r, n: t + ".__nowhere__"):
        assert _build(tmp_path / "m", "import pkg.analysis.b", "pkg.analysis.b.f()")[0] == []
    assert _build(tmp_path / "r", "import pkg.analysis.b", "pkg.analysis.b.f()")[0] == ["pkg.analysis.b.f"]


def test_mutation_without_root_equality_the_package_root_is_external(tmp_path):
    """D3. The old test, `startswith(pkg + ".")`, files `import pkg; pkg.top()` as external."""
    old = lambda target, modpath: target.startswith(modpath.split(".")[0] + ".")
    with mock.patch.object(behavior, "_is_internal", old):
        assert _build(tmp_path / "m", "import pkg", "pkg.top()") == ([], {"external": 1})
    assert _build(tmp_path / "r", "import pkg", "pkg.top()") == (["pkg.top"], {"resolved": 1})


def test_mutation_without_external_chains_they_read_unresolved(tmp_path):
    """D2. Without the chain walk, `os.path.join()` is "unresolved" — ignorance claimed where
    the tool knows the call leaves the package."""
    with mock.patch.object(behavior, "_attr_chain", lambda node: None):
        assert _build(tmp_path / "m", "import os.path", 'os.path.join("a")')[1] == {"unresolved": 1}
    assert _build(tmp_path / "r", "import os.path", 'os.path.join("a")')[1] == {"external": 1}
