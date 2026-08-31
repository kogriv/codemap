"""R1-C37 — every contract rule, fed the thing it must react to, on a real tree.

The method is the lab's, not ours. Sent a `no_lazy_cycles` gate that answered green on
their repository, they did not believe the green: they put **one** lazy import back and
watched the gate go red. That is the only evidence a gate is doing anything, and after
running it on our two trees the obvious question was which of the six rules had ever been
given the same treatment.

Answer: as end-to-end paths, none. Each rule does have a violation test
(`test_r1c3_arch_contract.py`), and each is built on a hand-assembled three-node `Graph`
whose layers are spelled into the node ids and whose `root` is set by hand. That proves
the rule's arithmetic. It cannot show that a rule finds a real violation in a real graph,
because nothing between source and rule participates: no extraction, no layer inference
from a package tree, no re-exports, no lazy edges, no thousands of legitimate imports for
the offending one to hide among. The dogfood test (`test_r1c3_dogfood.py`) runs the real
tree — and asserts green, which is the shape of evidence the lab correctly refused.

So: one copy of codemap's own package, and for each rule, green → change exactly one line
→ red naming the edge that was added → restore → the file is byte-identical again. The
contract in each case holds **only the rule under test**, so nothing else can fire and be
mistaken for it. Mutation 1 also creates a cycle, for instance; under a layers-only
contract that cannot be confused with a layering violation.

Cost is about 20 s: seven extractions of a 90-file package. That is the price of testing
the path that runs in production instead of the arithmetic underneath it.
"""

from __future__ import annotations

import shutil

import pytest

from codemap.arch import check_contract, parse_contract
from codemap.extract import extract
from codemap.query import Query

# Every top-level component of codemap that exists today. `exhaustive` is about a *new*
# one appearing, so the baseline has to name all of them or it is red before we start.
# A topological order of codemap's *real* cross-layer imports, not the shipped contract's
# ten-layer view: `codemap.toml` names the layers a reader should think in, and leaves the
# six leaf modules undeclared (harmless — an undeclared layer is inert unless `exhaustive`).
# Here every component must be named, or the baseline is red before a mutation is applied
# and the mutation proves nothing. The baseline assertion in each test guards this list:
# if it goes stale, the failure says so rather than passing quietly.
REAL_LAYERS = ["cli", "incremental", "extract", "serve", "apidiff", "arch", "diagnostics",
               "freshness", "integrations", "provenance", "query", "store", "model",
               "tomlio", "watch", "scope"]

SRC = __import__("pathlib").Path(__file__).resolve().parent.parent / "codemap"


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    """One copy of the real package. Mutations are applied and reverted in place."""
    dst = tmp_path_factory.mktemp("mutation") / "codemap"
    shutil.copytree(SRC, dst)
    return dst


@pytest.fixture(scope="module")
def baseline(tree):
    """The unmutated graph — every `green →` half of the six checks below."""
    return Query(extract(str(tree)))


def _check(q, rules: dict):
    return check_contract(q, parse_contract(rules))


def _mutate(tree, rel: str, line: str) -> tuple[str, str]:
    """Append one import line to a real module. Returns (path, original text)."""
    path = tree / rel
    original = path.read_text()
    path.write_text(original + f"\n\n{line}\n")
    return str(path), original


def _restore(path: str, original: str) -> None:
    __import__("pathlib").Path(path).write_text(original)


def _run(tree, rel, line, rules):
    """green → mutate → measure → restore → byte-identical. Returns the violations."""
    path, original = _mutate(tree, rel, line)
    try:
        return check_contract(Query(extract(str(tree))), parse_contract(rules))
    finally:
        _restore(path, original)
        assert (tree / rel).read_text() == original


# -- one rule per mutation, each with a contract holding only that rule ------

def test_layers_catches_an_import_up_the_stack(tree, baseline):
    rules = {"layers": REAL_LAYERS}
    assert _check(baseline, rules) == [], "baseline must be green or the mutation proves nothing"
    v = _run(tree, "model.py", "from codemap.cli import main  # noqa: F401", rules)
    assert [x.rule for x in v] == ["layered"]
    assert ("codemap.model", "codemap.cli") in v[0].edges


