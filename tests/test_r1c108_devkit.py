"""R1-C108 — the devkit and the `allowed` ratchet (design ``docs/design/devkit.md``).

E1/E2: the `allowed` rule and its schema. E5: the region editor keeps hand lines. E6/E8: init, status,
update and the one rule for touching managed artifacts. E9 (D7): what keeps the templates current — every
command in every template parses with the CLI's own parser, every MCP tool named exists, and a template
cannot change without DEVKIT_VERSION and TEMPLATES_SHA256 changing with it. E10: the hooks.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from codemap import arch, devkit
from codemap.cli import build_parser
from codemap.devkit import install, ratchet
from codemap.devkit.hooks import build_index, touched
from codemap.extract import extract
from codemap.query import Query
from codemap.serve.check import build_check, render_check
from codemap.serve.mcp_server import MCP_TOOLS


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


ABC = {
    "pkg/__init__.py": "",
    "pkg/a/__init__.py": "",
    "pkg/a/m.py": "from pkg.b.n import g\n\ndef f():\n    return g()\n",
    "pkg/b/__init__.py": "",
    "pkg/b/n.py": "def g():\n    from pkg.c.o import h\n    return h()\n",
    "pkg/c/__init__.py": "",
    "pkg/c/o.py": "def h():\n    return 1\n",
}


@pytest.fixture(scope="module")
def abc(tmp_path_factory):
    root = _tree(tmp_path_factory.mktemp("r1c108"), ABC)
    return Query(extract(str(root / "pkg")))


def _contract(section: dict) -> arch.ArchitectureContract:
    return arch.parse_contract(section)


# ----------------------------------------------------------------------------- E1, E2

def test_e1_an_import_between_layers_not_listed_is_a_violation_function_local_included(abc):
    c = _contract({"allowed": [{"from": "a", "to": "b"}]})
    assert c.error is None
    v = arch.check_contract(abc, c)
    assert [x.rule for x in v] == ["allowed"]
    assert v[0].edges == (("pkg.b.n", "pkg.c.o"),), v[0].edges      # the function-local edge
    assert "`b` → `c`" in v[0].summary


def test_e1_listed_pairs_pass_and_an_unused_pair_is_a_note_not_a_violation(abc):
    c = _contract({"allowed": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"},
                               {"from": "c", "to": "a"}]})
    assert arch.check_contract(abc, c) == []
    assert arch.allowed_unused(abc, c) == [("c", "a")]
    md = render_check(abc, c, [])
    assert "allowed (3)" in md and "no longer used" in md and "--tighten" in md
    js = build_check(abc, c, [])
    assert js["ok"] and js["allowed_unused"] == [["c", "a"]]
    assert js["applicability"]["allowed"] == {"declared": 3, "applicable": 3}


def test_e1_an_empty_list_allows_no_cross_layer_import_at_all(abc):
    c = _contract({"allowed": []})
    assert c.allowed == () and not c.is_empty()
    v = arch.check_contract(abc, c)
    assert v and v[0].rule == "allowed" and len(v[0].edges) == 2


def test_e1_without_allowed_the_answer_does_not_change(abc):
    c = _contract({"no_cycles": True})
    md = render_check(abc, c, arch.check_contract(abc, c))
    assert "allowed" not in md and "no longer used" not in md
    js = build_check(abc, c, [])
    assert "allowed_unused" not in js
    assert js["applicability"]["allowed"] == {"declared": 0, "applicable": 0}


def test_e2_a_bad_allowed_list_is_one_error_naming_every_problem_and_nothing_runs():
    c = _contract({"no_cycles": True, "allowed": [
        {"from": "a", "to": "b"}, {"from": "a", "to": "b"},
        {"from": "c", "to": "c"}, {"from": "d", "to": "e", "why": "x"}]})
    assert c.error and c.is_empty()
    assert "`allowed[1]` repeats `a` → `b`" in c.error
    assert "`allowed[2]`: `from` and `to` are both `c`" in c.error
    assert "`allowed[3]` has unknown key(s) `why`" in c.error


# ----------------------------------------------------------------------------- E5 region editor

def test_e5_generate_then_tighten_removes_exactly_the_unused_line_and_keeps_hand_lines(tmp_path):
    (tmp_path / "codemap.toml").write_text("[architecture]\nno_cycles = true\n\n[other]\nx = 1\n")
    r = ratchet.edit_region(tmp_path, [("a", "b"), ("b", "c")])
    assert r.created_region and r.added == [("a", "b"), ("b", "c")]
    text = (tmp_path / "codemap.toml").read_text()
    assert text.index("allowed = [") < text.index("[other]")          # inside the table
    # hand edits: a reason comment on one pair, a hand-added pair, a free comment line
    text = text.replace('{ from = "b", to = "c" },', '{ from = "b", to = "c" },  # b reads c on purpose')
    text = text.replace("]\n# <<<", '  # free note kept\n  { from = "x", to = "y" },  # added by hand\n]\n# <<<')
    (tmp_path / "codemap.toml").write_text(text)
    r = ratchet.edit_region(tmp_path, [("b", "c"), ("x", "y")], tighten=True)
    assert r.removed == [("a", "b")] and r.added == []
    after = (tmp_path / "codemap.toml").read_text()
    assert '{ from = "a", to = "b" }' not in after
    assert '{ from = "b", to = "c" },  # b reads c on purpose' in after
    assert '  # free note kept\n' in after and '{ from = "x", to = "y" },  # added by hand' in after
    assert after.replace('  { from = "a", to = "b" },\n', "") == after   # nothing else moved
    assert text.replace('  { from = "a", to = "b" },\n', "") == after


def test_e5_generate_adds_missing_pairs_and_refuses_a_hand_written_allowed(tmp_path):
    (tmp_path / "codemap.toml").write_text('[architecture]\nallowed = [{ from = "a", to = "b" }]\n')
    with pytest.raises(ratchet.RatchetError, match="by hand outside"):
        ratchet.edit_region(tmp_path, [("a", "b")])
    (tmp_path / "codemap.toml").write_text("[architecture]\n")
    ratchet.edit_region(tmp_path, [("a", "b")])
    r = ratchet.edit_region(tmp_path, [("a", "b"), ("c", "d")])
    assert r.added == [("c", "d")] and not r.created_region
    assert arch.load_contract(tmp_path).allowed == (("a", "b"), ("c", "d"))


def test_e5_an_edit_that_would_break_the_contract_writes_nothing(tmp_path):
    (tmp_path / "codemap.toml").write_text("[architecture]\nno_cycles = true\n")
    ratchet.edit_region(tmp_path, [("a", "b")])
    before = (tmp_path / "codemap.toml").read_text()
    bad = before.replace('{ from = "a", to = "b" },', '{ from = "a", to = "b" },\n  { from = "a", to = "b" },')
    (tmp_path / "codemap.toml").write_text(bad)
    with pytest.raises(ratchet.RatchetError, match="not be a valid contract"):
        ratchet.edit_region(tmp_path, [("a", "b"), ("c", "d")])
    assert (tmp_path / "codemap.toml").read_text() == bad


# ----------------------------------------------------------------------------- E6, E8 init / update

def _repo(tmp_path: Path) -> Path:
    root = _tree(tmp_path / "repo", {**ABC, "tests/test_m.py": "from pkg.a.m import f\n\ndef test_f():\n"
                                                               "    assert f() == 1\n"})
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


def _pin(monkeypatch):
    monkeypatch.setattr(install, "running_pin", lambda: [sys.executable, "-m", "codemap"])


def test_e6_init_writes_every_artifact_and_status_is_clean(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    root = _repo(tmp_path)
    rc = install.init(root, package="pkg", consumers=["tests"], docs=[], agents_file=None,
                      claude_hooks=True, codex=True, ci="github", hook=True, build=True,
                      ratchet=False, dry_run=False, force=False)
    assert rc == 0, capsys.readouterr().out
    for rel in ("AGENTS.md", ".mcp.json", ".codex/config.toml", ".claude/settings.json",
                ".github/workflows/codemap.yml", ".git/hooks/post-commit", ".codemap-devkit.json",
                "codemap.toml", ".codemap/graph.json", ".codemap/devkit/index.json"):
        assert (root / rel).is_file(), rel
    assert ".codemap/" in (root / ".gitignore").read_text()
    c = arch.load_contract(root)
    assert c.no_cycles and c.allowed == (("a", "b"), ("b", "c"))
    entry = json.loads((root / ".mcp.json").read_text())["mcpServers"]["codemap"]
    assert entry["command"] == sys.executable and entry["args"][:3] == ["-m", "codemap", "serve"]
    assert install.status(root) == 0


def test_e8_update_rewrites_outdated_keeps_hand_edits_and_force_overwrites(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    root = _repo(tmp_path)
    install.init(root, package="pkg", consumers=[], docs=[], agents_file=None, claude_hooks=False,
                 codex=False, ci=None, hook=False, build=False, ratchet=False, dry_run=False, force=False)
    capsys.readouterr()
    # a newer devkit: status says outdated, update brings it current
    monkeypatch.setattr(install, "DEVKIT_VERSION", devkit.DEVKIT_VERSION + 1)
    assert install.status(root) == 1
    assert "outdated" in capsys.readouterr().out
    assert install.update(root, force=False, repin=False, dry_run=False) == 0
    assert f"codemap-devkit:begin v{devkit.DEVKIT_VERSION + 1}" in (root / "AGENTS.md").read_text()
    assert install.status(root) == 0
    capsys.readouterr()
    # a hand edit inside the block is kept and reported; --force rewrites it
    agents = root / "AGENTS.md"
    agents.write_text(agents.read_text().replace("**Upkeep**", "**Upkeep, local**"))
    monkeypatch.setattr(install, "DEVKIT_VERSION", devkit.DEVKIT_VERSION + 2)
    assert install.update(root, force=False, repin=False, dry_run=False) == 1
    out = capsys.readouterr().out
    assert "edited" in out and "**Upkeep, local**" in agents.read_text()
    assert install.update(root, force=True, repin=False, dry_run=False) == 0
    assert "**Upkeep, local**" not in agents.read_text()


def test_e8_a_foreign_artifact_is_never_overwritten_and_the_hook_goes_beside_it(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch)
    root = _repo(tmp_path)
    (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"codemap": {"command": "/other/codemap",
                                                                            "args": ["serve"]},
                                                               "other": {"command": "x"}}}))
    hook = root / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\necho mine\n")
    (root / "AGENTS.md").write_text("# Mine\n\nKeep this text.\n")
    rc = install.init(root, package="pkg", consumers=[], docs=[], agents_file=None, claude_hooks=False,
                      codex=False, ci=None, hook=True, build=False, ratchet=False, dry_run=False, force=False)
    out = capsys.readouterr().out
    assert rc == 1, out
    assert json.loads((root / ".mcp.json").read_text())["mcpServers"]["codemap"]["command"] == "/other/codemap"
    assert hook.read_text() == "#!/bin/sh\necho mine\n"
    assert (root / ".codemap" / "devkit" / "post-commit").is_file()
    assert "foreign" in out and "did not write" in out
    assert (root / "AGENTS.md").read_text().startswith("# Mine\n\nKeep this text.\n\n<!-- codemap-devkit:begin")


def test_e8_update_keeps_the_pin_and_repin_moves_it(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(install, "running_pin", lambda: ["/first/codemap"])
    root = _repo(tmp_path)
    install.init(root, package="pkg", consumers=[], docs=[], agents_file=None, claude_hooks=False,
                 codex=False, ci=None, hook=False, build=False, ratchet=False, dry_run=False, force=False)
    monkeypatch.setattr(install, "running_pin", lambda: ["/second/codemap"])
    install.update(root, force=False, repin=False, dry_run=False)
    assert json.loads((root / ".mcp.json").read_text())["mcpServers"]["codemap"]["command"] == "/first/codemap"
    install.update(root, force=False, repin=True, dry_run=False)
    assert json.loads((root / ".mcp.json").read_text())["mcpServers"]["codemap"]["command"] == "/second/codemap"


# ----------------------------------------------------------------------------- E9 / D7 currency guards

SAMPLE = {"devkit_version": 1, "codemap_version": "0.0.0", "package": "src/pkg", "package_name": "pkg",
          "graph": ".codemap/graph.json", "graph_next": ".codemap/graph.next.json",
          "build_args": "--consumer tests --mode full", "agents_file": "AGENTS.md", "pin_shell": "codemap",
          "pin_assign": "codemap", "pin_command_toml": '"codemap"', "pin_args_toml": "", "pairs": "",
          "flags": "no_cycles = true", "currency": "current", "devkit_note": "", "root_toml": '"/repo"',
          "outside_languages": "; this repository also has typescript, which it does not read",
          "lazy": "", "type_only": ""}

_OPS = ("|", "||", "&&", ";", "&")


def _commands(name: str, text: str) -> list[list[str]]:
    """Every codemap invocation a rendered template contains, as argv after `codemap`."""
    found: list[str] = []
    if name.endswith((".md", ".txt", ".toml")) and name != "codex_region.toml":
        for span in re.findall(r"`([^`]+)`", text):
            for m in re.finditer(r"(?:^|[\s|(])codemap\s+(.*)$", span):
                found.append(m.group(1))
    if name.endswith(".sh"):
        joined = text.replace("\\\n", " ")
        for line in joined.splitlines():
            for m in re.finditer(r"\$C\s+(.*)$", line):
                found.append(m.group(1))
    if name.endswith(".yml"):
        for m in re.finditer(r"^\s*-?\s*(?:run:)?\s*-?\s*codemap\s+(.*)$", text, re.M):
            found.append(m.group(1))
    if name.endswith(".json"):
        for ev in json.loads(text).values():
            for g in ev:
                for h in g["hooks"]:
                    found.append(h["command"].split("codemap", 1)[1])
    if name == "mcp_claude.args":
        found.append(text.strip())
    if name == "codex_region.toml":
        import tomllib
        found.append(shlex.join(tomllib.loads(text)["mcp_servers"]["codemap"]["args"]))
    out = []
    for cmd in found:
        toks = []
        for t in shlex.split(cmd, posix=True):
            if t in _OPS or t.startswith((">", "2>", "<")):
                break
            toks.append(t)
        out.append(toks)
    return out


def _all_templates():
    return sorted(p for p in devkit.TEMPLATES_DIR.iterdir() if p.is_file())


#: How many codemap commands the scan finds in each template. Pinned so the scan cannot quietly stop
#: reading a file (or a command form) and keep passing over what it no longer checks; a template that
#: gains or loses a command updates its count here, in the same commit.
COMMANDS_PER_TEMPLATE = {"agents_block.md": 9, "brief.txt": 1, "claude_hooks.json": 2, "codex_region.toml": 1,
                         "contract_head.toml": 1, "github-workflow.yml": 2, "gitlab-ci.yml": 2,
                         "mcp_claude.args": 1, "post-commit.sh": 3, "ratchet_region.toml": 2,
                         "cycles_region.toml": 1}


def test_d7_every_command_in_every_template_parses_with_the_cli_parser():
    parser = build_parser()
    seen = {}
    for p in _all_templates():
        text = devkit.render(p.read_text(encoding="utf-8"), SAMPLE)
        cmds = _commands(p.name, text)
        seen[p.name] = len(cmds)
        for argv in cmds:
            try:
                parser.parse_args(argv)
            except SystemExit as exc:
                assert exc.code == 0, f"{p.name}: `codemap {shlex.join(argv)}` does not parse"
    assert seen == COMMANDS_PER_TEMPLATE, seen


def test_d7_every_template_is_scanned_by_some_rule():
    """A new template type the scanner does not read would be a hole in D7."""
    for p in _all_templates():
        assert p.suffix in (".md", ".txt", ".toml", ".sh", ".yml", ".json", ".args"), p.name


def test_d7_every_mcp_tool_the_rules_block_names_exists():
    text = devkit.template("agents_block.md")
    named = set(re.findall(r"`(\w+)` \(MCP\)", text))
    assert named, "the block names no MCP tool — the scan is broken"
    assert named <= set(MCP_TOOLS), named - set(MCP_TOOLS)


def test_d7_templates_cannot_change_without_a_devkit_version_bump():
    assert devkit.templates_sha256() == devkit.TEMPLATES_SHA256, (
        "the devkit templates changed: bump DEVKIT_VERSION and set TEMPLATES_SHA256 to "
        f"{devkit.templates_sha256()} in codemap/devkit/__init__.py")


def test_d7_every_placeholder_in_every_template_has_a_value():
    for p in _all_templates():
        devkit.render(p.read_text(encoding="utf-8"), SAMPLE)     # raises KeyError on an unknown one


# ----------------------------------------------------------------------------- E10 hooks

def test_e10_touched_names_the_importers_of_an_edited_module(tmp_path, monkeypatch):
    root = _tree(tmp_path, ABC)
    g = extract(str(root / "pkg"))
    idx = build_index(g)
    assert idx["pkg/b/n.py"]["importers"] == 1 and idx["pkg/b/n.py"]["top"] == [["g", 1]]
    (root / ".codemap" / "devkit").mkdir(parents=True)
    (root / ".codemap" / "devkit" / "index.json").write_text(json.dumps({"files": idx, "built_at": None}))
    out = []
    monkeypatch.setattr("builtins.print", lambda s, **k: out.append(s))
    touched(root, json.dumps({"tool_input": {"file_path": str(root / "pkg/b/n.py")}}))
    ctx = json.loads(out[0])["hookSpecificOutput"]
    assert ctx["hookEventName"] == "PostToolUse"
    assert "`pkg.b.n` is imported by 1 module(s)" in ctx["additionalContext"]
    out.clear()
    assert touched(root, json.dumps({"tool_input": {"file_path": "/etc/hosts"}})) == 0 and out == []
    assert touched(root, "not json") == 0 and out == []


def test_e10_touched_without_a_digest_says_so_in_one_line(tmp_path, monkeypatch):
    root = _tree(tmp_path, ABC)
    out = []
    monkeypatch.setattr("builtins.print", lambda s, **k: out.append(s))
    touched(root, json.dumps({"tool_input": {"file_path": str(root / "pkg/a/m.py")}}))
    assert "no devkit index yet" in json.loads(out[0])["hookSpecificOutput"]["additionalContext"]


def _consts(text: str) -> tuple[int | None, str | None]:
    v = re.search(r"^DEVKIT_VERSION = (\d+)", text, re.M)
    h = re.search(r'^TEMPLATES_SHA256 = "([0-9a-f]{64})"', text, re.M)
    return (int(v.group(1)) if v else None), (h.group(1) if h else None)


def test_d7_the_hash_never_moves_without_the_version_in_git_history():
    """Updating TEMPLATES_SHA256 alone would silence the guard above without telling adopters.
    Over every commit that touched the constants (and the working tree against HEAD): when the hash
    changed, the version rose with it."""
    repo = Path(__file__).resolve().parent.parent
    rel = "codemap/devkit/__init__.py"
    git = ["git", "-C", str(repo)]
    if subprocess.run([*git, "rev-parse", "--git-dir"], capture_output=True).returncode != 0:
        pytest.skip("not a git checkout")
    revs = subprocess.run([*git, "log", "--format=%H", "--", rel], capture_output=True, text=True).stdout.split()

    def at(rev: str) -> str | None:
        r = subprocess.run([*git, "show", f"{rev}:{rel}"], capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None

    pairs = [((repo / rel).read_text(encoding="utf-8"), at("HEAD"), "working tree")]
    pairs += [(at(r), at(f"{r}~1"), r[:9]) for r in revs]
    for new, old, where in pairs:
        if new is None or old is None:
            continue
        (nv, nh), (ov, oh) = _consts(new), _consts(old)
        if None in (nv, nh, ov, oh) or oh == "0" * 64:
            continue
        if nh != oh:
            assert nv > ov, f"{where}: TEMPLATES_SHA256 changed while DEVKIT_VERSION stayed {nv}"


def test_d6_usage_counts_assistant_records_once_per_id_and_reads_newline_as_a_separator(tmp_path):
    from datetime import datetime, timezone

    from codemap.devkit.usage import count
    now = datetime.now(timezone.utc).isoformat()

    def rec(kind, items, ts=now):
        o = {"type": kind, "message": {"content": items}}
        if ts:
            o["timestamp"] = ts
        return json.dumps(o)

    tu = lambda i, name, cmd=None: {"type": "tool_use", "id": i, "name": name,
                                    **({"input": {"command": cmd}} if cmd else {})}
    lines = [
        rec("assistant", [tu("1", "mcp__codemap__callers"), tu("2", "Grep")]),
        rec("assistant", [tu("1", "mcp__codemap__callers")]),                    # same id again
        rec("api-request-blob", [tu("9", "mcp__codemap__impact")], ts=None),     # a request blob
        rec("assistant", [tu("3", "Bash", "cd x\n  grep -rn foo .")]),           # newline separator
        rec("assistant", [tu("4", "Bash", "echo grep")]),                        # an argument, not a command
        rec("assistant", [tu("5", "Bash", "find . | xargs rg bar")]),
        rec("assistant", [tu("6", "mcp__codemap__impact")], ts="2000-01-01T00:00:00+00:00"),  # outside window
    ]
    (tmp_path / "sub").mkdir()
    (tmp_path / "s.jsonl").write_text("\n".join(lines[:4]) + "\n")
    (tmp_path / "sub" / "agent.jsonl").write_text("\n".join(lines[4:]) + "\n")   # subagents count too
    r = count(tmp_path, 7)
    assert r["codemap"] == {"callers": 1}
    assert r["grep"] == {"Grep tool": 1, "grep/rg in Bash": 2}
    assert r["files"] == 2
