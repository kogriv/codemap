"""R1-C59 — a drop in graph completeness between two builds of one input went unnoticed.

Measured on a frozen tree (`bquant@cb89a24`, the package alone): codmap 0.0.3 and the current
code read the **same** `scope_id` and produced −25 `imports`, −28 `references`, −26 `calls`
against each other. `build` wrote either graph without a word; `diff` said "different tool" —
*that* the builder changed, never *what it lost*. Post 04 is the same picture (30 edges against
38 on a frozen tree, one declared schema). R1-C25 taught the artifact to name its input and its
builder; it did not teach it to compare completeness.

The counts are derived from the two graphs at the moment of comparison and never stored, so
neither the schema nor the answer format moves (design D1). Compared only on one `scope_id`
and one tier (D2); a class has dropped at >= 3 edges and >= 1 % (D3, above the deep tier's
measured noise of single edges). Design: `docs/design/completeness_drop.md`.
"""

from __future__ import annotations

import copy

import pytest

from codemap import store
from codemap.cli import main
from codemap.model import Edge, Graph
from codemap.provenance import comparability, completeness_drops, describe_drops
from codemap.serve.apidiff import build_apidiff, render_apidiff

# Three method calls on a local `engine` — only jedi types the receiver, so a deep build has
# them and a deep build whose jedi answers nothing does not. The constructor call survives
# through the fast fallback, which is what makes the drop partial rather than total.
FILES = {
    "__init__.py": "",
    "core.py": ("class Engine:\n"
                "    def start(self):\n        return 1\n\n"
                "    def stop(self):\n        return 2\n\n"
                "    def reset(self):\n        return 3\n"),
    "app.py": ("from pkg.core import Engine\n\n\n"
               "def main():\n"
               "    engine = Engine()\n"
               "    engine.start()\n"
               "    engine.stop()\n"
               "    engine.reset()\n"),
}


class _SilentScript:
    """A jedi that imports, constructs and answers every question with nothing."""

    def __init__(self, *args, **kwargs):
        pass

    def goto(self, *args, **kwargs):
        return []

    def infer(self, *args, **kwargs):
        return []


@pytest.fixture()
def pkg(tmp_path):
    root = tmp_path / "pkg"
    root.mkdir()
    for rel, body in FILES.items():
        (root / rel).write_text(body)
    return root


def _build(capsys, *argv) -> tuple[int, str]:
    capsys.readouterr()
    rc = main(["build", *map(str, argv)])
    return rc, capsys.readouterr().err


def _graph(tier="fast", scope="sha256:aaaa", calls=300, imports=40) -> Graph:
    g = Graph(target="pkg")
    g.provenance = {"tier": tier, "scope_id": scope,
                    "tool": {"name": "codemap", "version": "0.0.21"}}
    for i in range(calls):
        g.add_edge(Edge("calls", f"pkg.a.f{i}", "pkg.b.g"))
    for i in range(imports):
        g.add_edge(Edge("imports", f"pkg.m{i}", "pkg.b"))
    return g


# -- build: the graph about to be overwritten is the comparison ----------------------------

def test_a_dependency_that_resolves_less_is_named_at_build(pkg, tmp_path, capsys, monkeypatch):
    """The acceptance shape on a fixture: same input, same tier, same tool — and jedi
    answering nothing. Before R1-C59 this rebuild was silent and exited 0."""
    out = tmp_path / "g.json"
    rc, err = _build(capsys, pkg, "-o", out, "--deep")
    assert rc == 0 and "completeness" not in err          # first build: nothing to compare
    before = store.load(str(out))

    import jedi
    monkeypatch.setattr(jedi, "Script", _SilentScript)
    rc, err = _build(capsys, pkg, "-o", out, "--deep")
    assert rc == 0, "a warning, never a refusal: rebuilding with another builder is legitimate"
    assert "[warning] completeness fell on the same input: calls 4 → 1 (−75.0 %)" in err
    after = store.load(str(out))
    assert len(after.edges) < len(before.edges), "and the new graph was still written"


