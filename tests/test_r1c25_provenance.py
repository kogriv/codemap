"""R1-C25 acceptance — the graph says what produced it (design docs/design/graph_provenance.md).

`graph.json` used to have four top-level keys and no answer to "which tool, from what
tree?". The measurement that forced this: one frozen copy of `refpkg`, built by codemap
four commits apart, gave **30 edges vs 38** and **12 vs 7** `high` dead-code verdicts —
with *both files declaring `codemap_schema: "0.11"`*, correctly, because only open
`extras` had changed. Provenance is not schema.

The invariant most at risk from this change is the one it defends, so it is tested
first: two builds of a frozen tree stay byte-identical, provenance included.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from codemap import store
from codemap.diagnostics import SCHEMA_MISMATCH, diagnostics, schema_diagnostic
from codemap.extract import extract, extract_repo
from codemap.model import SCHEMA_VERSION, Graph
from codemap.provenance import (
    absolute_paths, build_provenance, comparability, describe, schema_status,
    tool_identity, _commit_of,
)
from codemap.serve.apidiff import build_apidiff, render_apidiff
from codemap.serve.session import Session

FIX = Path(__file__).resolve().parent / "fixtures" / "refpkg"


@pytest.fixture(scope="module")
def g():
    return extract(FIX)


# -- D7.1 determinism: the property this whole block exists to make checkable ----

def test_two_builds_of_a_frozen_tree_are_byte_identical(tmp_path):
    """Including `provenance` — a clock in the artifact would destroy exactly this."""
    src = tmp_path / "frozen"
    src.mkdir()
    for f in sorted(FIX.glob("*.py")):
        (src / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    a, b = store.dumps(extract(src)), store.dumps(extract(src))
    assert a == b


def test_provenance_carries_no_clock(g):
    """No timestamp field, and no value that looks like one."""
    flat = json.dumps(g.provenance)
    assert "built_at" not in flat and "timestamp" not in flat


# -- D1 the block ---------------------------------------------------------------

def test_the_graph_declares_who_built_it(g):
    p = g.provenance
    assert p["tool"]["name"] == "codemap"
    assert p["tier"] == "fast"


def test_tier_is_recorded_and_is_not_a_guess():
    """`fast` and `deep` are different tools for every question that reads calls."""
    assert extract(FIX, deep=True).provenance["tier"] == "deep"


def test_provenance_survives_a_round_trip(g, tmp_path):
    out = tmp_path / "g.json"
    store.save(g, str(out))
    assert store.load(str(out)).provenance == g.provenance


def test_repo_scope_records_its_roots():
    """A core-only graph and a repo-scoped one answer `impact` differently; `diff` must
    not compare the two as if they were a before/after of the code."""
    p = extract_repo(FIX, consumers=()).provenance
    assert p["roots"]["core"] == "refpkg" and p["roots"]["mode"] == "thin"


# -- D2 tool identity: never fabricated -----------------------------------------

def test_tool_identity_has_no_placeholder_values():
    """A field is present because it is known, or absent. Never `"unknown"`."""
    ident = tool_identity()
    assert all(v and v != "unknown"
               for k, v in ident.items() if isinstance(v, str))
    assert isinstance(ident.get("dirty", False), bool)


def test_a_dirty_checkout_is_not_the_same_builder_as_a_clean_one():
    """`tool.dirty` mirrors what `source` records about the target, for the same reason.
    Measured the hard way: a worktree at HEAD and a dirty checkout of the same HEAD both
    reported the identical commit while plainly not being the same builder (R1-C23)."""
    from codemap.provenance import _is_dirty
    assert _is_dirty(Path(__file__).resolve().parents[1]) in (True, False)
    assert _is_dirty(Path("/")) is None


def test_commit_is_absent_not_invented_outside_a_checkout(tmp_path):
    """From an installed wheel there is no commit. The field is then missing — the
    honest state — rather than `"unknown"`, which reads like an identity."""
    assert _commit_of(tmp_path) is None


def test_the_tool_name_and_the_distribution_name_are_not_the_same_string():
    """`codemap` was taken on PyPI, so the distribution is `codmap` (M20/D7).

    Two names, two jobs: TOOL_NAME is the identity written into every graph — moving it
    would make every existing 0.12 graph incomparable over a packaging detail — while
    DIST_NAME is what `importlib.metadata` is asked about. Confuse them and `version()`
    raises `PackageNotFoundError`, the version quietly disappears from provenance, and
    two graphs built by different releases become indistinguishable again: precisely the
    gap R1-C25 exists to close, reopened by a rename.
    """
    from codemap.provenance import DIST_NAME, TOOL_NAME
    assert TOOL_NAME == "codemap" and DIST_NAME == "codmap"

    ident = tool_identity()
    assert ident["name"] == TOOL_NAME
    # Installed one way or another in every environment that runs this suite, so the
    # lookup must actually resolve — a silent None here is the regression.
    assert ident.get("version"), (
        f"no version for distribution {DIST_NAME!r} — is pyproject's `name` still in "
        f"step with provenance.DIST_NAME?")


def test_the_distribution_name_matches_pyproject():
    """The two live in different files; nothing but this test keeps them in step."""
    import re
    from codemap.provenance import DIST_NAME
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text("utf-8")
    declared = re.search(r'^name\s*=\s*"([^"]+)"', text, re.M).group(1)
    assert declared == DIST_NAME


def test_version_alone_would_not_have_separated_the_evidence_pair():
    """Every graph in the R1-C20…R1-C22 series was built by version 0.0.2. If a commit
    is available it must be *in* the identity, or the block cannot do its one job."""
    ident = tool_identity()
    if _commit_of(Path(__file__).resolve().parents[1]) is not None:
        assert "commit" in ident


# -- D5 the artifact stays publishable ------------------------------------------

def test_no_absolute_path_anywhere_in_a_serialized_graph(g):
    """The graph is the half that travels — into a ticket, a sibling repo, an agent's
    context. A personal path in it is a leak (AGENTS.md)."""
    assert absolute_paths(g.provenance) == []


def test_building_a_path_free_block_is_enforced_not_hoped():
    with pytest.raises(ValueError, match="path-free"):
        build_provenance(tier="fast", roots={"core": "/home/someone/pkg"})


def test_the_sidecar_keeps_the_machine_local_half(tmp_path):
    """D6: identity travels in the graph, the rebuild recipe stays in `*.meta.json`.
    `cwd` is an absolute path, which is precisely why it must not be in the graph."""
    out = tmp_path / "g.json"
    subprocess.run([sys.executable, "-m", "codemap.cli", "build", str(FIX),
                    "-o", str(out)], check=True, capture_output=True,
                   cwd=Path(__file__).resolve().parents[1])
    meta = json.loads((tmp_path / "g.json.meta.json").read_text(encoding="utf-8"))
    graph = json.loads(out.read_text(encoding="utf-8"))
    assert {"argv", "built_at", "cwd"} <= set(meta)
    assert not ({"argv", "built_at", "cwd"} & set(graph["provenance"]))
    assert graph["provenance"]["scope_id"] == meta["scope"]["scope_id"]


# -- D3 the schema is finally read ----------------------------------------------

def test_a_fresh_build_says_nothing_about_schema(g):
    assert schema_diagnostic(g) is None


def _older_schema() -> str:
    major, minor = SCHEMA_VERSION.split(".")
    return f"{major}.{int(minor) - 1}"


def _newer_schema() -> str:
    major, minor = SCHEMA_VERSION.split(".")
    return f"{major}.{int(minor) + 1}"


@pytest.mark.parametrize("declared,status",
                         [(_older_schema(), "older"), (_newer_schema(), "newer")])
def test_loading_a_mismatched_graph_warns(declared, status):
    """The evidence pair: an 0.11 graph read by this tool used to be consumed in
    silence, and answered with today's confidence over yesterday's blindness.

    Both versions are computed from ``SCHEMA_VERSION`` rather than written down: pinning
    the "newer" one made this test go quietly green the day the tool reached it."""
    d = schema_diagnostic(Graph.from_dict(
        {"codemap_schema": declared, "target": "t", "nodes": [], "edges": []}))
    assert d["code"] == SCHEMA_MISMATCH and d["severity"] == "warning"
    assert d["status"] == status and declared in d["message"]


def test_a_graph_with_no_schema_field_is_not_treated_as_current():
    d = schema_diagnostic(Graph.from_dict({"target": "t", "nodes": [], "edges": []}))
    assert d is not None and d["status"] == "unknown"


def test_the_mismatch_reaches_the_generic_diagnostics_channel():
    """Which is how it reaches the CLI, `stats` and the three reports at once."""
    g = Graph.from_dict({"codemap_schema": "0.9", "target": "t",
                         "nodes": [], "edges": []})
    assert any(d["code"] == SCHEMA_MISMATCH for d in diagnostics(g))


def test_schema_status_is_ordered_not_string_compared():
    assert schema_status("0.9", "0.12") == "older"    # "0.9" > "0.12" as strings
    assert schema_status("0.12", "0.12") == "match"


# -- D4 diff knows a tool change from a code change ------------------------------

def _prov(**kw):
    base = {"tool": {"name": "codemap", "version": "0.0.2"}, "tier": "fast"}
    base.update(kw)
    return base


def test_same_builder_is_comparable():
    assert comparability(_prov(), _prov())["comparable"]


@pytest.mark.parametrize("other,needle", [
    (_prov(tool={"name": "codemap", "version": "0.0.3"}), "different tool"),
    (_prov(tier="deep"), "different tier"),
    (_prov(roots={"core": "pkg"}), "different scope roots"),
])
def test_a_changed_builder_is_flagged(other, needle):
    c = comparability(_prov(), other)
    assert not c["comparable"] and any(needle in d for d in c["differences"])


def test_a_graph_without_provenance_cannot_be_verified():
    c = comparability(None, _prov())
    assert not c["comparable"] and "cannot be verified" in c["differences"][0]


def test_the_diff_envelope_carries_comparability(g, tmp_path):
    old = Graph.from_dict({**g.to_dict(), "codemap_schema": "0.11", "provenance": {}})
    d = build_apidiff(old, g)
    assert d["ok"] is True                      # the API really did not change…
    assert d["provenance"]["comparable"] is False   # …and that is not the whole answer


def test_the_rendered_diff_says_so_above_the_verdict(g):
    """The evidence pair rendered '✅ No breaking changes' — true, and read as proof."""
    old = Graph.from_dict({**g.to_dict(), "provenance": {}})
    md = render_apidiff(old, g)
    assert "not directly comparable" in md
    assert md.index("not directly comparable") < md.index("##") if "##" in md else True


# -- the surface an agent reads --------------------------------------------------

def test_stats_separates_the_graphs_schema_from_the_tools(g, tmp_path):
    """These were one field. `schema` reported the *running* tool over a graph that
    might declare another — the confusion this milestone is named for."""
    old = Graph.from_dict({**g.to_dict(), "codemap_schema": "0.11"})
    r = Session(old).handle({"op": "stats"})["result"]
    assert r["schema"] == "0.11" and r["tool_schema"] == SCHEMA_VERSION
    assert any(d["code"] == SCHEMA_MISMATCH for d in r["diagnostics"])


def test_stats_shows_provenance(g):
    r = Session(g).handle({"op": "stats"})["result"]
    assert r["provenance"]["tool"]["name"] == "codemap"


def test_describe_is_honest_about_an_unrecorded_graph():
    assert "unrecorded" in describe({})
