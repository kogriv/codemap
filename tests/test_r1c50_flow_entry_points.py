"""R1-C50/C51/C52 — three findings that arrived in one message from the dogfood target.

[Issue #19](https://github.com/kogriv/codemap/issues/19), filed the day after 0.0.16 while
they were *verifying our own measurement* from bquant#120 on their tree. Gap:
`gaps/flow_entry_points_2026-09-10.md`.

**R1-C50 — an entry point defined so that a library never has one.** `entry_points` asked
for in-degree zero across the whole graph, so the one function a user enters the package
through was disqualified by being used: 43 calls, all from `tests`/`examples`/`scripts`/
`research`. Worse, the better tier answered *emptier* — deep resolution closes the chain
above a node, removing it as a head, so `report impact` said "step 3" on fast and "no
entry point reaches it" on deep, same tree, same version. Fixed three ways: in-degree is
counted **within the root** (D7), an entry says which outside roots enter it (D8), and the
empty answer names its kind — including the nearest head past the depth bound (D9).

**R1-C51 — a filter is partiality too.** `callers(min_confidence="exact")` returned a bare
`[]` for symbols called on every run through a factory. Their measurement is what makes it
matter: of the 25 symbols their registry fan-out reaches, **13 have no `exact` caller at
all** — every strategy method. The envelope now carries a `filter` block in the shape
R1-C28 uses for limits, always, including when nothing was dropped.

**R1-C52 — `diff` judged the consumers' API.** 40 of 47 "added public symbols" in their
release-gate run were test functions, because `diff_api` filtered on visibility alone. It
compares one provenance root now, and says what it did not judge.
"""

from __future__ import annotations

import pytest

from codemap import apidiff
from codemap.extract import extract, extract_repo
from codemap.query import Query
from codemap.serve.apidiff import build_apidiff, render_apidiff
from codemap.serve.impact import render_impact
from codemap.serve.session import Session

# public → mid → leaf, and the public head is called only from the consumer root.
CORE_API = '''from core.mid import step


def public_entry(x):
    return step(x)
'''
CORE_MID = '''from core.leaf import work


def step(x):
    return work(x)
'''
CORE_LEAF = '''def work(x):
    return x
'''
# a pair that calls each other: a chain with no head at all
CORE_RING = '''def ping(n):
    return pong(n) if n else 0


def pong(n):
    return ping(n - 1)


def rung():
    return ping(2)
'''
USAGE = '''from core.api import public_entry


def scenario():
    return public_entry(1)


def scenario_two():
    return public_entry(2)
'''


def _repo(tmp_path):
    core = tmp_path / "core"
    core.mkdir()
    (core / "__init__.py").write_text("")
    (core / "api.py").write_text(CORE_API)
    (core / "mid.py").write_text(CORE_MID)
    (core / "leaf.py").write_text(CORE_LEAF)
    (core / "ring.py").write_text(CORE_RING)
    usage = tmp_path / "usage"
    usage.mkdir()
    (usage / "script.py").write_text(USAGE)
    return core, usage


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    core, usage = _repo(tmp_path_factory.mktemp("r1c50"))
    return Query(extract_repo(core, consumers=(usage,), mode="full"))


@pytest.fixture(scope="module")
def package_only(tmp_path_factory):
    core, _ = _repo(tmp_path_factory.mktemp("r1c50-solo"))
    return Query(extract(core))


def _entries(rep):
    return {f["entry"]: f["first_step"] for f in rep["flows"]}


# -- D7: the head of a library's flow is public, not internal ---------------------------

def test_a_head_called_only_from_a_consumer_root_is_an_entry_point(repo):
    head = "core.api.public_entry"
    assert head in repo.entry_points("core")
    assert repo._calls.in_degree(head) == 2, "and it is called — twice, from the consumer"


def test_the_flow_reaches_the_leaf_from_the_public_head(repo):
    rep = repo.flows_to("core.leaf.work")
    assert _entries(rep)["core.api.public_entry"] == 2


