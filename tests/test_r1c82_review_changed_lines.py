"""R1-C82 — `review` reads changed lines, not hunks; a module constant has readers.

Design `docs/design/review_changed_lines.md` (pre-registered ab16f1e).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.extract import extract
from codemap.query import Query
from codemap.serve.review import build_review, parse_unified_diff, render_review

CONTRACTS = (
    "import os\n"                                   # 1
    "\n"                                            # 2
    "NAMES = (\"a\", \"b\")\n"                      # 3
    "# the surfaces\n"                              # 4
    "LIMIT = 3\n"                                   # 5
    "\n"                                            # 6
    "\n"                                            # 7
    "class Spec:\n"                                 # 8
    "    def check(self, x):\n"                     # 9
    "        return x in NAMES\n"                   # 10
    "\n"                                            # 11
    "\n"                                            # 12
    "def use():\n"                                  # 13
    "    return LIMIT + 1\n"                        # 14
    "\n"                                            # 15
    "\n"                                            # 16
    "def caller_a():\n"                             # 17
    "    return use() + use()\n"                    # 18
)
GATES = (
    "from pkg.contracts import NAMES\n"
    "from pkg import contracts\n\n\n"
    "def gate(x):\n    return x in NAMES\n\n\n"
    "def other():\n    return contracts.LIMIT\n\n\n"
    "def shadow(NAMES):\n    return NAMES\n\n\n"
    "def rebound():\n    NAMES = ()\n    return NAMES\n\n\n"
    "def uses_spec():\n    return contracts.use()\n"
)


@pytest.fixture(scope="module")
def q(tmp_path_factory) -> Query:
    root = tmp_path_factory.mktemp("r1c82")
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "contracts.py").write_text(CONTRACTS)
    (root / "pkg" / "gates.py").write_text(GATES)
    return Query(extract(str(root / "pkg")))


def _diff(start_old, lines, file="pkg/contracts.py"):
    """A unified diff hunk; ``lines`` are body lines with their tag."""
    old_n = sum(1 for ln in lines if ln[0] in " -")
    new_n = sum(1 for ln in lines if ln[0] in " +")
    return (f"--- a/{file}\n+++ b/{file}\n@@ -{start_old},{old_n} +{start_old},{new_n} @@\n"
            + "\n".join(lines) + "\n")


ONE_CONSTANT = _diff(1, [" import os", " ", "-NAMES = (\"a\",)", "+NAMES = (\"a\", \"b\")",
                         " # the surfaces", " LIMIT = 3", " "])


def _accesses(q):
    return {(e.source, e.target, e.extras.get("resolution")) for e in q.graph.edges if e.type == "accesses"}


# -- D1: changed lines only ---------------------------------------------------

def test_D1_context_lines_are_not_changes():
    assert parse_unified_diff(ONE_CONSTANT) == [
        {"file": "pkg/contracts.py", "ranges": [[3, 3]], "soft": []}]


def test_D1_a_pure_deletion_anchors_where_it_stood():
    d = _diff(13, [" def use():", "-    x = 1", "     return LIMIT + 1"])
    assert parse_unified_diff(d)[0]["ranges"] == [[14, 14]]


def test_D1_a_removed_line_that_looks_like_a_header_is_still_a_body_line():
    d = _diff(9, ["     def check(self, x):", "--- not a header", "         return x in NAMES"])
    assert parse_unified_diff(d)[0]["ranges"] == [[10, 10]]


def test_E1_one_constant_one_symbol(q):
    rv = build_review(q, hunks=parse_unified_diff(ONE_CONSTANT))
    assert [d["symbol"] for d in rv["changed"]] == ["pkg.contracts.NAMES"]
    assert rv["summary"]["unresolved_hunks"] == []


# -- D1b: a comment between definitions is not a module change ----------------

def test_E4_a_comment_line_outside_definitions_names_nothing(q):
    d = _diff(3, [" NAMES = (\"a\", \"b\")", "-# the surfaces", "+# the surfaces, renamed", " LIMIT = 3"])
    rv = build_review(q, hunks=parse_unified_diff(d))
    assert rv["changed"] == [] and rv["summary"]["unresolved_hunks"] == []


def test_D1b_a_comment_inside_a_definition_still_names_it(q):
    d = _diff(13, [" def use():", "+    # why", "     return LIMIT + 1"])
    rv = build_review(q, hunks=parse_unified_diff(d))
    assert [x["symbol"] for x in rv["changed"]] == ["pkg.contracts.use"]


# -- D2: a module dossier is about the module ---------------------------------

def test_E4_an_import_line_gives_the_module_without_a_call_site_contract(q):
    d = _diff(1, ["-import os", "+import sys", " ", " NAMES = (\"a\", \"b\")"])
    rv = build_review(q, hunks=parse_unified_diff(d))
    (dossier,) = rv["changed"]
    assert dossier["symbol"] == "pkg.contracts" and dossier["module_level"] is True
    assert dossier["call_contract"] == [] and dossier["callers"] == []
    # direct references to the module only: gates imports it — not the members' callers
    assert dossier["consumers_by_root"] == {"core": 1}
    md = render_review(q, hunks=parse_unified_diff(d))
    assert "Module-level code changed" in md and "check on signature change" not in md


# -- D3: bare-name reads of a module attribute --------------------------------

def test_E3_bare_name_reads_are_accesses(q):
    es = _accesses(q)
    assert ("pkg.gates.gate", "pkg.contracts.NAMES", "name") in es          # imported name
    assert ("pkg.contracts.Spec.check", "pkg.contracts.NAMES", "name") in es  # same module
    assert ("pkg.contracts.use", "pkg.contracts.LIMIT", "name") in es
    assert ("pkg.gates.other", "pkg.contracts.LIMIT", "class") in es         # unchanged form


def test_E3_a_local_binding_shadows(q):
    srcs = {s for s, t, _ in _accesses(q) if t == "pkg.contracts.NAMES"}
    assert "pkg.gates.shadow" not in srcs and "pkg.gates.rebound" not in srcs


def test_E2_the_constant_dossier_names_its_readers(q):
    rv = build_review(q, hunks=parse_unified_diff(ONE_CONSTANT))
    (d,) = rv["changed"]
    assert d["consumers_by_root"] == {"core": 2}       # gate, Spec.check
    assert d["risk"] != "low"


def test_D3_a_function_is_not_an_attribute(q):
    # `use()` called by bare name stays in the calls layer
    assert not any(t == "pkg.contracts.use" for _, t, _ in _accesses(q))
