"""Griffe object → its source file, normalized (R1-C21 / design D4).

``filepath`` on a griffe object has **three** shapes, not two:

- a ``Path`` — the ordinary module/class/function case;
- ``None`` — no file (synthetic objects);
- a ``list[Path]`` — a **namespace package** (a directory with no ``__init__.py``),
  which has search locations rather than one source file.

Every consumer used to take the first two into account and crash on the third
(``TypeError: ... not 'list'``, issue #4). The list shape is normalized here, once,
so no pass has to know about it: a namespace package has no single file, and ``None``
is the value every one of those call sites already handles.

Note the shape that made the old guards fail: ``if not fp`` *passes* a non-empty
list, so each site sailed past its own check straight into ``Path(list)``.
"""

from __future__ import annotations

from pathlib import Path


def module_file(obj) -> Path | None:
    """The single source file behind a griffe object, or ``None`` if it has none."""
    fp = getattr(obj, "filepath", None)
    if fp is None or isinstance(fp, list):
        return None
    return Path(fp)


def is_namespace_dir(obj) -> bool:
    """True for a namespace package (a directory without ``__init__.py``)."""
    return isinstance(getattr(obj, "filepath", None), list)


def module_identity(obj) -> str | None:
    """The **real** path behind a module — symlinks resolved (R1-C23 / design D1).

    A directory symlink that points into its own ancestry makes the same file reachable
    under unboundedly many module names: a single ``loop -> .`` link turned a 17-file
    package into **615 modules** nested 40 deep, silently. Resolving to a canonical path
    lets the walk notice it has read this file already.

    A namespace package has search locations rather than a file; its first location
    identifies it well enough for that purpose.
    """
    fp = getattr(obj, "filepath", None)
    if isinstance(fp, list):
        fp = fp[0] if fp else None
    if fp is None:
        return None
    try:
        return str(Path(fp).resolve())
    except OSError:
        return None


def module_imports(mod, modpath: str, known_modules) -> dict[str, str]:
    """``mod.imports``, with flat-layout sibling targets package-qualified (R1-C21).

    griffe records an import target exactly as the source writes it, so in a flat layout
    (`from alpha import X`, the directory itself on ``sys.path``) the target is
    ``alpha.X`` — unprefixed, and therefore indistinguishable from ``pandas.X`` to every
    consumer that tests ``target.startswith(pkg + ".")``. Qualifying the map here means
    the inference lives in **one** place and each pass (calls, attribute access) simply
    stops being blind to the layout, rather than each re-deriving it.

    Same guard as the ``imports``-edge resolution (design D2): only a target that is not
    already package-internal, and only when its head names a module sitting **beside**
    the importer. The module-level inference stays visible on the corresponding
    ``imports`` edge, which carries ``extras.resolution="flat"``.
    """
    imports = dict(getattr(mod, "imports", None) or {})
    if "." not in modpath:
        return imports
    parent, pkg = modpath.rsplit(".", 1)[0], modpath.split(".", 1)[0] + "."
    out = {}
    for name, target in imports.items():
        if not target.startswith(pkg) and f"{parent}.{target.split('.', 1)[0]}" in known_modules:
            target = f"{parent}.{target}"
        out[name] = target
    return out
