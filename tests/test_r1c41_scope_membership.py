"""R1-C41 — the manifest must describe the input the graph was actually built from.

Raised by the second real target (issue #15): their sidecar listed 47 files with a
`git_blob` and a `sha256` on each while the graph carried 48, and the artifact a
consumer reads to answer *"what exactly was analyzed"* answered wrong in silence.

Measuring it made the defect wider than the report — no decoy directory is needed. In
git mode the manifest enumerated the *tracked* set while the extractor walked the
*filesystem*, so an untracked module (one that exists and has not been `git add`ed) or a
gitignored one was in the graph, absent from `scope.files`, and moved `scope_id` not at
all. Since `scope_id` is the cache key for `--incremental` and the `watch` probe, that is
a correctness defect and not a reporting one: `--incremental` printed
`unchanged: 0 module(s) recomputed` over a file that had just grown a new symbol.

Every test here drives the real CLI over a real git repo. The point is not the arithmetic
of a comparison — it is whether the condition can arise at all, which is the lesson 0.0.6
paid for.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from codemap import cli
from codemap.diagnostics import SCOPE_MEMBERSHIP, scope_membership_diagnostic
from codemap.provenance import build_provenance
from codemap.scope import resolve_scope, unlisted_files


def _git(base: Path, *args: str) -> None:
    subprocess.run(("git", "-C", str(base), *args), check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path) -> Path:
    """A git repo whose .gitignore excludes a *source* file the extractor still reads."""
    if not shutil.which("git"):
        pytest.skip("git not available")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "core.py").write_text("def a():\n    return 1\n")
    (tmp_path / ".gitignore").write_text("pkg/generated_*.py\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _build(repo: Path, out: Path, *extra: str) -> tuple[dict, dict]:
    assert cli.main(["build", str(repo / "pkg"), "-o", str(out), *extra]) == 0
    graph = json.loads(out.read_text(encoding="utf-8"))
    meta = json.loads(Path(str(out) + ".meta.json").read_text(encoding="utf-8"))
    return graph, meta


def _files(meta: dict) -> dict[str, dict]:
    return {f["path"]: f for f in meta["scope"]["files"]}


# -- D1: enumerate what will be read, not what the commit remembers ------------

def test_an_untracked_module_enters_the_manifest_and_moves_the_identity(repo, tmp_path):
    before, meta_before = _build(repo, tmp_path / "a.json")
    (repo / "pkg" / "untracked.py").write_text("def brand_new():\n    return 42\n")
    after, meta_after = _build(repo, tmp_path / "b.json")

    assert "pkg/untracked.py" not in _files(meta_before)
    assert "pkg/untracked.py" in _files(meta_after), (
        "a module that exists and has not been `git add`ed is read by the extractor; "
        "leaving it out of the manifest describes a different input than the graph")
    # …and the identity has to move, or every cache keyed on it is wrong (below).
    assert before["provenance"]["scope_id"] != after["provenance"]["scope_id"]


def test_incremental_recomputes_an_untracked_edit(repo, tmp_path):
    out = tmp_path / "inc.json"
    (repo / "pkg" / "untracked.py").write_text("def brand_new():\n    return 42\n")
    _build(repo, out)
    (repo / "pkg" / "untracked.py").write_text(
        "def brand_new():\n    return 42\n\n\ndef added_later():\n    return 7\n")
    graph, _ = _build(repo, out, "--incremental")
    assert any(n["id"].endswith("added_later") for n in graph["nodes"]), (
        "scope_id is the incremental cache key: if an untracked edit does not move it, "
        "the rebuild reports `unchanged` and serves a stale graph as current")


def test_git_mode_states_tracked_on_every_record_and_fs_mode_omits_it(repo):
    scope = resolve_scope(repo / "pkg")
    (repo / "pkg" / "untracked.py").write_text("x = 1\n")
    scope2 = resolve_scope(repo / "pkg")
    recs = {f["path"]: f for f in scope2["files"]}

    # stated on every record, never inferred from a missing key (R1-C28's rule)
    assert all("tracked" in f for f in scope["files"])
    assert recs["pkg/core.py"]["tracked"] is True
    assert recs["pkg/untracked.py"]["tracked"] is False
    assert "git_blob" not in recs["pkg/untracked.py"]  # there is none to record
    assert "git_blob" in recs["pkg/core.py"]

    # fs mode has no index, so the question does not arise and nothing is claimed
    fs = resolve_scope(repo / "pkg", use_git=False)
    assert fs["files"] and all("tracked" not in f for f in fs["files"])


# -- D2: membership named, not adopted ----------------------------------------

def test_a_gitignored_module_is_named_and_not_quietly_adopted(repo, tmp_path, capsys):
    (repo / "pkg" / "generated_version.py").write_text('def v():\n    return "1.2.3"\n')
    graph, meta = _build(repo, tmp_path / "g.json")

    # the repo says this file is not part of the tree; the manifest does not overrule it
    assert "pkg/generated_version.py" not in _files(meta)
    # …and the graph says so out loud instead of leaving a hole
    unlisted = graph["provenance"]["inputs"]["unlisted"]
    assert unlisted["count"] == 1
    assert unlisted["sample"] == ["pkg/generated_version.py"]
    assert "not listed in the input manifest" in capsys.readouterr().err


def test_the_count_check_stays_silent_on_exactly_this_state(repo, tmp_path):
    """The conservation law cannot catch it, which is why this check exists."""
    (repo / "pkg" / "generated_version.py").write_text('def v():\n    return "1.2.3"\n')
    graph, _ = _build(repo, tmp_path / "g.json")
    from codemap.diagnostics import module_count_diagnostic
    from codemap.store import load

    g = load(str(tmp_path / "g.json"))
    modules = sum(1 for n in g.nodes.values() if n.kind == "module")
    assert modules == graph["provenance"]["inputs"]["python_files"] == 3
    assert module_count_diagnostic(g) is None       # right to be silent: it agrees
    assert scope_membership_diagnostic(g)["code"] == SCOPE_MEMBERSHIP


# -- the trap: the two sides do not share an origin ----------------------------

def test_a_src_layout_is_not_a_violation(tmp_path):
    """Node paths are root-relative to the graph's base, manifest paths to the repo.

    On `src/pkg` those differ by a segment, and comparing the strings as they stand
    called both files of a healthy build unlisted — 2 of 2, measured before the fix.
    """
    if not shutil.which("git"):
        pytest.skip("git not available")
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
    (tmp_path / "src" / "pkg" / "core.py").write_text("def a():\n    return 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_core.py").write_text("from pkg.core import a\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")

    out = tmp_path / "s.json"
    assert cli.main(["build", str(tmp_path / "src" / "pkg"), "-o", str(out)]) == 0
    core_only = json.loads(out.read_text(encoding="utf-8"))
    assert cli.main(["build", str(tmp_path / "src" / "pkg"), "--consumer",
                     str(tmp_path / "tests"), "-o", str(out)]) == 0
    repo_scoped = json.loads(out.read_text(encoding="utf-8"))

    assert core_only["provenance"]["inputs"]["unlisted"]["count"] == 0
    assert repo_scoped["provenance"]["inputs"]["unlisted"]["count"] == 0


def test_a_file_outside_the_root_is_reduced_to_a_bare_name(tmp_path):
    """The files this check catches are the ones most likely to be absolute — and the
    provenance block refuses an absolute path by contract, so a naive record would turn
    the diagnostic into a build crash."""
    scope = {"root": str(tmp_path), "files": [{"path": "pkg/core.py"}]}
    result = unlisted_files(["pkg/core.py", "/elsewhere/decoy/impostor.py"], scope)

    assert result["count"] == 1
    assert result["sample"] == ["impostor.py"]      # not the absolute path
    assert result["outside_root"] is True
    # the contract that would have been violated (build_provenance raises on absolutes)
    block = build_provenance(tier="fast", inputs={"python_files": 1, "unlisted": result})
    assert block["inputs"]["unlisted"]["outside_root"] is True


# -- zero is a statement; unknown is an omission -------------------------------

def test_zero_is_stated_and_no_manifest_is_left_unstated(repo, tmp_path, monkeypatch):
    graph, _ = _build(repo, tmp_path / "clean.json")
    assert graph["provenance"]["inputs"]["unlisted"] == {
        "count": 0, "sample": [], "outside_root": False}

    from codemap import cli as cli_mod
    monkeypatch.setattr(cli_mod, "_resolve_scope_quietly", lambda args: None)
    out = tmp_path / "noscope.json"
    assert cli.main(["build", str(repo / "pkg"), "-o", str(out)]) == 0
    unresolved = json.loads(out.read_text(encoding="utf-8"))
    assert "unlisted" not in unresolved["provenance"]["inputs"], (
        "no manifest means the build could not compare — writing a zero there would "
        "turn an unknown into a clean bill of health")


def test_the_diagnostic_reports_nothing_when_there_is_nothing_to_report():
    class _G:
        provenance = {"inputs": {"unlisted": {"count": 0, "sample": [],
                                              "outside_root": False}}}

    assert scope_membership_diagnostic(_G()) is None
    _G.provenance = {"inputs": {}}                  # pre-R1-C41 graph
    assert scope_membership_diagnostic(_G()) is None