def test_the_old_rule_loses_the_flow_entirely(repo, monkeypatch):
    """R1-C37, and the exact shape of #19: with in-degree counted across the whole graph,
    the public head is disqualified by being used, and nothing reaches the leaf at any
    depth — so raising `--flow-depth` cannot help, which is what they measured."""
    def global_indegree(self, root="core"):
        return sorted(n for n in self._calls.nodes
                      if self.root_of(n) == root
                      and self._calls.out_degree(n) > 0
                      and self._calls.in_degree(n) == 0)

    monkeypatch.setattr(Query, "entry_points", global_indegree)
    assert "core.api.public_entry" not in repo.entry_points("core")
    for depth in (2, 5, 50):
        assert repo.flows_to("core.leaf.work", max_depth=depth)["flows"] == []


def test_a_single_package_graph_is_unaffected(package_only):
    """The rule may not silently change the answer where no consumer root exists: with one
    root, in-root in-degree *is* in-degree."""
    q = package_only
    old = sorted(n for n in q._calls.nodes if q.root_of(n) == "core"
                 and q._calls.out_degree(n) > 0 and q._calls.in_degree(n) == 0)
    assert q.entry_points("core") == old


# -- D8: an entry says what enters it ---------------------------------------------------

def test_an_entry_carries_the_roots_that_enter_it(repo):
    rep = repo.flows_to("core.leaf.work")
    flow = next(f for f in rep["flows"] if f["entry"] == "core.api.public_entry")
    assert flow["external_callers"] == {"usage": 2}
    assert repo.external_callers("core.api.public_entry") == {"usage": 2}
    md = render_impact(repo, "core.leaf.work")
    assert "entered from usage ×2" in md


def test_an_internal_head_has_no_external_callers(package_only):
    assert package_only.external_callers("core.api.public_entry") == {}


# -- D9: the empty answer names its kind ------------------------------------------------

def test_the_nearest_head_past_the_bound_is_named_and_actionable(repo):
    rep = repo.flows_to("core.leaf.work", max_depth=1)
    assert rep["flows"] == [] and rep["beyond_depth"] == 1 and rep["nearest_beyond"] == 2
    md = render_impact(repo, "core.leaf.work", flow_depth=1)
    assert "the nearest at step **2**" in md and "--flow-depth 2" in md


def test_called_but_headless_is_not_nothing_calls_it(repo):
    """`ping`/`pong` call each other and `rung` calls `ping`; nothing reaches `pong` from
    a head, because the chain closes in a cycle. That is not 'no call reaches it'."""
    rep = repo.flows_to("core.ring.pong")
    assert rep["in_call_graph"] is True and rep["inbound_calls"] >= 1
    md = render_impact(repo, "core.ring.pong")
    if not rep["flows"]:
        assert "closed in a call cycle" in md and "Not 'nothing calls it'" in md


def test_the_note_warns_in_both_directions(repo):
    md = render_impact(repo, "core.leaf.work")
    assert "looking like an entry point" in md, "the over-estimate, as before"
    assert "*removes* an entry point" in md, "and the reverse (#19)"
    assert "**more** complete graph can answer with **fewer** flows" in md
    assert "a use, not an internal caller" in md


# -- R1-C51: a filter declares itself ---------------------------------------------------

def _handle(q, op, args):
    return Session(q.graph).handle({"op": op, "args": args})


@pytest.fixture(scope="module")
def registry():
    from pathlib import Path
    return Query(extract(Path(__file__).resolve().parent / "fixtures" / "dispatchpkg"))


def test_the_filter_block_is_present_even_with_no_filter(registry):
    target = next(e.target for e in registry.graph.edges
                  if e.extras.get("resolution") == "registry-candidate")
    env = _handle(registry, "callers", {"symbol": target})
    f = env["filter"]
    assert f["min_confidence"] is None and f["dropped"] == 0
    assert f["returned"] == f["total"] == len(env["result"])
    assert f["by_grade"], "the composition is stated before anyone filters"


