"""What the Claude Code hooks run, and the digest they read (R1-C108 D5).

- ``brief`` (SessionStart): graph currency and the rule in one paragraph, as plain stdout. It never loads
  the graph: currency comes from the meta sidecar and a re-hash of the input scope.
- ``touched`` (PostToolUse on Edit/Write): reads the hook payload on stdin; for a module of the package it
  prints ``hookSpecificOutput.additionalContext`` — how many modules import it and which of its functions
  have outside callers. It reads ``.codemap/devkit/index.json`` (a few hundred KB), never the graph.
- ``index``: writes that digest; the post-commit hook runs it after every successful build.

A hook must never block or break the session: both always exit 0, and anything unexpected becomes one line
saying what is missing.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

INDEX = ".codemap/devkit/index.json"


def _state(root: Path) -> dict:
    """The state, or the defaults when there is none — or when it was refused (R1-C121): a hook must not
    follow a committed path out of the repository, and must not break the session either."""
    from codemap.devkit.state import StateError, load_state
    try:
        return load_state(root) or {}
    except StateError:
        return {}


def _graph_path(root: Path, st: dict) -> Path:
    return root / st.get("graph", ".codemap/graph.json")


def _ago(ts: float) -> str:
    d = max(0, int(time.time() - ts))
    if d < 120:
        return f"{d} s ago"
    if d < 7200:
        return f"{d // 60} min ago"
    if d < 172800:
        return f"{d // 3600} h ago"
    return f"{d // 86400} days ago"


def currency_line(root: Path, st: dict) -> str:
    from codemap.freshness import read_meta
    from codemap.serve.currency import graph_currency
    gp = _graph_path(root, st)
    rel = os.path.relpath(gp, root)
    if not gp.is_file():
        # R1-C119: a fresh clone has no graph and `refresh` has no recipe to repeat — give the first build.
        from codemap.devkit import build_args
        cmd = " ".join(x for x in ("codemap build", st.get("package", "<package>"), build_args(st), "-o", rel) if x)
        return (f"absent ({rel} does not exist; build it once: `{cmd}` — after that the post-commit hook "
                "keeps it)")
    meta = read_meta(str(gp)) or {}
    built = meta.get("built_at")
    when = f", built {_ago(built)}" if isinstance(built, (int, float)) else ""
    scope_id = (meta.get("scope") or {}).get("scope_id")
    cur = graph_currency(str(gp), scope_id, base=str(root))
    status = cur.get("status")
    if status == "current":
        return f"current ({rel}{when})"
    if status == "behind":
        parts = [f"{cur[k]} {k}" for k in ("changed", "added", "removed") if cur.get(k)]
        return (f"BEHIND its source tree ({', '.join(parts) or 'the scope differs'}{when}) — answers describe "
                f"the older tree until it is rebuilt: `codemap refresh {rel}`")
    return f"of unknown currency ({cur.get('reason', 'no recipe')}{when})"


def brief(root: Path) -> int:
    try:
        from codemap.devkit import DEVKIT_VERSION, render, template
        st = _state(root)
        installed = st.get("devkit_version")
        note = ""
        if installed is not None and installed < DEVKIT_VERSION:
            note = (f" in this repository, v{DEVKIT_VERSION} available — `codemap devkit status`")
        text = render(template("brief.txt"), {
            "package": st.get("package", "the package"),
            "currency": currency_line(root, st),
            "agents_file": st.get("agents_file", "AGENTS.md"),
            "devkit_version": installed if installed is not None else DEVKIT_VERSION,
            "devkit_note": note,
        })
        print(text.strip())
    except Exception as exc:  # noqa: BLE001 - a hook must never break the session
        print(f"codemap: the devkit brief could not be produced ({type(exc).__name__}: {exc}).")
    return 0


def build_index(graph) -> dict:
    """Per source file of the core: the module, its importer count, its functions with outside callers."""
    nodes = graph.nodes
    file_of = {nid: n.file for nid, n in nodes.items() if n.file}
    module_of_file: dict[str, str] = {}
    for nid, n in nodes.items():
        if n.kind == "module" and n.file:
            module_of_file[n.file] = nid
    importers: dict[str, set[str]] = {}
    callers: dict[str, set[str]] = {}
    for e in graph.edges:
        if e.type == "imports":
            importers.setdefault(e.target, set()).add(e.source)
        elif e.type == "calls":
            src_file, dst_file = file_of.get(e.source), file_of.get(e.target)
            if dst_file and src_file != dst_file:
                callers.setdefault(e.target, set()).add(e.source)
    out: dict[str, dict] = {}
    for f, mid in module_of_file.items():
        if (nodes[mid].extras or {}).get("root", "core") != "core":
            continue
        top = sorted(((nid, len(c)) for nid, c in callers.items()
                      if file_of.get(nid) == f and nodes[nid].kind == "function"),
                     key=lambda x: (-x[1], x[0]))[:5]
        out[f] = {"module": mid, "importers": len(importers.get(mid, ())),
                  "top": [[nid.rsplit(".", 1)[-1] if nid.startswith(mid + ".") else nid, n]
                          for nid, n in top]}
    return out


def index(root: Path, graph_path: str | None = None) -> int:
    from codemap import store
    from codemap.freshness import read_meta
    st = _state(root)
    gp = Path(graph_path) if graph_path else _graph_path(root, st)
    if not gp.is_file():
        print(f"error: no graph at {gp}", file=sys.stderr)
        return 1
    graph = store.load(str(gp))
    meta = read_meta(str(gp)) or {}
    data = {"graph": os.path.relpath(gp, root), "built_at": meta.get("built_at"),
            "files": build_index(graph)}
    out = root / INDEX
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    tmp.replace(out)
    print(f"{out.relative_to(root)}: {len(data['files'])} file(s)")
    return 0


def touched(root: Path, payload: str | None = None) -> int:
    try:
        raw = sys.stdin.read() if payload is None else payload
        data = json.loads(raw) if raw.strip() else {}
        fp = ((data.get("tool_input") or {}).get("file_path")) or ""
        if not fp or not fp.endswith(".py"):
            return 0
        try:
            rel = os.path.relpath(Path(fp).resolve(), root.resolve())
        except ValueError:
            return 0
        if rel.startswith(".."):
            return 0
        idx_path = root / INDEX
        st = _state(root)
        pkg = st.get("package")
        if pkg and not (rel == pkg or rel.startswith(pkg.rstrip("/") + "/")):
            return 0
        if not idx_path.is_file():
            ctx = ("codemap: no devkit index yet (.codemap/devkit/index.json) — it appears after the next "
                   "commit's graph build, or run `codemap devkit index`.")
        else:
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
            entry = (idx.get("files") or {}).get(rel)
            if entry is None:
                ctx = (f"codemap: {rel} is not in the graph yet (new file, or the graph predates it); "
                       "the next commit's build adds it.")
            else:
                top = ", ".join(f"`{n}` ({c})" for n, c in entry.get("top", []))
                ctx = (f"codemap: `{entry['module']}` is imported by {entry['importers']} module(s)"
                       + (f"; its functions with callers elsewhere: {top}" if top else
                          "; none of its functions has callers in other files")
                       + ". Before changing a public signature here, run `impact` on it.")
                built = idx.get("built_at")
                try:
                    if isinstance(built, (int, float)) and Path(fp).stat().st_mtime > built:
                        ctx += " (Counts are from the last commit's graph.)"
                except OSError:
                    pass
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                 "additionalContext": ctx}}))
    except Exception:  # noqa: BLE001 - a hook must never break the session
        return 0
    return 0
