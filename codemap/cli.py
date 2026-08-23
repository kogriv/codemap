"""codemap CLI (DESIGN §6, §14.1). CLI-AI-first: JSON by default, stable exit codes.

    codemap build  <path> [-o graph.json] [--deep]
                   [--consumer PATH ...] [--docs PATH ...] [--mode thin|full]
    codemap scope  <path> [--consumer PATH ...] [--docs PATH ...] [--no-git] [--json]
                   | --diff A.meta.json B.meta.json   → input scope manifest (M19.A)
    codemap query  <name> (--graph g.json | --build <path>) [--format json|text]
    codemap report <kind> (--graph g.json | --build <path>) [--format markdown|json]
        kinds: api-surface | dependencies | dead-code | behavior | impact --symbol X
    codemap export <kind> (--graph g.json | --build <path>) [-o out]
        rag                          → JSONL chunks (consumer A)
        vault -o <dir>               → Obsidian vault tree (consumer B)
        mermaid --mkind class|deps|calls [--scope X] [--root Y] [--depth N]
        scip -o <file>               → SCIP index (defs + symbol info; interop, R1-C1)
        ctags [-o tags]              → universal-ctags tags file (defs; editor interop, R1-C2)
        docs                         → living documentation (subsystem-organized, R1-C15)
    codemap review [diff|-] (--graph g.json | --build <path>) [--format markdown|json]
        unified diff (or stdin) → risk-sorted change-set review (M15/F17)
    codemap serve  (--graph g.json | --build <path>) [--source-root DIR] [--mcp]
        warm resident process: line-delimited JSON stdio, or MCP with --mcp (M17)
    codemap refresh <graph.json>
        rebuild a graph from the recipe recorded beside it at build time (M18)
    codemap route  <capability> <question> [--root DIR]
        forward a capability to an opt-in external tool (DESIGN §13.1; needs
        codemap.toml [integrations].enabled + the tool installed)
    codemap semantic <query> (--graph g.json | --build <path>) [--root DIR] [--limit N]
        semantic search via an opt-in adapter, enriched to codemap symbols (R1-C16)
    codemap pack (--graph g.json | --build <path>) [--budget N] [--seed X …]
        token-budgeted context pack: most relevant graph slice under N tokens (R1-C6)
"""

from __future__ import annotations

import argparse
import os
import json
import sys
from pathlib import Path

from codemap import store
from codemap.extract import extract, extract_repo
from codemap.query import Query
from codemap.serve import (
    build_query_result,
    build_vault,
    render_api_surface,
    render_architecture,
    render_behavior,
    render_dead_code,
    render_dependencies,
    render_impact,
    render_mermaid,
    render_rag,
)

_REPORTS = {
    "api-surface": render_api_surface,       # takes Graph
    "dependencies": render_dependencies,     # takes Query
    "dead-code": render_dead_code,           # takes Query
    "behavior": render_behavior,             # takes Query
    "architecture": render_architecture,     # takes Query (M16/A9)
}
_REPORT_KINDS = sorted(_REPORTS) + ["impact", "communities", "flows"]  # extra args


def _graph_from(args):
    if getattr(args, "build", None):
        return extract(args.build, deep=getattr(args, "deep", False))
    if getattr(args, "graph", None):
        return store.load(args.graph)
    raise SystemExit("error: need --graph <file> or --build <path>")


def _cmd_build(args) -> int:
    if args.consumer or args.docs:
        graph = extract_repo(
            args.path,
            consumers=tuple(args.consumer or ()),
            docs=tuple(args.docs or ()),
            mode=args.mode,
            deep=args.deep,
        )
    else:
        graph = extract(args.path, deep=args.deep)
    if args.out:
        store.save(graph, args.out)
        # M18: record the build recipe beside the graph so `codemap refresh` can
        # rebuild it, and so the graph's age is meaningful to `serve`/stats.
        # M19.A: also record the input scope manifest (scope_id + profile + git).
        from codemap.freshness import write_meta
        from codemap.scope import resolve_scope
        try:
            scope = resolve_scope(args.path, consumers=tuple(args.consumer or ()),
                                  docs=tuple(args.docs or ()))
        except Exception:
            scope = None  # scope manifest is provenance, never fatal to a build
        write_meta(args.out, argv=getattr(args, "_argv", []),
                   cwd=os.getcwd(), target=graph.target, scope=scope)
        print(args.out)
    else:
        print(store.dumps(graph))
    return 0


