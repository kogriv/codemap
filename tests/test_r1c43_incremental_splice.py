"""R1-C43 — an incremental deep graph says that parts of it were not recomputed.

Two separate things are pinned here, and only the second one is a *fix*:

1. ``provenance.incremental`` is written by every build path, ``false`` included — a
   consumer must be able to tell "recomputed in full" from "predates the field", and an
   absent key is the second of those (R1-C28).
2. The diagnostic that reads it, which fires on the deep tier only.

The third block pins a **known limit, not a guarantee**: ``_affected_modules`` rule (b)
reads the *old* graph, so an edge that build missed is a dependency it cannot see. On
the deep tier the old graph is one jedi sample, so a noise-dropped edge switches off the
recompute that would have restored it. Measured on an 88-module package — same edit,
same tree, the writer module was invalidated when the edge was present and not when it
was absent (gaps/incremental_noise_persistence_2026-09-02.md §6). These tests state that
behaviour deliberately: when it is fixed, they must be rewritten, not deleted quietly.
"""

from __future__ import annotations

import json
from pathlib import Path

from codemap import cli, store
from codemap.diagnostics import (
    DEEP_TIER_UNSTABLE, INCREMENTAL_DEEP_SPLICE, NOTE, WARNING,
    diagnostics, incremental_splice_diagnostic, render_lines,
)
from codemap.extract import extract
from codemap.incremental import _affected_modules, _module_indexer, update_graph
from codemap.model import Edge, Graph, Node
from codemap.provenance import build_provenance
from codemap.scope import resolve_scope

PKG_INIT = '"""Tiny package."""\n'
BASE = '''\
"""Base."""


class Config:
    """A config."""

    width = 10
'''
LEAF = '''\
"""Leaf."""

from .base import Config


def widen(c: Config) -> int:
    """Read a field off a typed parameter."""
    return c.width + 1
'''
OTHER = '''\
"""Unrelated to the pair above."""


def helper() -> int:
    return 1
'''


def _pkg(tmp_path: Path) -> Path:
    pkg = tmp_path / "tiny"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(PKG_INIT, encoding="utf-8")
    (pkg / "base.py").write_text(BASE, encoding="utf-8")
    (pkg / "leaf.py").write_text(LEAF, encoding="utf-8")
    (pkg / "other.py").write_text(OTHER, encoding="utf-8")
    return pkg


def _scope(pkg: Path) -> dict:
    return resolve_scope(pkg, use_git=False)


# -- 1. the field ------------------------------------------------------------

def test_a_full_build_declares_that_it_recomputed_everything(tmp_path):
    """`false` is a statement; the reader must not have to infer it from absence."""
    g = extract(_pkg(tmp_path), deep=False)
    assert g.provenance["incremental"] is False


def test_an_incremental_rebuild_declares_that_it_did_not(tmp_path):
    pkg = _pkg(tmp_path)
    g0 = extract(pkg, deep=False)
    s0 = _scope(pkg)
    (pkg / "other.py").write_text(OTHER + "\n# edited\n", encoding="utf-8")
    g1, info = update_graph(g0, pkg, s0, _scope(pkg), deep=False)
    if info["mode"] == "incremental":
        assert g1.provenance["incremental"] is True
    else:
        # a four-module fixture trips the >=50% full-rebuild fallback easily; a full
        # rebuild recomputes everything and must say so.
        assert g1.provenance["incremental"] is False


