"""Obsidian-vault export — consumer B (DESIGN §4.1-B, M2.2).

Renders the graph as a browsable knowledge base: one Markdown note per module and
per class/function, cross-linked with ``[[wikilinks]]``. Note names are the full
canonical id (unambiguous), so links resolve without collisions.

``build_vault`` returns ``{relative_path: content}``; the CLI writes the tree.
"""

from __future__ import annotations

from collections import defaultdict

from codemap.query import Query

_SYMBOL_KINDS = {"class", "function"}


def build_vault(query: Query) -> dict[str, str]:
    """Return ``{path: markdown}`` for the whole vault (index + module + symbol notes)."""
    graph = query.graph
    by_module: dict[str, list] = defaultdict(list)
    for node in graph.nodes.values():
        if node.kind in _SYMBOL_KINDS:
            by_module[node.id.rsplit(".", 1)[0]].append(node)

    modules = sorted(n.id for n in graph.nodes.values() if n.kind == "module")
    out: dict[str, str] = {"index.md": _index_note(graph.target, modules)}
    for module in modules:
        out[f"{module}.md"] = _module_note(module, sorted(by_module.get(module, []), key=lambda n: n.id))
    for node in graph.nodes.values():
        if node.kind in _SYMBOL_KINDS:
            out[f"{node.id}.md"] = _symbol_note(query, node)
    return out


def _link(node_id: str) -> str:
    return f"[[{node_id}|{node_id.rsplit('.', 1)[-1]}]]"


def _index_note(target: str, modules: list[str]) -> str:
    lines = [f"# {target} — code map", "", f"_{len(modules)} modules._", ""]
    lines += [f"- {_link(m)}" for m in modules]
    return "\n".join(lines) + "\n"


def _module_note(module: str, symbols: list) -> str:
    lines = [f"# `{module}`", "", "#module", ""]
    classes = [n for n in symbols if n.kind == "class"]
    funcs = [n for n in symbols if n.kind == "function" and "." not in n.id[len(module) + 1:]]
    if classes:
        lines += ["## Classes", ""] + [f"- {_link(c.id)}" for c in classes] + [""]
    if funcs:
        lines += ["## Functions", ""] + [f"- {_link(f.id)}" for f in funcs] + [""]
    return "\n".join(lines).rstrip() + "\n"


def _symbol_note(query: Query, node) -> str:
    pkg = query.graph.target
    module = node.id.rsplit(".", 1)[0]
    tags = f"#{node.kind}" + (" #deprecated" if node.is_deprecated else "")
    lines = [f"# `{node.id.rsplit('.', 1)[-1]}`", "", tags, "", f"In {_link(module)}."]
    if node.signature:
        lines += ["", f"```python\n{node.signature}\n```"]
    if node.docstring:
        lines += ["", node.docstring.strip()]

    if node.kind == "class":
        _section(lines, "Inherits", query.bases(node.id), pkg)
        _section(lines, "Subclasses", query.subclasses(node.id), pkg)
        reg = node.extras.get("registry")
        if reg:
            lines += ["", f"**Registered as** `{reg.get('key')}`."]
    if node.kind == "function":
        _section(lines, "Calls", query.callees(node.id), pkg)
        _section(lines, "Called by", query.callers(node.id), pkg)
    return "\n".join(lines).rstrip() + "\n"


def _section(lines: list, title: str, ids: list[str], pkg: str) -> None:
    if not ids:
        return
    lines += ["", f"## {title}", ""]
    for i in ids:
        # internal targets get a note + wikilink; external (abc.ABC, stdlib) as code
        internal = i == pkg or i.startswith(pkg + ".")
        lines.append(f"- {_link(i)}" if internal else f"- `{i}`")
