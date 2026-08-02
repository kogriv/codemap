"""R1-C1 acceptance — SCIP export.

codemap's graph is symbol-level (no call-site coordinates), so the faithful SCIP
export is *definitions + symbol information* (kind, docstring, inherits/implements
as relationships). These tests pin the symbol-string grammar, the kind mapping,
determinism, and protobuf round-trip on a hand-built graph, plus a real-extraction
integration test and an optional validation against the real `scip` CLI.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("google.protobuf")  # the optional `scip` extra

from codemap.extract import extract  # noqa: E402
from codemap.model import Edge, Graph, Node  # noqa: E402
from codemap.query import Query  # noqa: E402
from codemap.serve import _scip_pb2 as pb2  # noqa: E402
from codemap.serve.scip import build_scip, write_scip  # noqa: E402

CORE = Path(__file__).resolve().parent / "fixtures" / "reporoot" / "core"


@pytest.fixture(scope="module")
def tiny() -> Graph:
    """A minimal deterministic graph exercising every descriptor kind + a relationship."""
    g = Graph(target="pkg")
    g.add_node(Node(id="pkg", kind="module", file="pkg/__init__.py"))
    g.add_node(Node(id="pkg.mod", kind="module", file="pkg/mod.py"))
    g.add_node(Node(id="pkg.mod.Base", kind="class", file="pkg/mod.py",
                    lineno=1, endlineno=3, docstring="Base."))
    g.add_node(Node(id="pkg.mod.Derived", kind="class", file="pkg/mod.py",
                    lineno=5, endlineno=10))
    g.add_node(Node(id="pkg.mod.Derived.run", kind="function", file="pkg/mod.py",
                    lineno=6, endlineno=8))
    g.add_node(Node(id="pkg.mod.top_func", kind="function", file="pkg/mod.py",
                    lineno=12, endlineno=13))
    g.add_node(Node(id="pkg.CONST", kind="attribute", file="pkg/__init__.py",
                    lineno=2, endlineno=2))
    g.add_edge(Edge(type="inherits", source="pkg.mod.Derived", target="pkg.mod.Base"))
    return g


def _symbols(index) -> dict:
    return {s.symbol: s for d in index.documents for s in d.symbols}


# -- symbol-string grammar ----------------------------------------------------

def test_symbol_string_descriptors(tiny):
    idx = build_scip(Query(tiny), project_root="/x", package="pkg", version=".")
    syms = set(_symbols(idx))
    P = "codemap python pkg . "
    assert P + "pkg/mod/" in syms                      # module → namespace '/'
    assert P + "pkg/mod/Base#" in syms                 # class → type '#'
    assert P + "pkg/mod/Derived#run()." in syms        # method → '().'
    assert P + "pkg/mod/top_func()." in syms           # top-level function → '().'
    assert P + "pkg/CONST." in syms                    # attribute → term '.'


# -- kind mapping -------------------------------------------------------------

def test_kind_mapping(tiny):
    idx = build_scip(Query(tiny), project_root="/x", package="pkg", version=".")
    syms = _symbols(idx)
    K = pb2.SymbolInformation.Kind
    P = "codemap python pkg . "
    assert syms[P + "pkg/mod/"].kind == K.Module
    assert syms[P + "pkg/mod/Base#"].kind == K.Class
    assert syms[P + "pkg/mod/Derived#run()."].kind == K.Method        # parent is a class
    assert syms[P + "pkg/mod/top_func()."].kind == K.Function         # parent is a module
    assert syms[P + "pkg/CONST."].kind == K.Variable                  # module-level attr


# -- definitions, docs, relationships -----------------------------------------

def test_definition_occurrence_and_range(tiny):
    idx = build_scip(Query(tiny), project_root="/x", package="pkg", version=".")
    # every symbol has exactly one Definition occurrence
    occs = [o for d in idx.documents for o in d.occurrences]
    assert len(occs) == 7
    assert all(o.symbol_roles & pb2.SymbolRole.Definition for o in occs)
    # Base spans lines 1..3 → 0-based def line 0, enclosing end line 2
    base = next(o for o in occs if o.symbol.endswith("Base#"))
    assert base.single_line_range.line == 0
    assert base.multi_line_enclosing_range.end_line == 2


def test_docstring_and_relationship(tiny):
    idx = build_scip(Query(tiny), project_root="/x", package="pkg", version=".")
    syms = _symbols(idx)
    P = "codemap python pkg . "
    assert syms[P + "pkg/mod/Base#"].documentation == ["Base."]
    rels = syms[P + "pkg/mod/Derived#"].relationships
    assert len(rels) == 1
    assert rels[0].symbol == P + "pkg/mod/Base#"
    assert rels[0].is_implementation is True


# -- metadata -----------------------------------------------------------------

def test_metadata(tiny):
    idx = build_scip(Query(tiny), project_root="/data/proj", package="pkg",
                     version=".", tool_version="1.2.3")
    assert idx.metadata.tool_info.name == "codemap"
    assert idx.metadata.tool_info.version == "1.2.3"
    assert idx.metadata.project_root == "file:///data/proj"
    assert idx.metadata.text_document_encoding == pb2.TextEncoding.UTF8


# -- determinism + round-trip -------------------------------------------------

def test_deterministic_bytes(tiny):
    kw = dict(project_root="/x", package="pkg", version=".", tool_version="1")
    a = write_scip(build_scip(Query(tiny), **kw))
    b = write_scip(build_scip(Query(tiny), **kw))
    assert a == b


def test_protobuf_roundtrip(tiny):
    data = write_scip(build_scip(Query(tiny), project_root="/x", package="pkg", version="."))
    idx = pb2.Index()
    idx.ParseFromString(data)
    assert idx.SerializeToString(deterministic=True) == data


# -- real extraction ----------------------------------------------------------

def test_scip_from_real_extraction():
    g = extract(CORE)
    idx = build_scip(Query(g), project_root=str(CORE.parent), package="core", version=".")
    syms = set(_symbols(idx))
    assert any(s.endswith("Engine#") for s in syms)          # the core class is defined
    data = write_scip(idx)
    back = pb2.Index()
    back.ParseFromString(data)
    assert back.SerializeToString(deterministic=True) == data


# -- optional: validate against the real `scip` CLI ---------------------------

def test_scip_cli_parses(tiny, tmp_path):
    scip = shutil.which("scip")
    if not scip:
        pytest.skip("scip CLI not on PATH")
    out = tmp_path / "index.scip"
    out.write_bytes(write_scip(build_scip(Query(tiny), project_root=str(tmp_path),
                                          package="pkg", version=".")))
    res = subprocess.run([scip, "print", str(out)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert "Base#" in res.stdout  # the CLI decoded our symbols
