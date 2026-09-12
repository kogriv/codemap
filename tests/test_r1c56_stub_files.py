"""R1-C56 — a `.pyi` is a declaration Python never executes, and it said so nowhere.

Found by axis B4 (`gaps/third_shape_2026-09-12.md` §S1) on Pillow, where the package's
**only** hard import cycle was fabricated by a stub:

    PIL.ImageFont → PIL._imagingft → PIL.ImageFont

`ImageFont.py` really does import `_imagingft` at module level; the way back is the line
`from . import ImageFont` inside `_imagingft.pyi` — a file Python never runs, declaring a
module implemented in C. Nothing there can break on import, and the flagship number of the
project ("hard cycles: 1, and that one is actionable") was 100 % false positive.

One object had three answers in one tool: the extractor read stubs as modules (R1-C23), the
input manifest did not list them (so `scope_id`, `--incremental` and `watch` read as
unknown on any tree that ships stubs), and dead-code had a third rule for them. Design:
`docs/design/stub_files.md`.

The fixture below is that shape in miniature, and the file that carries it is the point:
put the same import in a `.py` and it is a real hard cycle — asserted here as the positive
control, so the fix cannot pass by demoting every import it sees.
"""

from __future__ import annotations

import pytest

from codemap import scope as scope_mod
from codemap.extract import extract
from codemap.query import Query
from codemap.serve.session import Session

# `runtime.py` imports the extension eagerly; the extension's *stub* names it back.
RUNTIME = '''from . import _ext


def go():
    return _ext.work()
'''
EXT_PYI = '''from . import runtime


def work() -> "runtime.Thing": ...
'''
# the same pair, written in code that actually executes
EAGER_A = '''from . import eager_b


def a():
    return eager_b.b()
'''
EAGER_B = '''from . import eager_a


def b():
    return eager_a.a()
'''


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    pkg = tmp_path_factory.mktemp("r1c56") / "stubpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "runtime.py").write_text(RUNTIME)
    (pkg / "_ext.pyi").write_text(EXT_PYI)
    (pkg / "eager_a.py").write_text(EAGER_A)
    (pkg / "eager_b.py").write_text(EAGER_B)
    g = extract(str(pkg))
    return pkg, g, Query(g)


def _edge(g, src, dst):
    e = [x for x in g.edges if x.type == "imports"
         and x.source.endswith("." + src) and x.target.endswith("." + dst)]
    assert len(e) == 1, (src, dst, e)
    return e[0]


# -- D1: the scope on the edge ---------------------------------------------------------

def test_an_import_written_in_a_stub_is_scope_stub(tree):
    _, g, _ = tree
    assert _edge(g, "_ext", "runtime").extras.get("scope") == "stub"


def test_the_import_of_the_stub_from_real_code_stays_eager(tree):
    """The other direction runs: `runtime.py` is executed like any module."""
    _, g, _ = tree
    assert _edge(g, "runtime", "_ext").extras.get("scope", "module") == "module"


def test_the_stub_module_is_still_in_the_graph(tree):
    """R1-C23 kept declarations rather than dropping them; this fix does not undo that."""
    _, g, _ = tree
    node = [n for n in g.nodes.values() if n.id.endswith("._ext")]
    assert len(node) == 1 and node[0].extras.get("stub") is True


# -- D2: which cycle class it lands in --------------------------------------------------

def test_a_stub_cannot_close_a_hard_import_cycle(tree):
    """The shape the fix exists to reject (R1-C37), in the words the report used to use."""
    _, _, q = tree
    hard = {frozenset(c) for c in q.import_cycles()}
    assert not any({"stubpkg.runtime", "stubpkg._ext"} == c for c in hard), \
        "a file Python never executes cannot break an import"


def test_it_lands_in_the_never_executes_class(tree):
    _, _, q = tree
    type_only = {frozenset(c) for c in q.type_only_import_cycles()}
    assert {"stubpkg.runtime", "stubpkg._ext"} in type_only
    assert not any({"stubpkg.runtime", "stubpkg._ext"} == frozenset(c)
                   for c in q.lazy_import_cycles()), "not runtime coupling either"


def test_the_positive_control_a_real_eager_cycle_is_still_hard(tree):
    """Same two-module shape written in `.py`: it must stay in the hard class, or the
    fix has bought its result by demoting everything."""
    _, _, q = tree
    hard = {frozenset(c) for c in q.import_cycles()}
    assert {"stubpkg.eager_a", "stubpkg.eager_b"} in hard


def test_import_map_carries_the_scope_always(tree):
    """R1-C28's rule applied to the fourth scope: a reader must not have to tell 'no stub
    imports here' from 'this build did not look'."""
    _, _, q = tree
    assert q.import_map()["stub"] == 1


def test_import_map_reports_zero_on_a_tree_without_stubs(tmp_path):
    pkg = tmp_path / "plainpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text("X = 1\n")
    q = Query(extract(str(pkg)))
    assert q.import_map()["stub"] == 0, "the key is present at zero, not absent"


# -- D3: the manifest -------------------------------------------------------------------

def test_the_manifest_includes_stubs(tree):
    pkg, _, _ = tree
    assert "*.pyi" in scope_mod.DEFAULT_INCLUDE
    resolved = scope_mod.resolve_scope(str(pkg.parent))
    paths = {f["path"] for f in resolved["files"]}
    assert any(p.endswith("_ext.pyi") for p in paths), \
        "a file the extractor reads must be in the manifest that identifies the input"


# -- D4: the answer says so -------------------------------------------------------------

def test_the_dossier_says_the_symbol_is_a_declaration(tree):
    _, g, _ = tree
    s = Session(g)
    match = s.handle({"op": "query", "args": {"name": "_ext"}})["result"]["matches"][0]
    assert match["stub"] is True, "the file extension is not an answer"


def test_a_plain_symbol_carries_no_stub_key(tree):
    """Absence means 'not a stub' — the same rule as the epistemic label (R1-C13)."""
    _, g, _ = tree
    s = Session(g)
    match = s.handle({"op": "query", "args": {"name": "go"}})["result"]["matches"][0]
    assert "stub" not in match
