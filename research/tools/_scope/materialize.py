#!/usr/bin/env python3
"""R2 benchmark scope harness — realize a scope spec as a clean staging tree.

Feature B of docs/design/scope.md §3. Reuses Feature A (`codemap.scope.resolve_scope`)
so the staging carries the *same* `scope_id` as the canonical in-place scope.

Usage:
    materialize.py <spec.json> <out-dir> [--root PATH] [--no-verify]

What it does:
  1. Read the spec (root + roots-with-roles + include).
  2. resolve_scope() over the REAL tree (git mode) → canonical manifest + scope_id.
  3. Copy EXACTLY the manifest's files into <out-dir> (same relative paths). Copying the
     manifest set — not an rsync-with-excludes — is what guarantees the staging is byte-for-byte
     the canonical scope (no stray generated/untracked files, e.g. docs/_build).
  4. Write <out-dir>/manifest.json (= the canonical scope dict).
  5. Verify: re-resolve <out-dir> (fs mode) and assert its scope_id equals the canonical one.

Why materialize at all: only for third-party tools that can't take a file list and have
unreliable excludes (graphlens's venv trap). codemap itself is NEVER materialized — it indexes
the real tree in place. Live/watch tools should be pointed at the real tree too when possible.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# Make `import codemap.scope` work when run with any interpreter: the codemap repo root is
# three levels up from this file (research/tools/_scope/ → repo root).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from codemap.scope import resolve_scope  # noqa: E402

_CONSUMER_ROLES = {"tests", "examples", "research", "scripts", "benchmarks"}


def _load_spec(spec_path: Path, root_override: str | None) -> tuple[Path, dict]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if root_override:
        root = Path(root_override).expanduser().resolve()
    else:
        root = (spec_path.parent / spec.get("root", ".")).resolve()
    if not root.is_dir():
        sys.exit(f"error: spec root does not exist: {root}")
    return root, spec


def _split_roots(root: Path, spec: dict) -> tuple[Path, list[Path], list[Path]]:
    """Map spec roots (path+role) → resolve_scope's (core, consumers, docs)."""
    core: Path | None = None
    consumers: list[Path] = []
    docs: list[Path] = []
    for entry in spec.get("roots", []):
        p = root / entry["path"]
        role = entry.get("role", "core")
        if role == "core":
            core = p
        elif role == "docs":
            docs.append(p)
        elif role in _CONSUMER_ROLES:
            consumers.append(p)
        else:
            consumers.append(p)  # unknown role → treat as a consumer (still gets a ref role)
    if core is None:
        sys.exit("error: spec has no root with role 'core'")
    return core, consumers, docs


def _materialize(root: Path, scope: dict, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in scope["files"]:
        src = root / f["path"]
        dst = out_dir / f["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        n += 1
    (out_dir / "manifest.json").write_text(
        json.dumps(scope, indent=2, ensure_ascii=False), encoding="utf-8")
    return n


def _verify(out_dir: Path, spec: dict, expected_id: str) -> bool:
    """Re-resolve the staging (fs mode) and confirm the scope_id round-trips."""
    core, consumers, docs = _split_roots(out_dir, spec)
    got = resolve_scope(core, consumers=tuple(consumers), docs=tuple(docs),
                        include=tuple(spec.get("include", ("*.py", "*.md"))),
                        use_git=False)
    return got["scope_id"] == expected_id


def main() -> None:
    ap = argparse.ArgumentParser(description="Materialize an R2 benchmark scope spec.")
    ap.add_argument("spec", type=Path, help="Path to <name>.scope.json")
    ap.add_argument("out_dir", type=Path, help="Staging directory to create")
    ap.add_argument("--root", help="Override the spec's root (the tree to materialize from)")
    ap.add_argument("--no-verify", action="store_true", help="Skip the scope_id round-trip check")
    args = ap.parse_args()

    root, spec = _load_spec(args.spec.resolve(), args.root)
    core, consumers, docs = _split_roots(root, spec)
    scope = resolve_scope(core, consumers=tuple(consumers), docs=tuple(docs),
                          include=tuple(spec.get("include", ("*.py", "*.md"))), use_git=True)

    sid = scope["scope_id"]
    prof = scope["profile"]
    print(f"canonical scope_id: {sid}")
    print(f"  {prof['file_count']} files, {prof['total_bytes']} bytes, {prof['loc_total']} loc")
    print(f"  git: {scope['git'].get('mode')} {scope['git'].get('commit', '')[:12]} "
          f"{scope['git'].get('ref', '')} dirty={scope['git'].get('dirty')}")

    exp = spec.get("expected", {}).get("scope_id")
    if exp and exp != sid:
        print(f"  ⚠ WARNING: scope_id != spec.expected ({exp}) — the tree moved since the spec was pinned")

    n = _materialize(root, scope, args.out_dir.resolve())
    print(f"materialized {n} files → {args.out_dir}")

    if not args.no_verify:
        ok = _verify(args.out_dir.resolve(), spec, sid)
        print(f"verify: staging scope_id {'== canonical ✓' if ok else '!= canonical ✗ (BUG)'}")
        if not ok:
            sys.exit(2)


if __name__ == "__main__":
    main()
