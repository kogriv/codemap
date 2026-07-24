"""codemap CLI (DESIGN §6, §14.1). CLI-AI-first: JSON by default, stable exit codes.

    codemap build <path> [-o graph.json]      # source -> canonical graph
    codemap report api-surface (--graph g.json | --build <path>) [--format markdown|json]
"""

from __future__ import annotations

import argparse
import sys

from codemap import store
from codemap.extract import extract
from codemap.serve import render_api_surface


def _cmd_build(args) -> int:
    graph = extract(args.path)
    if args.out:
        store.save(graph, args.out)
        print(args.out)
    else:
        print(store.dumps(graph))
    return 0


def _cmd_report(args) -> int:
    if args.build:
        graph = extract(args.build)
    elif args.graph:
        graph = store.load(args.graph)
    else:
        print("error: report needs --graph <file> or --build <path>", file=sys.stderr)
        return 2

    if args.kind != "api-surface":
        print(f"error: unknown report '{args.kind}'", file=sys.stderr)
        return 2

    if args.format == "json":
        print(store.dumps(graph))
    else:
        print(render_api_surface(graph), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="codemap", description="Static code-graph builder.")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="Build the canonical graph from a package path.")
    b.add_argument("path", help="Path to the package directory (holds __init__.py).")
    b.add_argument("-o", "--out", help="Write graph.json here (default: stdout JSON).")
    b.set_defaults(func=_cmd_build)

    r = sub.add_parser("report", help="Render a report over the graph.")
    r.add_argument("kind", choices=["api-surface"], help="Report kind.")
    r.add_argument("--graph", help="Read an existing graph.json.")
    r.add_argument("--build", help="Build fresh from this package path.")
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
