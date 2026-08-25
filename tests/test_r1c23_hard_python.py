"""R1-C23 acceptance — robustness on hard Python (axis B2, design docs/design/hard_python_robustness.md).

A 17-file probe, one module per construct, built cleanly and printed **nothing**: exit 0,
no warning, no note. Most of "hard Python" came through honestly — metaclasses, a
`type()`-built class (recorded as an *attribute*, not invented as a class), PEP 562/695,
`match`, `async`, `singledispatch`, monkeypatching — and `dead-code high` was empty.

Five things did not, all silently:

- **D1** a directory symlink into its own ancestry: **615 modules from 15 real ones**,
  2378 nodes from 58, nested 40 deep — while `codemap scope` on the same tree answered
  `files: 17`. Two halves of the tool disagreeing 36× with nothing comparing them.
- **D2** a file with a syntax error or a non-UTF-8 byte simply disappeared.
- **D3** `from X import *` produced no `imports` edge at all.
- **D4** a *quoted* annotation was invisible — the idiom used precisely for types that
  would otherwise be a circular import.
- **D5** a stub-only `.pyi` module was presented as real code.

The hazardous inputs (a broken file, a latin-1 file, a recursive symlink) are built in a
temp copy rather than committed, so the repository stays sane; everything else lives in
`tests/fixtures/hardpkg`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from codemap import store
from codemap.diagnostics import (
    MODULE_COUNT_MISMATCH, UNREAD_INPUTS, diagnostics,
)
from codemap.extract import extract
from codemap.query import Query

FIX = Path(__file__).resolve().parent / "fixtures" / "hardpkg"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def g():
    return extract(FIX)


@pytest.fixture
def copy(tmp_path):
    """A writable copy of the fixture — the hazards get added to it, not to the repo."""
    dst = tmp_path / "hardpkg"
    shutil.copytree(FIX, dst)
    return dst


def _codes(graph):
    return {d["code"] for d in diagnostics(graph)}


# -- D1: a symlink cycle must not multiply the tree ------------------------------

def test_a_directory_symlink_cycle_does_not_inflate_the_graph(copy, g):
    """`loop -> .` used to yield 615 modules for 15. The same file read under a second
    name is the same file."""
    (copy / "loop").symlink_to(".", target_is_directory=True)
    looped = extract(copy)
    assert len(looped.nodes) == len(g.nodes)
    assert not [i for i in looped.nodes if ".loop" in i or i.endswith(".loop")]


def test_the_alias_is_recorded_not_merely_dropped(copy):
    """Silently dropping is how the original defect worked. Say what was skipped."""
    (copy / "loop").symlink_to(".", target_is_directory=True)
    aliased = extract(copy).provenance["inputs"]["aliased_modules"]
    assert aliased == [{"id": "hardpkg.loop", "same_as": "hardpkg"}]


def test_no_edge_points_at_a_node_that_was_never_added(copy):
    """The `contains` edge is emitted by the parent *before* the child is walked, so a
    skip in the wrong place leaves an edge dangling into nothing."""
    (copy / "loop").symlink_to(".", target_is_directory=True)
    graph = extract(copy)
    ids = set(graph.nodes)
    dangling = [(e.type, e.source, e.target) for e in graph.edges
                if e.source.startswith("hardpkg") and e.source not in ids]
    assert dangling == []


def test_a_symlink_to_a_real_sibling_is_still_followed(tmp_path):
    """The fix must not become "ignore symlinks" — a symlinked source tree is a
    legitimate layout, and dropping real code is the worse error."""
    src = tmp_path / "elsewhere"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "sub.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    link = tmp_path / "pkg"
    link.symlink_to(src, target_is_directory=True)
    # (the package takes its *real* directory's name — `build_structural` resolves the
    # path it is given, which is long-standing behaviour and not what is under test here)
    assert any(i.endswith(".sub") for i in extract(link).nodes)


# -- D2: an unreadable input is named, not dropped -------------------------------

def _with_broken_files(pkg: Path) -> Path:
    (pkg / "broken.py").write_text("def bad(:\n    return 2\n", encoding="utf-8")
    (pkg / "latin1.py").write_bytes(
        b'# -*- coding: latin-1 -*-\nNAME = "caf\xe9"\n')
    return pkg


def test_unreadable_files_are_reported_with_a_reason(copy):
    skipped = extract(_with_broken_files(copy)).provenance["inputs"]["skipped"]
    assert {(s["path"], s["reason"]) for s in skipped} == {
        ("hardpkg/broken.py", "syntax"), ("hardpkg/latin1.py", "encoding")}


def test_unreadable_files_raise_a_diagnostic(copy):
    """Same channel as every other build diagnostic, so CLI, `stats` and the three
    report headers all get it without knowing about this check."""
    assert UNREAD_INPUTS in _codes(extract(_with_broken_files(copy)))


def test_a_clean_tree_says_nothing(g):
    assert not _codes(g)


def test_the_build_command_names_them_on_stderr(copy, tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "codemap.cli", "build", str(_with_broken_files(copy)),
         "-o", str(tmp_path / "g.json")],
        capture_output=True, text=True, check=True, cwd=ROOT)
    assert "[warning]" in r.stderr and "broken.py" in r.stderr


# -- D3: `from X import *` is a dependency ---------------------------------------

def test_a_star_import_produces_an_import_edge(g):
    """The least explicit dependency in the language, and the one most worth seeing:
    without it the module cannot appear in a layer violation or an import cycle."""
    assert any(e.type == "imports" and e.source == "hardpkg.star"
               and e.target == "hardpkg.meta" for e in g.edges)


def test_the_explicit_import_beside_it_still_resolves(g):
    assert any(e.type == "imports" and e.source == "hardpkg.star"
               and e.target == "hardpkg.wrapped" for e in g.edges)


def test_an_external_star_import_invents_nothing(g):
    """`from os.path import *` is out of scope; no edge may be guessed for it."""
    assert not [e for e in g.edges
                if e.type == "imports" and e.source == "hardpkg.extstar"]


# -- D4: a quoted annotation is a reference too ----------------------------------

def test_a_string_annotation_resolves(g):
    """`def dump(o) -> "Base"` — the idiom for a type that would otherwise be a circular
    import, i.e. exactly the dependency worth seeing."""
    e = [e for e in g.edges if e.type == "references"
         and e.source == "hardpkg.condimport.dump" and e.target == "hardpkg.meta.Base"]
    assert e and e[0].extras["resolution"] == "annotation"


def test_the_unquoted_form_is_unchanged(g):
    assert [e for e in g.edges if e.type == "references"
            and e.source == "hardpkg.modern.fetch" and e.target == "hardpkg.modern.Reader"]


def test_a_string_that_is_not_a_type_expression_yields_nothing():
    from codemap.extract.behavior import _string_annotation_names
    assert _string_annotation_names("not a type ((") == []
    assert [n.id for n in _string_annotation_names("dict[str, Node]")] == \
        ["dict", "str", "Node"]


# -- D5: a stub is a declaration, not code ---------------------------------------

def test_stub_only_symbols_are_labelled(g):
    assert g.nodes["hardpkg.api"].extras["stub"] is True
    assert g.nodes["hardpkg.api.stub_only"].extras["stub"] is True


def test_a_real_module_is_not_labelled(g):
    assert "stub" not in g.nodes["hardpkg.meta"].extras


def test_a_stub_is_never_a_dead_code_candidate(g):
    """"Nothing calls it" says nothing about a symbol that has no body."""
    assert not [c for c in Query(g).dead_code() if c["id"].startswith("hardpkg.api")]


# -- D6: the conservation law over the build -------------------------------------

def test_modules_cannot_outnumber_their_input_files(g):
    """The backstop: it catches the symlink explosion without knowing what a symlink is,
    and would have fired on issue #5."""
    doctored = store.loads(store.dumps(g)) if hasattr(store, "loads") else extract(FIX)
    doctored.provenance = {**g.provenance, "inputs": {"python_files": 3}}
    d = [x for x in diagnostics(doctored) if x["code"] == MODULE_COUNT_MISMATCH]
    assert d and "cannot outnumber" in d[0]["message"]


