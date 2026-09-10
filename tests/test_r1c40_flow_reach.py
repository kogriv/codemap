"""R1-C40 — which scenarios a change lands on, and at which step.

From the OntoIndex разбор (`research/tools/ontoindex.md`, «What we'd take», п. 2): their
`impact` says, per affected process, where the break first lands; codemap had both ends —
`impact` walks inbound, `flows` walks outbound — and nothing joining them. The question
asked *before* a change is not "who references this" but "what stops working, and where".

What is pinned (design `docs/design/flow_reach.md`):

1. D1 — a flow is what `flows` already calls one: an entry point of a *root*, default
   `core`; consumer roots (tests/examples) are not scenarios of the product.
2. D2 — `first_step` is the **shortest** distance in `calls` edges to the symbol or one
   of its members, computed by one reverse BFS. The acceptance test is the equivalence:
   for every entry point, the reverse walk agrees with the forward `flow()` — including
   the entries it says do *not* reach.
3. D3 — *reached*, never *broken*: the graph knows the symbol is on the path, not what an
   edit does to it.
4. D4 — three partialities named separately: `non_call_refs` (a reference that cannot
   appear in a flow at all), `beyond_depth` (reaches further than the bound — counted,
   not dropped), and the standing "calls are a lower bound".
5. D5 — `in_call_graph: false` ("nothing to say") is not an empty flow list ("nothing
   reaches it") — the eleventh application of `unknown` ≠ `none`.
6. D6 — the serve answer is whole; the transport cuts and declares it.
"""

from __future__ import annotations

import pytest

from codemap.extract import extract
from codemap.query import Query
from codemap.serve.impact import render_impact
from codemap.serve.mcp_server import _compact_impact

# main → fast → hit  (2 steps) and main → slow → detour → hit (3): the shortest wins.
ENTRY = '''from .mid import fast, slow, use_engine, draw


def main():
    fast()
    slow()
    use_engine()
    draw()
'''
MID = '''from .leaf import hit
from .klass import Engine, Widget


def fast():
    hit()


def slow():
    detour()


def detour():
    hit()


def use_engine():
    Engine().run()


def draw():
    Widget.paint()
'''
LEAF = '''def hit():
    return 1
'''
KLASS = '''class Engine:
    def run(self):
        return self.step()

    def step(self):
        return 2


class Sub(Engine):
    pass


class Widget:
    """Never constructed — a flow reaches it only through the method it calls."""

    @staticmethod
    def paint():
        return 4


def lonely():
    return 3
'''


def _pkg(tmp_path, files):
    pkg = tmp_path / "flowpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    for name, body in files.items():
        (pkg / f"{name}.py").write_text(body)
    return pkg


@pytest.fixture(scope="module")
def q(tmp_path_factory):
    pkg = _pkg(tmp_path_factory.mktemp("r1c40"),
               {"entry": ENTRY, "mid": MID, "leaf": LEAF, "klass": KLASS})
    return Query(extract(str(pkg)))


def _entries(rep):
    return {f["entry"]: f["first_step"] for f in rep["flows"]}


# -- D1: what counts as a flow ----------------------------------------------------------

def test_a_consumer_scenario_is_not_a_flow_of_the_product(tmp_path):
    """D1: with a repo-scoped graph the default root stays `core` — a script that uses
    the package is a consumer, not a scenario of it, and it is already visible in the
    blast radius under its own root. Ask for that root and it is there."""
    from pathlib import Path

    from codemap.extract import extract_repo
    fix = Path(__file__).resolve().parent / "fixtures" / "reporoot"
    r = Query(extract_repo(fix / "core", consumers=(fix / "usage",),
                           docs=(fix / "docs",), mode="full"))
    core = r.flows_to("core.engine.Engine")
    assert _entries(core) == {"core.engine.Engine.run": 0}
    usage = r.flows_to("core.engine.Engine", root="usage")
    assert _entries(usage) == {"usage.use_engine.scenario": 1}
    assert usage["root"] == "usage" and core["root"] == "core"