def test_the_same_build_twice_is_silent(pkg, tmp_path, capsys):
    out = tmp_path / "g.json"
    _build(capsys, pkg, "-o", out)
    rc, err = _build(capsys, pkg, "-o", out)
    assert rc == 0 and "completeness" not in err


def test_an_unreadable_previous_graph_is_named_not_skipped(pkg, tmp_path, capsys):
    """Unreadable is not absent (R1-C27): say that nothing was compared, and still build."""
    out = tmp_path / "g.json"
    out.write_text("{ this is not a graph")
    rc, err = _build(capsys, pkg, "-o", out)
    assert rc == 0
    assert f"[note] the graph already at {out} could not be read" in err
    assert "completeness against it not compared" in err
    assert store.load(str(out)).target == "pkg"


# -- diff: the drop is one more difference, in both surfaces ------------------------------

def test_diff_names_the_drop_in_the_answer_and_on_stderr(pkg, tmp_path, capsys, monkeypatch):
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    _build(capsys, pkg, "-o", old, "--deep")
    import jedi
    monkeypatch.setattr(jedi, "Script", _SilentScript)
    _build(capsys, pkg, "-o", new, "--deep")
    a, b = store.load(str(old)), store.load(str(new))

    d = build_apidiff(a, b)
    assert d["provenance"]["comparable"] is False
    assert any(x.startswith("completeness fell") for x in d["provenance"]["differences"])
    assert "completeness fell on the same input: calls 4 → 1" in render_apidiff(a, b)

    capsys.readouterr()
    assert main(["diff", str(old), str(new)]) == 0
    assert "[warning] completeness fell on the same input" in capsys.readouterr().err


def test_a_diff_without_a_drop_does_not_move():
    """Control: the pair that loses nothing renders exactly as it did without the graphs."""
    a, b = _graph(), _graph()
    assert comparability(a.provenance, b.provenance, old_graph=a, new_graph=b) == \
        comparability(a.provenance, b.provenance)
    assert "completeness" not in render_apidiff(a, b)


# -- D2: what is compared, and what is not -----------------------------------------------

def test_another_input_is_not_compared():
    """A drop across a code change may be deleted code; it cannot be put on the tool."""
    assert completeness_drops(_graph(), _graph(scope="sha256:bbbb", calls=10)) is None


def test_another_tier_is_not_compared():
    """deep → fast loses jedi edges by construction; `different tier` already says why."""
    assert completeness_drops(_graph(tier="deep"), _graph(tier="fast", calls=10)) is None


def test_an_unrecorded_input_is_unknown_not_equal():
    a, b = _graph(scope=None), _graph(scope=None, calls=10)
    assert completeness_drops(a, b) is None


def test_compared_and_nothing_fell_is_an_empty_list_not_none():
    """R1-C44: "compared, nothing fell" and "not compared" are different answers."""
    assert completeness_drops(_graph(), _graph()) == []


# -- D3: the threshold, shown both sides of it (R1-C37) ----------------------------------

@pytest.mark.parametrize("old,new,flagged", [
    (20, 18, False),       # 2 edges, 10 % of a small class: the deep tier's noise is single edges
    (300, 297, True),      # 3 edges, 1 %
    (1000, 991, False),    # 9 edges, under 1 % of a large class
    (1000, 990, True),     # 10 edges, 1 %
    (40, 0, True),         # a class that vanished
])
def test_the_threshold_both_ways(old, new, flagged):
    a, b = _graph(calls=old), _graph(calls=new)
    drops = completeness_drops(a, b)
    assert bool(drops) is flagged, drops
    if flagged:
        assert drops == [{"type": "calls", "old": old, "new": new}]


def test_a_growing_class_is_not_a_drop():
    assert completeness_drops(_graph(calls=10), _graph(calls=400)) == []


def test_the_rendering_is_stable_and_sorted():
    a, b = _graph(calls=300, imports=40), _graph(calls=200, imports=10)
    drops = completeness_drops(a, b)
    assert describe_drops(drops) == ("completeness fell on the same input: "
                                     "calls 300 → 200 (−33.3 %), imports 40 → 10 (−75.0 %)")
    assert describe_drops(copy.deepcopy(drops)) == describe_drops(drops)
