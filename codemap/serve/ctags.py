"""ctags export — codemap's graph as a universal-ctags ``tags`` file (R1-C2).

The ``tags`` file is the lowest common denominator of code navigation: vim, Emacs,
``readtags`` and countless editors do go-to-definition by binary-searching a sorted
``tags`` file. codemap already knows every definition's name, file, line and scope,
so emitting this format is near-free interop — the "floor" of capability codemap
comfortably clears (research/00_landscape.md ranks ctags a *learn/emit* peer that
survives on simplicity where heavier graph indexers churned).

**Format.** Extended (exuberant/universal-ctags) format, one line per definition::

    {name}<Tab>{file}<Tab>{address};"<Tab>{kind}<Tab>{ext fields}

The address is a search pattern ``/^<source line>$/`` when the source is readable
(robust to line drift — the whole point of ctags patterns), else a bare line number
(always available from the graph). Extension fields carry ``line:``, ``scope`` (e.g.
``class:Foo``), ``typeref`` / ``signature`` (functions), ``access`` (public/private)
and ``end:`` — all facts codemap already holds, no guessing.

**Honest scope.** Definitions only (classes / functions / methods / attributes);
codemap tracks no token positions, so this is a *tags* file, not a references index
(that is SCIP's job, R1-C1). Modules are files, not tags, so they are skipped — as
universal-ctags itself does. Output is byte-stable: pseudo-tags declare it sorted,
and real tags are sorted by name (then file, then address) for binary search.
"""

from __future__ import annotations

import os

from codemap.model import Graph
from codemap.query import Query

# universal-ctags Python kind letters. Modules are not tagged (a module is a file).
# Methods (function whose parent is a class) use 'm'; module/function-level defs 'f'.
_CLASS, _FUNC, _METHOD, _VAR = "c", "f", "m", "v"

# Long kind names for the scope field key (``class:Foo`` / ``function:bar``).
_SCOPE_KIND = {"class": "class", "function": "function"}

# Node kinds that become tags (module/doc/column are skipped).
_TAGGABLE = {"class", "function", "attribute"}


def _kind_letter(kind: str, parent_kind: str | None) -> str:
    if kind == "class":
        return _CLASS
    if kind == "function":
        return _METHOD if parent_kind == "class" else _FUNC
    return _VAR  # attribute


def _parent_id(nid: str) -> str | None:
    return nid.rsplit(".", 1)[0] if "." in nid else None


def _module_prefix(nodes: dict, nid: str) -> str | None:
    """Return the id of the nearest module ancestor of ``nid`` (for scope stripping)."""
    parts = nid.split(".")
    for i in range(len(parts) - 1, 0, -1):
        pid = ".".join(parts[:i])
        node = nodes.get(pid)
        if node and node.kind == "module":
            return pid
    return None


def _scope_field(nodes: dict, nid: str) -> str | None:
    """Build the ``<scopekind>:<name>`` field, or None for a top-level (module-scoped) def."""
    parent = _parent_id(nid)
    if parent is None:
        return None
    pnode = nodes.get(parent)
    if pnode is None or pnode.kind == "module":
        return None  # top-level def — universal-ctags omits module scope
    scopekind = _SCOPE_KIND.get(pnode.kind, pnode.kind)
    mod = _module_prefix(nodes, parent)
    name = parent[len(mod) + 1:] if mod and parent.startswith(mod + ".") else parent
    return f"{scopekind}:{name}"


def _param_list(signature: str) -> str | None:
    """Extract the parenthesised parameter list from a signature (paren-balanced)."""
    start = signature.find("(")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(signature)):
        c = signature[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return signature[start:i + 1]
    return None


def _return_type(signature: str) -> str | None:
    arrow = signature.rfind("->")
    if arrow == -1:
        return None
    ret = signature[arrow + 2:].strip()
    return ret or None


def _escape_pattern(line: str) -> str:
    """Escape a source line for a ctags ``/^…$/`` search address.

    Backslash first, then the pattern delimiter and regex end-anchor so a literal
    ``/`` or ``$`` in the line does not break or mis-anchor the match.
    """
    return line.replace("\\", "\\\\").replace("/", "\\/").replace("$", "\\$")


def _tab_sanitize(field: str) -> str:
    """Tabs/newlines are field separators — never let them into a field value."""
    return field.replace("\t", " ").replace("\r", " ").replace("\n", " ")


class _SourceLines:
    """Lazily read source files (relative to ``root``) to build search-pattern addresses."""

    def __init__(self, root: str | None):
        self.root = root
        self._cache: dict[str, list[str] | None] = {}

    def line(self, rel_path: str, lineno: int) -> str | None:
        if self.root is None or not lineno:
            return None
        lines = self._cache.get(rel_path, "unset")
        if lines == "unset":
            try:
                with open(os.path.join(self.root, rel_path), encoding="utf-8") as fh:
                    lines = fh.read().split("\n")
            except (OSError, UnicodeDecodeError):
                lines = None
            self._cache[rel_path] = lines
        if not lines or lineno > len(lines):
            return None
        return lines[lineno - 1]


def _address(src: _SourceLines, file: str, lineno: int) -> str:
    """Search-pattern address if the source line is readable, else a bare line number."""
    text = src.line(file, lineno)
    if text is not None:
        return f"/^{_escape_pattern(text)}$/"
    return str(lineno)


def build_ctags(
    query: Query,
    *,
    source_root: str | None = None,
    tool_version: str = "0.0.1",
) -> str:
    """Render the graph as a sorted universal-ctags ``tags`` file (text)."""
    graph: Graph = query.graph
    nodes = graph.nodes
    src = _SourceLines(source_root)

    rows: list[tuple[str, str, str]] = []  # (name, file, full line) — sort key is (name, file, addr)
    for nid in nodes:
        node = nodes[nid]
        if node.kind not in _TAGGABLE or not node.file or not node.lineno:
            continue
        name = nid.rsplit(".", 1)[-1]
        parent = _parent_id(nid)
        parent_kind = nodes[parent].kind if parent and parent in nodes else None

        address = _address(src, node.file, node.lineno)
        fields = [_kind_letter(node.kind, parent_kind), f"line:{node.lineno}"]
        scope = _scope_field(nodes, nid)
        if scope:
            fields.append(scope)
        if node.kind == "function" and node.signature:
            params = _param_list(node.signature)
            if params:
                fields.append(f"signature:{params}")
            ret = _return_type(node.signature)
            if ret:
                fields.append(f"typeref:typename:{ret}")
        fields.append(f"access:{node.visibility}")
        if node.endlineno and node.endlineno != node.lineno:
            fields.append(f"end:{node.endlineno}")

        fields = [_tab_sanitize(f) for f in fields]
        line = f"{name}\t{node.file}\t{address};\"\t" + "\t".join(fields)
        rows.append((name, node.file, line))

    # Sorted by name (byte order), then file, then the whole line — binary-searchable.
    rows.sort(key=lambda r: (r[0], r[1], r[2]))

    header = [
        "!_TAG_FILE_FORMAT\t2\t/extended format; --format=1 will not append ;\" to lines/",
        "!_TAG_FILE_SORTED\t1\t/0=unsorted, 1=sorted, 2=foldcase/",
        "!_TAG_PROGRAM_NAME\tcodemap\t//",
        "!_TAG_PROGRAM_URL\thttps://github.com/kogriv/codemap\t/graph-native tags/",
        f"!_TAG_PROGRAM_VERSION\t{_tab_sanitize(tool_version)}\t//",
    ]
    body = [r[2] for r in rows]
    return "\n".join(header + body) + "\n"