def test_the_flows_are_entry_points_of_the_named_root(q):
    rep = q.flows_to("flowpkg.leaf.hit")
    assert rep["root"] == "core"
    assert rep["entry_points"] == len(q.entry_points("core"))
    assert set(_entries(rep)) <= set(q.entry_points("core"))
    assert "flowpkg.entry.main" in _entries(rep)


# -- D2: the number is the shortest distance --------------------------------------------

def test_first_step_is_the_shortest_of_two_paths(q):
    """main reaches hit through fast (2) and through slow → detour (3)."""
    assert _entries(q.flows_to("flowpkg.leaf.hit"))["flowpkg.entry.main"] == 2


def test_a_member_of_the_symbol_counts_as_the_symbol(q):
    """A change to a class lands where the flow calls its *method*. `Widget` is never
    constructed, so the class node has no inbound call at all — only `Widget.paint` does,
    and a flow that ignores members would not see the change reach anything."""
    rep = q.flows_to("flowpkg.klass.Widget")
    assert rep["in_call_graph"] is True
    assert _entries(rep)["flowpkg.entry.main"] == 2  # main → draw → Widget.paint


def test_an_entry_point_inside_the_symbol_is_step_zero(q):
    """`Engine.run` is itself an entry point and itself a member: the flow does not
    reach the change, it starts inside it."""
    assert _entries(q.flows_to("flowpkg.klass.Engine"))["flowpkg.klass.Engine.run"] == 0


def test_the_reverse_walk_agrees_with_the_forward_flow_on_every_entry(q):
    """The acceptance criterion, and the proof that one reverse BFS may replace N
    forward walks: for *every* entry point, reachability and the step agree with
    `flow()` — the entries it excludes as loudly as the ones it lists."""
    for symbol in ("flowpkg.leaf.hit", "flowpkg.klass.Engine", "flowpkg.mid.detour"):
        targets = {i for i in q.graph.nodes if i == symbol or i.startswith(symbol + ".")}
        rep = q.flows_to(symbol, max_depth=5)
        listed = _entries(rep)
        for entry in q.entry_points("core"):
            forward = q.flow(entry, max_depth=5)["edges"]
            hits = [e["distance"] for e in forward if e["target"] in targets]
            if entry in targets:
                hits.append(0)
            assert (min(hits) if hits else None) == listed.get(entry), (symbol, entry)


# -- D3: reached, not broken ------------------------------------------------------------

def test_the_report_says_reached_and_never_broken(q):
    md = render_impact(q, "flowpkg.leaf.hit")
    assert "Flows reached" in md and "step 2" in md
    assert "*Reached*, not *broken*" in md
    assert "broken step" not in md.lower()


# -- D4: what the answer does not judge -------------------------------------------------

def test_beyond_depth_is_counted_not_dropped(q):
    near = q.flows_to("flowpkg.leaf.hit", max_depth=2)
    far = q.flows_to("flowpkg.leaf.hit", max_depth=1)
    assert _entries(near)["flowpkg.entry.main"] == 2
    assert far["flows"] == [] and far["beyond_depth"] == 1, "reaches at 2, bound is 1"
    assert near["beyond_depth"] == 0


def test_a_reference_that_cannot_appear_in_a_flow_is_counted(q):
    """`Sub` inherits `Engine`: a real dependency, and one no call-flow can show."""
    rep = q.flows_to("flowpkg.klass.Engine")
    kinds = {r["type"] for r in q.references_to("flowpkg.klass.Engine")}
    assert "inherits" in kinds
    assert rep["non_call_refs"] >= 1
    md = render_impact(q, "flowpkg.klass.Engine")
    assert "cannot appear in a flow at all" in md


def test_the_depth_bound_is_stated_when_nothing_reaches(q):
    """R1-C50/D9 replaced the bare "No entry point reaches it within N step(s)" here:
    a head one step past the bound is a different answer from no head at all, and the
    only one a reader can act on. The bare sentence survives for the case that really
    is empty — see `test_never_modelled_by_the_call_layer_is_not_an_empty_flow_list`."""
    md = render_impact(q, "flowpkg.leaf.hit", flow_depth=1)
    assert "No entry point within 1 step(s)" in md
    assert "1 reach it further out, the nearest at step **2**" in md
    assert "--flow-depth 2" in md


