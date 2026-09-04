"""R1-C47 — the incremental chain samples N times everywhere it samples at all.

Door (2) of R1-C43 asked for a periodic full rebuild. Measured on twenty real commits
(gaps/incremental_chain_replay_2026-09-04.md), the chain's misses come from single jedi
samples — the base, the fallback, the recompute of the touched modules — and not from
age: the periodic rebuild bought nothing. So `--repeat N` is let into the chain, with N a
property of the chain: the graph records it, and a different N is a different builder.

The deep tier on a four-module toy is a few seconds per sample; every test here that
builds does so on the deep tier because the fast tier refuses `--repeat` (R1-C45).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codemap import cli, store
from codemap.incremental import _same_builder, update_graph
from codemap.extract import extract
from codemap.model import Edge
from codemap.provenance import build_provenance, tool_identity
from codemap.scope import resolve_scope

BASE = "class Config:\n    def __init__(self, w):\n        self.width = w\n\n\ndef make():\n    return Config(3)\n"
LEAF = "from rs_pkg.base import make\n\n\ndef go():\n    c = make()\n    return c.width\n"
UTIL = "def helper(x):\n    return x * 2\n"


def _write(root: Path) -> Path:
    pkg = root / "rs_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "base.py").write_text(BASE)
    (pkg / "leaf.py").write_text(LEAF)
    (pkg / "util.py").write_text(UTIL)
    return pkg


def _scope(pkg):
    return resolve_scope(pkg, use_git=False)


# -- the builder identity includes N -------------------------------------------------------

def test_a_different_sample_count_is_a_different_builder():
    prov = build_provenance(tier="deep", samples={"runs": 2, "unstable": 0})
    assert _same_builder(prov, "deep", 2) is None
    assert _same_builder(prov, "deep", 3) == "samples-changed"
    assert _same_builder(prov, "fast", 2) == "builder-changed"
    assert _same_builder({}, "deep", 1) == "builder-changed"
    one = build_provenance(tier="deep")  # runs: 1
    assert _same_builder(one, "deep", 1) is None
    assert _same_builder(one, "deep", 2) == "samples-changed"


# -- the chain -----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    pkg = _write(tmp_path_factory.mktemp("chain"))
    base = extract(pkg, deep=True, repeat=2)
    return pkg, base, _scope(pkg)


def test_an_incremental_tick_keeps_the_chain_sample_count(chain):
    pkg, base, scope0 = chain
    (pkg / "util.py").write_text(UTIL + "\n\ndef helper2(x):\n    return helper(x) + 1\n")
    g, info = update_graph(base, pkg, scope0, _scope(pkg), deep=True, repeat=2)
    assert info["mode"] == "incremental" and "rs_pkg.util" in info["affected"]
    assert g.provenance["incremental"] is True
    assert g.provenance["samples"]["runs"] == 2
    assert "unstable" in g.provenance["samples"]
    assert ("rs_pkg.util.helper2", "rs_pkg.util.helper") in {
        (e.source, e.target) for e in g.edges if e.type == "calls"}
    assert ("rs_pkg.leaf.go", "rs_pkg.base.make") in {
        (e.source, e.target) for e in g.edges if e.type == "calls"}, "spliced from the base"


def test_a_request_with_another_n_restarts_the_chain_from_a_full_build(chain):
    pkg, base, scope0 = chain
    g, info = update_graph(base, pkg, scope0, _scope(pkg), deep=True, repeat=3)
    assert info == {"mode": "full", "affected": [], "reason": "samples-changed"}
    assert g.provenance["samples"]["runs"] == 3
    assert g.provenance["incremental"] is False


def test_the_fallback_full_build_keeps_the_chain_sample_count(tmp_path):
    pkg = _write(tmp_path)
    base = extract(pkg, deep=True, repeat=2)
    scope0 = _scope(pkg)
    for name in ("base.py", "leaf.py", "util.py"):  # every module: past the fallback fraction
        (pkg / name).write_text((pkg / name).read_text() + "\n# touched\n")
    g, info = update_graph(base, pkg, scope0, _scope(pkg), deep=True, repeat=2)
    assert info["mode"] == "full" and info["affected"]
    assert g.provenance["samples"]["runs"] == 2, \
        "the fallback used to be the chain's weakest point — one sample on the largest change"
    assert g.provenance["incremental"] is False


def test_seen_on_an_unaffected_module_survives_the_splice_and_is_counted(tmp_path):
    pkg = _write(tmp_path)
    base = extract(pkg, deep=True, repeat=2)
    scope0 = _scope(pkg)
    # pretend the base saw this edge in 1 of its 2 runs — the fact the splice must carry
    edge = next(e for e in base.edges if e.type == "calls" and e.source == "rs_pkg.leaf.go"
                and e.target == "rs_pkg.base.make")
    edge.extras["seen"] = 1
    (pkg / "util.py").write_text(UTIL + "\n\ndef helper2(x):\n    return helper(x) + 1\n")
    g, info = update_graph(base, pkg, scope0, _scope(pkg), deep=True, repeat=2)
    assert info["mode"] == "incremental" and "rs_pkg.leaf" not in info["affected"]
    carried = [e for e in g.edges if e.source == "rs_pkg.leaf.go" and e.target == "rs_pkg.base.make"]
    assert carried and carried[0].extras.get("seen") == 1
    assert g.provenance["samples"]["unstable"] >= 1, "recounted over the graph a reader holds"


def test_repeat_one_is_the_path_that_ran_before(tmp_path):
    """R1-C9's byte-identity on the fast tier is untouched: repeat=1 takes the old code."""
    pkg = _write(tmp_path)
    base = extract(pkg)
    scope0 = _scope(pkg)
    (pkg / "util.py").write_text(UTIL + "\n\ndef helper2(x):\n    return helper(x) + 1\n")
    inc, info = update_graph(base, pkg, scope0, _scope(pkg), deep=False, repeat=1)
    full = extract(pkg)
    strip = lambda g: json.dumps({k: v for k, v in json.loads(store.dumps(g)).items() if k != "provenance"}, sort_keys=True)
    assert strip(inc) == strip(full)
    assert inc.provenance["samples"] == {"runs": 1}


# -- the CLI and the watch recipe -------------------------------------------------------------

def test_the_cli_chains_and_the_second_run_is_incremental(tmp_path, capsys):
    pkg = _write(tmp_path)
    out = tmp_path / "graph.json"
    assert cli.main(["build", str(pkg), "--deep", "--repeat", "2", "-o", str(out)]) == 0
    (pkg / "util.py").write_text(UTIL + "\n\ndef helper2(x):\n    return helper(x) + 1\n")
    assert cli.main(["build", str(pkg), "--deep", "--repeat", "2", "--incremental", "-o", str(out)]) == 0
    err = capsys.readouterr().err
    assert "[incremental] incremental:" in err
    g = store.load(out)
    assert g.provenance["samples"]["runs"] == 2 and g.provenance["incremental"] is True
    assert cli.main(["build", str(pkg), "--repeat", "2", "--incremental", "-o", str(out)]) == 2, \
        "the fast tier still refuses --repeat"


def test_the_watch_recipe_carries_the_sample_count():
    import argparse
    args = argparse.Namespace(path="pkg", out="g.json", deep=True, consumer=None, docs=None,
                              mode="thin", repeat=3)
    argv = cli._watch_build_argv(args)
    assert argv[argv.index("--repeat") + 1] == "3"
    args.repeat = 1
    assert "--repeat" not in cli._watch_build_argv(args)
