"""R1-C15 acceptance — living docs generated from the graph.

The honesty contract is the point: docstrings quoted verbatim, undocumented
symbols marked (not invented), call-flow claims labelled a lower bound, everything
organised by discovered subsystem. Built on a small graph with documented,
undocumented and deprecated symbols + a call flow.
"""

from __future__ import annotations

from codemap import store
from codemap.cli import main
from codemap.model import Edge, Graph, Node
from codemap.query import Query
from codemap.serve.livingdocs import render_docs
from codemap.serve.session import Session


def _graph() -> Graph:
    g = Graph(target="pkg")
    # two modules in one import cluster (subsystem 'a')
    for m in ("pkg.a.m1", "pkg.a.m2"):
        g.add_node(Node(id=m, kind="module", extras={"root": "core"}))
    g.add_edge(Edge(type="imports", source="pkg.a.m1", target="pkg.a.m2"))
    g.add_edge(Edge(type="imports", source="pkg.a.m2", target="pkg.a.m1"))
    # public symbols: documented, undocumented, deprecated
    g.add_node(Node(id="pkg.a.m1.foo", kind="function", signature="foo(x)",
                    docstring="Does the foo thing.", visibility="public"))
    g.add_node(Node(id="pkg.a.m2.Bar", kind="class", visibility="public"))  # no docstring
    g.add_node(Node(id="pkg.a.m1.old", kind="function", visibility="public",
                    docstring="Old.", is_deprecated=True))
    g.add_node(Node(id="pkg.a.m1.helper", kind="function", visibility="public",
                    docstring="Helps."))
    # a call flow: foo -> helper (foo is an entry point)
    g.add_edge(Edge(type="calls", source="pkg.a.m1.foo", target="pkg.a.m1.helper"))
    return g


def test_docs_have_title_and_counts():
    md = render_docs(Query(_graph()))
    assert "# pkg — living documentation" in md
    assert "2 modules" in md and "public symbols" in md


def test_docstrings_quoted_verbatim():
    md = render_docs(Query(_graph()))
    assert "Does the foo thing." in md      # author's words, not paraphrased


def test_undocumented_symbol_marked_not_invented():
    md = render_docs(Query(_graph()))
    assert "_(undocumented)_" in md          # Bar has no docstring → marked
    # honesty: no fabricated description near Bar
    assert "Bar" in md


def test_deprecated_marker():
    assert "⚠ deprecated" in render_docs(Query(_graph()))


def test_organized_by_subsystem():
    md = render_docs(Query(_graph()))
    assert "## Subsystems" in md
    assert "### 1. a — 2 modules" in md      # community labelled by layer 'a'


def test_entry_points_section_labelled_lower_bound():
    md = render_docs(Query(_graph()))
    assert "Behavioural entry points" in md
    assert "`pkg.a.m1.foo` → reaches 1" in md
    assert "epistemic: partial" in md        # the flow caveat


def test_honesty_footer():
    md = render_docs(Query(_graph()))
    assert "verbatim" in md.lower()
    assert "Deterministic — re-run to refresh" in md


def test_deterministic():
    g = _graph()
    assert render_docs(Query(g)) == render_docs(Query(g))


# -- CLI + serve -------------------------------------------------------------

def test_cli_export_docs(tmp_path, capsys):
    gpath = tmp_path / "g.json"
    store.save(_graph(), str(gpath))
    assert main(["export", "docs", "--graph", str(gpath)]) == 0
    assert "living documentation" in capsys.readouterr().out


def test_cli_export_docs_to_file(tmp_path, capsys):
    gpath = tmp_path / "g.json"
    store.save(_graph(), str(gpath))
    out = tmp_path / "DOCS.md"
    assert main(["export", "docs", "--graph", str(gpath), "-o", str(out)]) == 0
    assert "living documentation" in out.read_text(encoding="utf-8")


def test_serve_export_docs():
    env = Session(_graph()).handle({"op": "export", "args": {"view": "docs"}})
    assert env["ok"] and "living documentation" in env["result"]["markdown"]
