"""The `allowed` region of the contract and the starter contract (R1-C108 D3).

The region lives inside ``[architecture]`` in ``codemap.toml`` between two marker comments, and it is edited
line by line: a pair line is ``{ from = "…", to = "…" },`` with an optional ``# comment``. Generating adds the
pairs the graph uses that the list lacks; ``tighten`` removes exactly the pair lines no import uses any more.
Every other line — comments, hand-added pairs with their reasons — is kept byte for byte. Whatever the edit,
the new file must still read as a valid contract, or nothing is written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from codemap.devkit import DEVKIT_VERSION, render, template

BEGIN = re.compile(r"^# >>> codemap-devkit allowed v\d+")
END = "# <<< codemap-devkit allowed"
PAIR = re.compile(r'^\s*\{\s*from\s*=\s*"([^"]+)"\s*,\s*to\s*=\s*"([^"]+)"\s*\}\s*,?\s*(#.*)?$')
# A table header, not an array line: `  ["pkg.a", "pkg.b"],` inside the cycles region also opens with `[` (R1-C116).
TABLE = re.compile(r'^\s*\[\[?[^\]",]*\]\]?\s*(#.*)?$')


class RatchetError(Exception):
    """The contract cannot be edited safely; nothing was written."""


@dataclass
class RatchetResult:
    path: Path
    added: list[tuple[str, str]] = field(default_factory=list)
    removed: list[tuple[str, str]] = field(default_factory=list)
    created_region: bool = False
    created_table: bool = False
    text: str = ""


def pair_line(a: str, b: str) -> str:
    return f'  {{ from = "{a}", to = "{b}" }},'


def _region_text(pairs: list[tuple[str, str]], package_name: str) -> str:
    body = "".join(pair_line(a, b) + "\n" for a, b in pairs)
    return render(template("ratchet_region.toml"),
                  {"devkit_version": DEVKIT_VERSION, "pairs": body})


def _find_table(lines: list[str]) -> tuple[int, int] | None:
    """``(header, end)`` line indices of ``[architecture]``; ``end`` is exclusive."""
    for i, ln in enumerate(lines):
        if ln.strip() == "[architecture]":
            j = i + 1
            while j < len(lines) and not TABLE.match(lines[j]):
                j += 1
            return i, j
    return None


def _find_region(lines: list[str], lo: int, hi: int) -> tuple[int, int] | None:
    for i in range(lo, hi):
        if BEGIN.match(lines[i]):
            for j in range(i + 1, hi):
                if lines[j].rstrip() == END:
                    return i, j
            raise RatchetError("the `allowed` region has a begin marker and no end marker")
    return None


def _validate(text: str, path: Path) -> None:
    import tomllib

    from codemap.arch import parse_contract
    try:
        data = tomllib.loads(text)
    except ValueError as exc:
        raise RatchetError(f"the edited {path.name} would not be valid TOML ({exc}); nothing written")
    c = parse_contract(data.get("architecture", {}))
    if c.error:
        raise RatchetError(f"the edited {path.name} would not be a valid contract ({c.error}); "
                           "nothing written")


def edit_region(root: Path, used: list[tuple[str, str]], *, tighten: bool = False,
                create_table_flags: str | None = None, package_name: str = "",
                graph: str = "", dry_run: bool = False) -> RatchetResult:
    """Bring the `allowed` region in line with ``used`` (the graph's layer pairs, sorted).

    No region yet: write one holding ``used``. ``create_table_flags`` given and no ``[architecture]``
    table: write the starter contract (head + flags + region). A region present: add the pairs ``used``
    has and the list lacks; with ``tighten``, also remove pair lines whose pair is not in ``used``.
    """
    path = root / "codemap.toml"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = text.splitlines(keepends=True)
    res = RatchetResult(path=path)
    table = _find_table([ln.rstrip("\n") for ln in lines])
    if table is None:
        if create_table_flags is None:
            raise RatchetError(f"{path} has no `[architecture]` table; `codemap devkit init` writes one")
        head = render(template("contract_head.toml"),
                      {"package_name": package_name, "graph": graph,
                       "devkit_version": DEVKIT_VERSION, "flags": create_table_flags.rstrip("\n")})
        sep = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        new = text + sep + head.rstrip("\n") + "\n" + _region_text(used, package_name)
        res.added, res.created_region, res.created_table = list(used), True, True
    else:
        lo, hi = table
        plain = [ln.rstrip("\n") for ln in lines]
        region = _find_region(plain, lo + 1, hi)
        if region is None:
            for k in range(lo + 1, hi):
                if re.match(r"^\s*allowed\s*=", plain[k]):
                    raise RatchetError("`allowed` is written by hand outside the devkit's region; "
                                       "`codemap devkit ratchet` edits only its own region")
            # insert at the end of the table, before its trailing blank lines
            at = hi
            while at > lo + 1 and not plain[at - 1].strip():
                at -= 1
            block = _region_text(used, package_name)
            new = "".join(lines[:at]) + block + "".join(lines[at:])
            res.added, res.created_region = list(used), True
        else:
            b, e = region
            have: list[tuple[str, str]] = []
            out = lines[:b + 1]
            close = None
            for k in range(b + 1, e):
                m = PAIR.match(plain[k])
                if m:
                    pair = (m.group(1), m.group(2))
                    if tighten and pair not in used:
                        res.removed.append(pair)
                        continue
                    have.append(pair)
                elif plain[k].strip() == "]":
                    close = len(out)
                out.append(lines[k])
            if close is None:
                raise RatchetError("the `allowed` region has no closing `]` on a line of its own")
            missing = [p for p in used if p not in have]
            res.added = missing
            out[close:close] = [pair_line(a, b) + "\n" for a, b in missing]
            new = "".join(out) + "".join(lines[e:])
    _validate(new, path)
    res.text = new
    if not dry_run and new != text:
        path.write_text(new, encoding="utf-8")
    return res


# --------------------------------------------------------------------------- R1-C116: the cycle region

CBEGIN = re.compile(r"^# >>> codemap-devkit cycles v\d+")
CEND = "# <<< codemap-devkit cycles"
CKEY = re.compile(r"^\s*(known_lazy_cycles|known_type_only_cycles)\s*=\s*\[\s*$")
GROUP = re.compile(r'^\s*\[\s*((?:"[^"]+"\s*,\s*)*"[^"]+")\s*,?\s*\]\s*,?\s*(#.*)?$')
CYCLE_KEYS = ("known_lazy_cycles", "known_type_only_cycles")


@dataclass
class CyclesResult:
    path: Path
    added: dict[str, list[frozenset[str]]] = field(default_factory=dict)
    removed: dict[str, list[frozenset[str]]] = field(default_factory=dict)
    created_region: bool = False
    text: str = ""


def group_line(group) -> str:
    return "  [" + ", ".join(f'"{m}"' for m in sorted(group)) + "],"


def has_cycles_region(root: Path) -> bool:
    path = root / "codemap.toml"
    return path.is_file() and any(CBEGIN.match(ln) for ln in path.read_text(encoding="utf-8").splitlines())


def edit_cycles_region(root: Path, now: dict[str, list[frozenset[str]]], *, tighten: bool = False,
                       dry_run: bool = False) -> CyclesResult:
    """Bring the known-cycles region in line with ``now`` (key → the graph's tangles as module sets).

    No region: write one listing ``now``. A region: add each tangle no listed group contains; with ``tighten``,
    remove group lines that contain no tangle. Other lines — comments, hand-added groups — are kept.
    """
    path = root / "codemap.toml"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = text.splitlines(keepends=True)
    plain = [ln.rstrip("\n") for ln in lines]
    res = CyclesResult(path=path)
    table = _find_table(plain)
    if table is None:
        raise RatchetError(f"{path} has no `[architecture]` table; `codemap devkit init` writes one")
    lo, hi = table
    region = None
    for i in range(lo + 1, hi):
        if CBEGIN.match(plain[i]):
            end = next((j for j in range(i + 1, hi) if plain[j].rstrip() == CEND), None)
            if end is None:
                raise RatchetError("the cycles region has a begin marker and no end marker")
            region = (i, end)
            break
    if region is None:
        for k in range(lo + 1, hi):
            m = re.match(r"^\s*(known_lazy_cycles|known_type_only_cycles)\s*=", plain[k])
            if m:
                raise RatchetError(f"`{m.group(1)}` is written by hand outside the devkit's region; "
                                   "`codemap devkit ratchet` edits only its own region")
        body = {key: "".join(group_line(g) + "\n" for g in sorted(now.get(key, []), key=sorted))
                for key in CYCLE_KEYS}
        block = render(template("cycles_region.toml"), {"devkit_version": DEVKIT_VERSION,
                                                        "lazy": body["known_lazy_cycles"],
                                                        "type_only": body["known_type_only_cycles"]})
        at = hi
        while at > lo + 1 and not plain[at - 1].strip():
            at -= 1
        new = "".join(lines[:at]) + block + "".join(lines[at:])
        res.added = {k: list(v) for k, v in now.items() if v}
        res.created_region = True
    else:
        b, e = region
        out = lines[:b + 1]
        key = None
        have: dict[str, list[frozenset[str]]] = {k: [] for k in CYCLE_KEYS}
        close: dict[str, int] = {}
        for k in range(b + 1, e):
            km = CKEY.match(plain[k])
            if km:
                key = km.group(1)
            elif key and plain[k].strip() == "]":
                close[key] = len(out)
                key = None
            elif key:
                g = GROUP.match(plain[k])
                if g:
                    group = frozenset(re.findall(r'"([^"]+)"', g.group(1)))
                    tangles = now.get(key, [])
                    if tighten and not any(t <= group for t in tangles) and not any(
                            group < t for t in tangles):   # absorbed whole: alive inside a larger one (R1-C123)
                        res.removed.setdefault(key, []).append(group)
                        continue
                    have[key].append(group)
            out.append(lines[k])
        missing_keys = [k for k in CYCLE_KEYS if k not in close]
        if missing_keys:
            raise RatchetError("the cycles region has no closing `]` for " + ", ".join(f"`{k}`" for k in missing_keys))
        inserts = []
        for k in CYCLE_KEYS:
            add = sorted((t for t in now.get(k, []) if not any(t <= g for g in have[k])), key=sorted)
            if add:
                res.added[k] = add
                inserts.append((close[k], [group_line(g) + "\n" for g in add]))
        for at, rows in sorted(inserts, reverse=True):
            out[at:at] = rows
        new = "".join(out) + "".join(lines[e:])
    _validate(new, path)
    res.text = new
    if not dry_run and new != text:
        path.write_text(new, encoding="utf-8")
    return res


def tangles_now(query) -> dict[str, list[frozenset[str]]]:
    return {"known_lazy_cycles": [frozenset(t["modules"]) for t in query.lazy_import_tangles()],
            "known_type_only_cycles": [frozenset(t["modules"]) for t in query.type_only_import_tangles()]}


def starter_flags(query) -> str:
    """`no_cycles` / `no_type_only_cycles` on when the graph holds them today; else a comment with the count.

    A gate that is red on day one is not a ratchet (D3).
    """
    eager = query.import_tangles()
    type_only = query.type_only_import_tangles()
    lazy = query.lazy_import_tangles()
    out = []
    out.append("no_cycles = true" if not eager else
               f"# no_cycles = true  — {len(eager)} import tangle(s) close at import time today; "
               "turn on once they are gone")
    out.append("no_type_only_cycles = true" if not type_only else
               f"# no_type_only_cycles = true  — {len(type_only)} tangle(s) closed only under "
               "TYPE_CHECKING today")
    out.append(f"# no_lazy_cycles = true  — {len(lazy)} tangle(s) closed by a function-local import today"
               if lazy else "no_lazy_cycles = true")
    return "\n".join(out) + "\n"
