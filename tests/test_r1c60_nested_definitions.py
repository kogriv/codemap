"""R1-C60 — nested definitions are not nodes, and no answer said so.

Measured by an independent AST scan on the `rag_for_git` scope (`bquant@cb89a24`, package +
four consumer roots, `--mode full`): **49** definitions nested in a function body inside the
package, **0** of them nodes under any name; **35** in the consumer roots, **35 of 35** nodes
(`outer.inner`). The package is read by griffe, which does not enter function bodies; consumer
roots are read by codemap's own AST scanner, which does. One shape of code, two answers, in
one graph — and `dead-code` silent about the half it cannot judge. A decorator defined inside
a registering method is the ordinary shape of a plugin registry.

This item **declares** the narrowing; it does not emit the nodes (an owner's decision — it
changes graph content for every consumer). So the guard holds both sides of the declaration:
the text must say it, and the fact it says must still be true. Design:
`docs/design/nested_definitions.md`.
"""

from __future__ import annotations

import pytest

from codemap.extract import extract, extract_repo
from codemap.model import Node
from codemap.query import Query
from codemap.serve.audit import build_dead_code, render_dead_code

PKG = {
    "__init__.py": "",
    "reg.py": ("class Registry:\n"
               "    def register(self, name):\n"
               "        def decorator(cls):\n"
               "            return cls\n"
               "        return decorator\n\n\n"
               "def _build():\n"
               "    class _Local:\n"
               "        def go(self):\n"
               "            return 1\n"
               "    def _inner():\n"
               "        return _Local().go()\n"
               "    return _inner()\n"),
}
NESTED_IN_PACKAGE = ("pkg.reg.Registry.register.decorator", "pkg.reg._build._Local",
                     "pkg.reg._build._Local.go", "pkg.reg._build._inner")
CONSUMER = ("def test_it():\n"
            "    def _local_helper():\n"
            "        return 1\n"
            "    assert _local_helper() == 1\n")
NESTED_IN_CONSUMER = ("tests.test_reg.test_it._local_helper",)

DECLARATION = "definitions nested inside a function body (not nodes, so never judged)"


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    base = tmp_path_factory.mktemp("r1c60")
    (base / "pkg").mkdir()
    (base / "tests").mkdir()
    for rel, body in PKG.items():
        (base / "pkg" / rel).write_text(body)
    (base / "tests" / "test_reg.py").write_text(CONSUMER)
    return base


def _absent_by_any_name(graph, qualified: str) -> bool:
    """Not under its dotted id, not as `<locals>`, not as any id ending in its own name path."""
    tail = qualified.split(".", 2)[-1]                    # drop `pkg.reg.` / `tests.test_reg.`
    return not any(nid == qualified or "<locals>" in nid or nid.endswith("." + tail)
                   for nid in graph.nodes)


# -- the fact the declaration states --------------------------------------------------------

def test_package_nested_definitions_are_not_nodes(tree):
    graph = extract(str(tree / "pkg"))
    for q in NESTED_IN_PACKAGE:
        assert _absent_by_any_name(graph, q), (
            f"{q} is now a node — the narrowing R1-C60 declares is no longer true. Update the "
            "dead-code blind-spot line and docs/dead-code.md, or this is a regression.")


def test_consumer_nested_definitions_are_nodes_in_full_mode(tree):
    """The other half of the asymmetry the docs state: per root, not per graph."""
    graph = extract_repo(str(tree / "pkg"), consumers=(str(tree / "tests"),), mode="full")
    for q in NESTED_IN_CONSUMER:
        assert q in graph.nodes


def test_the_absence_check_is_shown_what_it_must_reject(tree):
    """R1-C37: the probe above, fed a graph where the nested node exists, must say so."""
    graph = extract(str(tree / "pkg"))
    q = NESTED_IN_PACKAGE[0]
    graph.add_node(Node(id=q, kind="function"))
    assert not _absent_by_any_name(graph, q)


# -- the declaration in the answer whose silence it was --------------------------------------

def test_dead_code_names_the_blind_spot(tree):
    md = render_dead_code(Query(extract(str(tree / "pkg"))))
    header = md.splitlines()[2]
    assert DECLARATION in header, header
    assert header.startswith("_Static heuristics only") and "**Candidates, not proof.**" in header


def test_the_nested_private_helper_is_not_a_candidate_it_is_unjudged(tree):
    """What the declaration is about: `_inner` is private and only called from its parent,
    and it is in no list at all — neither dead nor alive."""
    dead = build_dead_code(Query(extract(str(tree / "pkg"))))
    ids = {c["id"] for c in dead["candidates"]}
    assert not any("_inner" in i or "_Local" in i for i in ids)
    assert "pkg.reg._build" in ids                       # its parent is judged as usual


def test_the_structured_answer_does_not_change_shape(tree):
    """Declaration-only: no field was added (that would be an ANSWER_FORMAT bump)."""
    dead = build_dead_code(Query(extract(str(tree / "pkg"))))
    assert set(dead) == {"kind", "target", "orphan_modules", "candidates", "totals",
                         "shadowed", "whitelist", "min_confidence", "diagnostics"}
