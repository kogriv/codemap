"""R1-C133 — a pin reached through a link or directory the repository carries is not an installed codemap.

Follow-up audit FU-01. Expectations E1–E5 are in BACKLOG.md (R1-C133), written before the change; on 0.0.46 the
whole chain was reproduced here: `.mcp.json` → tracked link `tools/codemap → /bin/sh` → `update` wrote it into
the post-commit hook → the hook ran `sh build` in the root. Every attack uses a harmless marker file.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from codemap.devkit import install
from tests.test_r1c108_devkit import _fake_codemap, _repo
from tests.test_r1c121_devkit_trust import _installed, _tamper_mcp

SH = shutil.which("sh") or "/bin/sh"
SCRIPT = "#!/bin/sh\nfrom codemap.cli import main\n"


def _git_add(root: Path, *paths: str) -> None:
    subprocess.run(["git", "-C", str(root), "add", "--", *paths], check=True)


def _run_hook(root: Path, timeout: float = 30) -> None:
    """Run the installed post-commit hook and wait for its background loop to log one pass."""
    log = root / ".codemap/rebuild.log"
    subprocess.run(["bash", str(root / ".git/hooks/post-commit")], cwd=root, check=True)
    end = time.monotonic() + timeout
    while time.monotonic() < end and not (log.is_file() and log.read_text().strip()):
        time.sleep(0.1)
    assert log.is_file() and log.read_text().strip(), "the hook did not finish a pass"


def test_e1_a_tracked_link_named_codemap_is_refused_and_never_reaches_the_hook(tmp_path, monkeypatch, capsys):
    root = _installed(tmp_path, monkeypatch)
    monkeypatch.undo()
    monkeypatch.setattr(install, "running_pin", lambda: [_fake_codemap(tmp_path / "bin")])
    marker = tmp_path / "MARKER"
    (root / "tools").mkdir()
    os.symlink(SH, root / "tools/codemap")
    (root / "build").write_text(f"touch {marker}\n")
    _git_add(root, "tools/codemap", "build")
    pin = str(root / "tools/codemap")
    assert "a file of this repository" in (install.pin_problem(root, [pin]) or "")
    _tamper_mcp(root, pin, [])
    install.status(root)
    install.update(root, force=False, repin=False, dry_run=False)
    assert "was not run and is not kept" in capsys.readouterr().out
    hook = (root / ".git/hooks/post-commit").read_text()
    assert "tools/codemap" not in hook and f"C={tmp_path}/bin/codemap" in hook
    _run_hook(root)                                      # E6 of the audit: the hook itself, not only the check
    assert not marker.exists(), "the post-commit hook ran a file the repository carries"


def test_e2_a_tracked_directory_link_on_the_way_is_refused(tmp_path):
    root = _repo(tmp_path)
    real = tmp_path / "elsewhere"
    real.mkdir()
    (real / "codemap").write_text(SCRIPT)                # a genuine-looking codemap outside the repository
    os.symlink(real, root / "tools")
    _git_add(root, "tools")
    problem = install.pin_problem(root, [str(root / "tools/codemap")])
    assert problem and "`tools` on its way is carried by this repository" in problem, problem
    assert install.pin_problem(root, [str(real / "codemap")]) is None          # the same file, named directly


def test_e3_a_file_named_codemap_is_judged_by_what_it_holds(tmp_path):
    root = _repo(tmp_path / "r")
    outside = tmp_path / "bin"
    outside.mkdir()
    shutil.copy(SH, outside / "codemap")
    problem = install.pin_problem(root, [str(outside / "codemap")])
    assert problem and "not a console script that starts codemap" in problem, problem
    os.symlink(SH, tmp_path / "codemap")
    assert "not a console script" in (install.pin_problem(root, [str(tmp_path / "codemap")]) or "")


def test_e4_installed_codemaps_still_pass(tmp_path):
    root = _repo(tmp_path / "r")
    outside = tmp_path / "bin"
    outside.mkdir()
    (outside / "codemap").write_text(SCRIPT)
    assert install.pin_problem(root, [str(outside / "codemap")]) is None
    venv = root / ".venv/bin"                            # untracked, inside the root
    venv.mkdir(parents=True)
    (venv / "codemap").write_text(SCRIPT)
    assert install.pin_problem(root, [str(venv / "codemap")]) is None
    py = Path(shutil.which("python3") or "/usr/bin/python3").resolve()
    os.symlink(py, venv / "python3")                     # a venv's python is a link out of the root
    assert install.pin_problem(root, [str(venv / "python3"), "-I", "-m", "codemap"]) is None
    real = Path(_fake_codemap(tmp_path / "fake"))
    assert install.pin_problem(root, [str(real)]) is None
    # the running codemap's own console script, when there is one, passes as it is
    own = Path(shutil.which("codemap") or "")
    if own.name == "codemap" and own.is_file():
        assert install.pin_problem(root, [str(own)]) is None


def test_e5_outside_git_a_pin_inside_the_root_is_refused(tmp_path):
    root = tmp_path / "plain"
    (root / ".venv/bin").mkdir(parents=True)
    (root / ".venv/bin/codemap").write_text(SCRIPT)
    problem = install.pin_problem(root, [str(root / ".venv/bin/codemap")])
    assert problem and "not a git repository" in problem, problem
    outside = tmp_path / "bin"
    outside.mkdir()
    (outside / "codemap").write_text(SCRIPT)
    assert install.pin_problem(root, [str(outside / "codemap")]) is None


def test_a_dotdot_spelling_does_not_hide_a_tracked_link(tmp_path):
    root = _repo(tmp_path)
    (root / "tools").mkdir()
    os.symlink(SH, root / "tools/codemap")
    _git_add(root, "tools/codemap")
    sneaky = f"{root}/pkg/../tools/codemap"
    assert "a file of this repository" in (install.pin_problem(root, [sneaky]) or "")
    json.dumps(install.pin_problem(root, [sneaky]))


def test_the_pin_this_codemap_writes_passes_its_own_check(tmp_path, monkeypatch):
    import sys
    wrapper = tmp_path / "w" / "codemap"
    wrapper.parent.mkdir()
    wrapper.write_text('#!/bin/sh\nexec python3 -m codemap "$@"\n')    # a wrapper: not a console script
    monkeypatch.setattr(sys, "argv", [str(wrapper)])
    assert install.running_pin()[1:] == ["-I", "-m", "codemap"]
    script = tmp_path / "s" / "codemap"
    script.parent.mkdir()
    script.write_text(SCRIPT)
    monkeypatch.setattr(sys, "argv", [str(script)])
    assert install.running_pin() == [str(script)]
    assert install.pin_problem(_repo(tmp_path), install.running_pin()) is None
