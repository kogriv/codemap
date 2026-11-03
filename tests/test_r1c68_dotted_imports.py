"""R1-C68 — `import a.b.c` depends on `a.b.c`, not on `a`.

Found by the failed control of a probe (gap `contract_silent_passes_2026-11-03`): a contract
`forbidden core → analysis` answered "✅ satisfied" over `import pkg.analysis.b`, because the edge
went to the root package. griffe files a dotted import under its *bound name* (`{"pkg": "pkg"}`).

What is pinned (design `docs/design/dotted_imports.md`):

1. Every spelling of E1: the edge goes to the module named and only there (D1). A plain
   `import pkg` beside it keeps its own edge (D2).
2. Under `TYPE_CHECKING` no eager edge to the head is left behind. That was the second
   symptom of the same root, measured before the change.
3. The gate (E2) fails on the tree it used to pass.
4. A file whose *only* imports are at the top is still read. The file gate learnt the
   spelling (D3).

Each of the three pieces of the fix is reverted in a mutation test below, and a test goes red.
"""

from __future__ import annotations

import re
from unittest import mock

import pytest

from codemap import arch
from codemap.extract import extract
from codemap.extract import griffe_extractor as gx
from codemap.query import Query

B = "X = 1\n\n\ndef f():\n    return 1\n"


def _tree(tmp_path, core_a: str):
    pkg = tmp_path / "dpkg"
    for d in (pkg, pkg / "core", pkg / "analysis"):
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").write_text("")
    (pkg / "analysis" / "b.py").write_text(B)
    (pkg / "x.py").write_text("Y = 1\n")
    (pkg / "core" / "a.py").write_text(core_a)
    return pkg


def _edges(pkg) -> list[tuple[str, str]]:
    g = extract(str(pkg))
    return sorted((e.target, e.extras.get("scope", "module")) for e in g.edges
                  if e.type == "imports" and e.source == "dpkg.core.a")


@pytest.mark.parametrize("source, expected", [
    ("import dpkg.analysis.b\n", [("dpkg.analysis.b", "module")]),
    ("import dpkg.analysis\n", [("dpkg.analysis", "module")]),
    ("import dpkg.analysis.b, dpkg.x\n", [("dpkg.analysis.b", "module"), ("dpkg.x", "module")]),
    ("import dpkg\nimport dpkg.analysis.b\n", [("dpkg", "module"), ("dpkg.analysis.b", "module")]),
    ("def f():\n    import dpkg.analysis.b\n    return dpkg\n", [("dpkg.analysis.b", "function")]),
    ("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import dpkg.analysis.b\n",
     [("dpkg.analysis.b", "type_checking")]),
    ("try:\n    import dpkg.analysis.b\nexcept ImportError:\n    pass\n", [("dpkg.analysis.b", "module")]),
    ("import dpkg.analysis.b as bb\n", [("dpkg.analysis.b", "module")]),
], ids=["dotted", "package", "two-names", "plain-and-dotted", "function", "type-checking", "try", "as"])
def test_each_spelling_depends_on_the_module_it_names(tmp_path, source, expected):
    assert _edges(_tree(tmp_path, source)) == expected


def test_type_checking_leaves_no_eager_edge_to_the_head(tmp_path):
    """The second symptom: griffe filed the head `dpkg` as module-level beside our
    `type_checking` entry for the full name, and the demotion never met it."""
    edges = _edges(_tree(tmp_path, "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n"
                                   "    import dpkg.analysis.b\n"))
    assert ("dpkg", "module") not in edges


def test_the_gate_fails_on_the_tree_it_used_to_pass(tmp_path):
    """E2 — exactly the probe's control."""
    q = Query(extract(str(_tree(tmp_path, "import dpkg.analysis.b\n"))))
    contract = arch.parse_contract({"forbidden": [{"from": "core", "to": "analysis"}]})
    violations = arch.check_contract(q, contract)
    assert [v.edges for v in violations] == [(("dpkg.core.a", "dpkg.analysis.b"),)]


def test_external_dotted_imports_add_no_edge(tmp_path):
    """`import os.path` is outside the package: no edge before, none after."""
    assert _edges(_tree(tmp_path, "import os.path\nimport dpkg.x\n")) == [("dpkg.x", "module")]


# -- mutation: each piece of the fix, reverted, turns a test red --------------------------

def test_mutation_without_the_gate_a_top_level_only_file_is_not_read(tmp_path):
    """D3. The fixture has no indented import, so only the new gate lets it be parsed."""
    pkg = _tree(tmp_path, "import dpkg.analysis.b\n")
    with mock.patch.object(gx, "DOTTED_IMPORT_HINT", re.compile(r"(?!)")):
        assert _edges(pkg) != [("dpkg.analysis.b", "module")]
    assert _edges(pkg) == [("dpkg.analysis.b", "module")]


def test_mutation_without_the_head_suppression_the_root_edge_returns(tmp_path):
    """D2. Disable the drop list and griffe's bound-name entry comes back as `→ dpkg`."""
    pkg = _tree(tmp_path, "import dpkg.analysis.b\n")
    real = gx._source_import_targets

    def no_drop(module):
        out, eager, _ = real(module)
        return out, eager, set()

    with mock.patch.object(gx, "_source_import_targets", no_drop):
        assert ("dpkg", "module") in _edges(pkg)
    assert ("dpkg", "module") not in _edges(pkg)


def test_mutation_without_the_module_level_append_the_dependency_is_lost(tmp_path):
    """D1. Drop the full names the AST pass adds at module level, and the module is gone."""
    pkg = _tree(tmp_path, "import dpkg.analysis.b\n")
    real = gx._source_import_targets

    def no_append(module):
        out, eager, drop = real(module)
        return [(t, s) for t, s in out if s != "module"], eager, drop

    with mock.patch.object(gx, "_source_import_targets", no_append):
        assert ("dpkg.analysis.b", "module") not in _edges(pkg)
    assert ("dpkg.analysis.b", "module") in _edges(pkg)
