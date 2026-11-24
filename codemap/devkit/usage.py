"""Codemap MCP, CLI and grep tool use in local Claude Code transcripts.

Reads ``~/.claude/projects/<project path with "/" → "-">/**/*.jsonl`` (or ``--transcripts``) — sessions and
their subagents. Counts ``mcp__codemap__*``, codemap CLI in Bash, and ``Grep`` or grep/rg in Bash.
Only ``assistant`` records count, once per tool-use id: a transcript also stores request
blobs that repeat earlier calls without a timestamp, and counting them inflated the numbers (measured on the
acceptance run, 1 301 repeats in 16 536). Only counts and tool names are reported.
Codex transcripts are outside this reader's scope.
"""

from __future__ import annotations

import json
import re
import shlex
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

# A command starts at the line start (a newline separates commands in bash), after `;`, `&`, `|`, `(`, or as
# the argument of `xargs`.
GREP_CMD = re.compile(r"(?:^[ \t]*|[;&|(][ \t]*|\bxargs[ \t]+)(?:grep|egrep|rg)\b", re.MULTILINE)
_SHELL_SEPARATORS = frozenset(";&|()\n")
_SHELL_KEYWORDS = frozenset({"!", "{", "if", "then", "elif", "else", "while", "until", "do"})
_SHELL_TRIVIA = re.compile(r"""'[^']*'|"(?:\\[\s\S]|[^"\\])*"|\\[\s\S]|(?<![^\s;&|()<>])\#[^\n]*""")
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z_0-9]*=")
_PYTHON = re.compile(r"python(?:3(?:\.\d+)?)?")
_UV_VALUE_OPTIONS = frozenset({"--with", "--with-editable", "--with-requirements",
                               "--python", "-p", "--project", "--directory", "--env-file",
                               "--group", "--no-group", "--extra", "--index", "--default-index"})
_SHARE_BASIS = "(MCP + CLI) / (MCP + CLI + grep)"


def _unquote(word: str) -> str:
    if len(word) >= 2 and word[0] == word[-1] and word[0] in ("'", '"'):
        return word[1:-1]
    return word


def _skip_options(words: list[str], value_options: frozenset[str]) -> list[str]:
    i = 0
    while i < len(words) and words[i].startswith("-"):
        option = words[i]
        if option == "--":
            return words[i + 1:]
        i += 2 if option in value_options else 1
    return words[i:]


def _cli_command(words: list[str]) -> bool:
    while words:
        head, *args = words
        program = _unquote(head).rsplit("/", 1)[-1]
        if program == "codemap":
            return True
        if _PYTHON.fullmatch(program):
            return _python_module(args) == "codemap"
        if head in _SHELL_KEYWORDS or _ASSIGNMENT.match(head):
            words = args
        elif program == "uv" and args[:1] == ["run"]:
            words = _skip_options(args[1:], _UV_VALUE_OPTIONS)
        elif program == "env" and not {"-S", "--split-string"}.intersection(args):
            words = _skip_options(args, frozenset({"-u", "--unset", "-C", "--chdir"}))
        elif program == "command" and args[:1] not in (["-v"], ["-V"]):
            words = args[1:] if args[:1] == ["-p"] else args
        else:
            break
    return False


def _python_module(args: list[str]) -> str | None:
    i = 0
    while i < len(args):
        option = args[i]
        if option == "-m" and i + 1 < len(args):
            return _unquote(args[i + 1])
        if option in ("-W", "-X"):
            i += 2
        elif option.startswith(("-W", "-X")) or re.fullmatch(r"-[bBdEIPiOqRsSuvx]+", option):
            i += 1
        else:
            return None
    return None


