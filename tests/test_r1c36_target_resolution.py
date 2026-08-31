"""R1-C36 — the graph describes the directory that was asked for, or nothing.

Found while doing something else: verifying the new `apidiff` rule on a real pair of
releases. Two tags were extracted to a scratch directory, both were built, and the graphs
came out with the *same* node ids and the *same* edge count — 2973 → 2973 — across nine
changed source files. Neither graph was of the tag it named. Both described the working
tree, because the build ran from the repo root.

`griffe.load(name, ...)` defaults to `try_relative_path=True`, which reinterprets the
module *name* as a path relative to the current directory, and that wins over the
`search_paths` we pass. So `codemap build /elsewhere/pkg`, run from a repo whose root
holds `pkg/`, analysed the local `pkg`. Exit 0, no warning, a complete and well-formed
graph of the wrong code — the failure this project keeps naming: an answer shaped exactly
like the right one.

It hides in the common case, where the two coincide (you build your own package from your
own repo root). It appears exactly where the difference matters: a tag archive, a
worktree, a copy — that is, in **any two-snapshot workflow**, which is what `codemap diff`
is for. A release gate comparing two builds resolved to the same tree reports "no API
changes" every time, and the more diligent the gate, the quieter the lie.

Two changes, and the second is the one that keeps this fixed:

* the name resolves through `search_paths` and nowhere else;
* after loading, the resolved file must sit under the requested directory, or the build
  raises. Whatever a future default, a `.pth` file or a namespace package does next, a
  mismatch here cannot be noticed downstream — so it is not allowed to be silent.

The absolute paths in `file` were a symptom of the same thing: the loaded files were not
under the given root, so relativising them silently gave up (D5 says the artifact carries
no absolute paths).
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from codemap.extract import extract

TOY = {
    "__init__.py": '"""A package that merely shares a name with another one."""\n',
    "only_here.py": "def unique_marker(x):\n    return x\n",
}


@pytest.fixture
def toy(tmp_path):
    """A package named `pkg`, in its own directory."""
    root = tmp_path / "elsewhere" / "pkg"
    root.mkdir(parents=True)
    for name, src in TOY.items():
        (root / name).write_text(src)
    return root


@pytest.fixture
def shadow(tmp_path):
    """A *different* package with the same name, in what will be the working directory."""
    root = tmp_path / "workdir" / "pkg"
    root.mkdir(parents=True)
    (root / "__init__.py").write_text("")
    (root / "impostor.py").write_text("def wrong_symbol():\n    return 0\n")
    return root.parent


def test_the_graph_is_of_the_directory_that_was_named(toy):
    g = extract(str(toy))
    assert {n.id for n in g.nodes.values() if n.kind == "function"} == {"pkg.only_here.unique_marker"}


def test_a_same_named_package_in_the_working_directory_does_not_win(toy, shadow, tmp_path):
    """The reproduction, at the CLI where it happened."""
    out = tmp_path / "g.json"
    r = subprocess.run([sys.executable, "-m", "codemap.cli", "build", str(toy), "-o", str(out)],
                       cwd=str(shadow), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    ids = {n["id"] for n in json.loads(out.read_text())["nodes"]}
    assert "pkg.only_here.unique_marker" in ids
    assert not any("impostor" in i for i in ids), "built the package in the cwd, not the one asked for"


def test_the_files_stay_relative_to_the_target(toy, shadow, tmp_path):
    """D5: the publishable artifact carries no absolute paths. They appeared when the
    resolved files were not under the given root and relativising gave up."""
    out = tmp_path / "g.json"
    subprocess.run([sys.executable, "-m", "codemap.cli", "build", str(toy), "-o", str(out)],
                   cwd=str(shadow), capture_output=True, text=True, check=True)
    files = [n["file"] for n in json.loads(out.read_text())["nodes"] if n["file"]]
    assert files and not any(f.startswith("/") for f in files)


def test_two_copies_of_one_package_give_two_different_graphs(tmp_path):
    """The property the release gate depends on: build A and build B must be able to
    disagree. Before the fix, both resolved to the same tree and the diff was empty."""
    a, b = tmp_path / "a" / "pkg", tmp_path / "b" / "pkg"
    for root, extra in ((a, "def only_in_a():\n    return 1\n"), (b, "def only_in_b():\n    return 2\n")):
        root.mkdir(parents=True)
        (root / "__init__.py").write_text("")
        (root / "mod.py").write_text(extra)
    ga = {n.id for n in extract(str(a)).nodes.values()}
    gb = {n.id for n in extract(str(b)).nodes.values()}
    assert "pkg.mod.only_in_a" in ga and "pkg.mod.only_in_a" not in gb
    assert "pkg.mod.only_in_b" in gb and "pkg.mod.only_in_b" not in ga
