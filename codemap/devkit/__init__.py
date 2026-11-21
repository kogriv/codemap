"""The devkit: codemap adopted by a project in one command, kept current by codemap's suite (R1-C108).

Design ``docs/design/devkit.md``. Templates live in ``templates/`` (package data) and are rendered into a
project's repository by ``codemap devkit init | update``; ``status`` says what is behind. The devkit writes
only regions it owns, records the hash of what it wrote in ``.codemap-devkit.json``, and never overwrites a
region edited by hand or an artifact it did not write without ``--force`` (D2).

What keeps the templates current is ``tests/test_r1c108_devkit.py``, not memory (D7): every command in every
template parses with the CLI's own parser, every MCP tool a template names exists, and a template cannot
change without ``DEVKIT_VERSION`` and ``TEMPLATES_SHA256`` changing with it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

#: Raised whenever a template changes; adopting projects see "outdated" in `codemap devkit status`.
DEVKIT_VERSION = 1

#: sha256 over the templates (name + content, sorted). The suite recomputes it: a template edited without
#: bumping DEVKIT_VERSION and updating this value fails there, in the same commit (D7).
TEMPLATES_SHA256 = "98882c967d953e4e5bc689c15a69cceac3802f85e9ecbb445fd8b9bc6f25ad64"

TEMPLATES_DIR = Path(__file__).parent / "templates"


def template(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def templates_sha256() -> str:
    h = hashlib.sha256()
    for p in sorted(TEMPLATES_DIR.iterdir()):
        if p.is_file():
            h.update(p.name.encode())
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def render(text: str, ctx: dict[str, object]) -> str:
    """Replace ``{{name}}`` placeholders. An unknown placeholder is an error, not left in the output."""
    import re

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in ctx:
            raise KeyError(f"template placeholder `{{{{{key}}}}}` has no value")
        return str(ctx[key])

    return re.sub(r"\{\{(\w+)\}\}", sub, text)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