# -- D5: three kinds of emptiness -------------------------------------------------------

def test_never_modelled_by_the_call_layer_is_not_an_empty_flow_list(q):
    """`lonely` neither calls nor is called: the call layer has no node for it, so the
    honest answer is "nothing to say", not "no scenario touches it"."""
    rep = q.flows_to("flowpkg.klass.lonely")
    assert rep["in_call_graph"] is False and rep["flows"] == []
    reached = q.flows_to("flowpkg.leaf.hit", max_depth=0)
    assert reached["in_call_graph"] is True and reached["flows"] == []
    assert rep != reached, "the two empties must be distinguishable"


def test_an_absent_symbol_keeps_the_r1c44_answer(q):
    ghost = q.flows_to("flowpkg.nope.missing")
    assert ghost["in_call_graph"] is False and ghost["flows"] == []
    assert q.impact("flowpkg.nope.missing")["risk"] == "unknown"
    md = render_impact(q, "flowpkg.nope.missing")
    assert "No definition found" in md and "Flows reached" not in md


# -- D6: the transport cuts and declares it ---------------------------------------------

def test_the_transport_cut_declares_the_flows_list_in_its_own_vocabulary(q):
    env = {"ok": True, "result": {"symbol": "x", "markdown": "…", "impact": [
        {"refs": [{"source": f"s{i}"} for i in range(3)],
         "flows": {"flows": [{"entry": f"e{i}", "first_step": 1} for i in range(5)],
                   "beyond_depth": 0, "non_call_refs": 0, "in_call_graph": True}}]}}
    out = _compact_impact(env, 2)
    entry = out["result"]["impact"][0]
    assert entry["flows"]["flows_total"] == 5 and entry["flows"]["flows_shown"] == 2
    assert len(entry["flows"]["flows"]) == 2
    assert entry["refs_total"] == 3
    assert out["limit"]["total"] == 3, "the envelope block counts refs"
    assert "flows_shown" in out["limit"]["note"], "and says which list it does not count"


def test_the_op_carries_the_section(q):
    from codemap.serve.session import Session
    env = Session(q.graph).handle({"op": "impact",
                                   "args": {"symbol": "flowpkg.leaf.hit"}})
    assert env["ok"]
    rep = env["result"]["impact"][0]["flows"]
    assert _entries(rep)["flowpkg.entry.main"] == 2
    assert env["result"]["impact"][0]["refs"], "the blast radius is still there"


# -- the mutations ----------------------------------------------------------------------

def test_without_members_a_class_change_reaches_nothing(q, monkeypatch):
    """R1-C37: the check has been shown the defect. Targeting the symbol alone — the
    obvious implementation — makes a class change invisible, since a flow calls the
    method, not the class. And it fails *silently*, as `in_call_graph: false`, which
    reads as "nothing to say" rather than as a bug."""
    assert q.flows_to("flowpkg.klass.Widget")["flows"], "the fixed code sees it"
    monkeypatch.setattr(Query, "_member_ids", lambda self, sid: {sid})
    rep = q.flows_to("flowpkg.klass.Widget")
    assert rep["in_call_graph"] is False and rep["flows"] == []


def test_a_non_shortest_walk_would_report_the_later_step(q):
    """The second defect this pins: first-path-wins instead of shortest. `main` reaches
    `hit` through `fast` in 2 steps and through `slow → detour` in 3; a depth-first walk
    that takes the branches in the other order answers 3, and 3 is a different decision —
    it says the change is buried deep in the scenario when it is one call from the top."""
    def dfs(node, targets, depth=0, seen=frozenset()):
        if node in targets:
            return depth
        for nxt in sorted(q._calls.successors(node), reverse=True):  # slow before fast
            if nxt not in seen:
                got = dfs(nxt, targets, depth + 1, seen | {node})
                if got is not None:
                    return got
        return None

    assert dfs("flowpkg.entry.main", {"flowpkg.leaf.hit"}) == 3, "the defect's answer"
    assert _entries(q.flows_to("flowpkg.leaf.hit"))["flowpkg.entry.main"] == 2
