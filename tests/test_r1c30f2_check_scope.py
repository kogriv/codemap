"""R1-C30-f2 — what a passing gate did not judge, and the opt-in that judges it.

`no_cycles` gates the **eager** import graph deliberately (R1-C29): a function-local import
is the accepted way to break an import cycle, so failing a build because someone applied the
remedy would be worse than the disease. §7 of the R1-C29 gap doc left open whether a contract
should be able to gate the lazy ones, and the second real target answered it by running the
gate on a tree with 48 of them:

    # Architecture check — `shared`
    ✅ **Contract satisfied.** Rules enforced: no_cycles.

    ## Import cycles: 0        (report architecture, same graph)
    ### Dependency cycles closed only by a function-local import: 48

Their verdict, which is the one worth keeping: *"`check` did not fail on an unexpected
violation. It did not fail where violations exist — and that is worse."* The reader concludes
the graph is acyclic; the gate judged a subset and said nothing about the rest. That is the
R1-C29 defect — a property claim over a partial view — moved out of the report and into the
gate, one day after it was removed from the report.

So the gate stays eager, the **disclosure** becomes mandatory, and `no_lazy_cycles = true`
lets a contract owner state the other position rather than having one picked for them.
"""

from __future__ import annotations

import pytest

from codemap.arch import check_contract, parse_contract
from codemap.extract import extract
from codemap.query import Query
from codemap.serve.check import build_check, render_check


@pytest.fixture
def lazy_cycle(tmp_path):
    """`a` imports `b` eagerly; `b` imports `a` inside a function. Eagerly acyclic, and
    mutually dependent all the same."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text("from pkg.b import beta\n\n\ndef alpha():\n    return beta()\n")
    (pkg / "b.py").write_text("def beta():\n    from pkg.a import alpha\n    return alpha\n")
    return Query(extract(str(pkg)))


@pytest.fixture
def eager_only(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text("x = 1\n")
    (pkg / "b.py").write_text("from pkg.a import x\n")
    return Query(extract(str(pkg)))


def _run(query, section):
    contract = parse_contract(section)
    violations = check_contract(query, contract)
    return contract, violations


# -- the gate keeps judging the eager graph ---------------------------------

def test_a_lazy_cycle_does_not_fail_the_default_gate(lazy_cycle):
    """Failing here would report someone's cycle-break as their bug."""
    _, violations = _run(lazy_cycle, {"no_cycles": True})
    assert violations == []


# -- but a passing run says what it did not look at -------------------------

def test_the_passing_report_names_what_was_not_judged(lazy_cycle):
    contract, violations = _run(lazy_cycle, {"no_cycles": True})
    out = render_check(lazy_cycle, contract, violations)
    assert "Contract satisfied" in out
    assert "eager import graph only" in out
    assert "**1** dependency cycle(s)" in out


def test_the_structured_payload_carries_it_too(lazy_cycle):
    contract, violations = _run(lazy_cycle, {"no_cycles": True})
    scope = build_check(lazy_cycle, contract, violations)["scope"]
    assert len(scope) == 1
    assert scope[0]["rule"] == "no_cycles"
    assert scope[0]["count"] == 1


def test_it_is_declared_even_when_there_is_nothing_to_declare(eager_only):
    """The R1-C28 rule: a field that appears only when something was skipped forces a
    consumer to tell "nothing was skipped" from "this build does not report skips"."""
    contract, violations = _run(eager_only, {"no_cycles": True})
    scope = build_check(eager_only, contract, violations)["scope"]
    assert len(scope) == 1 and scope[0]["count"] == 0
    assert "no dependency cycle is closed only by a function-local import" \
        in render_check(eager_only, contract, violations)


def test_a_failing_run_carries_the_same_disclosure(lazy_cycle):
    """A broken `layered` rule must not swallow the note: the reader is looking at cycle
    output either way."""
    contract, violations = _run(lazy_cycle, {"no_cycles": True, "exhaustive": True,
                                             "layers": ["nonexistent"]})
    assert violations
    assert "eager import graph only" in render_check(lazy_cycle, contract, violations)


def test_nothing_is_declared_when_the_rule_is_not_enforced(lazy_cycle):
    contract, violations = _run(lazy_cycle, {"layers": ["a", "b"]})
    assert build_check(lazy_cycle, contract, violations)["scope"] == []


# -- and the contract owner can take the other position ---------------------

def test_the_opt_in_gates_the_lazy_cycle(lazy_cycle):
    _, violations = _run(lazy_cycle, {"no_cycles": True, "no_lazy_cycles": True})
    assert [v.rule for v in violations] == ["no_lazy_cycles"]
    # the rotation a cycle enumerator starts from is not part of the answer
    assert len(violations[0].modules) == 1
    assert set(violations[0].modules[0].split(" → ")) == {"pkg.a", "pkg.b"}


def test_the_opt_in_alone_is_a_contract(lazy_cycle):
    """`no_lazy_cycles` without `no_cycles` is a legitimate (if odd) contract, and must not
    read as "no rules configured"."""
    contract = parse_contract({"no_lazy_cycles": True})
    assert not contract.is_empty()
    assert [v.rule for v in check_contract(lazy_cycle, contract)] == ["no_lazy_cycles"]


def test_opting_in_removes_the_disclaimer_because_nothing_is_left_out(lazy_cycle):
    contract, violations = _run(lazy_cycle, {"no_cycles": True, "no_lazy_cycles": True})
    assert build_check(lazy_cycle, contract, violations)["scope"] == []
    assert "not** judged" not in render_check(lazy_cycle, contract, violations)


def test_an_eager_cycle_still_fails_the_default_gate(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text("from pkg.b import beta\n")
    (pkg / "b.py").write_text("from pkg.a import alpha\n")
    query = Query(extract(str(pkg)))
    _, violations = _run(query, {"no_cycles": True})
    assert [v.rule for v in violations] == ["no_cycles"]
