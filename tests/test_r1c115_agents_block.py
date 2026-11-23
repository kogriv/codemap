"""R1-C115 — the agent rules block in the project's language, and moved to another file. E1–E5 in BACKLOG.md."""

from __future__ import annotations

import re

from codemap.devkit import install, template
from tests.test_r1c108_devkit import _repo


def _init(root, **kw):
    args = dict(package="pkg", consumers=[], docs=[], agents_file=None, claude_hooks=False, codex=False, ci=None,
                hook=False, build=False, ratchet=False, dry_run=False, force=False)
    args.update(kw)
    return install.init(root, **args)


def _commands(text: str) -> list[str]:
    return sorted(m.group(0) for m in re.finditer(r"`codemap [^`]+`", text))


def _pin(monkeypatch):
    monkeypatch.setattr(install, "running_pin", lambda: ["/x/codemap"])
    monkeypatch.setattr(install, "pin_has_mcp", lambda pin: True)


def test_e1_the_russian_block_carries_the_same_commands():
    assert _commands(template("agents_block.ru.md")) == _commands(template("agents_block.md"))
    assert set(re.findall(r"\{\{(\w+)\}\}", template("agents_block.ru.md"))) == \
        set(re.findall(r"\{\{(\w+)\}\}", template("agents_block.md")))


def test_e1_init_writes_the_russian_block(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    root = _repo(tmp_path)
    _init(root, agents_lang="ru")
    text = (root / "AGENTS.md").read_text()
    assert "## codemap — граф кода `pkg`" in text and "Что когда звать" in text


def test_e2_update_translates_an_untouched_block_and_keeps_an_edited_one(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    root = _repo(tmp_path)
    _init(root)
    assert install.update(root, force=False, repin=False, dry_run=False, agents_lang="ru") == 0
    assert "Что когда звать" in (root / "AGENTS.md").read_text()
    root2 = _repo(tmp_path / "edited")
    _init(root2)
    p = root2 / "AGENTS.md"
    p.write_text(p.read_text().replace("**When to call what**", "**When to call what (ours)**"))
    capsys.readouterr()
    assert install.update(root2, force=False, repin=False, dry_run=False, agents_lang="ru") == 1
    assert "edited by hand" in capsys.readouterr().out and "(ours)" in p.read_text()


def test_e3_update_moves_the_block(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    root = _repo(tmp_path)
    (root / "AGENTS.md").write_text("# Rules\n\nOur own text.\n")
    _init(root)
    assert "codemap-devkit:begin" in (root / "AGENTS.md").read_text()
    capsys.readouterr()
    install.update(root, force=False, repin=False, dry_run=False, agents_file="docs/codemap.md")
    out = capsys.readouterr().out
    assert "rules block moved: AGENTS.md → docs/codemap.md" in out
    assert (root / "AGENTS.md").read_text() == "# Rules\n\nOur own text.\n"
    assert "codemap-devkit:begin" in (root / "docs/codemap.md").read_text()
    assert install.load_state(root)["agents_file"] == "docs/codemap.md"
    capsys.readouterr()
    assert install.update(root, force=False, repin=False, dry_run=False) == 0      # settled: current
    assert "current" in capsys.readouterr().out


def test_e3_an_edited_old_block_stays_with_a_note(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    root = _repo(tmp_path)
    _init(root)
    p = root / "AGENTS.md"
    p.write_text(p.read_text().replace("**When to call what**", "**When to call what (ours)**"))
    capsys.readouterr()
    install.update(root, force=False, repin=False, dry_run=False, agents_file="RULES.md")
    assert "was edited by hand — kept there" in capsys.readouterr().out
    assert "(ours)" in p.read_text() and "codemap-devkit:begin" in (root / "RULES.md").read_text()


def test_e4_a_repeated_init_honours_the_file_and_the_language(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    root = _repo(tmp_path)
    _init(root)
    _init(root, agents_file="docs/rules.md", agents_lang="ru")
    assert "Что когда звать" in (root / "docs/rules.md").read_text()
    assert "codemap-devkit:begin" not in (root / "AGENTS.md").read_text()
