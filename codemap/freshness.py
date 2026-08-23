"""Graph freshness (M18, a first step of the deferred M3.2).

The canonical ``graph.json`` is deterministic and **timestamp-free** by design, so
freshness metadata lives *outside* it:

- the graph file's **mtime** gives build time — works for any graph, no cooperation
  needed — surfaced as ``age_seconds`` in ``stats`` so an agent knows the map may be
  stale;
- an optional **sidecar** ``<graph>.meta.json`` records the exact build invocation so
  a stale graph can be rebuilt with one command (``codemap refresh``).

No timestamps ever enter ``graph.json`` itself — determinism is preserved.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def meta_path(graph_path: str) -> str:
    """Sidecar path for a graph file (``graph.json`` → ``graph.json.meta.json``)."""
    return str(graph_path) + ".meta.json"


def write_meta(graph_path: str, *, argv: list[str], cwd: str, target: str,
               scope: dict | None = None) -> None:
    """Record the build recipe beside a freshly-written graph (best-effort).

    ``scope`` (M19.A) is the input manifest — ``{scope_id, profile, git, files}`` —
    so a graph's exact input is provable/diffable. Provenance, not structure: it lives
    in the sidecar, never in the timestamp-free ``graph.json``.
    """
    meta = {"built_at": round(time.time()), "argv": list(argv),
            "cwd": cwd, "target": target}
    if scope is not None:
        meta["scope"] = scope
    try:
        Path(meta_path(graph_path)).write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass  # freshness metadata is a convenience, never fatal


def read_meta(graph_path: str) -> dict | None:
    """The build recipe sidecar for a graph file, or None if absent/unreadable."""
    try:
        return json.loads(Path(meta_path(graph_path)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def freshness(graph_path: str | None, *, now: float | None = None,
              served_mtime: float | None = None) -> dict | None:
    """Freshness of a graph: ``{built_at, age_seconds, rebuild?, stale?, ...}`` or None.

    ``built_at``/``age_seconds`` describe the graph **actually in hand**. For a one-shot
    read that is the on-disk file's mtime. For a long-lived server that cached the graph
    at start, pass ``served_mtime`` (the file mtime captured when it loaded): then the
    report is about the *served* snapshot, and if the on-disk file has since advanced,
    it is flagged ``stale: True`` with ``on_disk_built_at`` + a ``reason`` — never the
    silent "fresh" that issue #3 caught (a stale answer labelled current). ``rebuild``
    (the recorded ``argv``/``cwd``) is present only when a sidecar exists.
    """
    if not graph_path:
        return None
    now = time.time() if now is None else now
    try:
        disk_mtime = os.path.getmtime(graph_path)
    except OSError:
        disk_mtime = None
    if disk_mtime is None and served_mtime is None:
        return None  # nothing on disk and nothing served — unknown

    base = served_mtime if served_mtime is not None else disk_mtime
    out = {"built_at": round(base), "age_seconds": max(0, round(now - base))}
    # On-disk divergence: the served snapshot is older than the artifact on disk
    # (an external rebuild happened) — or the artifact is gone. Say so, don't reassure.
    if served_mtime is not None:
        if disk_mtime is None:
            out["stale"] = True
            out["reason"] = ("the on-disk graph is gone since this server loaded it; "
                             "restart to serve a current graph")
        elif disk_mtime > served_mtime + 1e-6:
            out["stale"] = True
            out["on_disk_built_at"] = round(disk_mtime)
            out["reason"] = ("the on-disk graph was rebuilt after this server loaded "
                             "it; call `reload` (or restart) to serve the current graph")
    meta = read_meta(graph_path)
    if meta and meta.get("argv"):
        out["rebuild"] = {"argv": meta["argv"], "cwd": meta.get("cwd")}
    return out
