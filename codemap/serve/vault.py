"""Obsidian-vault export — consumer B (DESIGN §4.1-B, M2.2; repo scope M6).

Renders the graph as a browsable knowledge base: one Markdown note per module and
per class/function, cross-linked with ``[[wikilinks]]``. Note names are the full
canonical id (unambiguous), so links resolve without collisions.

With a repo-scoped graph (``extract_repo``) the vault also carries provenance:
core-symbol notes get a **Used by** section grouped by root (tests/docs/…), each
consumer note a **Uses (core)** section, and every ``doc`` node its own note — so
the Obsidian graph shows the blast radius, not just the package interior.

``build_vault`` returns ``{relative_path: content}``; the CLI writes the tree.
"""

from __future__ import annotations

from collections import defaultdict

from codemap.query import Query

_SYMBOL_KINDS = {"class", "function"}
_USE_EDGES = {"calls", "references", "imports"}


def build_vault(query: Query) -> dict[str, str]:
    """Return ``{path: markdown}`` for the whole vault (index + module + symbol + doc notes)."""
    graph = query.graph
    known = set(graph.nodes)
    by_module: dict[str, list] = defaultdict(list)
    for node in graph.nodes.values():
        if node.kind in _SYMBOL_KINDS:
            by_module[node.id.rsplit(".", 1)[0]].append(node)

    # outbound uses (source -> [(target, type)]) for consumer "Uses (core)" sections.
    outbound: dict[str, list[tuple[str, str]]] = defaultdict(list)
    doc_refs: dict[str, list[str]] = defaultdict(list)
    for e in graph.edges:
        if e.type in _USE_EDGES and e.target in known:
            outbound[e.source].append((e.target, e.type))
        if e.type == "references" and graph.nodes.get(e.source) \
                and graph.nodes[e.source].kind == "doc" and e.target in known:
            doc_refs[e.source].append(e.target)

    modules = sorted(n.id for n in graph.nodes.values() if n.kind == "module")
    docs = sorted(n.id for n in graph.nodes.values() if n.kind == "doc")
    out: dict[str, str] = {"index.md": _index_note(graph.target, modules, docs)}
    for module in modules:
        node = graph.nodes[module]
        out[f"{module}.md"] = _module_note(
            node, sorted(by_module.get(module, []), key=lambda n: n.id),
            outbound.get(module, []), known,
        )
    for node in graph.nodes.values():
        if node.kind in _SYMBOL_KINDS:
            out[f"{node.id}.md"] = _symbol_note(query, node, known)
    for doc in docs:
        out[f"{doc}.md"] = _doc_note(graph.nodes[doc], sorted(set(doc_refs.get(doc, []))), known)
    return out


def _link(node_id: str) -> str:
    return f"[[{node_id}|{node_id.rsplit('.', 1)[-1]}]]"


def _tags(node) -> str:
    """Kind + provenance-root tags, so Obsidian graph groups can colour by root."""
    root = node.extras.get("root", "core")
    parts = [f"#{node.kind}", f"#{root}"]
    if node.is_deprecated:
        parts.append("#deprecated")
    return " ".join(parts)


def _linked(i: str, known: set) -> str:
    """Wikilink when the target has its own note, else inline code (external base)."""
    return f"- {_link(i)}" if i in known else f"- `{i}`"


def _index_note(target: str, modules: list[str], docs: list[str]) -> str:
    lines = [f"# {target} — code map", "", f"_{len(modules)} modules, {len(docs)} docs._", ""]
    lines += [f"- {_link(m)}" for m in modules]
    if docs:
        lines += ["", "## Docs", ""] + [f"- [[{d}|{d.rsplit('/', 1)[-1]}]]" for d in docs]
    return "\n".join(lines) + "\n"


def _module_note(node, symbols: list, uses: list[tuple[str, str]], known: set) -> str:
    module = node.id
    root = node.extras.get("root", "core")
    lines = [f"# `{module}`", "", _tags(node), ""]
    classes = [n for n in symbols if n.kind == "class"]
    funcs = [n for n in symbols if n.kind == "function" and "." not in n.id[len(module) + 1:]]
    if classes:
        lines += ["## Classes", ""] + [f"- {_link(c.id)}" for c in classes] + [""]
    if funcs:
        lines += ["## Functions", ""] + [f"- {_link(f.id)}" for f in funcs] + [""]
    # consumer roots: show what core symbols this file reaches into (the impact link).
    if root != "core" and uses:
        core_targets = sorted({t for t, _ in uses})
        lines += ["## Uses (core)", ""] + [_linked(t, known) for t in core_targets] + [""]
    return "\n".join(lines).rstrip() + "\n"


def _symbol_note(query: Query, node, known: set) -> str:
    module = node.id.rsplit(".", 1)[0]
    lines = [f"# `{node.id.rsplit('.', 1)[-1]}`", "", _tags(node), "", f"In {_link(module)}."]
    if node.signature:
        lines += ["", f"```python\n{node.signature}\n```"]
    if node.docstring:
        lines += ["", node.docstring.strip()]

    if node.kind == "class":
        _section(lines, "Inherits", query.bases(node.id), known)
        _section(lines, "Subclasses", query.subclasses(node.id), known)
        reg = node.extras.get("registry")
        if reg:
            lines += ["", f"**Registered as** `{reg.get('key')}`."]
    if node.kind == "function":
        _section(lines, "Calls", query.callees(node.id), known)
        _section(lines, "Called by", query.callers(node.id), known)
    _used_by_section(lines, query, node.id, known)
    return "\n".join(lines).rstrip() + "\n"


def _doc_note(node, targets: list[str], known: set) -> str:
    lines = [f"# `{node.id}`", "", _tags(node), ""]
    if targets:
        lines += ["## References", ""] + [_linked(t, known) for t in targets]
    return "\n".join(lines).rstrip() + "\n"


def _used_by_section(lines: list, query: Query, node_id: str, known: set) -> None:
    """Inbound references grouped by root — the blast radius (repo-scoped graphs)."""
    refs = query.references_to(node_id)
    if not refs:
        return
    by_root: dict[str, set] = defaultdict(set)
    for r in refs:
        by_root[r["root"]].add(r["source"])
    # core self-references are already covered by Calls/Called-by; highlight the rest.
    external_roots = {r: s for r, s in by_root.items() if r != "core"}
    if not external_roots:
        return
    total = sum(len(s) for s in external_roots.values())
    lines += ["", f"## Used by ({total} outside core)", ""]
    for root in sorted(external_roots):
        for src in sorted(external_roots[root])[:20]:
            lines.append(f"- {_link(src) if src in known else f'`{src}`'} _({root})_")


def _section(lines: list, title: str, ids: list[str], known: set) -> None:
    if not ids:
        return
    lines += ["", f"## {title}", ""]
    for i in ids:
        lines.append(_linked(i, known))
