"""R1-C31 — one path origin per graph, and a consumer symbol that has a file (#12).

Reported by the second target against item 5 of the list filed for them: `codemap tests`
ends in a ready-to-paste `pytest …` line, and when the build roots are not at the repo root
that line names a path that does not exist — while looking exactly like one that does.

    $ pytest tests/test_mod.py::test_f
    ERROR: file or directory not found

Reproducing it found the printed path was the symptom, not the defect. Each root was its
**own** origin: core files relative to the core package's parent, consumer files relative to
their own root's parent. With roots side by side those coincide, which is why the packaged
dogfood never showed it; with `src/pkg` beside `tests/`, one graph carried two coordinate
systems and nothing anywhere said so. At most one of `pkg/mod.py` and `tests/test_mod.py`
could be read from the repo root, and the artifact did not say which.

Three things follow, and they are separate on purpose:

- the **graph** gets one origin — the nearest common ancestor of the roots' parents;
- the **location** of that origin stays out of the graph (design D5: no absolute paths in a
  publishable artifact) and goes in the `*.meta.json` sidecar, which never travels;
- the **local** command resolves against that sidecar, and only when the file is really
  there — an unverifiable rewrite is not printed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from codemap.extract.roots import extract_repo, roots_base


def _repo(tmp_path, *, core="src/pkg", tests="tests"):
    """A tree whose roots do not share a parent — the shape the bug needs."""
    core_dir = tmp_path / core
    core_dir.mkdir(parents=True)
    (core_dir / "__init__.py").write_text("")
    (core_dir / "mod.py").write_text("def f():\n    return 1\n")
    tests_dir = tmp_path / tests
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_mod.py").write_text(
        "from pkg.mod import f\n\n\ndef test_f():\n    assert f() == 1\n")
    return core_dir, tests_dir


def _files(graph):
    return {n.id: n.file for n in graph.nodes.values()}


# -- one origin --------------------------------------------------------------

def test_paths_from_roots_in_different_directories_share_an_origin(tmp_path):
    core, tests = _repo(tmp_path)
    files = _files(extract_repo(core, consumers=(tests,), mode="full"))
    assert files["pkg.mod"] == "src/pkg/mod.py"
    assert files["tests.test_mod"] == "tests/test_mod.py"


def test_every_path_resolves_against_that_origin(tmp_path):
    """The property worth having, stated as a property: join and it exists."""
    core, tests = _repo(tmp_path)
    graph = extract_repo(core, consumers=(tests,), mode="full")
    base = roots_base(core, (tests,))
    for node in graph.nodes.values():
        if node.file:
            assert (base / node.file).exists(), node.id


def test_a_single_package_build_is_unaffected(tmp_path):
    """One root, so its parent is the origin — the same paths as before this change."""
    core, _ = _repo(tmp_path)
    assert _files(extract_repo(core))["pkg.mod"] == "pkg/mod.py"


def test_roots_are_recorded_relative_to_the_origin_not_by_basename(tmp_path):
    core, tests = _repo(tmp_path)
    roots = extract_repo(core, consumers=(tests,), mode="full").provenance["roots"]
    assert roots["core"] == "src/pkg"          # was "pkg": the `src/` segment was lost
    assert roots["consumers"] == ["tests"]


def test_the_graph_still_carries_no_absolute_path(tmp_path):
    """Design D5 — the artifact stays publishable. The origin is a machine location and
    must not be in it; the paths above are relative precisely so this holds."""
    core, tests = _repo(tmp_path)
    blob = json.dumps(extract_repo(core, consumers=(tests,), mode="full").to_dict())
    assert str(tmp_path) not in blob


# -- a consumer symbol has a file -------------------------------------------

def test_a_consumer_function_carries_its_file(tmp_path):
    """It had `lineno` and nothing else, so `search` answered a line number with no file
    while every core symbol answered both."""
    core, tests = _repo(tmp_path)
    graph = extract_repo(core, consumers=(tests,), mode="full")
    node = graph.nodes["tests.test_mod.test_f"]
    assert node.file == "tests/test_mod.py"
    assert node.lineno == 4


# -- and the line you paste actually runs -----------------------------------

@pytest.fixture
def built(tmp_path):
    """Built the way the reporter built it: roots one level down, run from the top."""
    core, tests = _repo(tmp_path, core="research/core/pkg", tests="research/tests")
    out = tmp_path / "g.json"
    subprocess.run([sys.executable, "-m", "codemap.cli", "build", str(core),
                    "--mode", "full", "--consumer", str(tests), "-o", str(out)],
                   cwd=tmp_path, capture_output=True, check=True)
    return tmp_path, out


def test_the_sidecar_records_the_origin(built):
    tmp_path, out = built
    meta = json.loads((tmp_path / "g.json.meta.json").read_text())
    assert meta["roots_base"] == str(tmp_path / "research")


def test_the_pytest_line_names_a_path_that_exists_from_here(built):
    tmp_path, out = built
    r = subprocess.run([sys.executable, "-m", "codemap.cli", "tests", "f",
                        "--graph", str(out)], cwd=tmp_path, capture_output=True, text=True)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("pytest ")][-1]
    path = line[len("pytest "):].split("::")[0]
    assert path == "research/tests/test_mod.py"
    assert (tmp_path / path).exists()


def test_the_graph_relative_id_is_what_the_op_returns(built):
    """Only the local command rewrites. The payload keeps the portable id, because a
    served answer may be read on a machine where this tree does not exist."""
    tmp_path, out = built
    r = subprocess.run([sys.executable, "-m", "codemap.cli", "tests", "f",
                        "--graph", str(out), "--format", "json"],
                       cwd=tmp_path, capture_output=True, text=True)
    payload = json.loads(r.stdout)
    assert payload["tests"][0]["node_id"] == "tests/test_mod.py::test_f"


def test_without_a_sidecar_the_path_is_left_alone_and_said_so(built):
    """A rewrite that cannot be verified is not printed — and the reader is told which
    directory the untouched path belongs to instead of finding out from pytest."""
    tmp_path, out = built
    os.remove(tmp_path / "g.json.meta.json")
    r = subprocess.run([sys.executable, "-m", "codemap.cli", "tests", "f",
                        "--graph", str(out)], cwd=tmp_path, capture_output=True, text=True)
    assert "pytest tests/test_mod.py::test_f" in r.stdout
    assert "relative to the build roots' common directory" in r.stderr
