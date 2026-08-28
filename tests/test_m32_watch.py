"""M3.2 acceptance — the auto-loop: source → incremental rebuild → served answer.

Three bricks were already here (M18 age, R1-C9 incremental, issue #3 honest freshness +
`reload`); this milestone is the glue that joins them, so the tests are mostly about the
*glue's* judgement calls rather than about extraction:

- what counts as a change is `scope_id` — the build's own manifest, not a second notion;
- a burst of edits is one rebuild, not one per keystroke (debounce);
- an act that did not take effect does **not** advance the baseline, so a failed reload
  is retried instead of leaving a server confidently answering from the old graph;
- a probe that raises does not kill a loop whose job is to outlive a messy tree.

The state machine is driven with an injected clock, so the suite waits for nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codemap.watch import DebouncedPoller, mtime_probe, scope_probe


class Clock:
    """A hand-cranked monotonic clock: `sleep` advances it, nothing blocks."""

    def __init__(self) -> None:
        self.t = 0.0

    def sleep(self, seconds: float) -> None:
        self.t += seconds

    def __call__(self) -> float:
        return self.t


def _poller(tokens, acts, **kw):
    """A poller over a scripted token sequence; the last token repeats forever."""
    seq = list(tokens)

    def probe():
        return seq.pop(0) if len(seq) > 1 else seq[0]

    c = Clock()
    kw.setdefault("interval", 1.0)
    kw.setdefault("debounce", 2.0)
    return DebouncedPoller(probe, acts.append, clock=c, sleep=c.sleep, **kw)


# -- the state machine -------------------------------------------------------

def test_quiet_tree_never_acts():
    acts: list = []
    p = _poller(["A"], acts)
    assert [p.tick() for _ in range(5)] == ["quiet"] * 5
    assert acts == []


def test_a_change_acts_once_it_has_settled():
    acts: list = []
    p = _poller(["A", "B"], acts)          # changes on the first tick, then holds
    assert p.tick() == "settling"          # seen, not yet acted on
    assert p.tick() == "settling"          # still inside the 2 s debounce
    assert p.tick() == "acted"
    assert acts == ["B"] and p.tick() == "quiet"


def test_a_burst_is_one_rebuild_not_one_per_save():
    """The reason debounce exists: `git checkout` touches 300 files in a moment."""
    acts: list = []
    p = _poller(["A", "B", "C", "D", "E"], acts)
    for _ in range(8):
        p.tick()
    assert acts == ["E"], "each intermediate state must not trigger its own rebuild"
    assert p.acted == 1


def test_debounce_restarts_while_the_tree_keeps_moving():
    acts: list = []
    p = _poller(["A", "B", "B", "C"], acts, debounce=1.5)
    assert p.tick() == "settling"          # B seen
    assert p.tick() == "settling"          # B held 1 s — not yet 1.5 s
    assert p.tick() == "settling"          # C seen: the clock restarts, no act
    assert acts == []


def test_a_probe_that_raises_is_survived_not_fatal():
    """A tree mid-`git checkout` must not end the watcher."""
    calls = {"n": 0}

    def probe():
        calls["n"] += 1
        if calls["n"] in (2, 3):
            raise OSError("tree in flux")
        return "A" if calls["n"] < 4 else "B"

    c = Clock()
    acts: list = []
    p = DebouncedPoller(probe, acts.append, clock=c, sleep=c.sleep, debounce=0.0)
    assert [p.tick() for _ in range(4)] == \
        ["probe-failed", "probe-failed", "settling", "acted"]
    assert acts == ["B"]


def test_a_failed_act_is_retried_and_does_not_advance_the_baseline():
    """The honesty case: a failed reload must not be recorded as having happened.

    Advancing the baseline here would leave a server answering from the old graph while
    believing it is current — the exact silent staleness issue #3 removed elsewhere.
    """
    outcomes = [False, False, True]
    seen: list = []

    def act(token):
        seen.append(token)
        return outcomes.pop(0)

    c = Clock()
    p = DebouncedPoller(lambda: "B" if seen or True else "A", act,
                        clock=c, sleep=c.sleep, debounce=0.0)
    p.baseline = "A"                       # start from the pre-change state
    assert p.tick() == "settling"
    assert p.tick() == "act-failed" and p.acted == 0
    p.tick()                               # re-detects the same change…
    assert p.tick() == "act-failed"        # …and tries again
    p.tick()
    assert p.tick() == "acted" and p.acted == 1
    assert seen == ["B", "B", "B"]
    assert p.tick() == "quiet", "after a successful act the change is finally settled"


def test_run_returns_the_number_of_acts():
    acts: list = []
    p = _poller(["A", "B"], acts, debounce=0.0)
    assert p.run(cycles=4) == 1


# -- the probes: the same authority the build uses ---------------------------

def test_scope_probe_is_the_builds_own_notion_of_change(tmp_path):
    """Not our own file filter: the probe asks `resolve_scope`, so watcher and build
    cannot drift apart about what an input is."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text("def a():\n    return 1\n")
    probe = scope_probe(str(pkg))
    first = probe()
    assert first.startswith("sha256:") and probe() == first

    (pkg / "m.py").write_text("def a():\n    return 2\n")
    changed = probe()
    assert changed != first

    # Content, not mtime: rewriting identical bytes is not a change.
    (pkg / "m.py").write_text("def a():\n    return 2\n")
    assert probe() == changed

    # A file of a kind the build ignores is not a change either.
    (pkg / "notes.rst").write_text("hello")
    assert probe() == changed


