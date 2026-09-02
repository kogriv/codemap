"""R1-C42 — the deep tier is not byte-stable, and the artifact must say so.

Raised by the second real target: seven builds of an unchanged clean tree, and in one
of them a real `calls` edge (resolved through `getattr`) was gone — 9524 edges against
9523. They had briefly concluded a regression between two releases from it, which is
the failure this suite exists to prevent: a consumer reading "deterministic" and
comparing two deep graphs as if every difference were a change in the code.

The instability itself was **known** — measured at R1-C9, and the reason the CI
determinism job runs the fast tier only. It lived in a comment in a workflow file,
while README said "deterministic" unqualified and `provenance.md` said two builds of an
unchanged tree are byte-identical. So the fix is disclosure in the places a consumer
actually reads: the graph's own diagnostics, and any comparison of two deep graphs.

Reproduced here on our own tree before the fix: ten deep builds → two distinct
artifacts (7/3), differing in two per-symbol call counters and no edges. The cause is
jedi's per-script execution budget: an inference that runs out of it returns nothing,
and nothing reads as `unresolved`. That is not testable in a unit suite — a build takes
~40 s and flips about one run in three — so what is pinned here is the disclosure.
"""

from __future__ import annotations

from codemap.diagnostics import DEEP_TIER_UNSTABLE, NOTE, WARNING, deep_tier_diagnostic, diagnostics
from codemap.model import Graph
from codemap.provenance import comparability
from codemap.serve.apidiff import render_apidiff


def _graph(tier: str) -> Graph:
    g = Graph(target="pkg")
    g.provenance = {"tier": tier, "tool": {"name": "codemap", "version": "0.0.9"}}
    return g


# -- the note on the artifact --------------------------------------------------

def test_a_fast_graph_says_nothing():
    assert deep_tier_diagnostic(_graph("fast")) is None


def test_a_deep_graph_declares_its_noise_floor():
    d = deep_tier_diagnostic(_graph("deep"))
    assert d is not None and d["code"] == DEEP_TIER_UNSTABLE
    assert "not byte-stable" in d["message"]
    assert d["consequence"]


def test_it_is_a_note_and_not_a_warning():
    """A warning says the findings below are invalid. Nothing here is invalid — the
    graph is sound, it is one sample of a slightly fuzzy function (issue #8's rule)."""
    d = deep_tier_diagnostic(_graph("deep"))
    assert d["severity"] == NOTE != WARNING


def test_it_reaches_the_surface_a_consumer_reads():
    codes = [d["code"] for d in diagnostics(_graph("deep"))]
    assert DEEP_TIER_UNSTABLE in codes
    assert DEEP_TIER_UNSTABLE not in [d["code"] for d in diagnostics(_graph("fast"))]


def test_a_pre_provenance_graph_is_not_guessed_about():
    g = Graph(target="pkg")
    g.provenance = {}
    assert deep_tier_diagnostic(g) is None


# -- the caveat on a comparison ------------------------------------------------

def test_two_deep_graphs_stay_comparable_and_carry_the_caveat():
    c = comparability(_graph("deep").provenance, _graph("deep").provenance)
    assert c["comparable"] is True, "matching tiers are the right pair — never a refusal"
    assert c["caveats"] and "not byte-stable" in c["caveats"][0]


def test_two_fast_graphs_carry_no_caveat():
    c = comparability(_graph("fast").provenance, _graph("fast").provenance)
    assert c["caveats"] == []


def test_mixed_tiers_are_still_an_incomparability_not_a_caveat():
    c = comparability(_graph("fast").provenance, _graph("deep").provenance)
    assert c["comparable"] is False
    assert any("different tier" in d for d in c["differences"])
    assert c["caveats"] == [], "a caveat must not soften a genuine incomparability"


def test_the_rendered_diff_shows_it_above_the_verdict():
    out = render_apidiff(_graph("deep"), _graph("deep"))
    assert "not byte-stable" in out
    head = out.split("## ")[0]
    assert "not byte-stable" in head, "a footnote is not a disclosure"