def _uses_cli(command: str) -> bool:
    def trivia(match):
        token = match[0]
        if token.startswith("#") or token == "\\\n":
            return ""
        if token.startswith("\\") and token[1:] in _SHELL_SEPARATORS:
            return "_"
        return token

    # Retain quotes so an argument such as `";"` cannot become a command separator.
    lexer = shlex.shlex(_SHELL_TRIVIA.sub(trivia, command), posix=False, punctuation_chars=";&|()<>\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError:
        return False
    if "<<" in tokens:  # shell input bodies are data
        return False
    words = []
    arithmetic = False
    for token in tokens:
        if set(token) <= _SHELL_SEPARATORS:
            if not arithmetic and _cli_command(words):
                return True
            words = []
            if "((" in token:
                arithmetic = True
            if "))" in token:
                arithmetic = False
        elif not arithmetic:
            words.append(token)
    return _cli_command(words)


def transcripts_dir(root: Path) -> Path:
    slug = str(Path(root).resolve()).replace("/", "-")
    return Path.home() / ".claude" / "projects" / slug


def _ts(obj: dict) -> float | None:
    t = obj.get("timestamp")
    if not isinstance(t, str):
        return None
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def count(directory: Path, days: int) -> dict:
    since = time.time() - days * 86400
    codemap: Counter = Counter()
    cli = 0
    grep = Counter()
    files = 0
    seen: set[str] = set()
    for f in sorted(directory.glob("**/*.jsonl")) if directory.is_dir() else []:
        if f.stat().st_mtime < since:
            continue
        files += 1
        with f.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"tool_use"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("type") != "assistant":
                    continue
                ts = _ts(obj)
                if ts is None or ts < since:
                    continue
                content = (obj.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for item in content:
                    if not isinstance(item, dict) or item.get("type") != "tool_use":
                        continue
                    tid = str(item.get("id", ""))
                    if tid in seen:
                        continue
                    seen.add(tid)
                    name = str(item.get("name", ""))
                    if name.startswith("mcp__codemap__"):
                        codemap[name[len("mcp__codemap__"):]] += 1
                    elif name == "Grep":
                        grep["Grep tool"] += 1
                    elif name == "Bash":
                        cmd = str((item.get("input") or {}).get("command", ""))
                        cli += _uses_cli(cmd)
                        if GREP_CMD.search(cmd):
                            grep["grep/rg in Bash"] += 1
    mcp = sum(codemap.values())
    grep_total = sum(grep.values())
    numerator = mcp + cli
    denominator = numerator + grep_total
    return {"transcripts": str(directory), "files": files, "days": days,
            "codemap": dict(codemap), "codemap_total": mcp,
            "codemap_cli": {"codemap in Bash": cli} if cli else {}, "codemap_cli_total": cli,
            "grep": dict(grep), "grep_total": grep_total,
            "share": {"basis": _SHARE_BASIS, "numerator": numerator, "denominator": denominator,
                      "fraction": numerator / denominator if denominator else None},
            "not_read": "Codex transcripts"}


def render(r: dict) -> str:
    fraction = r["share"]["fraction"]
    share = f"{100 * fraction:.0f} %" if fraction is not None else "—"
    lines = [f"# codemap usage — last {r['days']} day(s)", "",
             f"Transcripts: `{r['transcripts']}` ({r['files']} file(s) touched in the window).", "",
             "| | calls |", "|---|---|",
             f"| codemap (MCP) | {r['codemap_total']} |",
             f"| codemap (CLI in Bash) | {r['codemap_cli_total']} |",
             f"| grep (Grep tool + grep/rg in Bash) | {r['grep_total']} |",
             f"| codemap share | {share} |", ""]
    lines.append(f"Share: {r['share']['basis']}. A Bash tool-use can count once for CLI and once for grep.")
    lines.append("")
    if r["codemap"]:
        lines.append("By tool: " + ", ".join(f"`{k}` {v}" for k, v in
                                             sorted(r["codemap"].items(), key=lambda x: (-x[1], x[0]))))
        lines.append("")
    lines.append(f"_Not read: {r['not_read']}. The Bash scan recognises simple command positions; "
                 "these counts describe tool use, including searches in text, logs and configs._")
    return "\n".join(lines) + "\n"
