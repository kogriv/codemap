"""Dataflow-by-string-key pass — column/key flow (DESIGN §7, M12, gap-doc F6).

The behavioral layer follows *symbols*; but bquant threads its data through
string-keyed DataFrame columns — ``df['macd_hist'] = …`` here, ``macd_data['macd_hist']``
there — and the call-graph sees none of it (dogfood F6: querying ``macd_hist``
returned nothing, worse than grep). This pass makes those keys first-class:

- a ``column`` node per distinct string key (``column:macd_hist``);
- a ``writes`` edge  (function → column) for ``x['key'] = …`` (Store subscript) and
  for a dict-literal producer ``{'key': value}`` (how bquant returns computed columns);
- a ``reads``  edge  (function → column) for ``x['key']`` used as a value (Load).

**Honesty.** This is *string-keyed access* flow, an **over-set** of DataFrame
columns: ``config['path']`` and ``d['k']`` land here too — statically we cannot
tell a frame from a dict without type inference. Querying a *specific* key
(``macd_hist``) is precise regardless; treat the node set as "keys", not "columns".
Embedded sample-data modules (literal datasets) are skipped — they are data, not code.
"""

from __future__ import annotations

import ast

from codemap.extract.behavior import _index_modules, _named_functions, _node_id
from codemap.model import Edge, Node

_COLUMN_PREFIX = "column:"


def add_dataflow(graph, griffe_root, target_pkg: str) -> None:
    """Add column nodes + reads/writes edges for string-keyed subscripts."""
    modules = _index_modules(griffe_root)
    columns: set[str] = set()
    edges: set[tuple[str, str, str]] = set()  # (type, func_id, column_id)
    for modpath in sorted(modules):
        if "samples.embedded" in modpath:
            continue  # embedded datasets are data, not code
        mod = modules[modpath]
        fp = getattr(mod, "filepath", None)
        if not fp:
            continue
        try:
            tree = ast.parse(open(fp, encoding="utf-8").read())
        except (OSError, SyntaxError):
            continue
        for fnode, class_stack in _named_functions(tree):
            node_id = _node_id(modpath, class_stack, fnode.name)
            if node_id not in graph.nodes:
                continue
            for key, is_write in _own_key_uses(fnode):
                col_id = _COLUMN_PREFIX + key
                columns.add(key)
                edges.add(("writes" if is_write else "reads", node_id, col_id))

    for key in sorted(columns):
        col_id = _COLUMN_PREFIX + key
        if col_id not in graph.nodes:
            graph.add_node(Node(id=col_id, kind="column", extras={"key": key, "root": "core"}))
    for etype, src, col_id in sorted(edges):
        graph.add_edge(Edge(etype, src, col_id, extras={"resolution": "string-key"}))


def _own_key_uses(fnode):
    """Yield (key, is_write) for string-keyed use in a function's own body.

    Skips nested defs/classes (their own scope). ``is_write`` is set for a Store
    subscript (``x['k'] = …`` / ``x['k'] += …``) and for a dict-literal key
    (``{'k': value}`` — a producer of that key). A Load subscript is a read.
    """
    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(child, ast.Subscript) and isinstance(child.slice, ast.Constant) \
                    and isinstance(child.slice.value, str):
                yield child.slice.value, isinstance(child.ctx, ast.Store)
            elif isinstance(child, ast.Dict):
                for k in child.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        yield k.value, True  # dict-literal key = producer (write)
            yield from visit(child)

    yield from visit(fnode)
