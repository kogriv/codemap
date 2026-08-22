"""Transport helpers for adapters/routers that call an external tool (DESIGN §13).

Modes 3–4 call a **user-installed** tool as a subprocess (or MCP client) — codemap
bundles nothing (DESIGN §13.1 п.1: calling ≠ distributing). These helpers keep that
call uniform: locate the binary, run it, parse JSON. Failures return None rather
than raising, so a flaky external tool degrades to "capability unavailable", never a
crash of the core.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any


def which(binary: str) -> str | None:
    """Absolute path to a user-installed binary on PATH, or None."""
    return shutil.which(binary)


def run_json(cmd: list[str], *, timeout: float = 120.0,
             input_text: str | None = None, cwd: str | None = None) -> Any | None:
    """Run ``cmd``, parse stdout as JSON, return it (or None on any failure).

    A non-zero exit, timeout, missing binary, or non-JSON stdout all yield None —
    the caller treats that as "the external tool couldn't answer" and falls back to
    the deterministic core. ``cwd`` runs the tool in a specific directory (some
    tools, e.g. a per-repo index, key off the working dir).
    """
    if not cmd or which(cmd[0]) is None:
        return None
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            input=input_text, cwd=cwd,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except (ValueError, TypeError):
        return None
