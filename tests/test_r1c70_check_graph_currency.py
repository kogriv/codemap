"""R1-C70 — `check --graph` says whether the graph is the tree it judges.

From the probe in gap `contract_silent_passes_2026-11-03` (row P6): a graph built before a forbidden
import was added answered "✅ Contract satisfied", exit 0, with no word about its age.
Design `docs/design/check_graph_currency.md`.

Pinned: S1–S5 and S7 of the design, the recipe parser agreeing with `build_parser`, and two
mutations (currency forced to "current", and the exit branch removed), each turning a test red.
"""

from __future__ import annotations

import os
import shutil
from unittest import mock

import pytest

from codemap import store
from codemap.serve import currency
from codemap.cli import build_parser, main
from codemap.serve.session import Session

TOML = '[architecture]\nforbidden = [{from="core", to="analysis"}]\n'


@pytest.fixture
def built(tmp_path, monkeypatch):
    """A clean tree, a graph built from it with its sidecar, and the contract beside it."""
    root = tmp_path / "proj"
    pkg = root / "cpkg"
    for d in (pkg, pkg / "core", pkg / "analysis"):
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").write_text("")
    (pkg / "analysis" / "b.py").write_text("X = 1\n")
    (pkg / "core" / "a.py").write_text("X = 2\n")
    (root / "codemap.toml").write_text(TOML)
    monkeypatch.chdir(root)
    assert main(["build", "cpkg", "-o", "g.json"]) == 0
    return root


def _check(capsys, *extra) -> tuple[int, str]:
    rc = main(["check", "--graph", "g.json", "--root", ".", *extra])
    return rc, capsys.readouterr().out


def _break(root):
    (root / "cpkg" / "core" / "a.py").write_text("from cpkg.analysis import b\n")


def test_s2_a_current_graph_says_so(built, capsys):
    rc, out = _check(capsys)
    assert rc == 0 and "matches its source tree" in out


def test_s1_a_graph_behind_its_source_fails_and_says_why(built, capsys):
    _break(built)
    rc, out = _check(capsys)
    assert rc == 2
    assert "behind its source tree" in out and "1 changed" in out
    assert "codemap refresh" in out and "--build" in out
    assert "Contract satisfied" in out, "the verdict about the recorded tree is still shown"


def test_s3_allow_stale_restores_the_verdicts_exit_but_keeps_the_line(built, capsys):
    _break(built)
    rc, out = _check(capsys, "--allow-stale")
    assert rc == 0 and "behind its source tree" in out


def test_s4_no_sidecar_is_named_not_assumed(built, capsys):
    _break(built)
    os.remove(built / "g.json.meta.json")
    rc, out = _check(capsys)
    assert rc == 0 and "currency not checked: no build recipe beside the graph" in out


def test_s5_a_new_file_makes_it_behind(built, capsys):
    (built / "cpkg" / "core" / "c.py").write_text("Z = 1\n")
    rc, out = _check(capsys)
    assert rc == 2 and "1 added" in out


def test_build_path_carries_no_currency_line(built, capsys):
    """S6 — the graph is built from the tree in this process; nothing to say."""
    rc = main(["check", "--build", "cpkg", "--root", "."])
    out = capsys.readouterr().out
    assert rc == 0 and "source tree" not in out and "currency" not in out


def test_s7_mcp_check_is_not_ok_on_a_graph_behind_its_tree(built):
    _break(built)
    s = Session(store.load(str(built / "g.json")), source_root=str(built),
                graph_path=str(built / "g.json"))
    res = s.handle({"op": "check", "args": {}})
    payload = res.get("result", res)
    assert payload["graph_currency"]["status"] == "behind"
    assert payload["ok"] is False


@pytest.mark.parametrize("argv", [
    ["build", "pkg", "-o", "g.json"],
    ["build", "src/pkg", "--consumer", "tests", "--consumer", "examples", "--docs", "docs", "-o", "x.json"],
    ["build", "pkg", "--deep", "--repeat", "3", "-o", "g.json", "--docs", "d"],
])
def test_the_recipe_parser_agrees_with_build_parser(argv):
    """serve.currency cannot import cli (layer contract), so it parses the recipe itself."""
    full = build_parser().parse_args(argv)
    assert currency.recipe_scope_args(argv) == (full.path, full.consumer or [], full.docs or [])


# -- mutation ---------------------------------------------------------------------------

def test_mutation_currency_forced_current_lets_the_stale_graph_pass(built, capsys):
    _break(built)
    with mock.patch.object(currency, "graph_currency",
                           lambda *a, **k: {"status": "current", "scope_id": "sha256:x" * 3}):
        assert _check(capsys)[0] == 0
    assert _check(capsys)[0] == 2


def test_mutation_without_the_exit_branch_the_stale_graph_passes(built, capsys):
    """The line is printed, but the pipeline proceeds: the defect with a footnote (D2)."""
    from codemap import cli
    _break(built)
    with mock.patch.object(cli, "_check_exit", lambda v, c, a: 2 if v else 0):
        rc, out = _check(capsys)
        assert rc == 0 and "behind its source tree" in out
    assert _check(capsys)[0] == 2