def test_independent_catches_a_new_edge_between_two_declared_peers(tree, baseline):
    rules = {"independent": [["extract", "serve"]]}
    assert _check(baseline, rules) == [], "extract and serve are independent today"
    v = _run(tree, "extract/roots.py",
             "from codemap.serve.check import render_check  # noqa: F401", rules)
    assert [x.rule for x in v] == ["independent"]
    assert ("codemap.extract.roots", "codemap.serve.check") in v[0].edges


def test_forbidden_catches_the_banned_direction_only(tree, baseline):
    rules = {"forbidden": [{"from": "model", "to": "query"}]}
    assert _check(baseline, rules) == []
    v = _run(tree, "model.py", "from codemap.query import Query  # noqa: F401", rules)
    assert [x.rule for x in v] == ["forbidden"]
    assert ("codemap.model", "codemap.query") in v[0].edges
    # The same edge under the opposite ban is not a violation.
    assert _check(baseline, {"forbidden": [{"from": "query", "to": "model"}]})


def test_no_cycles_catches_a_cycle_the_import_actually_closes(tree, baseline):
    rules = {"no_cycles": True}
    assert _check(baseline, rules) == [], "codemap's eager import graph is acyclic today"
    v = _run(tree, "model.py", "from codemap.store import save  # noqa: F401", rules)
    assert [x.rule for x in v] == ["no_cycles"]
    # `modules` on a cycle violation holds *rendered paths*, not ids — "a → b → a".
    assert any("codemap.model" in c and "codemap.store" in c for c in v[0].modules), v[0].modules


def test_no_lazy_cycles_catches_a_cycle_only_a_function_local_import_closes(tree, baseline):
    rules = {"no_lazy_cycles": True}
    assert _check(baseline, rules) == []
    line = ("def _mutation_probe():\n"
            "    from codemap.serve.vault import build_vault\n"
            "    return build_vault")
    v = _run(tree, "query.py", line, rules)
    assert [x.rule for x in v] == ["no_lazy_cycles"]
    assert any("codemap.query" in c and "codemap.serve.vault" in c for c in v[0].modules), v[0].modules


def test_no_cycles_stays_silent_on_the_lazy_one(tree):
    """The pair that makes the two rules different rules, on the real tree."""
    line = ("def _mutation_probe():\n"
            "    from codemap.serve.vault import build_vault\n"
            "    return build_vault")
    path, original = _mutate(tree, "query.py", line)
    try:
        q = Query(extract(str(tree)))
        assert check_contract(q, parse_contract({"no_cycles": True})) == []
        assert check_contract(q, parse_contract({"no_lazy_cycles": True}))
    finally:
        _restore(path, original)


def test_exhaustive_catches_a_new_undeclared_component(tree, baseline):
    rules = {"layers": REAL_LAYERS, "exhaustive": True}
    assert _check(baseline, rules) == [], "REAL_LAYERS is stale — a component was added"
    newpkg = tree / "newlayer"
    newpkg.mkdir()
    (newpkg / "__init__.py").write_text('"""A component nobody declared."""\n')
    try:
        v = check_contract(Query(extract(str(tree))), parse_contract(rules))
        assert [x.rule for x in v] == ["exhaustive"]
        assert "newlayer" in v[0].modules
    finally:
        shutil.rmtree(newpkg)


def test_the_tree_is_unchanged_after_every_mutation(tree, baseline):
    """The other half of a mutation test, once: the red went away with the change that
    caused it, so the reds above were the mutations and not the harness."""
    after = Query(extract(str(tree)))
    assert set(after.graph.nodes) == set(baseline.graph.nodes)
    rules = {"layers": REAL_LAYERS, "no_cycles": True, "no_lazy_cycles": True,
             "exhaustive": True, "independent": [["extract", "serve"]],
             "forbidden": [{"from": "model", "to": "query"}]}
    assert check_contract(after, parse_contract(rules)) == []
