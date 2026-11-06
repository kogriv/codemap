"""Is a graph read from disk the tree it is about to be judged as? (R1-C70)

Design ``docs/design/check_graph_currency.md``. Lives in the ``serve`` layer, not in
``freshness``, because it needs ``scope`` — which sits *above* ``freshness`` in codemap's own
layer contract (the dogfood test caught the first placement). ``cli`` and the MCP session both
call it, so the two surfaces answer the same thing.
"""

from __future__ import annotations

import os

from codemap.freshness import read_meta


def recipe_scope_args(argv: list[str]) -> tuple[str, list[str], list[str]]:
    """``(path, consumers, docs)`` from a recorded ``build`` argv (R1-C70).

    A narrow parser on purpose: this module sits below ``cli`` in codemap's own layer
    contract (``serve``), so it cannot borrow ``build_parser``. It reads only what decides the input
    scope and ignores every other flag. ``tests/test_r1c70_check_graph_currency.py`` pins that
    it agrees with ``build_parser`` on the same argv, so the two cannot drift apart unseen.
    """
    import argparse
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("cmd")
    p.add_argument("path")
    p.add_argument("--consumer", action="append", default=[])
    p.add_argument("--docs", action="append", default=[])
    ns, _ = p.parse_known_args(argv)
    if ns.cmd != "build":
        raise ValueError(f"the recorded recipe is not a build: {argv[:1]}")
    return ns.path, ns.consumer, ns.docs


def _via_roots(graph_scope_id: str, roots: dict | None, target: str | None,
               base: str | None, why: str) -> dict:
    """R1-C90: no usable recipe — check from the graph's own recorded roots under ``base``.

    A graph built on another machine records its roots relative to its path base
    (R1-C25/R1-C31) and its input identity; the scope id depends on file content and
    relative paths, not on where the tree lives, so the same roots under this directory
    give a comparable id.
    """
    from pathlib import Path
    b = Path(base or os.getcwd())
    if roots:
        core = b / roots.get("core", "")
        consumers = tuple(b / c for c in roots.get("consumers") or ())
        docs = tuple(b / d for d in roots.get("docs") or ())
    elif target:
        core, consumers, docs = b / target, (), ()
    else:
        return {"status": "unknown", "reason": why}
    if not core.is_dir() or any(not p.is_dir() for p in (*consumers, *docs)):
        return {"status": "unknown",
                "reason": f"{why}; the graph's roots are not under {b} "
                          "(run from the directory the graph's paths are relative to, or "
                          "pass --source-root)"}
    try:
        from codemap.scope import resolve_scope
        now = resolve_scope(str(core), consumers=tuple(map(str, consumers)),
                            docs=tuple(map(str, docs)))
    except (Exception, SystemExit) as exc:
        return {"status": "unknown", "reason": f"{why}; resolving the roots failed ({exc})"}
    via = f"provenance roots under {b}"
    if now["scope_id"] == graph_scope_id:
        return {"status": "current", "scope_id": graph_scope_id, "via": via}
    return {"status": "behind", "recorded": graph_scope_id, "current": now["scope_id"],
            "via": via}


def graph_currency(graph_path: str, graph_scope_id: str | None, *, roots: dict | None = None,
                   target: str | None = None, base: str | None = None) -> dict:
    """Is the graph at ``graph_path`` the tree it would be judged as? (R1-C70)

    ``{"status": "current" | "behind" | "unknown", …}``. Design ``check_graph_currency.md`` D1:
    the scope is re-derived from the build recipe recorded beside the graph (``argv`` +
    ``cwd``), read by :func:`recipe_scope_args` and resolved by the build's own
    ``resolve_scope`` — so "the same input" means the same thing here as in ``build``. It is
    then compared by ``scope_id``, the content and not the mtimes. ``unknown`` always carries
    a ``reason``: "not checked" is said, never left as an absence (R1-C28).
    """
    if not graph_scope_id:
        return {"status": "unknown",
                "reason": "the graph records no input identity (`provenance.scope_id`)"}
    meta = read_meta(graph_path)
    if not meta or not meta.get("argv"):
        return _via_roots(graph_scope_id, roots, target, base,
                          "no build recipe beside the graph")
    cwd = meta.get("cwd")
    if not cwd or not os.path.isdir(cwd):
        return _via_roots(graph_scope_id, roots, target, base,
                          f"the recorded build directory is gone ({cwd})")
    try:
        from codemap.scope import diff_scopes, resolve_scope
        path, consumers, docs = recipe_scope_args(meta["argv"])
        rel = lambda p: p if os.path.isabs(p) else os.path.join(cwd, p)
        now = resolve_scope(rel(path), consumers=tuple(rel(c) for c in consumers),
                            docs=tuple(rel(d) for d in docs))
    except (Exception, SystemExit) as exc:      # argparse exits on a recipe it cannot read
        return {"status": "unknown", "reason": f"the recorded scope could not be resolved ({exc})"}
    if now["scope_id"] == graph_scope_id:
        return {"status": "current", "scope_id": graph_scope_id, "via": "recipe"}
    d = diff_scopes(meta.get("scope") or {}, now)
    return {"status": "behind", "recorded": graph_scope_id, "current": now["scope_id"],
            "added": len(d["added"]), "removed": len(d["removed"]), "changed": len(d["changed"]),
            "via": "recipe"}