def test_the_cli_does_not_drop_the_flag_when_it_restamps_provenance(tmp_path):
    """The subtle one: `_cmd_build` **overwrites** the block `update_graph` produced.

    Nothing in the library-level tests can catch that — they read the graph object
    before the CLI touches it — so the field would have been written, overwritten with
    the default, and shipped as `false` on every incremental build.
    """
    pkg = _pkg(tmp_path)
    out = tmp_path / "g.json"
    assert cli.main(["build", str(pkg), "-o", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["provenance"]["incremental"] is False

    (pkg / "other.py").write_text(OTHER + "\n# edited\n", encoding="utf-8")
    assert cli.main(["build", str(pkg), "-o", str(out), "--incremental"]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))["provenance"]
    assert written["incremental"] is True


def test_an_untouched_tree_is_carried_over_too(tmp_path):
    """`mode: unchanged` returns the previous graph whole — nothing was recomputed."""
    pkg = _pkg(tmp_path)
    out = tmp_path / "g.json"
    assert cli.main(["build", str(pkg), "-o", str(out)]) == 0
    assert cli.main(["build", str(pkg), "-o", str(out), "--incremental"]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["provenance"]["incremental"] is True


def test_the_flag_survives_a_round_trip_through_the_artifact(tmp_path):
    g = extract(_pkg(tmp_path), deep=False)
    g.provenance = build_provenance(tier="deep", incremental=True)
    out = tmp_path / "g.json"
    store.save(g, out)
    assert store.load(out).provenance["incremental"] is True


# -- 2. the diagnostic -------------------------------------------------------

def _graph(tier: str, **kw) -> Graph:
    g = Graph(target="tiny")
    g.provenance = build_provenance(tier=tier, **kw)
    return g


def test_a_spliced_deep_graph_says_so():
    d = incremental_splice_diagnostic(_graph("deep", incremental=True))
    assert d is not None
    assert d["code"] == INCREMENTAL_DEEP_SPLICE
    assert d["severity"] == NOTE and d["severity"] != WARNING


def test_a_full_deep_graph_is_not_accused_of_splicing():
    assert incremental_splice_diagnostic(_graph("deep", incremental=False)) is None


def test_the_fast_tier_is_excluded_because_its_splice_is_exact():
    """Byte-identity to a full build is pinned there; there is no sample to freeze."""
    assert incremental_splice_diagnostic(_graph("fast", incremental=True)) is None


def test_a_graph_predating_the_field_is_not_guessed_about():
    g = Graph(target="tiny")
    g.provenance = {"tier": "deep", "tool": {"name": "codemap"}}  # no `incremental` key
    assert incremental_splice_diagnostic(g) is None


def test_it_reaches_the_aggregator_alongside_the_tier_note():
    """Two different facts about one graph: it is a sample, and the sample is frozen."""
    codes = {d["code"] for d in diagnostics(_graph("deep", incremental=True))}
    assert {INCREMENTAL_DEEP_SPLICE, DEEP_TIER_UNSTABLE} <= codes


def test_the_rendered_note_tells_the_reader_not_to_retry_incrementally():
    text = " ".join(render_lines(_graph("deep", incremental=True)))
    assert "full rebuild" in text or "full rebuild resamples" in text
    assert "ℹ️" in text


# -- 3. the limit this does NOT fix ------------------------------------------

def _old_graph(with_edge: bool) -> Graph:
    """Two old graphs differing by exactly one behavioral edge.

    `leaf.widen` writes/reads `base.Config.width`. The pair is *not* import-linked in
    the way rule (a) needs (that rule keys on module-level `imports` edges, added
    below only for the unrelated module), so rule (b) — which reads this graph — is the
    only route by which editing `base` can invalidate `leaf`.
    """
    g = Graph(target="tiny")
    for mid in ("tiny", "tiny.base", "tiny.leaf", "tiny.other"):
        g.add_node(Node(id=mid, kind="module"))
    g.add_node(Node(id="tiny.base.Config.width", kind="attribute"))
    g.add_node(Node(id="tiny.leaf.widen", kind="function"))
    if with_edge:
        g.add_edge(Edge(type="accesses", source="tiny.leaf.widen",
                        target="tiny.base.Config.width",
                        extras={"access": "read", "resolution": "deep"}))
    return g


def _affected_for(with_edge: bool) -> set[str]:
    old = _old_graph(with_edge)
    new = Graph(target="tiny")          # no fresh `imports` edge into base → rule (a) idle
    for mid in ("tiny", "tiny.base", "tiny.leaf", "tiny.other"):
        new.add_node(Node(id=mid, kind="module"))
    module_of = _module_indexer({n.id for n in old.nodes.values() if n.kind == "module"})
    changed = {"tiny.base"}
    return _affected_modules(old, new, changed, changed, module_of)


def test_the_edge_is_what_makes_the_writer_get_recomputed():
    assert "tiny.leaf" in _affected_for(with_edge=True)


def test_and_without_it_the_writer_is_silently_left_alone():
    """The measured failure, stated: a dropped edge is a dropped reason to recompute.

    Not an assertion that this is right — it is the limit R1-C43 names and does not
    close. Door (2) (a periodic full rebuild) or door (3) (restricting what an
    incremental deep graph may be used to conclude) would change this expectation.
    """
    assert "tiny.leaf" not in _affected_for(with_edge=False)
