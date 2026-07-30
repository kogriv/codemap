"""codemap CLI (DESIGN §6, §14.1). CLI-AI-first: JSON by default, stable exit codes.

    codemap build  <path> [-o graph.json] [--deep]
                   [--consumer PATH ...] [--docs PATH ...] [--mode thin|full]
    codemap query  <name> (--graph g.json | --build <path>) [--format json|text]
    codemap report <kind> (--graph g.json | --build <path>) [--format markdown|json]
        kinds: api-surface | dependencies | dead-code | behavior | impact --symbol X
    codemap export <kind> (--graph g.json | --build <path>) [-o out]
        rag                          → JSONL chunks (consumer A)
        vault -o <dir>               → Obsidian vault tree (consumer B)
        mermaid --mkind class|deps|calls [--scope X] [--root Y] [--depth N]
    codemap review [diff|-] (--graph g.json | --build <path>) [--format markdown|json]
        unified diff (or stdin) → risk-sorted change-set review (M15/F17)
"""

from __future__ import annotations

import argparse
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
_REPORT_KINDS = sorted(_REPORTS) + ["impact"]  # impact takes (Query, --symbol)


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
        print(args.out)
    else:
        print(store.dumps(graph))
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
        print(render_impact(Query(graph), args.symbol), end="")
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
    return 0


def _cmd_review(args) -> int:
    """Change-set review from a unified diff → what to review (M15/F17)."""
    from codemap.serve.review import build_review, parse_unified_diff, render_review
    text = (sys.stdin.read() if args.diff in (None, "-")
            else Path(args.diff).read_text(encoding="utf-8"))
    hunks = parse_unified_diff(text)
    q = Query(_graph_from(args))
    if args.format == "json":
        print(json.dumps(build_review(q, hunks=hunks), indent=2, sort_keys=True))
    else:
        print(render_review(q, hunks=hunks), end="")
    return 0


def _cmd_serve(args) -> int:
    """Load the graph once, then serve JSON requests over stdio (warm — M3.1)."""
    from codemap.serve.server import serve_stdio
    from codemap.serve.session import Session
    return serve_stdio(Session(_graph_from(args), source_root=args.source_root))


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

    q = sub.add_parser("query", help="Look up a symbol: where defined, deps both ways.")
    q.add_argument("name", help="Short symbol name (e.g. analyze_zones).")
    _add_source(q)
    q.add_argument("--format", choices=["json", "text"], default="json")
    q.set_defaults(func=_cmd_query)

    r = sub.add_parser("report", help="Render a report over the graph.")
    r.add_argument("kind", choices=_REPORT_KINDS)
    _add_source(r)
    r.add_argument("--symbol", help="Symbol for `report impact` (short or full name).")
    r.add_argument("--format", choices=["markdown", "json"], default="markdown")
    r.set_defaults(func=_cmd_report)

    e = sub.add_parser("export", help="Export a view: rag (JSONL) | vault | mermaid.")
    e.add_argument("kind", choices=["rag", "vault", "mermaid"])
    _add_source(e)
    e.add_argument("-o", "--out", help="Output file (rag/mermaid) or dir (vault).")
    e.add_argument("--mkind", choices=["class", "deps", "calls"], default="class",
                   help="mermaid diagram kind (default: class).")
    e.add_argument("--scope", help="mermaid class/deps: restrict to this id-prefix.")
    e.add_argument("--root", help="mermaid calls: root symbol.")
    e.add_argument("--depth", type=int, default=2, help="mermaid calls: BFS depth.")
    e.set_defaults(func=_cmd_export)

    rv = sub.add_parser("review", help="Change-set review from a unified diff → what to review.")
    rv.add_argument("diff", nargs="?", default="-",
                    help="Unified-diff file (or '-'/omit for stdin, e.g. `git diff | codemap review`).")
    _add_source(rv)
    rv.add_argument("--format", choices=["markdown", "json"], default="markdown")
    rv.set_defaults(func=_cmd_review)

    s = sub.add_parser("serve", help="Warm resident process: JSON requests over stdin/stdout.")
    _add_source(s)
    s.add_argument("--source-root", help="Base dir for the `source` op to read files "
                                         "(node paths are repo-relative; default: cwd).")
    s.set_defaults(func=_cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, don't traceback
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