def _cmd_scope(args) -> int:
    """Resolve/print the input scope manifest, or diff two (M19.A)."""
    from codemap.scope import resolve_scope, diff_scopes
    if args.diff:
        from codemap.freshness import read_meta
        metas = []
        for p in args.diff:
            m = read_meta(p) if p.endswith(".meta.json") else None
            if m is None:  # allow passing the graph path or the sidecar path
                import json as _json
                try:
                    m = _json.loads(Path(p).read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    raise SystemExit(f"error: cannot read scope/meta from {p!r}")
            metas.append(m.get("scope", m))  # sidecar has {scope:{…}}; or a raw manifest
        d = diff_scopes(metas[0], metas[1])
        print(json.dumps(d, indent=2))
        return 0 if not (d["added"] or d["removed"] or d["changed"]) else 1
    if not args.path:
        raise SystemExit("error: scope needs <path> (or --diff A B)")
    scope = resolve_scope(args.path, consumers=tuple(args.consumer or ()),
                          docs=tuple(args.docs or ()), use_git=not args.no_git)
    if args.json:
        print(json.dumps(scope, indent=2, sort_keys=True))
    else:
        p = scope["profile"]
        g = scope["git"]
        print(f"scope_id: {scope['scope_id']}")
        print(f"root:     {scope['root']}")
        print(f"files:    {p['file_count']}  ({p['total_bytes']} bytes, {p['loc_total']} loc)")
        if g.get("mode") == "git":
            print(f"git:      {g['ref']} @ {g['commit'][:10]}  dirty={g['dirty']}"
                  + (f" ({len(g['dirty_files'])} files)" if g["dirty"] else ""))
        else:
            print("git:      (fs mode — not a git repo / --no-git)")
        print("by_role:  " + ", ".join(f"{r}={v['files']}" for r, v in p["by_role"].items()))
        print("by_ext:   " + ", ".join(f"{e}={v['files']}" for e, v in p["by_ext"].items()))
    return 0


def _cmd_query(args) -> int:
    q = Query(_graph_from(args))
    result = build_query_result(q, args.name)
    if args.format == "text":
        _print_query_text(result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if (result["matches"] or result["defined_at"] or result.get("column")) else 1


def _print_query_text(r) -> None:
    print(f"# {r['name']}")
    print("defined at:", ", ".join(r["defined_at"]) or "—")
    for m in r["matches"]:
        loc = f" — {m['file']}:{m['lines'][0]}" if m.get("file") and m["lines"][0] else ""
        print(f"  - {m['id']} ({m['kind']}){loc}")
    for mid, dep in r.get("modules", {}).items():
        print(f"\n[{mid}]")
        print("  imports:", ", ".join(dep["dependencies"]) or "—")
        print("  imported by:", ", ".join(dep["dependents"]) or "—")
    for cid, h in r.get("classes", {}).items():
        print(f"\n[{cid}]")
        print("  bases:", ", ".join(h["bases"]) or "—")
        print("  subclasses:", ", ".join(h["subclasses"]) or "—")
        if h.get("implements"):
            print("  implements:", ", ".join(h["implements"]))
        if h.get("implementers"):
            print("  implementers (registry family):", ", ".join(h["implementers"]))
        if h.get("family"):
            print("  family siblings:", ", ".join(h["family"]))
        if h.get("registered_as"):
            reg = h["registered_as"]
            print(f"  register with: @{reg.get('decorator','?').rsplit('.',1)[-1]}('{reg.get('key')}')")
    for fid, h in r.get("functions", {}).items():
        print(f"\n[{fid}]")
        print("  calls:", ", ".join(h["callees"]) or "—")
        print("  called by:", ", ".join(h["callers"]) or "—")
        if h.get("columns"):
            c = h["columns"]
            if c.get("reads"):
                print("  reads columns:", ", ".join(c["reads"]))
            if c.get("writes"):
                print("  writes columns:", ", ".join(c["writes"]))
    for aid, acc in r.get("attributes", {}).items():
        print(f"\n[{aid}] attribute")
        if acc.get("reads"):
            print("  read by:", ", ".join(acc["reads"]))
        if acc.get("writes"):
            print("  written by:", ", ".join(acc["writes"]))
    for sid, by_root in r.get("used_by", {}).items():
        if by_root:
            summary = ", ".join(f"{root}: {n}" for root, n in sorted(by_root.items()))
            print(f"\n[{sid}] used by → {summary}")
    col = r.get("column")
    if col:
        print(f"\n[column '{r['name']}'] string-key dataflow")
        print("  written by:", ", ".join(col["writes"]) or "—")
        print("  read by:", ", ".join(col["reads"]) or "—")


def _cmd_report(args) -> int:
    graph = _graph_from(args)
    if args.format == "json":
        print(store.dumps(graph))
        return 0
    if args.kind == "impact":
        if not args.symbol:
            raise SystemExit("error: report impact needs --symbol <name>")
        print(render_impact(Query(graph), args.symbol, depth=args.depth), end="")
        return 0
    if args.kind in ("communities", "flows"):
        from codemap.serve.subsystems import render_communities, render_flows
        q = Query(graph)
        out = (render_communities(q) if args.kind == "communities"
               else render_flows(q, args.symbol, depth=args.depth))
        print(out, end="")
        return 0
    if args.kind == "dead-code":
        from codemap.serve.audit import load_dead_code_whitelist
        root = getattr(args, "source_root", None) or os.getcwd()
        print(render_dead_code(Query(graph),
                               whitelist=load_dead_code_whitelist(root),
                               min_confidence=args.min_confidence), end="")
        return 0
    renderer = _REPORTS[args.kind]
    payload = renderer(graph) if args.kind == "api-surface" else renderer(Query(graph))
    print(payload, end="")
    return 0


def _cmd_export(args) -> int:
    q = Query(_graph_from(args))
    if args.kind == "rag":
        _emit(render_rag(q), args.out)
    elif args.kind == "mermaid":
        _emit(render_mermaid(q, args.mkind, scope=args.scope, root=args.root,
                             depth=args.depth), args.out)
    elif args.kind == "vault":
        if not args.out:
            raise SystemExit("error: export vault needs -o <dir>")
        _write_vault(build_vault(q), args.out)
        print(args.out)
    elif args.kind == "docs":
        from codemap.serve.livingdocs import render_docs
        _emit(render_docs(q), args.out)
    elif args.kind == "scip":
        if not args.out:
            raise SystemExit("error: export scip needs -o <file> (binary output)")
        from codemap.serve.scip import build_scip, write_scip
        from codemap import __version__
        index = build_scip(
            q,
            project_root=args.project_root or os.getcwd(),
            package=args.package,
            version=args.package_version,
            tool_version=__version__,
        )
        Path(args.out).write_bytes(write_scip(index))
        print(f"{args.out} ({len(index.documents)} documents)")
    elif args.kind == "ctags":
        from codemap.serve.ctags import build_ctags
        from codemap import __version__
        # --project-root doubles as the source root for /^…$/ pattern addresses;
        # if lines are unreadable, build_ctags falls back to line-number addresses.
        _emit(build_ctags(q, source_root=args.project_root or os.getcwd(),
                          tool_version=__version__), args.out)
    return 0


def _cmd_review(args) -> int:
    """Change-set review from a unified diff → what to review (M15/F17)."""
    from codemap.serve.review import build_review, parse_unified_diff, render_review
    text = (sys.stdin.read() if args.diff in (None, "-")
            else Path(args.diff).read_text(encoding="utf-8"))
    hunks = parse_unified_diff(text)
    q = Query(_graph_from(args))
    base = store.load(args.base) if getattr(args, "base", None) else None
    if args.format == "json":
        print(json.dumps(build_review(q, hunks=hunks, base_graph=base), indent=2, sort_keys=True))
    else:
        print(render_review(q, hunks=hunks, base_graph=base), end="")
    return 0


def _cmd_refresh(args) -> int:
    """Rebuild a graph from the recipe recorded beside it at build time (M18)."""
    from codemap.freshness import read_meta
    meta = read_meta(args.graph)
    if not meta or not meta.get("argv"):
        raise SystemExit(
            f"error: no rebuild recipe for {args.graph!r} "
            "(build it with `codemap build … -o {graph}` first)")
    cwd = meta.get("cwd")
    if cwd and os.path.isdir(cwd):
        os.chdir(cwd)  # recorded argv may use paths relative to the build cwd
    print(f"rebuilding {args.graph} …", file=sys.stderr)
    return main(meta["argv"])


def _cmd_route(args) -> int:
    """Route a capability question to an opt-in external tool (DESIGN §13.1).

    Capability-first: the tool is picked from the registry by capability, gated on
    opt-in (codemap.toml) + install. A non-commercial tool's licensing notice is
    shown once (unless acknowledged in config). The answer is forwarded as-is —
    it never enters the graph.
    """
    from codemap.integrations import load_config, resolve
    cfg = load_config(args.root)
    integ = resolve(args.capability, config=cfg, root=args.root)
    if integ is None:
        raise SystemExit(
            f"error: no enabled + installed tool provides {args.capability!r}. "
            f"Enable one in codemap.toml [integrations].enabled and install it.")
    notice = integ.disclaimer()  # §13.1 п.3 — worded on use, not reselling
    if notice and not cfg.is_acknowledged(integ.name):
        print(notice, file=sys.stderr)
    answer = integ.route(args.capability, args.question)
    print(json.dumps(answer.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _cmd_semantic(args) -> int:
    """Semantic search via an opt-in adapter, enriched to codemap symbols (R1-C16).

    Resolves an installed + opted-in ADAPTER providing `semantic-search` (cocoindex
    today), runs it in `--root`, and resolves each fuzzy hit to the exact codemap
    symbol at that location. `--root` is the repo the tool's index was built in (and
    where file paths resolve); it defaults to cwd. The core needs no adapter — with
    none enabled+installed this prints an actionable hint, never crashes.
    """
    from codemap.serve.semantic import semantic_search
    q = Query(_graph_from(args))
    result = semantic_search(q, args.query, root=args.root, limit=args.limit)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if not result["resolver"]:
        raise SystemExit(
            "error: no enabled + installed adapter provides 'semantic-search'. "
            "Install one (e.g. `uv tool install 'cocoindex-code[full]'` + `ccc index`) "
            "and enable it in codemap.toml [integrations].enabled. "
            "For a router-only tool (e.g. gitnexus), use `codemap route semantic-search`.")
    if result["disclaimer"]:
        print(result["disclaimer"], file=sys.stderr)
    print(f"# semantic: {args.query!r}  (via {result['resolver']})")
    if not result["hits"]:
        print("_no hits._")
        return 0
    for h in result["hits"]:
        sym = h["symbol"] or f"(unresolved) {h['file']}"
        lines = h["lines"]
        print(f"  {h['score']:.3f}  {sym}  [{h['file']}:{lines[0]}-{lines[1]}]")
    return 0


def _cmd_pack(args) -> int:
    """Token-budgeted context pack — most relevant graph slice under N tokens (R1-C6)."""
    from codemap.serve.pack import build_pack, render_pack
    q = Query(_graph_from(args))
    seeds = tuple(args.seed or ())
    if args.format == "json":
        print(json.dumps(build_pack(q, budget=args.budget, seeds=seeds),
                         ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_pack(q, budget=args.budget, seeds=seeds), end="")
    return 0


def _cmd_check(args) -> int:
    """Enforce the [architecture] contract → exit 2 on any violation (R1-C3).

    The CI gate: reads codemap.toml [architecture] under --root, evaluates every
    rule against the graph, prints the report, and exits non-zero if the contract
    is broken (2 = violations) so a pipeline can fail on it. An empty/absent
    contract is a no-op success unless --require-contract is set.
    """
    from codemap.arch import check_contract, load_contract
    from codemap.serve.check import render_check
    q = Query(_graph_from(args))
    contract = load_contract(args.root)
    if contract.is_empty() and args.require_contract:
        print(render_check(q, contract, []), end="")
        raise SystemExit("error: no [architecture] contract found (--require-contract)")
    violations = check_contract(q, contract)
    print(render_check(q, contract, violations), end="")
    return 2 if violations else 0


def _cmd_diff(args) -> int:
    """Two-graph API diff → added/removed/changed + breaking-change (R1-C5).

    Renders the public-API delta between two graph.json snapshots. With
    ``--exit-code`` it behaves like a release gate: exit 1 when any breaking
    change (a removed public symbol or an incompatible signature change) is found.
    """
    from codemap.serve.apidiff import build_apidiff, render_apidiff
    old, new = store.load(args.old), store.load(args.new)
    print(render_apidiff(old, new), end="")
    if args.exit_code and not build_apidiff(old, new)["ok"]:
        return 1
    return 0


def _cmd_serve(args) -> int:
    """Load the graph once, then serve it warm (M3.1).

    Default transport is line-delimited JSON over stdio; ``--mcp`` serves the same
    ops over the Model Context Protocol instead (needs the optional `mcp` extra).
    """
    from codemap.serve.session import Session
    session = Session(_graph_from(args), source_root=args.source_root,
                      graph_path=getattr(args, "graph", None))
    if getattr(args, "mcp", False):
        from codemap.serve.mcp_server import build_mcp_server
        build_mcp_server(session).run("stdio")
        return 0
    from codemap.serve.server import serve_stdio
    return serve_stdio(session)


def _emit(text: str, out: str | None) -> None:
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(out)
    else:
        print(text, end="")


def _write_vault(files: dict[str, str], out_dir: str) -> None:
    base = Path(out_dir)
    for rel, content in files.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _add_source(p) -> None:
    p.add_argument("--graph", help="Read an existing graph.json.")
    p.add_argument("--build", help="Build fresh from this package path.")
    p.add_argument("--deep", action="store_true",
                   help="Deep call resolution via jedi (richer, ~1 min; default fast).")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="codemap", description="Static code-graph builder.")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="Build the canonical graph from a package path.")
    b.add_argument("path", help="Path to the package directory (holds __init__.py).")
    b.add_argument("-o", "--out", help="Write graph.json here (default: stdout JSON).")
    b.add_argument("--deep", action="store_true",
                   help="Deep call resolution via jedi (richer, ~1 min; default fast).")
    b.add_argument("--consumer", action="append", metavar="PATH",
                   help="Repo-scope: extra root that USES the core (tests/, examples/, "
                        "scripts/). Repeatable. Adds inbound refs for impact analysis.")
    b.add_argument("--docs", action="append", metavar="PATH",
                   help="Repo-scope: docs root (*.md) → doc nodes + references. Repeatable.")
    b.add_argument("--mode", choices=["thin", "full"], default="thin",
                   help="Consumer granularity: thin=per-file (default), full=per-function.")
    b.set_defaults(func=_cmd_build)

    sc = sub.add_parser("scope", help="Resolve the input scope manifest (scope_id + profile), or --diff two.")
    sc.add_argument("path", nargs="?", help="Package/dir to scope (like build's path).")
    sc.add_argument("--consumer", action="append", metavar="PATH",
                    help="Extra consumer root (tests/examples/scripts). Repeatable.")
    sc.add_argument("--docs", action="append", metavar="PATH", help="Docs root. Repeatable.")
    sc.add_argument("--no-git", action="store_true",
                    help="Force filesystem enumeration instead of git ls-files.")
    sc.add_argument("--diff", nargs=2, metavar=("A", "B"),
                    help="Diff two scopes: each is a <graph>.meta.json (or a manifest JSON).")
    sc.add_argument("--json", action="store_true", help="Full manifest as JSON (default: summary).")
    sc.set_defaults(func=_cmd_scope)

    q = sub.add_parser("query", help="Look up a symbol: where defined, deps both ways.")
    q.add_argument("name", help="Short symbol name (e.g. analyze_zones).")
    _add_source(q)
    q.add_argument("--format", choices=["json", "text"], default="json")
    q.set_defaults(func=_cmd_query)

    r = sub.add_parser("report", help="Render a report over the graph.")
    r.add_argument("kind", choices=_REPORT_KINDS)
    _add_source(r)
    r.add_argument("--symbol", help="Symbol for `report impact` (short or full name).")
    r.add_argument("--depth", type=int, default=2,
                   help="report impact: transitive BFS depth (default 2).")
    r.add_argument("--min-confidence", choices=["low", "medium", "high"], default=None,
                   help="report dead-code: only show candidates at/above this confidence.")
    r.add_argument("--format", choices=["markdown", "json"], default="markdown")
    r.set_defaults(func=_cmd_report)

    e = sub.add_parser("export", help="Export a view: rag (JSONL) | vault | mermaid | scip | ctags | docs.")
    e.add_argument("kind", choices=["rag", "vault", "mermaid", "scip", "ctags", "docs"])
    _add_source(e)
    e.add_argument("-o", "--out", help="Output file (rag/mermaid/scip/ctags) or dir (vault).")
    e.add_argument("--mkind", choices=["class", "deps", "calls"], default="class",
                   help="mermaid diagram kind (default: class).")
    e.add_argument("--scope", help="mermaid class/deps: restrict to this id-prefix.")
    e.add_argument("--root", help="mermaid calls: root symbol.")
    e.add_argument("--depth", type=int, default=2, help="mermaid calls: BFS depth.")
    e.add_argument("--project-root", help="scip/ctags: filesystem root the paths are relative to "
                                          "(default: cwd). SCIP writes it as project_root URI; "
                                          "ctags reads source lines from it for /^…$/ addresses.")
    e.add_argument("--package", help="scip: package name in symbol strings (default: graph target).")
    e.add_argument("--package-version", default=".",
                   help="scip: package version in symbol strings (default: '.' — unversioned).")
    e.set_defaults(func=_cmd_export)

    rv = sub.add_parser("review", help="Change-set review from a unified diff → what to review.")
    rv.add_argument("diff", nargs="?", default="-",
                    help="Unified-diff file (or '-'/omit for stdin, e.g. `git diff | codemap review`).")
    _add_source(rv)
    rv.add_argument("--base", help="Baseline graph.json to API-diff against (adds removed/"
                    "added/breaking symbols the hunks miss — R1-C5).")
    rv.add_argument("--format", choices=["markdown", "json"], default="markdown")
    rv.set_defaults(func=_cmd_review)

    s = sub.add_parser("serve", help="Warm resident process: JSON (or MCP) over stdin/stdout.")
    _add_source(s)
    s.add_argument("--source-root", help="Base dir for the `source` op to read files "
                                         "(node paths are repo-relative; default: cwd).")
    s.add_argument("--mcp", action="store_true",
                   help="Serve over the Model Context Protocol instead of JSON "
                        "(needs the optional 'mcp' extra: pip install 'codemap[mcp]').")
    s.set_defaults(func=_cmd_serve)

    rf = sub.add_parser("refresh", help="Rebuild a graph from the recipe recorded at build time.")
    rf.add_argument("graph", help="Path to the graph.json to rebuild (needs its .meta.json sidecar).")
    rf.set_defaults(func=_cmd_refresh)

    rt = sub.add_parser("route", help="Forward a capability to an opt-in external tool (§13.1).")
    rt.add_argument("capability", help="Capability to route, e.g. semantic-search.")
    rt.add_argument("question", help="The query to forward to the tool.")
    rt.add_argument("--root", default=".",
                    help="Dir with codemap.toml + the target tree (default: cwd).")
    rt.set_defaults(func=_cmd_route)

    sm = sub.add_parser("semantic", help="Semantic search via an opt-in adapter, "
                                         "enriched to codemap symbols (R1-C16).")
    sm.add_argument("query", help="Natural-language query (e.g. 'detect swing pivots').")
    _add_source(sm)
    sm.add_argument("--root", default=".",
                    help="Repo the adapter's index was built in + where paths resolve "
                         "(also holds codemap.toml [integrations]); default: cwd.")
    sm.add_argument("--limit", type=int, default=10, help="Max hits (default: 10).")
    sm.add_argument("--format", choices=["markdown", "json"], default="markdown")
    sm.set_defaults(func=_cmd_semantic)

    pk = sub.add_parser("pack", help="Token-budgeted context pack: the most relevant "
                                     "graph slice under N tokens (R1-C6).")
    _add_source(pk)
    pk.add_argument("--budget", type=int, default=2000, help="Max tokens (default: 2000).")
    pk.add_argument("--seed", action="append", metavar="X",
                    help="Bias relevance to this symbol / file (repeatable). "
                         "Omit for global importance.")
    pk.add_argument("--format", choices=["markdown", "json"], default="markdown")
    pk.set_defaults(func=_cmd_pack)

    df = sub.add_parser("diff", help="API diff two graph.json snapshots (added/removed/changed + breaking).")
    df.add_argument("old", help="Baseline graph.json (the 'before').")
    df.add_argument("new", help="Current graph.json (the 'after').")
    df.add_argument("--exit-code", action="store_true",
                    help="Exit 1 if any breaking change is found (release gate).")
    df.set_defaults(func=_cmd_diff)

    ck = sub.add_parser("check", help="Enforce the [architecture] contract (CI gate; exit 2 on violation).")
    _add_source(ck)
    ck.add_argument("--root", default=".",
                    help="Dir with codemap.toml holding [architecture] (default: cwd).")
    ck.add_argument("--require-contract", action="store_true",
                    help="Fail if no [architecture] contract is present (default: no-op success).")
    ck.set_defaults(func=_cmd_check)

    return p


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(raw)
    args._argv = raw  # M18: kept so `build` can record its own invocation (refresh)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, don't traceback
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
