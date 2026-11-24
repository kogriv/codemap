"""Source-only evidence of private methods declared on external ancestors."""

from __future__ import annotations

import sys
import tokenize
from collections import defaultdict, deque
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path

import griffe

_SUFFIXES = (*EXTENSION_SUFFIXES, ".py", ".pyc", ".pyi")
_SOURCE_SUFFIXES = {".py", ".pyi"}


class _ExternalSource:
    """Resolve qualified names using only direct file probes and Griffe's AST visitor."""

    def __init__(self, search_path: Path):
        self.paths = (search_path, *(Path(p) for p in sys.path if isinstance(p, str)))
        self.locations = {}
        self.modules = {}

    def _location(self, name: str) -> tuple[Path | None, tuple[Path, ...]]:
        if name not in self.locations:
            parent, _, leaf = name.rpartition(".")
            paths = self._location(parent)[1] if parent else self.paths
            self.locations[name] = (
                (None, ()) if name in sys.builtin_module_names else self._find(leaf, paths)
            )
        return self.locations[name]

    @staticmethod
    def _find(name, paths) -> tuple[Path | None, tuple[Path, ...]]:
        namespaces = []
        for path in paths:
            folder = path / name
            try:
                if folder.is_dir():
                    for suffix in _SUFFIXES:
                        init = folder / ("__init__" + suffix)
                        if init.is_file():
                            return init, (folder,)
                    namespaces.append(folder)
                for suffix in _SUFFIXES:
                    module = path / (name + suffix)
                    if module.is_file():
                        return module, ()
            except OSError:
                return None, ()
        return None, tuple(namespaces)

    def _module(self, name: str):
        if name not in self.modules:
            path, _ = self._location(name)
            module = None
            if path is not None and path.suffix in _SOURCE_SUFFIXES:
                parent, _, leaf = name.rpartition(".")
                try:
                    with tokenize.open(path) as source:
                        module = griffe.visit(
                            leaf, path, source.read(),
                            parent=griffe.Module(parent) if parent else None,
                        )
                except (OSError, UnicodeError, SyntaxError, ValueError):
                    pass
            self.modules[name] = module
        return self.modules[name]

    def find_class(self, target: str):
        seen = set()
        # Bound re-export chains, including aliases that keep lengthening the path.
        while target not in seen and len(seen) < 32:
            parts = target.split(".")
            if len(parts) < 2 or len(parts) > 32 or not all(p.isidentifier() for p in parts):
                return None
            seen.add(target)
            obj = None
            for i, part in enumerate(parts):
                prefix = ".".join(parts[:i + 1])
                member = obj.members.get(part) if obj is not None else None
                if member is not None and member.is_alias:
                    if not member.runtime:
                        return None
                    if member.target_path != prefix:
                        target = ".".join([member.target_path, *parts[i + 1:]])
                        break
                    member = None  # e.g. a package importing its own submodule
                if member is not None and member.is_class and member.runtime:
                    obj = member
                elif member is None and (obj is None or obj.is_module):
                    obj = self._module(prefix)
                    path, locations = self._location(prefix)
                    if obj is None and (path is not None or not locations):
                        return None
                else:
                    return None
            else:
                return obj if obj is not None and obj.is_class else None
        return None


def stamp_external_overrides(graph, external_bases, search_path: Path) -> None:
    """Record one canonical external declaration for each matching private method."""
    if not external_bases:
        return
    parents = defaultdict(list)
    for edge in graph.edges:
        if edge.type == "inherits" and not edge.extras.get("external"):
            parents[edge.source].append(edge.target)

    source = _ExternalSource(search_path)
    methods = defaultdict(dict)
    for node in graph.nodes.values():
        if node.kind == "function" and node.visibility == "private":
            parent, _, name = node.id.rpartition(".")
            if parent in parents or parent in external_bases:
                methods[parent][name] = node

    for cls, pending in methods.items():
        local = [cls]
        local_seen = {cls}
        queue = deque()
        for base in local:
            queue.extend(external_bases.get(base, ()))
            for parent in parents.get(base, ()):
                if parent not in local_seen:
                    local_seen.add(parent)
                    local.append(parent)
        seen = set()
        while queue and pending:
            target = queue.popleft()
            if target in seen:
                continue
            seen.add(target)
            ancestor = source.find_class(target)
            if ancestor is None or ancestor.path in graph.nodes:
                continue
            for name in pending.keys() & ancestor.members.keys():
                method = ancestor.members[name]
                if not method.is_alias and method.is_function and method.runtime:
                    pending.pop(name).extras["external_override"] = method.path
            queue.extend(path for base in ancestor.bases
                         if (path := getattr(base, "reference_path", None)))