def test_mtime_probe_reports_absence_without_raising(tmp_path):
    g = tmp_path / "graph.json"
    probe = mtime_probe(str(g))
    assert probe() is None                 # not an error — just "no artifact yet"
    g.write_text("{}")
    assert isinstance(probe(), float)


# -- end to end: the loop actually keeps a graph current ---------------------

def test_watch_rebuilds_the_graph_when_the_source_changes(tmp_path, monkeypatch, capsys):
    """One full turn of the source half, through the real CLI, with no sleeping.

    `--cycles` bounds the loop so this is a test and not a hang; the injected sleep is
    the CLI's own (time.sleep at interval 0), so what runs here is the shipped path.
    """
    from codemap import cli

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text("def a():\n    return b()\n\n\ndef b():\n    return 1\n")
    out = tmp_path / "g.json"

    rc = cli.main(["watch", str(pkg), "-o", str(out), "--interval", "0",
                   "--debounce", "0", "--cycles", "0"])
    assert rc == 0 and out.exists(), "a watcher that starts by watching nothing is a bug"
    ids = {n["id"] for n in json.loads(out.read_text())["nodes"]}
    assert "pkg.m.c" not in ids

    (pkg / "m.py").write_text("def a():\n    return b()\n\n\ndef b():\n    return c()"
                              "\n\n\ndef c():\n    return 2\n")
    # Started over an artifact that is already behind the tree: it must catch up at once,
    # not wait for the next edit — otherwise "the watcher is running" would mean nothing.
    assert cli.main(["watch", str(pkg), "-o", str(out), "--interval", "0",
                     "--debounce", "0", "--cycles", "0"]) == 0
    graph = json.loads(out.read_text())
    ids = {n["id"] for n in graph["nodes"]}
    assert "pkg.m.c" in ids, "the rebuild did not pick up the new symbol"
    assert {"source": "pkg.m.b", "target": "pkg.m.c", "type": "calls"} in [
        {"source": e["source"], "target": e["target"], "type": e["type"]}
        for e in graph["edges"]]
    assert "rebuilt in" in capsys.readouterr().err


def test_a_watcher_over_a_current_graph_does_not_rebuild_it(tmp_path, capsys):
    """The other half of the startup rule: catching up must not mean rebuilding always.

    The sidecar's recorded scope_id is compared against the tree — equal means the
    artifact is already the answer, and a rebuild would just burn a build for a
    byte-identical result.
    """
    from codemap import cli

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text("def a():\n    return 1\n")
    out = tmp_path / "g.json"
    cli.main(["watch", str(pkg), "-o", str(out), "--interval", "0", "--cycles", "0"])
    capsys.readouterr()

    cli.main(["watch", str(pkg), "-o", str(out), "--interval", "0", "--cycles", "0"])
    assert "rebuilt in" not in capsys.readouterr().err


