"""R1-C121 — the devkit runs and writes only what it may: project files are input from whoever pushed.

Expectations E1–E5 are in BACKLOG.md (R1-C121), written before the change; the gap note is
gaps/devkit_trusts_project_files_2026-11-23.md. Every attack here uses a harmless marker file.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

import pytest

from codemap.cli import main
from codemap.devkit import install, render, template
from codemap.devkit.state import STATE, path_problem
from tests.test_r1c108_devkit import _fake_codemap, _repo


def _installed(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(install, "running_pin", lambda: [_fake_codemap(tmp_path / "bin")])
    monkeypatch.setattr(install, "pin_has_mcp", lambda pin: True)
    root = _repo(tmp_path)
    assert install.init(root, package="pkg", consumers=[], docs=[], agents_file=None, claude_hooks=False,
                        codex=False, ci=None, hook=True, build=False, ratchet=False, dry_run=False,
                        force=False) == 0
    return root


def _tamper_mcp(root: Path, command: str, args: list[str]) -> None:
    m = json.loads((root / ".mcp.json").read_text())
    m["mcpServers"]["codemap"]["command"] = command
    m["mcpServers"]["codemap"]["args"] = [*args, "serve", "--mcp"]
    (root / ".mcp.json").write_text(json.dumps(m))


# --------------------------------------------------------------------------- E1 / E2: the pin


def test_e1_a_command_put_in_mcp_json_is_never_run(tmp_path, monkeypatch, capsys):
    root = _installed(tmp_path, monkeypatch)
    monkeypatch.undo()                                   # real pin checks from here on
    monkeypatch.setattr(install, "running_pin", lambda: [_fake_codemap(tmp_path / "bin")])
    marker = tmp_path / "MARKER"
    _tamper_mcp(root, "/bin/sh", ["-c", f"touch {marker}"])
    install.status(root)
    install.update(root, force=False, repin=False, dry_run=False)
    assert not marker.exists(), "status/update ran a command from .mcp.json"
    out = capsys.readouterr().out
    assert "was not run and is not kept" in out
    hook = (root / ".git/hooks/post-commit").read_text()
    assert "/bin/sh" not in hook and f"C={tmp_path}/bin/codemap" in hook


@pytest.mark.parametrize("pin, ok", [
    (["{bin}/codemap"], True),
    (["{bin}/python3.12", "-I", "-m", "codemap"], True),
    (["{bin}/codemap", "--x"], False),
    (["{bin}/python3.12", "-m", "codemap"], False),      # no -I: the working directory comes first
    (["{bin}/python3.12", "-c", "print(1)"], False),
    (["{bin}/sh"], False),
    (["codemap"], False),                                # relative
    (["{bin}/missing/codemap"], False),
])
def test_e2_only_the_shapes_the_devkit_writes_are_accepted(tmp_path, pin, ok):
    root = _repo(tmp_path / "r")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("codemap", "python3.12", "sh"):
        (bindir / name).write_text("#!/bin/sh\n")
    pin = [a.replace("{bin}", str(bindir)) for a in pin]
    assert (install.pin_problem(root, pin) is None) is ok, install.pin_problem(root, pin)


def test_e2_a_codemap_the_repository_carries_is_refused(tmp_path):
    root = _repo(tmp_path)
    (root / "tools").mkdir()
    (root / "tools/codemap").write_text("#!/bin/sh\n")
    subprocess.run(["git", "-C", str(root), "add", "tools/codemap"], check=True)
    assert "a file of this repository" in install.pin_problem(root, [str(root / "tools/codemap")])
    (root / ".venv/bin").mkdir(parents=True)                     # untracked venv inside the root: fine
    (root / ".venv/bin/codemap").write_text("#!/bin/sh\n")
    assert install.pin_problem(root, [str(root / ".venv/bin/codemap")]) is None


def test_e2_the_python_fallback_runs_isolated():
    import sys
    from unittest import mock
    with mock.patch.object(sys, "argv", ["/somewhere/python-script.py"]):
        assert install.running_pin()[1:] == ["-I", "-m", "codemap"]


# --------------------------------------------------------------------------- E3: paths


@pytest.mark.parametrize("field, value", [
    ("agents_file", "../outside.md"), ("agents_file", "{abs}/abs-outside.md"), ("graph", "../g.json"),
    ("package", "../../etc"), ("docs", ["ok", "../x"]),
])
def test_e3_a_state_path_out_of_the_repository_is_refused_before_any_write(tmp_path, monkeypatch, capsys,
                                                                           field, value):
    root = _installed(tmp_path, monkeypatch)
    st = json.loads((root / STATE).read_text())
    st[field] = value.replace("{abs}", str(tmp_path)) if isinstance(value, str) else value
    (root / STATE).write_text(json.dumps(st))
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and ".git/" not in str(p)}
    for argv in (["devkit", "update", "--root", str(root)], ["devkit", "status", "--root", str(root)]):
        assert main(argv) == 2
        assert "refused" in capsys.readouterr().err
    assert not (tmp_path / "outside.md").exists() and not (tmp_path / "abs-outside.md").exists()
    after = {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and ".git/" not in str(p)}
    assert after == before


def test_e3_a_symbolic_link_out_of_the_repository_is_refused(tmp_path, monkeypatch, capsys):
    root = _installed(tmp_path, monkeypatch)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (root / "docs").symlink_to(outside)
    assert "resolves outside" in path_problem(root, "docs/rules.md", "agents_file")
    assert main(["devkit", "update", "--root", str(root), "--agents-file", "docs/rules.md"]) == 2
    assert not list(outside.iterdir())


def test_e3_the_command_line_meets_the_same_rule(tmp_path, capsys):
    root = _repo(tmp_path)
    assert main(["devkit", "init", "--root", str(root), "--package", "pkg", "--agents-file", "../x.md",
                 "--no-build", "--no-hook"]) == 2
    assert "leaves the repository" in capsys.readouterr().err
    assert not (tmp_path / "x.md").exists() and not (root / STATE).exists()


# --------------------------------------------------------------------------- E4: templates


def test_e4_shell_metacharacters_are_refused_and_quoted_if_they_got_through(tmp_path, monkeypatch, capsys):
    root = _installed(tmp_path, monkeypatch)
    st = json.loads((root / STATE).read_text())
    st["package"] = "pkg;touch MARKER"
    (root / STATE).write_text(json.dumps(st))
    assert main(["devkit", "update", "--root", str(root)]) == 2
    assert "only letters, digits" in capsys.readouterr().err
    # The second wall: render the hook as if the check had been bypassed.
    ctx = install.context({**st, "graph": ".codemap/graph.json"}, ["/x/codemap"], "0.0.0", root)
    hook = render(template("post-commit.sh"), ctx)
    line = next(ln for ln in hook.splitlines() if "$C build" in ln and "--incremental" not in ln)
    assert "pkg;touch MARKER" in shlex.split(line.split("$C", 1)[1])
    path = tmp_path / "hook.sh"
    path.write_text(hook)
    assert subprocess.run(["bash", "-n", str(path)]).returncode == 0
    wf = render(template("github-workflow.yml"), ctx)
    run = next(ln for ln in wf.splitlines() if "codemap build" in ln).split("run:", 1)[1]
    assert shlex.split(run)[2] == "pkg;touch MARKER"


# --------------------------------------------------------------------------- E5: the ordinary path


def test_e5_an_ordinary_install_is_unchanged(tmp_path, monkeypatch, capsys):
    root = _installed(tmp_path, monkeypatch)
    capsys.readouterr()
    assert install.update(root, force=False, repin=False, dry_run=False) == 0
    out = capsys.readouterr().out
    assert "not run" not in out and "refused" not in out
    hook = (root / ".git/hooks/post-commit").read_text()
    assert " build pkg --deep --repeat 2 " in hook                   # a plain value renders unquoted
