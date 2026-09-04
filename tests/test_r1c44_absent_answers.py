"""R1-C44 — an empty answer has to say which kind of empty it is.

Found from our own mistake: a probe searched `bquant.…` on a graph rooted by its
directory name (`target.…`), and eighteen deep builds measured nothing while looking
like a result — "no edge" is a plausible outcome at a 25 % rate. Behind it, an
unconditional defect: `impact` on a symbol the graph does not hold answered
`risk: "none"`, and `callers`/`callees`/`flows` on it returned an envelope byte-identical
to the one for a real symbol nobody references. `canonical_info()` had computed "no such
symbol" as None; `handle()` discarded it with `if r and …`.

Design: docs/design/absent_answers.md (D1 `ok: true` + `resolved.found: false`, verdict
`unknown`; D2 a three-way branch; D4 the splice reason, derived from the spliced classes;
D5 the quieter wording for a graph older than the field; D6 three side fixes).

R1-C37: every "not found" assertion below feeds an **actual** ghost id, not merely an
ambiguous one — the case `if r and …` threw away is the case that must be shown.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap import cli
from codemap.extract import extract
from codemap.model import SPLICED_EDGE_TYPES
from codemap.incremental import _DEP_EDGE_TYPES
from codemap.query import Query
from codemap.serve.session import (
    _OP_EDGE_CLASSES, _PARTIAL_OPS, _SPLICE_OPS, Session,
)

GHOST = "lonelypkg.nosuch.module.Ghost.field"
LONELY = "lonelypkg.core.lonely"


@pytest.fixture(scope="module")
def pkg(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("absent") / "lonelypkg"
    root.mkdir()
    (root / "__init__.py").write_text('"""Fixture: one referenced function, one that nobody references."""\n')
    (root / "core.py").write_text(
        "class Box:\n    def __init__(self):\n        self.width = 1\n\n\n"
        "def helper():\n    return Box().width\n\n\n"
        "def caller():\n    return helper()\n\n\n"
        "def lonely():\n    return 0\n"
    )
    return root


@pytest.fixture(scope="module")
def graph(pkg):
    return extract(pkg)


@pytest.fixture(scope="module")
def session(graph):
    return Session(graph)


# Every op that resolves a symbol, with the argument it takes it under.
RESOLVING_OPS = [
    ("callers", "symbol"), ("callees", "symbol"), ("call_contract", "symbol"),
    ("flows", "symbol"), ("tests", "symbol"), ("impact", "symbol"),
    ("accessors", "attribute"), ("query", "name"),
]


# -- D1 / D2: a ghost and a lonely symbol are no longer the same envelope ----------------

@pytest.mark.parametrize("op,arg", RESOLVING_OPS)
def test_a_symbol_the_graph_does_not_hold_says_so(session, op, arg):
    env = session.handle({"op": op, "args": {arg: GHOST}})
    assert env["ok"] is True, "a well-formed question with an informative answer is not an error"
    assert env["resolved"] == {"input": GHOST, "id": None, "found": False,
                               "ambiguous": False, "alternatives": []}


@pytest.mark.parametrize("op,arg", [p for p in RESOLVING_OPS if p[0] != "accessors"])
def test_a_real_symbol_nobody_references_carries_no_resolved_noise(session, op, arg):
    env = session.handle({"op": op, "args": {arg: LONELY}})
    assert env["ok"] is True
    assert "resolved" not in env, "an exact id that exists is the quiet case (F13/F14)"


@pytest.mark.parametrize("op,arg", [p for p in RESOLVING_OPS if p[0] != "accessors"])
def test_the_two_empties_are_distinguishable_programmatically(session, op, arg):
    ghost = session.handle({"op": op, "args": {arg: GHOST}})
    lonely = session.handle({"op": op, "args": {arg: LONELY}})
    assert ghost != lonely
    assert ghost.get("resolved", {}).get("found") is False
    assert lonely.get("resolved", {}).get("found", True) is True


def test_impact_on_a_ghost_answers_unknown_not_none(graph):
    q = Query(graph)
    ghost = q.impact(GHOST)
    assert ghost["refs"] == [] and ghost["risk"] == "unknown"
    assert "not in graph" in ghost["risk_reason"]
    lonely = q.impact(LONELY)
    assert lonely["refs"] == [] and lonely["risk"] == "none", \
        "the one case where the verdict is earned stays `none`"


def test_the_impact_op_records_its_own_resolution(session):
    """`impact` resolves through `impact_targets`, not `_canon`, so D2 in `_canon`
    alone would have left this op answering an empty list with no `resolved` block."""
    env = session.handle({"op": "impact", "args": {"symbol": GHOST}})
    assert env["result"]["impact"] == []
    assert env["resolved"]["found"] is False
    assert "nothing is known about it" in env["result"]["markdown"]


def test_a_found_resolution_now_says_found(session):
    env = session.handle({"op": "callers", "args": {"symbol": "helper"}})
    # a short name rewritten to its canonical id carries the block, and the block says
    # `found` — the same shape as the not-found case, read by the same key
    assert env["resolved"]["found"] is True
    assert env["resolved"]["id"] == "lonelypkg.core.helper"


# -- D4: the lower-bound block, and the splice reason where it applies ---------------------

def test_accessors_now_carries_the_lower_bound_block(session):
    env = session.handle({"op": "accessors", "args": {"attribute": "lonelypkg.core.Box.width"}})
    assert env["epistemic"]["epistemic"] == "partial"
    assert "accessors" in _PARTIAL_OPS


def test_the_partial_set_did_not_shrink():
    assert {"callers", "callees", "impact", "flows", "call_contract",
            "tests", "covers"} <= _PARTIAL_OPS


def test_every_spliced_class_is_claimed_by_some_op():
    """Adding an edge class to the incremental splice must force a decision here."""
    assert _DEP_EDGE_TYPES == SPLICED_EDGE_TYPES
    claimed = set().union(*_OP_EDGE_CLASSES.values())
    assert SPLICED_EDGE_TYPES <= claimed, SPLICED_EDGE_TYPES - claimed
    assert _SPLICE_OPS == {op for op, cls in _OP_EDGE_CLASSES.items() if cls & SPLICED_EDGE_TYPES}


def _session_with(graph, provenance):
    import copy
    g = copy.deepcopy(graph)
    g.provenance = provenance
    return Session(g)


def test_a_deep_incremental_graph_adds_the_splice_reason_only_where_it_applies(graph):
    s = _session_with(graph, {"tier": "deep", "incremental": True})
    env = s.handle({"op": "callers", "args": {"symbol": LONELY}})
    assert "carried over" in env["epistemic"]["splice"]
    assert env["epistemic"]["reason"], "the first reason is kept — a different fact"
    stats = s.handle({"op": "stats", "args": {}})
    assert "epistemic" not in stats, "an op reading no spliced class says nothing new"


def test_a_full_deep_graph_and_the_fast_tier_carry_no_splice_reason(graph):
    for prov in ({"tier": "deep", "incremental": False},
                 {"tier": "fast", "incremental": True},
                 {"tier": "fast", "incremental": False}):
        env = _session_with(graph, prov).handle({"op": "callers", "args": {"symbol": LONELY}})
        assert "splice" not in env["epistemic"], prov


def test_a_deep_graph_older_than_the_field_gets_the_quieter_wording(graph):
    env = _session_with(graph, {"tier": "deep"}).handle({"op": "callers", "args": {"symbol": LONELY}})
    assert "unknown" in env["epistemic"]["splice"]
    assert "carried over from an earlier build is unknown" in env["epistemic"]["splice"]


# -- D6: the three side fixes --------------------------------------------------------------

def test_the_incremental_help_names_the_tier(capsys):
    with pytest.raises(SystemExit):
        cli.main(["build", "--help"])
    out = capsys.readouterr().out
    assert "Identical to a full build" not in out
    assert "fast tier" in out and "jedi sample" in out


def test_incremental_with_a_consumer_root_is_refused_out_loud(pkg, tmp_path, capsys):
    cons = tmp_path / "tests"
    cons.mkdir()
    (cons / "test_x.py").write_text("from lonelypkg.core import helper\n\ndef test_h():\n    helper()\n")
    out = tmp_path / "graph.json"
    assert cli.main(["build", str(pkg), "--incremental", "--consumer", str(cons), "-o", str(out)]) == 0
    err = capsys.readouterr().err
    assert "--incremental was not applied" in err and "repo-scoped" in err


def test_the_build_help_says_ids_start_with_the_directory_name(capsys):
    with pytest.raises(SystemExit):
        cli.main(["build", "--help"])
    assert "directory name is the package name" in capsys.readouterr().out
