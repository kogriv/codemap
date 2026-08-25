"""Build provenance — what produced this graph, and from what (R1-C25).

``graph.json`` is a claim: *this is the shape of that source tree, as read by this
tool*. Until now it recorded the claim and dropped both qualifiers — four top-level
keys, no tool identity, no input identity, and a ``codemap_schema`` that was written
and never read. One frozen tree built by two codemap versions four commits apart gave
30 edges vs 38 and 12 vs 7 ``high`` dead-code verdicts, with **both files declaring
schema 0.11** — correctly, because only open ``extras`` had changed. Provenance is not
schema (gaps/graph_provenance_2026-08-25.md).

Two rules shape everything here:

- **No clock.** The canonical graph is timestamp-free so two builds of a frozen tree
  are byte-identical; a timestamp would destroy exactly the property this block exists
  to make checkable. Wall-clock stays in the ``*.meta.json`` sidecar.
- **No absolute paths.** The graph is the half that travels — into a ticket, a sibling
  repo, an agent's context. A personal path in it is a leak (AGENTS.md), so paths here
  are repo-relative or a bare name, never a location.

Design: ``docs/design/graph_provenance.md`` (D1–D7).
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

TOOL_NAME = "codemap"

#: Schema comparison outcomes (D3).
MATCH, OLDER, NEWER, UNKNOWN = "match", "older", "newer", "unknown"


# -- tool identity (D2) -------------------------------------------------------

@lru_cache(maxsize=1)
def _tool_version() -> str | None:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version(TOOL_NAME)
    except (PackageNotFoundError, ImportError):
        return None


@lru_cache(maxsize=8)
def _commit_of(root: Path) -> str | None:
    """Short HEAD of the checkout at ``root``, or None when it is not one."""
    if not (Path(root) / ".git").exists():
        return None
    try:
        out = subprocess.run(("git", "-C", str(root), "rev-parse", "--short", "HEAD"),
                             capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def _tool_commit() -> str | None:
    """Short commit of codemap's **own** checkout, when it runs from a source tree.

    Absent — not ``"unknown"``, not a guess — when installed from a wheel. The package
    version alone is not an identity: every graph in the R1-C20…R1-C22 series was built
    by version ``0.0.2``, which is why this field exists at all.
    """
    return _commit_of(Path(__file__).resolve().parent.parent)


def tool_identity() -> dict:
    """``{name, version?, commit?}`` — only the fields we actually know."""
    ident: dict = {"name": TOOL_NAME}
    version, commit = _tool_version(), _tool_commit()
    if version:
        ident["version"] = version
    if commit:
        ident["commit"] = commit
    return ident


# -- the block ----------------------------------------------------------------

def canonicalize(value):
    """Sort every dict key, recursively — the block must serialize identically twice."""
    if isinstance(value, dict):
        return {k: canonicalize(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [canonicalize(v) for v in value]
    return value


def relative_root(root: str | Path | None, path: str | Path) -> str:
    """``path`` relative to ``root``, or its bare name — never an absolute path (D5)."""
    p = Path(path)
    if root is not None:
        try:
            return Path(p).resolve().relative_to(Path(root).resolve()).as_posix() or "."
        except (ValueError, OSError):
            pass
    return p.name or "."


def build_provenance(*, tier: str, scope: dict | None = None,
                     roots: dict | None = None) -> dict:
    """Assemble the ``provenance`` block. Deterministic; no clock, no absolute path."""
    prov: dict = {"tool": tool_identity(), "tier": tier}
    if scope:
        if scope.get("scope_id"):
            prov["scope_id"] = scope["scope_id"]
        git = scope.get("git") or {}
        if git.get("mode") == "git" and git.get("commit"):
            source = {"vcs": "git", "commit": git["commit"][:12],
                      "dirty": bool(git.get("dirty"))}
            if git.get("ref"):
                source["ref"] = git["ref"]
            prov["source"] = source
    if roots:
        prov["roots"] = roots
    block = canonicalize(prov)
    leaked = absolute_paths(block)
    if leaked:
        raise ValueError(f"provenance must stay path-free, got {leaked[0]!r}")
    return block


def absolute_paths(value, _path=()) -> list[str]:
    """Every string in ``value`` that looks like an absolute filesystem path (D5)."""
    found: list[str] = []
    if isinstance(value, dict):
        for k in sorted(value):
            found += absolute_paths(value[k], _path + (k,))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            found += absolute_paths(v, _path + (str(i),))
    elif isinstance(value, str):
        if value.startswith("/") or value.startswith("\\\\") or (
                len(value) > 2 and value[1] == ":" and value[2] in "\\/"):
            found.append(value)
    return found


# -- schema comparison (D3) ---------------------------------------------------

def _parts(v: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(p) for p in str(v).split("."))
    except (TypeError, ValueError):
        return None


def schema_status(loaded: str | None, running: str) -> str:
    """``match`` | ``older`` | ``newer`` | ``unknown`` — how a stored graph compares."""
    if loaded is None:
        return UNKNOWN
    if loaded == running:
        return MATCH
    a, b = _parts(loaded), _parts(running)
    if a is None or b is None:
        return UNKNOWN
    return OLDER if a < b else NEWER


# -- comparability of two graphs (D4) -----------------------------------------

def _tool_str(prov: dict) -> str:
    t = (prov or {}).get("tool") or {}
    bits = [t.get("name") or "?"]
    if t.get("version"):
        bits.append(t["version"])
    if t.get("commit"):
        bits.append(f"@{t['commit']}")
    return " ".join(bits)


def describe(prov: dict | None) -> str:
    """One-line human rendering of a provenance block (``unrecorded`` when absent)."""
    if not prov:
        return "unrecorded (built before schema 0.12)"
    bits = [_tool_str(prov), f"tier={prov.get('tier', '?')}"]
    src = prov.get("source") or {}
    if src.get("commit"):
        bits.append(f"source={src['commit']}{'+dirty' if src.get('dirty') else ''}")
    if prov.get("scope_id"):
        bits.append(f"scope={prov['scope_id'][7:19]}")
    return ", ".join(bits)


def comparability(old: dict | None, new: dict | None) -> dict:
    """Are two graphs a before/after of the *code*, or of the *tool*? (D4)

    Never a refusal — comparing across an upgrade is a legitimate thing to want. What
    was missing is being told: on the R1-C25 evidence pair, ``diff`` said "no breaking
    changes" (true, and useless) about two graphs that disagreed on which functions
    were dead.
    """
    differences: list[str] = []
    if not old or not new:
        differences.append("one of the graphs records no provenance "
                           "(built before schema 0.12) — the pair cannot be verified")
    else:
        if _tool_str(old) != _tool_str(new):
            differences.append(f"different tool: {_tool_str(old)} → {_tool_str(new)}")
        if old.get("tier") != new.get("tier"):
            differences.append(f"different tier: {old.get('tier')} → {new.get('tier')}")
        old_roots, new_roots = old.get("roots"), new.get("roots")
        if old_roots != new_roots:
            differences.append(f"different scope roots: {old_roots} → {new_roots}")
    return {
        "comparable": not differences,
        "differences": differences,
        "old": describe(old),
        "new": describe(new),
    }
