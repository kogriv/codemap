"""Is codemap used? Tool calls in local Claude Code transcripts, against grep (R1-C108 D6).

Reads ``~/.claude/projects/<project path with "/" → "-">/**/*.jsonl`` (or ``--transcripts``) — sessions and
their subagents. Counts tool uses named ``mcp__codemap__*`` against the ``Grep`` tool and Bash commands that run
``grep`` or ``rg``. Only ``assistant`` records count, once per tool-use id: a transcript also stores request
blobs that repeat earlier calls without a timestamp, and counting them inflated the numbers (measured on the
acceptance run, 1 301 repeats in 16 536). Only names and counts are read, never message text. Codex keeps its transcripts elsewhere and in another shape; they are
not read, and the report says so.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

# A command starts at the line start (a newline separates commands in bash), after `;`, `&`, `|`, `(`, or as
# the argument of `xargs`.
GREP_CMD = re.compile(r"(?:^[ \t]*|[;&|(][ \t]*|\bxargs[ \t]+)(?:grep|egrep|rg)\b", re.MULTILINE)


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
                        if GREP_CMD.search(cmd):
                            grep["grep/rg in Bash"] += 1
    return {"transcripts": str(directory), "files": files, "days": days,
            "codemap": dict(codemap), "codemap_total": sum(codemap.values()),
            "grep": dict(grep), "grep_total": sum(grep.values()),
            "not_read": "Codex transcripts"}


def render(r: dict) -> str:
    total = r["codemap_total"] + r["grep_total"]
    share = f"{100 * r['codemap_total'] / total:.0f} %" if total else "—"
    lines = [f"# codemap usage — last {r['days']} day(s)", "",
             f"Transcripts: `{r['transcripts']}` ({r['files']} file(s) touched in the window).", "",
             "| | calls |", "|---|---|",
             f"| codemap (MCP) | {r['codemap_total']} |",
             f"| grep (Grep tool + grep/rg in Bash) | {r['grep_total']} |",
             f"| codemap share | {share} |", ""]
    if r["codemap"]:
        lines.append("By tool: " + ", ".join(f"`{k}` {v}" for k, v in
                                             sorted(r["codemap"].items(), key=lambda x: (-x[1], x[0]))))
        lines.append("")
    lines.append(f"_Not read: {r['not_read']}. Grep counts every search, including non-structural ones "
                 "(text, logs, configs), so the share is a floor for structure questions, not a score._")
    return "\n".join(lines) + "\n"
