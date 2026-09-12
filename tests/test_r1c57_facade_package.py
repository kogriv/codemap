"""R1-C57 — a package whose whole job is re-export broke three ways at once.

Found by axis B4 (`gaps/third_shape_2026-09-12.md` §E1/§E10) on the facade layout, which
`pytest`/`_pytest` and `attrs`/`attr` both use: a public package that defines almost
nothing and re-exports a private one.

1. **The build crashed.** `codemap build attrs/src/attrs` exited 1 with
   `Could not resolve alias attrs.field pointing at attr.field`. griffe merges a `.pyi`
   beside `__init__.py`, the merge resolves aliases, and an alias into a package nobody
   loaded raises. No graph at all, for six valid published files.
2. **The surface read as one symbol.** `report api-surface` on the `pytest` facade printed
   *"1 public symbols across 1 modules"* where `__init__.py` re-exports 90 names: an alias
   to an outside definition produced no edge, so the package's entire API was invisible.
3. **The warning did not travel.** The build says "0 import edges … read them as unknown";
   four reports carried that and `api-surface` did not — the one report a reader of a
   facade package is most likely to ask for.

The fixture is that shape in miniature. The control that matters is the third test: an
ordinary `import numpy as np` must **not** become an exported name, or the fix would buy
its surface by calling every import an export.
"""

from __future__ import annotations

import pytest

from codemap.extract import extract
from codemap.serve.api_surface import build_api_surface, render_api_surface

IMPL_INIT = ""
IMPL_CORE = '''def field(name):
    """The real definition."""
    return name


def _private(x):
    return x
'''
# the facade: re-exports two public names, imports one thing for its own use
FACADE_INIT = '''from impl.core import field
from impl.core import _private as helper
import json

__all__ = ["field"]
'''
# The stub carries `@overload` declarations for a name the runtime module only *aliases*.
# That is what makes griffe's stub merge resolve the alias — and the alias points into a
# package nobody loaded. `attrs/__init__.pyi` has exactly this shape.
FACADE_PYI = '''from typing import overload

from impl.core import field as field

@overload
def field(name: str) -> str: ...
@overload
def field(name: int) -> int: ...

__all__ = ["field"]
'''


@pytest.fixture(scope="module")
def trees(tmp_path_factory):
    root = tmp_path_factory.mktemp("r1c57")
    impl = root / "impl"
    impl.mkdir()
    (impl / "__init__.py").write_text(IMPL_INIT)
    (impl / "core.py").write_text(IMPL_CORE)
    facade = root / "facade"
    facade.mkdir()
    (facade / "__init__.py").write_text(FACADE_INIT)
    (facade / "__init__.pyi").write_text(FACADE_PYI)
    (facade / "extra.py").write_text("VALUE = 1\n")
    return extract(str(facade))


# -- D1: the build completes ------------------------------------------------------------

def test_the_facade_builds_at_all(trees):
    """The shape the fix exists to reject (R1-C37): before it, this raised
    `AliasResolutionError` out of `griffe.load` and the CLI exited 1."""
    assert trees.target == "facade"
    assert any(n.id == "facade.extra.VALUE" for n in trees.nodes.values())


def test_the_sibling_is_loaded_but_not_extracted(trees):
    """Loading `impl` makes the aliases resolvable; it must not put `impl` in the graph,
    or a build of one package would silently describe two."""
    roots = {n.id.split(".")[0] for n in trees.nodes.values()}
    assert roots == {"facade"}


# -- D2: the re-exported surface ---------------------------------------------------------

def test_a_public_alias_to_an_outside_definition_is_recorded(trees):
    edges = [e for e in trees.edges if e.type == "export"
             and e.extras.get("external")]
    assert [(e.extras["as"], e.target) for e in edges] == [("field", "impl.core.field")]


def test_a_plain_import_is_not_an_export(trees):
    """The control: `import json` and a private alias are not this package's API. Without
    it, the fix would manufacture a public surface out of every import in `__init__`."""
    exported = {e.extras.get("as") for e in trees.edges if e.type == "export"}
    assert "json" not in exported and "helper" not in exported


def test_the_report_counts_and_names_them(trees):
    md = render_api_surface(trees)
    assert "1 more re-exported from outside this root" in md
    assert "not judged here" in md, "the report must say whose definitions it did not see"
    assert "`field`** → `impl.core.field`" in md


def test_the_structured_payload_carries_the_count_always(trees, tmp_path):
    assert build_api_surface(trees)["totals"]["reexported_from_outside"] == 1

    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "__init__.py").write_text("")
    (plain / "a.py").write_text("def go():\n    return 1\n")
    payload = build_api_surface(extract(str(plain)))
    assert payload["totals"]["reexported_from_outside"] == 0, \
        "zero is printed, not omitted — the reader must not have to tell it from 'we did not look'"
    assert payload["reexported_from_outside"] == []


# -- D3: the warning travels --------------------------------------------------------------

def test_api_surface_carries_the_build_diagnostics(trees):
    """`0 import edges` is exactly the condition a facade produces, and this is the report
    its reader asks for first."""
    md = render_api_surface(trees)
    assert "import graph is empty" in md
    assert "not as a clean bill of health" in md
    assert build_api_surface(trees)["diagnostics"], "the structured payload too"
