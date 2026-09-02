"""Input scope manifest — M19.A (design: ``docs/design/scope.md``).

A deterministic identity of the **input** that produced a graph. codemap is already
deterministic on its *output* (canonical ``graph.json``); this is the symmetric thing
for the *input*: resolve a scope (build args / spec) to a **sorted file list**,
content-hash each file (sha-256), build a **profile**, and compute a **scope_id**.

Operates **in place over the real tree** (the live path — enables watch/incremental
downstream). When the root is a git repo, enumeration prefers ``git ls-files`` (the
gitignore-correct set — no venv/build/cache, for free) and records git provenance;
identity (``scope_id``) is always our sha-256, independent of git and of dirty state.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

# What codemap actually consumes as input (source + docs it indexes as references).
DEFAULT_INCLUDE = ("*.py", "*.md")
# fs-mode default excludes (git mode gets these for free via .gitignore).
DEFAULT_EXCLUDE_DIRS = frozenset({
    "__pycache__", ".git", ".venv", "venv", "node_modules", "build", "dist",
    ".eggs", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
})
_LARGEST_N = 10
# consumer dir name → role; anything else keeps its own basename as the role.
_KNOWN_ROLES = frozenset({"tests", "examples", "research", "scripts", "docs", "benchmarks"})


def _git(root: Path, *args: str) -> str | None:
    """Run ``git -C root …``; return stdout (stripped) or None on any failure."""
    try:
        out = subprocess.run(("git", "-C", str(root), *args),
                             capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout


def _match_include(name: str, include: tuple[str, ...]) -> bool:
    from fnmatch import fnmatch
    return any(fnmatch(name, pat) for pat in include)


def _role_of(rel: str, roots: list[tuple[str, str]]) -> str:
    """Assign a relative path to a role by its longest matching root prefix."""
    parts = rel.split("/")
    best_role, best_len = "core", -1
    for rpath, role in roots:
        rp = rpath.split("/") if rpath else []
        if parts[:len(rp)] == rp and len(rp) > best_len:
            best_role, best_len = role, len(rp)
    return best_role


def _roots_spec(root: Path, core: Path, consumers, docs) -> list[tuple[str, str]]:
    """[(rel-path-from-root, role)] for core + consumers + docs (longest-match order)."""
    out: list[tuple[str, str]] = [(_rel(root, core), "core")]
    for c in consumers:
        p = Path(c).resolve()
        out.append((_rel(root, p), p.name if p.name in _KNOWN_ROLES else p.name))
    for d in docs:
        p = Path(d).resolve()
        out.append((_rel(root, p), "docs"))
    return out


def _rel(root: Path, p: Path) -> str:
    try:
        return p.resolve().relative_to(root).as_posix()
    except ValueError:
        return p.resolve().as_posix()


def _pick_root(core: Path, consumers, docs) -> tuple[Path, str]:
    """Choose the scope root (paths are stored relative to it) and enumeration mode.

    Prefer the git top-level (→ git mode); else the common ancestor of the inputs
    (→ fs mode). Returns (root, mode).
    """
    core = core.resolve()
    top = _git(core if core.is_dir() else core.parent, "rev-parse", "--show-toplevel")
    if top:
        return Path(top.strip()), "git"
    paths = [core] + [Path(p).resolve() for p in (*consumers, *docs)]
    base = Path(os.path.commonpath([str(p) for p in paths])) if len(paths) > 1 else core.parent
    return base, "fs"


def _enumerate_git(root: Path, roots: list[tuple[str, str]]) -> tuple[list[str], dict, set[str]]:
    """git ls-files over the scope pathspecs → (rel paths, {path: git_blob}, untracked).

    Two calls, because "the input" is not "the commit" (R1-C41). The tracked set is what
    ``git ls-files`` knows; ``--others --exclude-standard`` adds exactly what ``git add .``
    would stage — a module that exists and has not been added yet is read by the extractor
    like any other, so leaving it out made the manifest describe a different input than the
    graph was built from, without moving ``scope_id``. Ignored files stay out on purpose:
    if ``.gitignore`` says a file is not part of the tree, the manifest does not get to
    decide otherwise — the membership check names them instead (design §1.7 D2).
    """
    specs = [rp for rp, _ in roots if rp]
    out = _git(root, "ls-files", "-s", "--", *specs) or ""
    paths, blobs = [], {}
    for line in out.splitlines():
        # "<mode> <blob> <stage>\t<path>"
        meta, _, path = line.partition("\t")
        if not path:
            continue
        cols = meta.split()
        if len(cols) >= 2:
            blobs[path] = cols[1]
        paths.append(path)
    others = _git(root, "ls-files", "--others", "--exclude-standard", "--", *specs) or ""
    untracked = {p for p in others.splitlines() if p}
    return paths + sorted(untracked), blobs, untracked


def _enumerate_fs(root: Path, roots, include, exclude_dirs) -> list[str]:
    paths = []
    for rp, _role in roots:
        base = (root / rp) if rp else root
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
            for fn in filenames:
                if _match_include(fn, include):
                    paths.append(Path(dirpath, fn).resolve().relative_to(root).as_posix())
    return paths


def resolve_scope(
    core: str | Path,
    *,
    consumers: tuple[str | Path, ...] = (),
    docs: tuple[str | Path, ...] = (),
    include: tuple[str, ...] = DEFAULT_INCLUDE,
    exclude_dirs=DEFAULT_EXCLUDE_DIRS,
    use_git: bool = True,
) -> dict:
    """Resolve a scope to ``{scope_id, profile, git, files}`` (design §1)."""
    core = Path(core).resolve()
    root, mode = _pick_root(core, consumers, docs)
    if not use_git:
        mode = "fs"
    roots = _roots_spec(root, core, consumers, docs)

    if mode == "git":
        rels, blobs, untracked = _enumerate_git(root, roots)
        rels = [r for r in rels if _match_include(Path(r).name, include)]
    else:
        rels, blobs, untracked = _enumerate_fs(root, roots, include, exclude_dirs), {}, set()

    files = []
    for rel in sorted(set(rels)):
        fpath = root / rel
        try:
            data = fpath.read_bytes()
        except OSError:
            continue
        rec = {"path": rel, "sha256": hashlib.sha256(data).hexdigest(),
               "bytes": len(data), "role": _role_of(rel, roots),
               "loc": data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)}
        if rel in blobs:
            rec["git_blob"] = blobs[rel]
        if mode == "git":
            # Always stated, never inferred from a missing key — absence is ambiguous
            # (R1-C28's rule, applied to the manifest). fs mode omits it: there is no
            # index to be tracked in, so the question does not arise.
            rec["tracked"] = rel not in untracked
        files.append(rec)

    scope_id = "sha256:" + hashlib.sha256(
        "\n".join(f"{f['path']}\t{f['sha256']}" for f in files).encode("utf-8")
    ).hexdigest()

    return {
        "scope_id": scope_id,
        "root": str(root),
        "profile": _profile(files),
        "git": _git_block(root, roots, mode) if mode == "git" else {"mode": "fs"},
        # files carry loc for the profile; drop it from the persisted per-file record
        "files": [{k: v for k, v in f.items() if k != "loc"} for f in files],
    }


def _profile(files: list[dict]) -> dict:
    by_role: dict[str, dict] = {}
    by_ext: dict[str, dict] = {}
    for f in files:
        for bucket, key in ((by_role, f["role"]), (by_ext, Path(f["path"]).suffix or "—")):
            b = bucket.setdefault(key, {"files": 0, "bytes": 0, "loc": 0})
            b["files"] += 1
            b["bytes"] += f["bytes"]
            b["loc"] += f["loc"]
    largest = sorted(files, key=lambda f: (-f["bytes"], f["path"]))[:_LARGEST_N]
    return {
        "file_count": len(files),
        "total_bytes": sum(f["bytes"] for f in files),
        "loc_total": sum(f["loc"] for f in files),
        "by_role": dict(sorted(by_role.items())),
        "by_ext": dict(sorted(by_ext.items())),
        "largest": [{"path": f["path"], "bytes": f["bytes"]} for f in largest],
    }


def _git_block(root: Path, roots: list[tuple[str, str]], mode: str) -> dict:
    commit = (_git(root, "rev-parse", "HEAD") or "").strip()
    ref = (_git(root, "rev-parse", "--abbrev-ref", "HEAD") or "").strip()
    specs = [rp for rp, _ in roots if rp]
    status = _git(root, "status", "--porcelain", "--", *specs) or ""
    dirty_files = sorted(line[3:].strip() for line in status.splitlines() if line.strip())
    return {"mode": mode, "commit": commit, "ref": ref,
            "dirty": bool(dirty_files), "dirty_files": dirty_files}


def unlisted_files(node_files, scope: dict, *, base: str | Path | None = None,
                   sample: int = 5) -> dict:
    """Files the graph was built from that the manifest does not list (R1-C41).

    The manifest is the artifact a consumer reads to answer *"what exactly was
    analyzed"*, and until this check existed it could answer wrong in silence: the
    graph carried a module whose file the sidecar never mentioned, and ``scope_id`` —
    the same value ``--incremental`` and ``watch`` key off — did not move.

    **The two sides do not share an origin**, which is the whole difficulty. Node paths
    are relative to the graph's own base (R1-C31: the parent of the package, or the
    common ancestor of the roots), manifest paths are relative to the scope root (the
    git top-level). On a ``src/`` layout those differ by a segment, and a naive string
    comparison called both files of a healthy build unlisted — measured, 2 of 2. So the
    node path is joined onto ``base`` and re-expressed against the scope root before it
    is looked up; lexically, never through ``resolve()``, so a symlinked checkout does
    not silently rewrite the answer.

    Returns ``{count, sample, outside_root}`` — always, including ``count: 0``, because
    a missing field is not the same statement as "nothing was unlisted". Paths outside
    the scope root are reduced to a bare name: they are absolute (the D5 symptom of a
    file the build should never have read), and the provenance block this ends up in
    refuses absolute paths by contract.
    """
    root = Path(scope.get("root") or ".")
    listed = {f["path"] for f in scope.get("files") or ()}
    unlisted: set[str] = set()
    outside = False
    for raw in node_files:
        if not raw:
            continue
        p = Path(raw)
        absolute = p if p.is_absolute() else Path(os.path.normpath(Path(base or root) / p))
        try:
            rel = absolute.relative_to(root).as_posix()
        except ValueError:
            outside = True
            unlisted.add(p.name)
            continue
        if rel not in listed:
            unlisted.add(rel)
    return {"count": len(unlisted), "sample": sorted(unlisted)[:sample],
            "outside_root": outside}


def diff_scopes(a: dict, b: dict) -> dict:
    """Added / removed / changed files between two scope manifests (by path+sha256)."""
    am = {f["path"]: f["sha256"] for f in a.get("files", [])}
    bm = {f["path"]: f["sha256"] for f in b.get("files", [])}
    added = sorted(set(bm) - set(am))
    removed = sorted(set(am) - set(bm))
    changed = sorted(p for p in set(am) & set(bm) if am[p] != bm[p])
    return {"added": added, "removed": removed, "changed": changed,
            "same_scope_id": a.get("scope_id") == b.get("scope_id")}
