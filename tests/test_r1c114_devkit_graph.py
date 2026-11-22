"""R1-C114 — devkit writes a contract only from a graph this codemap built over the current tree.

Expectations E1–E6 are in BACKLOG.md (R1-C114), written before the change. E1, E2 and E4 fail on 0.0.42:
there `init` and `ratchet` read whatever `.codemap/graph.json` holds.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from codemap.cli import build_parser, main
from codemap.devkit import install
from tests.test_r1c108_devkit import _pin, _repo

GRAPH = ".codemap/graph.json"


def _build(root: Path) -> None:
    (root / ".codemap").mkdir(exist_ok=True)
    subprocess.run([sys.executable, "-m", "codemap", "build", "pkg", "--consumer", "tests", "-o", GRAPH],
                   cwd=root, check=True, capture_output=True)


def _init(root: Path, capsys, *, build: bool = False) -> str:
    rc = install.init(root, package="pkg", consumers=["tests"], docs=[], agents_file=None, claude_hooks=False,
                      codex=False, ci=None, hook=False, build=build, ratchet=False, dry_run=False, force=False)
    assert rc == 0
    return capsys.readouterr().out


def test_e3_a_current_graph_of_this_codemap_gives_the_contract(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    root = _repo(tmp_path)
    _build(root)
    out = _init(root, capsys)
    assert "starter contract written" in out
    assert "[architecture]" in (root / "codemap.toml").read_text()


def test_e1_a_graph_behind_its_tree_gives_no_contract(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    for build in (False, True):  # with a graph present, `init` does not rebuild either way
        root = _repo(tmp_path / str(build))
        _build(root)
        (root / "pkg/c/o.py").write_text("def h():\n    return 2\n")
        out = _init(root, capsys, build=build)
        assert "contract not written: the graph is behind its source tree" in out, out
        assert "`codemap devkit ratchet`" in out
        assert not (root / "codemap.toml").exists()


def test_e2_a_graph_of_another_codemap_gives_no_contract(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    root = _repo(tmp_path)
    _build(root)
    built_by = install._version()
    monkeypatch.setattr(install, "_version", lambda: "9.9.9")
    out = _init(root, capsys)
    assert f"the graph was built by codemap {built_by}, this is codemap 9.9.9" in out, out
    assert not (root / "codemap.toml").exists()


def test_e4_ratchet_refuses_the_same_graphs_and_leaves_the_file(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    root = _repo(tmp_path)
    _build(root)
    _init(root, capsys)
    before = (root / "codemap.toml").read_text()
    (root / "pkg/a/m.py").write_text("from pkg.c.o import h\n\ndef f():\n    return h()\n")
    rc = main(["devkit", "ratchet", "--root", str(root)])
    err = capsys.readouterr().err
    assert rc == 2 and "behind its source tree" in err, err
    assert (root / "codemap.toml").read_text() == before
    _build(root)  # control: rebuilt with this codemap, the same command goes through
    assert main(["devkit", "ratchet", "--root", str(root)]) == 0


def test_e5_the_help_no_longer_promises_an_unwritten_contract():
    def sub(parser, name):
        return next(a for a in parser._actions if isinstance(getattr(a, "choices", None), dict)
                    and name in a.choices).choices[name]
    init = sub(sub(build_parser(), "devkit"), "init")
    text = next(a.help for a in init._actions if a.dest == "build")
    assert "then not written" not in text and "existing graph" in text


def test_e6_repin_moves_the_hook_too(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(install, "running_pin", lambda: ["/first/codemap"])
    root = _repo(tmp_path)
    install.init(root, package="pkg", consumers=[], docs=[], agents_file=None, claude_hooks=False, codex=False,
                 ci=None, hook=True, build=False, ratchet=False, dry_run=False, force=False)
    hook = root / ".git/hooks/post-commit"
    assert "C=/first/codemap" in hook.read_text()
    monkeypatch.setattr(install, "running_pin", lambda: ["/second/codemap"])
    install.update(root, force=False, repin=False, dry_run=False)
    assert "C=/first/codemap" in hook.read_text()  # update keeps the project's pin (D2)
    install.update(root, force=False, repin=True, dry_run=False)
    assert "C=/second/codemap" in hook.read_text()
