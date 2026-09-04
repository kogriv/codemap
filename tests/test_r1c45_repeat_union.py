"""R1-C45 — one deep build is one sample; `--repeat N` unions N of them and says so.

The second target measured 175 full deep builds of one tree and found a real edge in
75 % of them (issue #16). Eight builds here agreed (5 of 8, the same `accesses` edge),
and the union of any three of the eight equalled the union of all eight in 55 cases
of 56. Design D7–D9 in docs/design/deep_tier_union.md.

What is pinned:

1. The merge is **per edge class**, not by `(type, source, target)`: a read and a write
   of one attribute survive as two edges; a `calls` site that one run resolved
   `imported` and another `deep` becomes the `deep` variant, whole.
2. What varied is written on the artifact (`extras.seen`, `provenance.samples`), and
   nothing is written when nothing varied — a single-sample build keeps its bytes.
3. The flag is refused out loud where it means nothing (fast tier) or would lie
   (`--incremental`), never swallowed.
4. The note carries the measured numbers in both wordings; the `runs ≥ 2` wording is
   checked on an **actual** union graph (R1-C37), not a hand-built provenance dict.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codemap import cli, store
from codemap.diagnostics import DEEP_TIER_UNSTABLE, NOTE, deep_tier_diagnostic, diagnostics
from codemap.extract import extract
from codemap.extract.union import BEHAVIOR_CALL_RES, merge_samples
from codemap.incremental import _BEHAVIOR_CALL_RES
from codemap.model import Edge, Graph, Node
from codemap.provenance import build_provenance, comparability, describe

FIX = Path(__file__).resolve().parent / "fixtures" / "deeppkg"


def _graph(edges, counters=None):
    g = Graph(target="pkg")
    for nid in ("pkg.a", "pkg.B", "pkg.B.m", "pkg.B.f"):
        g.add_node(Node(id=nid, kind="function"))
    for k, v in (counters or {}).items():
        g.nodes["pkg.a"].extras[k] = v
    for e in edges:
        g.add_edge(Edge(*e[:3], extras=dict(e[3])))
    return g


def _edges(g):
    return sorted((e.type, e.source, e.target, json.dumps(e.extras, sort_keys=True)) for e in g.edges)


# -- the merge, per class -----------------------------------------------------------------

def test_a_call_resolved_deep_in_one_run_wins_whole_and_the_extra_method_edge_is_marked():
    shallow = _graph([("calls", "pkg.a", "pkg.B", {"resolution": "imported", "callsites": 1})])
    deep = _graph([("calls", "pkg.a", "pkg.B", {"resolution": "deep", "callsites": 2}),
                   ("calls", "pkg.a", "pkg.B.m", {"resolution": "deep", "splat": True})])
    merged, stats = merge_samples([shallow, deep])
    by = {(e.source, e.target): e.extras for e in merged.edges}
    assert by[("pkg.a", "pkg.B")] == {"resolution": "deep", "callsites": 2}, \
        "the consumer's retraction: one call must not be listed as imported AND deep"
    assert by[("pkg.a", "pkg.B.m")] == {"resolution": "deep", "splat": True, "seen": 1}
    assert len(merged.edges) == 2
    assert stats == {"runs": 2, "unstable": 1}


def test_the_order_of_runs_does_not_change_the_result():
    shallow = _graph([("calls", "pkg.a", "pkg.B", {"resolution": "imported", "callsites": 1})])
    deep = _graph([("calls", "pkg.a", "pkg.B", {"resolution": "deep", "callsites": 2})])
    assert _edges(merge_samples([shallow, deep])[0]) == _edges(merge_samples([deep, shallow])[0])


def test_a_read_and_a_write_of_one_attribute_are_two_edges_not_one():
    """`(type, source, target)` would collapse these; 96 such pairs exist in one bquant build."""
    pair = [("accesses", "pkg.a", "pkg.B.f", {"access": "read", "resolution": "self"}),
            ("accesses", "pkg.a", "pkg.B.f", {"access": "write", "resolution": "self"})]
    merged, stats = merge_samples([_graph(pair), _graph(pair)])
    assert len(merged.edges) == 2
    assert all("seen" not in e.extras for e in merged.edges)
    assert stats == {"runs": 2, "unstable": 0}


def test_a_construct_write_and_a_deep_write_are_two_sites_and_both_survive():
    pair = [("accesses", "pkg.a", "pkg.B.f", {"access": "write", "resolution": "construct"}),
            ("accesses", "pkg.a", "pkg.B.f", {"access": "write", "resolution": "deep"})]
    merged, _ = merge_samples([_graph(pair), _graph(pair)])
    assert sorted(e.extras["resolution"] for e in merged.edges) == ["construct", "deep"]


def test_an_accesses_edge_missing_from_one_run_is_kept_and_counted():
    edge = ("accesses", "pkg.a", "pkg.B.f", {"access": "write", "resolution": "deep"})
    merged, stats = merge_samples([_graph([edge]), _graph([]), _graph([edge])])
    assert merged.edges[0].extras == {"access": "write", "resolution": "deep", "seen": 2}
    assert stats == {"runs": 3, "unstable": 1}


def test_node_counters_take_the_run_that_resolved_the_most_sites():
    """Counters count sites and sites dedupe into edges: the measured node had three
    counter variants behind one flapping edge."""
    worse = _graph([], {"attr_access": {"out": 13, "resolved": 11, "unresolved": 2}})
    better = _graph([], {"attr_access": {"out": 13, "resolved": 13, "unresolved": 0}})
    merged, _ = merge_samples([worse, better])
    assert merged.nodes["pkg.a"].extras["attr_access"] == {"out": 13, "resolved": 13, "unresolved": 0}
    merged, _ = merge_samples([better, worse])
    assert merged.nodes["pkg.a"].extras["attr_access"] == {"out": 13, "resolved": 13, "unresolved": 0}


def test_a_single_sample_is_returned_untouched_and_unmeasured():
    g = _graph([("calls", "pkg.a", "pkg.B", {"resolution": "imported"})])
    merged, stats = merge_samples([g])
    assert merged is g
    assert stats == {"runs": 1}, "`unstable` cannot be measured from one run — absent, not 0"


def test_the_merge_class_and_the_splice_class_are_one_list():
    assert _BEHAVIOR_CALL_RES is BEHAVIOR_CALL_RES


# -- through extract(): an actual union graph ----------------------------------------------

@pytest.fixture(scope="module")
def union2():
    return extract(FIX, deep=True, repeat=2)


def test_extract_records_the_samples_and_contains_every_single_run_edge(union2):
    assert union2.provenance["samples"]["runs"] == 2
    assert "unstable" in union2.provenance["samples"]
    single = extract(FIX, deep=True)
    logical = {(e.type, e.source, e.target) for e in union2.edges}
    assert {(e.type, e.source, e.target) for e in single.edges} <= logical


def test_every_ordinary_build_says_it_is_one_sample():
    assert extract(FIX).provenance["samples"] == {"runs": 1}
    assert extract(FIX, deep=True, repeat=1).provenance["samples"] == {"runs": 1}
    assert build_provenance(tier="fast")["samples"] == {"runs": 1}


def test_repeat_one_changes_no_edge_byte():
    a, b = extract(FIX, repeat=1), extract(FIX)
    assert _edges(a) == _edges(b)
    assert not any("seen" in e.extras for e in a.edges)


# -- refused out loud ------------------------------------------------------------------------

def test_repeat_on_the_fast_tier_exits_2(capsys):
    assert cli.main(["build", str(FIX), "--repeat", "2"]) == 2
    assert "--deep" in capsys.readouterr().err


def test_repeat_with_incremental_exits_2(tmp_path, capsys):
    out = tmp_path / "graph.json"
    assert cli.main(["build", str(FIX), "--deep", "--repeat", "2", "--incremental", "-o", str(out)]) == 2
    assert "--incremental" in capsys.readouterr().err
    assert not out.exists()


def test_repeat_below_one_exits_2(capsys):
    assert cli.main(["build", str(FIX), "--deep", "--repeat", "0"]) == 2


def test_the_cli_writes_a_union_graph(tmp_path):
    out = tmp_path / "graph.json"
    assert cli.main(["build", str(FIX), "--deep", "--repeat", "2", "-o", str(out)]) == 0
    g = store.load(out)
    assert g.provenance["samples"]["runs"] == 2
    meta = json.loads((tmp_path / "graph.json.meta.json").read_text())
    assert "--repeat" in meta["argv"], "refresh replays the sidecar argv, so it must carry the flag"


# -- the note, both wordings -------------------------------------------------------------------

def _prov(tier, samples=None):
    g = Graph(target="pkg")
    g.provenance = {"tier": tier, "tool": {"name": "codemap", "version": "0.0.11"}}
    if samples is not None:
        g.provenance["samples"] = samples
    return g


def test_one_sample_names_the_measured_share_and_the_remedy():
    d = deep_tier_diagnostic(_prov("deep", {"runs": 1}))
    assert d["severity"] == NOTE and d["samples"] == 1
    assert "126 of 168" in d["message"] and "75 %" in d["message"]
    assert "--repeat" in d["message"]
    assert "absence" in d["consequence"]


def test_a_graph_older_than_the_field_gets_the_one_sample_wording():
    d = deep_tier_diagnostic(_prov("deep"))
    assert d["samples"] == 1 and "one build is one sample" in d["message"]


def test_a_union_graph_says_how_many_runs_and_what_varied(union2):
    """Fed an actual union (R1-C37), not a provenance dict: a mutation that drops the
    `runs >= 2` branch must fail here."""
    d = next(d for d in diagnostics(union2) if d["code"] == DEEP_TIER_UNSTABLE)
    assert d["samples"] == 2
    assert d["unstable"] == union2.provenance["samples"]["unstable"]
    assert "union of 2 deep" in d["message"]
    assert "extras.seen" in d["message"]
    assert "6.2 %" in d["message"], "0.25^2 at the measured rate"


def test_the_union_wording_counts_the_seen_edges_it_promises():
    d = deep_tier_diagnostic(_prov("deep", {"runs": 3, "unstable": 2}))
    assert "2 edge(s) were seen in fewer than 3 runs" in d["message"]
    assert "1.6 %" in d["message"]


def test_a_fast_graph_says_nothing_whatever_its_samples():
    assert deep_tier_diagnostic(_prov("fast", {"runs": 1})) is None


# -- the comparison caveat names the sample count on each side -------------------------------

def test_the_caveat_names_the_samples_on_each_side():
    old = _prov("deep", {"runs": 1}).provenance
    new = _prov("deep", {"runs": 3}).provenance
    c = comparability(old, new)
    assert c["comparable"] is True
    assert "old: 1 sample, new: 3 samples" in c["caveats"][0]


def test_the_caveat_says_unrecorded_for_a_graph_older_than_the_field():
    c = comparability(_prov("deep").provenance, _prov("deep", {"runs": 2}).provenance)
    assert "old: samples unrecorded, new: 2 samples" in c["caveats"][0]


def test_describe_mentions_samples_only_when_there_is_more_than_one():
    assert "samples" not in describe(_prov("deep", {"runs": 1}).provenance)
    assert "samples=3" in describe(_prov("deep", {"runs": 3}).provenance)
