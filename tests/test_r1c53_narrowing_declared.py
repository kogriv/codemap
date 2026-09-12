"""R1-C53 — every narrowing declares itself, and the classes are enumerated.

Not a bug report: a **count**. Eight of the twelve fixes R1-C41…R1-C52 were one defect —
an answer narrower than it looks, silent about it — and four of the last five were found by
a consumer rather than by us. So this file is about the mechanism, not the instances.

Seven classes of narrowing, and what declares each:

| class | what narrows | declared by |
|---|---|---|
| `limit` | a computed list is cut | `limit` block, always (R1-C28) |
| `filter` | a predicate drops entries | `filter` block, always (R1-C51, R1-C53) |
| `scope` | one provenance root is judged | `scope` block (R1-C53), `diff`'s `excluded` (R1-C52) |
| `bound` | a walk stops at a depth | in-result (`by_distance`, `beyond_depth`, `nearest_beyond`) |
| `tier` | the answer is a lower bound | `epistemic` (R1-C13), splice reason (R1-C43) |
| `edge-class` | only some edge classes are read | `epistemic`, and the over-set variant (R1-C53) |
| `definition` | the answer's shape depends on a definition that may not fit | in-result (`definition`) |

The two tests that matter in a year are the guards at the bottom: one fails when an op
learns a narrowing argument without joining a class, the other when a class's declaration
stops being emitted. Everything above them is the evidence that each class is real.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from codemap.extract import extract, extract_repo
from codemap.query import Query
from codemap.serve import session as session_mod
from codemap.serve.mermaid import render_mermaid
from codemap.serve.session import (_LIMITED_OPS, _OVER_SET_OPS, _PARTIAL_OPS,
                                   _UNLIMITED_BY_DESIGN, Session)

FIX = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def flowgraph():
    return Query(extract(FIX / "flowpkg"))


@pytest.fixture(scope="module")
def repo():
    return Query(extract_repo(FIX / "reporoot" / "core",
                              consumers=(FIX / "reporoot" / "usage",),
                              docs=(FIX / "reporoot" / "docs",), mode="full"))


def _handle(q, op, args=None):
    return Session(q.graph).handle({"op": op, "args": args or {}})


# -- filter: the narrowing that hid the larger half -------------------------------------

def test_columns_declares_the_half_it_hides(flowgraph):
    """Measured on the dogfood tree before the fix: 331 returned of 1057, and the answer
    was a bare list. The default narrowing is deliberate (F15) and was undeclared, which
    is a different thing from being wrong."""
    env = _handle(flowgraph, "columns")
    f = env["filter"]
    assert f["basis"] == "subscripted_only"
    assert f["returned"] == len(env["result"])
    assert f["total"] >= f["returned"] and f["dropped"] == f["total"] - f["returned"]
    wide = _handle(flowgraph, "columns", {"all": True})
    assert wide["filter"]["basis"] is None and wide["filter"]["dropped"] == 0
    assert len(wide["result"]) == f["total"], "and the two agree on the total"


def test_the_over_set_is_not_called_a_lower_bound(flowgraph):
    """`reads`/`writes` are partial in the *other* direction. Borrowing the lower-bound
    wording would tell a caller to widen when it must verify instead."""
    for op, args in (("columns", {}), ("columns_of", {"symbol": "flowpkg.producer.make"})):
        env = _handle(flowgraph, op, args)
        reason = env.get("epistemic", {}).get("reason", "")
        assert "over-set" in reason, (op, reason)
        assert "lower bound" not in reason.replace("not a lower bound", ""), op
    assert _OVER_SET_OPS == {"column", "columns", "columns_of"}
    assert _OVER_SET_OPS <= _PARTIAL_OPS, "an over-set is still a partiality"


# -- scope: one root judged, the others named -------------------------------------------

def test_communities_names_the_root_it_judges(repo):
    env = _handle(repo, "communities")
    s = env["scope"]
    assert s["root"] == "core"
    assert s["not_judged"] == {"usage": 1}, "the consumer root is named, not silently cut"


def test_entry_points_name_the_root_and_the_definition(repo):
    env = _handle(repo, "flows")
    assert env["scope"]["not_judged"] == {"usage": 1}
    d = env["result"]
    assert "use, not an internal caller" in d["definition"], "R1-C50, in the answer"
    assert "fewer" in d["best_effort_both_ways"], "and the reverse direction too"


def test_a_single_root_graph_says_so_without_inventing_exclusions(flowgraph):
    env = _handle(flowgraph, "communities")
    assert env["scope"]["root"] == "core" and env["scope"]["not_judged"] == {}


# -- definition / mixed answers ----------------------------------------------------------

def test_a_mixed_dossier_declares_per_field_not_per_envelope(flowgraph):
    """The rule this file does **not** break: absence of `epistemic` means exact. A dossier
    whose definition is exact and whose `used_by` is a lower bound must not be stamped
    wholesale — over-claiming partiality is the same defect pointed the other way."""
    q = Query(extract(FIX / "argpkg"))
    env = _handle(q, "query", {"name": "configure"})
    assert env["result"]["used_by"], "the fixture must carry the field being declared"
    assert "epistemic" not in env, "the dossier as a whole is not a lower bound"
    assert "lower bound" in env["result"]["used_by_epistemic"]
    assert "are exact" in env["result"]["used_by_epistemic"]
    # and the note lives where the field is built, so the CLI dossier carries it too
    from codemap.serve.session import build_query_result
    assert "used_by_epistemic" in build_query_result(q, "configure")
    assert "used_by_epistemic" not in build_query_result(q, "nope_missing")


def test_a_scoped_diagram_says_what_it_left_out(flowgraph):
    scoped = render_mermaid(flowgraph, "class", scope="flowpkg.klass")
    assert "%% scope: flowpkg.klass" in scoped and "further line(s) exist" in scoped
    assert "%% scope" not in render_mermaid(flowgraph, "class")


# -- the guards --------------------------------------------------------------------------

_NARROWING_ARG = re.compile(
    r"""args\.get\(\s*["'](?:\w+_)?(limit|cap|budget|max|top|min_confidence|all|scope|root)(?:_\w+)?["']""")

#: Ops that read a narrowing argument and declare it, with the block that does the
#: declaring. Hand-written on purpose: the guard below compares this list against the
#: source, so a new narrowing forces an entry here rather than passing unnoticed.
_DECLARED = {
    "search": "limit", "semantic": "limit", "tests": "limit", "covers": "limit",
    "callers": "filter", "callees": "filter", "columns": "filter",
    "communities": "scope", "flows": "scope",
}
#: Read a narrowing-ish argument and deliberately declare nothing, with the reason.
_NOT_A_NARROWING = {
    "check": "`root` says where codemap.toml is read from — it does not narrow the answer; "
             "what the contract left unjudged is already declared by the R1-C30-f2 block",
    "export": "`root`/`scope` select *which view* to render rather than cutting an answer, "
              "and the scoped mermaid diagram carries its own `%% scope:` line (R1-C53)",
    "report": "a markdown report declares its own narrowing in prose — dead-code prints "
              "`(min-confidence: …)` and impact prints the flow note; there is no "
              "structured answer here for a block to describe",
    "pack": _UNLIMITED_BY_DESIGN["pack"],
    "impact": _UNLIMITED_BY_DESIGN["impact"],
}


def test_every_op_reading_a_narrowing_arg_is_classified():
    """Fails when an op learns a narrowing without joining a class. The list it checks is
    the ops' own source, because a hand-kept list is what gets forgotten — and the two
    hand-kept sets here exist so that "exempt, deliberately" is distinguishable from
    "nobody noticed"."""
    for op, fn in session_mod._OPS.items():
        if not _NARROWING_ARG.search(inspect.getsource(fn)):
            continue
        assert op in _DECLARED or op in _NOT_A_NARROWING, (
            f"op {op!r} reads a narrowing argument and neither declares it nor records "
            f"why it does not")
    for op, reason in _NOT_A_NARROWING.items():
        assert op in session_mod._OPS and len(reason) > 40, op
    assert set(_DECLARED) & _LIMITED_OPS == {"search", "semantic", "tests", "covers"}


def test_each_declared_op_actually_emits_its_block(flowgraph, repo):
    calls = {
        "search": (flowgraph, {"term": "hit"}), "tests": (flowgraph, {"symbol": "hit"}),
        "covers": (flowgraph, {"test": "t"}),
        "callers": (flowgraph, {"symbol": "flowpkg.leaf.hit"}),
        "callees": (flowgraph, {"symbol": "flowpkg.entry.main"}),
        "columns": (flowgraph, {}), "communities": (repo, {}), "flows": (repo, {}),
    }
    assert set(calls) | {"semantic"} == set(_DECLARED), "a declared op has no coverage here"
    for op, (q, args) in calls.items():
        env = _handle(q, op, args)
        assert env["ok"], (op, env)
        block = _DECLARED[op]
        assert block in env, f"{op} promised a {block!r} block and emitted {sorted(env)}"


def test_the_guard_catches_a_narrowing_name_it_has_not_seen():
    """R1-C37 on the guard itself: shown the shapes it must catch, including the ones that
    slipped past earlier versions of the pattern."""
    for src in ('args.get("min_confidence")', 'args.get("all", False)',
                'args.get("flow_limit", 5)', "args.get('max_results')",
                'args.get("scope")', 'args.get("root")'):
        assert _NARROWING_ARG.search(src), src
    for src in ('args.get("symbol")', 'args.get("depth", 2)', 'args.get("base")'):
        assert not _NARROWING_ARG.search(src), f"{src} is not a narrowing of the answer"
