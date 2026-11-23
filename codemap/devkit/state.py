"""`.codemap-devkit.json` — which devkit version the repository is on, and what the devkit last wrote.

Committed with the repository, so every machine sees the same version and the same hashes. It holds no
machine-specific path: the pin lives in `.mcp.json` and the git hook, which are local by default (D2).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

STATE = ".codemap-devkit.json"

#: A path the devkit stores and later renders into shell, YAML and Markdown (R1-C121): relative, inside the
#: repository, from a plain alphabet. Anything else in the committed state is refused, not escaped later.
SAFE_PATH = re.compile(r"[A-Za-z0-9._@+-][A-Za-z0-9._/@+-]*")


class StateError(Exception):
    """`.codemap-devkit.json` (or a path given on the command line) is not one the devkit will act on."""


def path_problem(root: Path, value, field: str) -> str | None:
    """Why ``value`` may not name a file of this repository, or None (R1-C121).

    The state file is committed, so it is input from whoever last pushed: a `../` or an absolute path, a
    symbolic link that leaves the root, or a shell metacharacter would make the devkit write outside the
    repository or run what a template renders.
    """
    if not isinstance(value, str) or not value:
        return f"`{field}` must be a non-empty string"
    if not SAFE_PATH.fullmatch(value):
        return (f"`{field}` = {value!r}: only letters, digits and `._/@+-` are allowed in a path the devkit "
                "stores (it is rendered into shell and YAML)")
    if value.startswith("/") or ".." in Path(value).parts:
        return f"`{field}` = {value!r} leaves the repository (absolute, or `..`)"
    base = Path(root).resolve()
    if not (base / value).resolve().is_relative_to(base):
        return f"`{field}` = {value!r} resolves outside the repository (a symbolic link?)"
    return None


def state_problems(root: Path, st: dict) -> list[str]:
    out = []
    for field in ("package", "graph", "agents_file"):
        if field in st:
            out.append(path_problem(root, st[field], field))
    for field in ("consumers", "docs"):
        vals = st.get(field, [])
        if not isinstance(vals, list):
            out.append(f"`{field}` must be a list")
            continue
        out += [path_problem(root, v, f"{field}[{i}]") for i, v in enumerate(vals)]
    if "agents_lang" in st and st["agents_lang"] not in ("en", "ru"):
        out.append(f"`agents_lang` = {st['agents_lang']!r}: en or ru")
    return [p for p in out if p]


def load_state(root: Path) -> dict | None:
    """The state, or None when there is none. Raises :class:`StateError` when it names a path the devkit must
    not act on (R1-C121): a committed file is no more trusted than any other input."""
    p = Path(root) / STATE
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    problems = state_problems(root, data)
    if problems:
        raise StateError(f"{STATE} refused — " + "; ".join(problems))
    return data


def save_state(root: Path, state: dict) -> None:
    p = Path(root) / STATE
    from codemap import atomic
    atomic.write_text(p, json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
