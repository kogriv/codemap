"""R1-C89 — `review` names the doc pages a diff changes, and what they document.

Design `docs/design/review_docs.md` (pre-registered 10a1867).
"""

from __future__ import annotations

import pytest

from codemap.extract import extract_repo
from codemap.query import Query
from codemap.serve.review import build_review, parse_unified_diff, render_review

MOD = "def f():\n    return 1\n\n\ndef g():\n    return f()\n"
PAGE = "# Using f\n\nCall `pkg.m.f` to get one.\n\nMore prose here.\n"


@pytest.fixture(scope="module")
def q(tmp_path_factory):
    root = tmp_path_factory.mktemp("r1c89")
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "m.py").write_text(MOD)
    (root / "docs").mkdir()
    (root / "docs" / "p.md").write_text(PAGE)
    (root / "docs" / "prose.md").write_text("# Nothing about code\n\nJust words.\n")
    return Query(extract_repo(str(root / "pkg"), docs=(str(root / "docs"),), mode="full"))


def _hunk(path, line, old, new):
    return f"--- a/{path}\n+++ b/{path}\n@@ -{line},1 +{line},1 @@\n-{old}\n+{new}\n"


PAGE_DIFF = _hunk("docs/p.md", 3, "Call `pkg.m.f` to get one.", "Call `pkg.m.f` to get exactly one.")
CODE_DIFF = _hunk("pkg/m.py", 2, "    return 1", "    return 2")


def test_E2_a_doc_page_diff_names_the_page_and_what_it_documents(q):
    rv = build_review(q, hunks=parse_unified_diff(PAGE_DIFF))
    assert rv["changed"] == []
    assert rv["changed_docs"] == [{"doc": "docs/p.md", "file": "docs/p.md", "documents": ["pkg.m.f"]}]
    assert rv["summary"]["changed_docs"] == 1
    assert rv["summary"]["unresolved_hunks"] == []


def test_D2_the_markdown_says_so(q):
    md = render_review(q, hunks=parse_unified_diff(PAGE_DIFF))
    assert "**1 changed doc page(s)** — check they still describe the code:" in md
    assert "- `docs/p.md` documents pkg.m.f" in md
    assert "Unresolved hunks" not in md


def test_E3_code_and_docs_together(q):
    code_only = build_review(q, hunks=parse_unified_diff(CODE_DIFF))
    both = build_review(q, hunks=parse_unified_diff(CODE_DIFF + PAGE_DIFF))
    assert both["changed"] == code_only["changed"]
    assert [d["doc"] for d in both["changed_docs"]] == ["docs/p.md"]
    assert "docs/p.md" not in both["summary"]["high_risk"]


def test_D2_a_page_that_names_no_code_is_not_a_node_and_stays_skipped(q):
    rv = build_review(q, hunks=parse_unified_diff(_hunk("docs/prose.md", 3, "Just words.", "Only words.")))
    assert rv["changed_docs"] == [] and rv["summary"]["skipped_files"] == ["docs/prose.md"]