def test_an_unreadable_sidecar_counts_as_stale(tmp_path):
    """"I cannot tell" must not resolve to "it is fine" (the R1-C27 lesson, again)."""
    from codemap.cli import _watch_start_is_stale

    out = tmp_path / "g.json"
    assert _watch_start_is_stale(str(out), "sha256:abc") is True   # no graph at all
    out.write_text("{}")
    assert _watch_start_is_stale(str(out), "sha256:abc") is True   # no sidecar
    Path(str(out) + ".meta.json").write_text("{not json")
    assert _watch_start_is_stale(str(out), "sha256:abc") is True   # unreadable sidecar


def test_watch_records_a_build_recipe_not_a_watch_recipe(tmp_path):
    """`codemap refresh` on a watched graph must rebuild it, not start a watcher.

    Left alone, M18 would record the *invoking* argv in the sidecar — and replaying a
    watch is a loop that never returns.
    """
    from codemap import cli

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text("def a():\n    return 1\n")
    out = tmp_path / "g.json"
    cli.main(["watch", str(pkg), "-o", str(out), "--interval", "0", "--cycles", "0"])

    argv = json.loads(Path(str(out) + ".meta.json").read_text())["argv"]
    assert argv[0] == "build" and "watch" not in argv
    assert "--incremental" in argv and str(out) in argv


def test_serve_watch_without_a_graph_says_so_instead_of_pretending(capsys):
    """A `--build` server has no artifact to follow; saying nothing would imply it does."""
    from argparse import Namespace
    from codemap.cli import _start_reload_watcher

    started = _start_reload_watcher(None, Namespace(graph=None, interval=1.0,
                                                    debounce=0.5))
    assert started is False
    assert "no artifact to follow" in capsys.readouterr().err


def test_serve_watch_reloads_the_session_when_the_artifact_moves(tmp_path):
    """The artifact half, driven directly: a rebuilt graph reaches the warm session."""
    from codemap.model import Graph, Node
    from codemap.serve.session import Session
    from codemap import store

    g = Graph(target="pkg")
    g.add_node(Node(id="pkg.a", kind="function", extras={"root": "core"}))
    path = tmp_path / "g.json"
    store.save(g, str(path))
    session = Session(store.load(str(path)), graph_path=str(path))
    assert session.handle({"op": "search", "args": {"term": "b"}})["result"] == []

    c = Clock()
    poller = DebouncedPoller(mtime_probe(str(path)),        # baseline = the loaded file
                             lambda _t: session.handle({"op": "reload"})["result"]
                             .get("reloaded", False),
                             clock=c, sleep=c.sleep, interval=0.0, debounce=0.0)

    g.add_node(Node(id="pkg.b", kind="function", extras={"root": "core"}))
    store.save(g, str(path))
    import os
    os.utime(path, (c.t + 10, c.t + 10))    # a rebuild the watcher must notice

    for _ in range(3):
        poller.tick()
    assert poller.acted == 1
    hits = session.handle({"op": "search", "args": {"term": "b"}})["result"]
    assert [h["id"] for h in hits] == ["pkg.b"]


@pytest.mark.parametrize("cmd", ["watch", "serve"])
def test_both_halves_expose_the_poll_knobs(cmd):
    """The cost of polling is real, so it must be tunable on both sides."""
    from codemap.cli import build_parser

    args = build_parser().parse_args(
        [cmd, "x", "-o", "g.json"] if cmd == "watch" else [cmd, "--graph", "g.json"])
    assert args.interval == 1.0
    # Different defaults on purpose: a source tree is edited in bursts, an artifact is
    # written once — so the artifact side only guards against a half-written read.
    assert args.debounce == (2.0 if cmd == "watch" else 0.5)
