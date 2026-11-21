"""`.codemap-devkit.json` — which devkit version the repository is on, and what the devkit last wrote.

Committed with the repository, so every machine sees the same version and the same hashes. It holds no
machine-specific path: the pin lives in `.mcp.json` and the git hook, which are local by default (D2).
"""

from __future__ import annotations

import json
from pathlib import Path

STATE = ".codemap-devkit.json"


def load_state(root: Path) -> dict | None:
    p = Path(root) / STATE
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def save_state(root: Path, state: dict) -> None:
    p = Path(root) / STATE
    p.write_text(json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
