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



def _fake_codemap(where: Path) -> str:
    """An installed-looking `codemap` outside the repository (R1-C121 keeps only such a pin)."""
    where.mkdir(parents=True, exist_ok=True)
    exe = where / "codemap"
    exe.write_text("#!/bin/sh\n# stands in for `from codemap.cli import main`\necho codemap 0.0.0\n")
    exe.chmod(0o755)
    return str(exe)

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
    for build in (False,):  # with building allowed, R1-C117 rebuilds instead (test_c117_e2)
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
    monkeypatch.setattr(install, "running_pin", lambda: [_fake_codemap(tmp_path / "bin1")])
    root = _repo(tmp_path)
    install.init(root, package="pkg", consumers=[], docs=[], agents_file=None, claude_hooks=False, codex=False,
                 ci=None, hook=True, build=False, ratchet=False, dry_run=False, force=False)
    hook = root / ".git/hooks/post-commit"
    assert f"C={tmp_path}/bin1/codemap" in hook.read_text()
    monkeypatch.setattr(install, "running_pin", lambda: [_fake_codemap(tmp_path / "bin2")])
    install.update(root, force=False, repin=False, dry_run=False)
    assert f"C={tmp_path}/bin1/codemap" in hook.read_text()  # update keeps the project's pin (D2)
    install.update(root, force=False, repin=True, dry_run=False)
    assert f"C={tmp_path}/bin2/codemap" in hook.read_text()


# --------------------------------------------------------------------------- R1-C117


def _init_with(root: Path, capsys, **kw) -> tuple[int, str]:
    args = dict(package="pkg", consumers=["tests"], docs=[], agents_file=None, claude_hooks=False, codex=False,
                ci=None, hook=False, build=True, ratchet=False, dry_run=False, force=False)
    args.update(kw)
    rc = install.init(root, **args)
    return rc, capsys.readouterr().out


def test_c117_e1_e5_a_rules_file_inside_docs_leaves_the_graph_current(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    for where in ("docs/rules.md", "RULES.md"):  # E1 inside a --docs root; E5 outside, the control
        root = _repo(tmp_path / where.replace("/", "_"))
        (root / "docs").mkdir()
        (root / "docs/a.md").write_text("# a\n")
        _init_with(root, capsys, docs=["docs"], agents_file=where)
        assert (root / where).is_file()
        rc = main(["check", "--graph", str(root / GRAPH), "--root", str(root), "--require-contract"])
        assert rc == 0, (where, capsys.readouterr().out)
        capsys.readouterr()


def test_c117_e2_a_stale_graph_is_rebuilt_when_building_is_allowed(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    root = _repo(tmp_path)
    _build(root)
    (root / "pkg/c/o.py").write_text("def h():\n    return 2\n")
    rc, out = _init_with(root, capsys)
    assert "graph rebuilt (the graph is behind its source tree" in out, out
    assert "starter contract written" in out
    assert install.graph_unfit(root, root / GRAPH) is None


def test_c117_e3_init_says_when_the_pin_cannot_serve_mcp(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    root = _repo(tmp_path)
    monkeypatch.setattr(install, "pin_has_mcp", lambda pin: False)
    rc, out = _init_with(root, capsys, build=False)
    assert rc == 1 and "cannot import `mcp`" in out and "codmap[mcp]" in out, out
    root2 = _repo(tmp_path / "control")
    monkeypatch.setattr(install, "pin_has_mcp", lambda pin: True)
    rc, out = _init_with(root2, capsys, build=False)
    assert rc == 0 and "cannot import `mcp`" not in out


def test_c117_e4_codex_from_a_linked_worktree_is_named(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    monkeypatch.setattr(install, "pin_has_mcp", lambda pin: True)
    main_co = _repo(tmp_path)
    for cmd in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"],
                ["worktree", "add", "-q", str(tmp_path / "wt")]):
        subprocess.run(["git", *cmd], cwd=main_co, check=True, capture_output=True)
    _, out = _init_with(tmp_path / "wt", capsys, build=False, codex=True)
    assert "linked worktree" in out and "`codemap devkit update` in the main checkout" in out, out
    _, out = _init_with(main_co, capsys, build=False, codex=True)
    assert "linked worktree" not in out
