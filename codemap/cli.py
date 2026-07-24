"""codemap CLI (DESIGN §6, §14.1). CLI-AI-first: JSON by default, stable exit codes.

    codemap build  <path> [-o graph.json]
    codemap query  <name> (--graph g.json | --build <path>) [--format json|text]
    codemap report <kind> (--graph g.json | --build <path>) [--format markdown|json]
        kinds: api-surface | dependencies | dead-code
"""

from __future__ import annotations

import argparse
import json
import sys

from codemap import store
from codemap.extract import extract
from codemap.query import Query
from codemap.serve import render_api_surface, render_dead_code, render_dependencies

_REPORTS = {
    "api-surface": render_api_surface,       # takes Graph
    "dependencies": render_dependencies,     # takes Query
    "dead-code": render_dead_code,           # takes Query
}


def _graph_from(args):
    if getattr(args, "build", None):
        return extract(args.build)
    if getattr(args, "graph", None):
        return store.load(args.graph)
    raise SystemExit("error: need --graph <file> or --build <path>")


def _cmd_build(args) -> int:
    graph = extract(args.path)
    if args.out:
        store.save(graph, args.out)
        print(args.out)
    else:
        print(store.dumps(graph))
    return 0


def _cmd_query(args) -> int:
    q = Query(_graph_from(args))
    matches = q.find(args.name)
    result = {
        "name": args.name,
        "defined_at": q.where_defined(args.name),
        "matches": [{"id": n.id, "kind": n.kind} for n in matches],
    }
    modules = [n.id for n in matches if n.kind == "module"]
    if modules:
        result["modules"] = {
            m: {"dependencies": q.dependencies(m), "dependents": q.dependents(m)}
            for m in modules
        }

    if args.format == "text":
        _print_query_text(result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if (matches or result["defined_at"]) else 1


def _print_query_text(r) -> None:
    print(f"# {r['name']}")
    print("defined at:", ", ".join(r["defined_at"]) or "—")
    for m in r["matches"]:
        print(f"  - {m['id']} ({m['kind']})")
    for mid, dep in r.get("modules", {}).items():
        print(f"\n[{mid}]")
        print("  imports:", ", ".join(dep["dependencies"]) or "—")
        print("  imported by:", ", ".join(dep["dependents"]) or "—")


def _cmd_report(args) -> int:
    graph = _graph_from(args)
    renderer = _REPORTS[args.kind]
    if args.format == "json":
        print(store.dumps(graph))
        return 0
    payload = renderer(graph) if args.kind == "api-surface" else renderer(Query(graph))
    print(payload, end="")
    return 0


def _add_source(p) -> None:
    p.add_argument("--graph", help="Read an existing graph.json.")
    p.add_argument("--build", help="Build fresh from this package path.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="codemap", description="Static code-graph builder.")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="Build the canonical graph from a package path.")
    b.add_argument("path", help="Path to the package directory (holds __init__.py).")
    b.add_argument("-o", "--out", help="Write graph.json here (default: stdout JSON).")
    b.set_defaults(func=_cmd_build)

    q = sub.add_parser("query", help="Look up a symbol: where defined, deps both ways.")
    q.add_argument("name", help="Short symbol name (e.g. analyze_zones).")
    _add_source(q)
    q.add_argument("--format", choices=["json", "text"], default="json")
    q.set_defaults(func=_cmd_query)

    r = sub.add_parser("report", help="Render a report over the graph.")
    r.add_argument("kind", choices=sorted(_REPORTS))
    _add_source(r)
    r.add_argument("--format", choices=["markdown", "json"], default="markdown")
    r.set_defaults(func=_cmd_report)

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