def test_an_empty_filtered_answer_says_what_it_dropped(registry):
    """The reported shape — theirs was a strategy method whose *every* caller is a
    registry fan-out, so `exact` answers `[]`. The block turns that into 'called, but
    only through routes you excluded', which a bare list cannot say."""
    target = next(t for t in sorted({e.target for e in registry.graph.edges
                                     if e.extras.get("resolution") == "registry-candidate"})
                  if set(registry.caller_grades(t)) == {"heuristic"})
    env = _handle(registry, "callers", {"symbol": target, "min_confidence": "exact"})
    f = env["filter"]
    assert env["result"] == [] and f["returned"] == 0
    assert f["total"] > 0 and f["dropped"] == f["total"]
    assert f["by_grade"].get("heuristic") == f["total"]
    assert f["min_confidence"] == "exact"


def test_callees_declares_it_too(registry):
    src = next(e.source for e in registry.graph.edges
               if e.extras.get("resolution") == "registry-candidate")
    env = _handle(registry, "callees", {"symbol": src, "min_confidence": "exact"})
    assert env["filter"]["dropped"] >= 1 and env["filter"]["by_grade"]


def test_the_grade_histogram_matches_the_edges(registry):
    for target in {e.target for e in registry.graph.edges if e.type == "calls"}:
        counted: dict[str, int] = {}
        for e in registry.graph.edges:
            if e.type == "calls" and e.target == target:
                from codemap.model import confidence_of
                g = confidence_of(e) or "unknown"
                counted[g] = counted.get(g, 0) + 1
        got = registry.caller_grades(target)
        # the graph edge collapses parallel resolutions onto one pair, keeping the
        # strongest, so the histogram counts pairs — never more than the raw edges.
        assert sum(got.values()) <= sum(counted.values())
        assert set(got) <= set(counted)


# -- R1-C52: the diff judges the package, and says so -----------------------------------

def test_a_consumers_public_function_is_not_this_packages_api(repo, tmp_path):
    core, usage = _repo(tmp_path)
    (usage / "script.py").write_text(USAGE + "\n\ndef brand_new_helper():\n    return 1\n")
    new = extract_repo(core, consumers=(usage,), mode="full")
    d = apidiff.diff_api(repo.graph, new)
    assert d.added == [], "a new public test/consumer function is not an API addition"
    assert d.excluded.get("usage", 0) >= 3, "and the count of what was not judged is stated"
    assert d.root == "core"
    everything = apidiff.diff_api(repo.graph, new, root=None)
    assert "usage.script.brand_new_helper" in everything.added, "asked for, and there"
    assert everything.excluded == {}


def test_the_package_api_still_diffs(repo, tmp_path):
    core, usage = _repo(tmp_path)
    (core / "api.py").write_text(CORE_API + "\n\ndef second_entry(y):\n    return y\n")
    new = extract_repo(core, consumers=(usage,), mode="full")
    d = apidiff.diff_api(repo.graph, new)
    assert d.added == ["core.api.second_entry"]


def test_the_report_names_what_it_did_not_judge(repo, tmp_path):
    core, usage = _repo(tmp_path)
    (usage / "script.py").write_text(USAGE + "\n\ndef brand_new_helper():\n    return 1\n")
    new = extract_repo(core, consumers=(usage,), mode="full")
    md = render_apidiff(repo.graph, new)
    assert "Compared: public symbols of root `core`" in md
    assert "Not judged:" in md and "`usage`" in md
    assert build_apidiff(repo.graph, new)["excluded"]


def test_a_single_root_diff_says_the_scope_without_an_exclusion_list(package_only, tmp_path):
    core, _ = _repo(tmp_path)
    (core / "api.py").write_text(CORE_API + "\n\ndef second_entry(y):\n    return y\n")
    md = render_apidiff(package_only.graph, extract(core))
    assert "Compared: public symbols of root `core` — the package._" in md
    assert "Not judged:" not in md
