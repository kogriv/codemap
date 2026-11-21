"""The artifacts the devkit manages, and the one rule for touching them (R1-C108 D2).

Each artifact can say what its managed content is *now* (``current``), whether something that is not the
devkit's occupies its place (``foreign``), and how to write new content (``write``). The caller compares the
current content's hash with the hash recorded when the devkit last wrote it:

- equal  → the devkit may rewrite it (``outdated`` if the new rendering differs, else ``current``);
- differ → it was edited by hand: reported, left alone, rewritten only with ``--force``;
- foreign → never overwritten without ``--force``; where there is somewhere else to put the devkit's
  version (the git hook), it goes there and the report says so.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

MD_BEGIN = re.compile(r"<!-- codemap-devkit:begin v\d+[^\n]*?-->")
MD_END = "<!-- codemap-devkit:end -->"
TOML_BEGIN = re.compile(r"^# >>> codemap-devkit v\d+[^\n]*$", re.M)
TOML_END = "# <<< codemap-devkit"
HOOK_MARK = "# codemap-devkit:post-commit v"
CI_MARK = "# codemap-devkit:ci v"
HOOK_COMMANDS = (" devkit brief", " devkit touched")


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _write(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2)


@dataclass
class Artifact:
    key: str          # name in the state file and the report
    path: Path

    def current(self) -> str | None:          # managed content now, None when absent
        raise NotImplementedError

    def foreign(self) -> bool:                # something not the devkit's sits in its place
        return False

    def write(self, content: str) -> None:
        raise NotImplementedError

    def alternative(self) -> Path | None:     # where the devkit's version goes when the place is foreign
        return None

    def normalize(self, content: str) -> str:   # the form `current()` returns once `content` is written
        return content


class MarkdownRegion(Artifact):
    """The agent-rules block in AGENTS.md (or CLAUDE.md): between the begin and end markers."""

    def normalize(self, content: str) -> str:
        return content.rstrip("\n")

    def _span(self, text: str) -> tuple[int, int] | None:
        m = MD_BEGIN.search(text)
        if not m:
            return None
        end = text.find(MD_END, m.end())
        if end < 0:
            return None
        return m.start(), end + len(MD_END)

    def current(self) -> str | None:
        text = _read(self.path)
        if text is None:
            return None
        span = self._span(text)
        return text[span[0]:span[1]] if span else None

    def write(self, content: str) -> None:
        text = _read(self.path)
        block = content.rstrip("\n")
        if text is None:
            _write(self.path, f"# {self.path.name}\n\n{block}\n")
            return
        span = self._span(text)
        if span:
            _write(self.path, text[:span[0]] + block + text[span[1]:])
        else:
            sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
            _write(self.path, text + sep + block + "\n")


class TomlRegion(Artifact):
    """The Codex MCP entry in .codex/config.toml: between `# >>> codemap-devkit` and `# <<<`."""

    def normalize(self, content: str) -> str:
        return content.rstrip("\n")

    def _span(self, text: str) -> tuple[int, int] | None:
        m = TOML_BEGIN.search(text)
        if not m:
            return None
        end = text.find(TOML_END, m.end())
        if end < 0:
            return None
        return m.start(), end + len(TOML_END)

    def current(self) -> str | None:
        text = _read(self.path)
        if text is None:
            return None
        span = self._span(text)
        return text[span[0]:span[1]] if span else None

    def foreign(self) -> bool:
        text = _read(self.path)
        if text is None:
            return False
        span = self._span(text)
        outside = text if not span else text[:span[0]] + text[span[1]:]
        return re.search(r"^\s*\[mcp_servers\.codemap\]", outside, re.M) is not None

    def write(self, content: str) -> None:
        text = _read(self.path)
        block = content.rstrip("\n")
        if text is None:
            _write(self.path, block + "\n")
            return
        span = self._span(text)
        if span:
            _write(self.path, text[:span[0]] + block + text[span[1]:])
        else:
            sep = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
            _write(self.path, text + sep + block + "\n")


class JsonKey(Artifact):
    """`mcpServers.codemap` in .mcp.json. The devkit's entry is recognised by the recorded hash only:
    an entry it has no record of is foreign, whatever it says."""

    recorded: str | None = None

    def _load(self) -> dict | None:
        text = _read(self.path)
        if text is None:
            return None
        try:
            data = json.loads(text)
        except ValueError:
            return {"__unreadable__": True}
        return data if isinstance(data, dict) else {"__unreadable__": True}

    def entry(self) -> dict | None:
        data = self._load()
        if not data or data.get("__unreadable__"):
            return None
        servers = data.get("mcpServers")
        return servers.get("codemap") if isinstance(servers, dict) else None

    def current(self) -> str | None:
        e = self.entry()
        return None if e is None else _canon(e)

    def unreadable(self) -> bool:
        data = self._load()
        return bool(data and data.get("__unreadable__"))

    def foreign(self) -> bool:
        # Unreadable JSON, or an entry the devkit has no record of writing.
        return self.unreadable() or (self.current() is not None and self.recorded is None)

    def write(self, content: str) -> None:
        data = self._load() or {}
        if data.get("__unreadable__"):
            raise ValueError(f"{self.path} is not valid JSON; not touched")
        servers = data.setdefault("mcpServers", {})
        servers["codemap"] = json.loads(content)
        _write(self.path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


class WholeFile(Artifact):
    """A file the devkit owns whole, recognised by its marker line (git hook, CI workflow)."""

    marker: str = ""
    mode: int | None = None
    alt: Path | None = None

    def current(self) -> str | None:
        text = _read(self.path)
        if text is None or self.marker not in text:
            return None
        return text

    def foreign(self) -> bool:
        text = _read(self.path)
        return text is not None and self.marker not in text

    def write(self, content: str) -> None:
        _write(self.path, content, self.mode)

    def alternative(self) -> Path | None:
        return self.alt


class ClaudeHooks(Artifact):
    """The devkit's entries under `hooks` in .claude/settings.json: groups whose command runs
    `devkit brief` or `devkit touched`. Every other hook and setting is left as it is."""

    def _load(self) -> dict | None:
        text = _read(self.path)
        if text is None:
            return None
        try:
            data = json.loads(text)
        except ValueError:
            return {"__unreadable__": True}
        return data if isinstance(data, dict) else {"__unreadable__": True}

    @staticmethod
    def _ours(group) -> bool:
        if not isinstance(group, dict):
            return False
        return any(isinstance(h, dict) and any(c in str(h.get("command", "")) for c in HOOK_COMMANDS)
                   for h in group.get("hooks", []) or [])

    def current(self) -> str | None:
        data = self._load()
        if not data or data.get("__unreadable__"):
            return None
        hooks = data.get("hooks") or {}
        mine = {ev: [g for g in groups if self._ours(g)]
                for ev, groups in hooks.items() if isinstance(groups, list)}
        mine = {ev: gs for ev, gs in mine.items() if gs}
        return _canon(mine) if mine else None

    def foreign(self) -> bool:
        data = self._load()
        return bool(data and data.get("__unreadable__"))

    def write(self, content: str) -> None:
        data = self._load() or {}
        if data.get("__unreadable__"):
            raise ValueError(f"{self.path} is not valid JSON; not touched")
        new = json.loads(content)
        hooks = data.setdefault("hooks", {})
        for ev in list(hooks):
            if isinstance(hooks[ev], list):
                hooks[ev] = [g for g in hooks[ev] if not self._ours(g)]
                if not hooks[ev]:
                    del hooks[ev]
        for ev, groups in new.items():
            hooks.setdefault(ev, []).extend(groups)
        _write(self.path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def canon_json(text: str) -> str:
    """The canonical form the JSON artifacts compare in."""
    return _canon(json.loads(text))