def test_an_unexplained_shortfall_is_flagged(g):
    doctored = extract(FIX)
    doctored.provenance = {**g.provenance, "inputs": {"python_files": 400}}
    d = [x for x in diagnostics(doctored) if x["code"] == MODULE_COUNT_MISMATCH]
    assert d and "unexplained" in d[0]["message"]


def test_accounted_for_files_are_not_a_shortfall(copy):
    """Two unreadable files explain themselves — that is not a conservation failure."""
    assert MODULE_COUNT_MISMATCH not in _codes(extract(_with_broken_files(copy)))


@pytest.mark.parametrize("pkg", ["codemap"])
def test_the_check_is_silent_on_a_real_package(pkg):
    assert MODULE_COUNT_MISMATCH not in _codes(extract(ROOT / pkg))


# -- what already held: stated, so a regression is caught ------------------------

def test_a_dynamically_built_class_is_an_attribute_not_an_invented_class(g):
    """`Generated = type("Generated", …)` — honest: it is a value, and saying so beats
    inventing a class node that no source declares."""
    assert g.nodes["hardpkg.dynamic.Generated"].kind == "attribute"


@pytest.mark.parametrize("nid", [
    "hardpkg.meta.Meta", "hardpkg.meta.Impl",        # metaclass + __init_subclass__
    "hardpkg.pep695.Box", "hardpkg.pep695.identity",  # PEP 695 generics
    "hardpkg.modern.parse", "hardpkg.modern.fetch",   # match / async
    "hardpkg.wrapped.traced_target",                  # functools.wraps
])
def test_hard_constructs_still_extract(g, nid):
    assert nid in g.nodes


def test_no_false_dead_code_on_the_probe(g):
    """The probe is full of indirection; not one of it may be graded a confident death."""
    assert [c["id"] for c in Query(g).dead_code() if c["confidence"] == "high"] == []
