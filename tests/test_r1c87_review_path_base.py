"""R1-C87 — a diff path is placed in the graph by a unique suffix, or named as not placed.

Design `docs/design/review_path_base.md` (pre-registered 0dba940).
"""

from __future__ import annotations

from codemap import store
from codemap.cli import main
from codemap.extract import extract, extract_repo
from codemap.query import Query
from codemap.serve.review import build_review, parse_unified_diff, render_review

MOD = "X = 1\n\n\ndef f():\n    return X\n\n\ndef g():\n    return 2\n"


def _hunk(path, line=5, old="    return X", new="    return X + 1"):
    return f"--- a/{path}\n+++ b/{path}\n@@ -{line},1 +{line},1 @@\n-{old}\n+{new}\n"


def _pkg(root, name="pkg", files=None):
    d = root / name
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("")
    for rel, body in (files or {"m.py": MOD}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return d


def test_E1_diff_longer_than_the_graph_path(tmp_path):
    # graph built from research/: files "pkg/m.py"; diff from the repo root: "research/pkg/m.py"
    q = Query(extract(str(_pkg(tmp_path / "research"))))
    rv = build_review(q, hunks=parse_unified_diff(_hunk("research/pkg/m.py")))
    assert [d["symbol"] for d in rv["changed"]] == ["pkg.m.f"]
    assert rv["summary"]["mapped_paths"] == {"research/pkg/m.py": "pkg/m.py"}
    assert rv["summary"]["unplaced_files"] == []


def test_E2_graph_longer_than_the_diff_path(tmp_path):
    core = _pkg(tmp_path / "research")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_m.py").write_text("from pkg.m import f\n\n\ndef test_f():\n    f()\n")
    q = Query(extract_repo(str(core), consumers=(str(tests),), mode="full"))
    assert any(n.file == "research/pkg/m.py" for n in q.graph.nodes.values())
    rv = build_review(q, hunks=parse_unified_diff(_hunk("pkg/m.py")))
    assert [d["symbol"] for d in rv["changed"]] == ["pkg.m.f"]
    assert rv["summary"]["mapped_paths"] == {"pkg/m.py": "research/pkg/m.py"}


def test_E3_an_ambiguous_suffix_is_named_not_chosen(tmp_path):
    q = Query(extract(str(_pkg(tmp_path, files={"a/m.py": MOD, "b/m.py": MOD,
                                                "a/__init__.py": "", "b/__init__.py": ""}))))
    rv = build_review(q, hunks=parse_unified_diff(_hunk("m.py")))
    assert rv["changed"] == []
    (u,) = rv["summary"]["unplaced_files"]
    assert u["file"] == "m.py" and u["candidates"] == ["pkg/a/m.py", "pkg/b/m.py"]
    assert "ambiguous: pkg/a/m.py, pkg/b/m.py" in render_review(q, hunks=parse_unified_diff(_hunk("m.py")))


def _graph_file(tmp_path):
    q = Query(extract(str(_pkg(tmp_path / "research"))))
    g = tmp_path / "g.json"
    store.save(q.graph, str(g))
    return g


def test_E4_nothing_placed_is_a_refusal_partial_is_a_warning(tmp_path, capsys):
    g = _graph_file(tmp_path)
    d = tmp_path / "d.diff"
    d.write_text(_hunk("elsewhere/other.py"))
    assert main(["review", str(d), "--graph", str(g)]) == 2
    cap = capsys.readouterr()
    assert "none of the 1 Python file(s) in the diff is in this graph" in cap.err
    assert "elsewhere/other.py" in cap.out
    d.write_text(_hunk("elsewhere/other.py") + _hunk("research/pkg/m.py"))
    assert main(["review", str(d), "--graph", str(g)]) == 0
    out = capsys.readouterr().out
    assert "**1 Python file(s) in the diff are not in this graph" in out
    assert "pkg.m.f" in out


def test_E5_a_module_level_line_names_the_module_an_unplaced_file_is_not_unresolved(tmp_path):
    # As pre-registered, E5 expected the module-level hunk in `unresolved_hunks`. It never was:
    # a module-level line names the module (M15 fallback; R1-C82 D2 dossier). What E5 guards
    # is the other half: a file not in the graph is reported as unplaced, not as unresolved.
    q = Query(extract(str(_pkg(tmp_path))))
    diff = _hunk("pkg/m.py", line=2, old="", new="import os") + _hunk("nowhere/z.py")
    rv = build_review(q, hunks=parse_unified_diff(diff))
    assert [d["symbol"] for d in rv["changed"]] == ["pkg.m"]
    assert rv["summary"]["unresolved_hunks"] == []
    assert [u["file"] for u in rv["summary"]["unplaced_files"]] == ["nowhere/z.py"]


def test_E6_an_exact_diff_renders_as_before(tmp_path):
    q = Query(extract(str(_pkg(tmp_path))))
    md = render_review(q, hunks=parse_unified_diff(_hunk("pkg/m.py")))
    assert "placed in the graph by suffix" not in md and "not in this graph" not in md
    assert build_review(q, hunks=parse_unified_diff(_hunk("pkg/m.py")))["summary"]["mapped_paths"] == {}


def test_E7_only_non_python_files(tmp_path, capsys):
    g = _graph_file(tmp_path)
    d = tmp_path / "d.diff"
    d.write_text(_hunk("README.md", line=1, old="a", new="b"))
    assert main(["review", str(d), "--graph", str(g)]) == 0
    out = capsys.readouterr().out
    assert "1 non-Python file(s) in the diff" in out and "not in this graph" not in out
