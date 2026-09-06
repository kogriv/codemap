"""R1-C48 — an import under `if TYPE_CHECKING:` is a third scope, not an eager edge.

From [issue #18](https://github.com/kogriv/codemap/issues/18), filed by the dogfood
target the day it put `no_cycles = true` into its gate: the one cycle named was closed by
an import written under `if TYPE_CHECKING:`, which never runs. griffe files such an
import as module-level; codemap's own AST pass looked only for what griffe misses; the
gate promised "imports that run at import time" and judged one that does not.

What is pinned (design `docs/design/type_checking_imports.md`):

1. Every recognised form of the condition (D3) — bare name, attribute, `not`, `else` —
   and the two that must *not* be recognised: a compound test, and the `if` inside a
   function (function-local already).
2. Precedence (D2): a pair imported both eagerly and under `TYPE_CHECKING` reads eager.
3. The eager graph excludes the scope; lazy cycles include it; `import_map` names it
   always, zero included (D4, D5), and every consumer says so in words.
4. Mutation: with the condition unrecognised, the edge is eager again and the tests go
   red — the check has been shown the thing it must not accept.
"""

from __future__ import annotations

from unittest import mock

import pytest

from codemap import arch
from codemap.extract import extract
from codemap.extract import griffe_extractor as gx
from codemap.query import Query
from codemap.serve.architecture import build_architecture, render_architecture
from codemap.serve.audit import render_dependencies
from codemap.serve.check import build_check, render_check
from codemap.serve.livingdocs import render_docs

CACHE = '''from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .pipeline import Config


def key(c: "Config") -> str:
    return c.name
'''
PIPELINE = '''from .cache import key
import typing as t
if t.TYPE_CHECKING:
    from .other import Other
if not TYPE_CHECKING:
    from .runtime import run
else:
    from .typed import Typed
if TYPE_CHECKING or key:
    from .compound import C


def go():
    if TYPE_CHECKING:
        from .infunc import F
    return key


class Config:
    name = "x"
'''
BOTH = '''from typing import TYPE_CHECKING
from .cache import key
if TYPE_CHECKING:
    from .cache import key as key2
'''


def _pkg(tmp_path, files):
    pkg = tmp_path / "tcpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    for name, body in files.items():
        (pkg / f"{name}.py").write_text(body)
    return pkg


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    files = {"cache": CACHE, "pipeline": PIPELINE, "both": BOTH}
    for leaf in ("other", "runtime", "typed", "compound", "infunc"):
        files[leaf] = "X = 1\n"
    pkg = _pkg(tmp_path_factory.mktemp("r1c48"), files)
    g = extract(str(pkg))
    return pkg, g, Query(g)


def _scope(g, src, dst):
    edges = [e for e in g.edges if e.type == "imports"
             and e.source.endswith("." + src) and e.target.endswith("." + dst)]
    assert len(edges) == 1, (src, dst, edges)
    return edges[0].extras.get("scope", "module")


# -- D3: every row --------------------------------------------------------------------

def test_the_bare_name_form_is_type_checking(tree):
    assert _scope(tree[1], "cache", "pipeline") == "type_checking"


def test_the_attribute_form_is_type_checking(tree):
    assert _scope(tree[1], "pipeline", "other") == "type_checking"


def test_not_swaps_the_branches(tree):
    g = tree[1]
    assert _scope(g, "pipeline", "runtime") == "module", "the body of `if not TYPE_CHECKING` runs"
    assert _scope(g, "pipeline", "typed") == "type_checking", "its `else` does not"


def test_a_compound_test_stays_eager(tree):
    """A condition the tool cannot read is judged strictly, never leniently."""
    assert _scope(tree[1], "pipeline", "compound") == "module"


def test_inside_a_function_it_is_function_local(tree):
    assert _scope(tree[1], "pipeline", "infunc") == "function"


def test_a_pair_imported_both_ways_reads_eager(tree):
    """D2: the edge says how the dependency is reached at its earliest."""
    assert _scope(tree[1], "both", "cache") == "module"


# -- D4 / D5: the graphs and the map ----------------------------------------------------

def test_the_cycle_is_lazy_not_eager(tree):
    q = tree[2]
    assert q.import_cycles() == [], "the gate's defect: this used to be the one eager cycle"
    assert [sorted(c) for c in q.lazy_import_cycles()] == [["tcpkg.cache", "tcpkg.pipeline"]]


def test_import_map_names_the_scope_always(tree):
    assert tree[2].import_map() == {"module_level": 4, "function_local": 1, "type_checking": 3}


def test_import_map_says_zero_when_there_is_none(tmp_path):
    pkg = _pkg(tmp_path, {"a": "from .b import x\n", "b": "x = 1\n"})
    assert Query(extract(str(pkg))).import_map()["type_checking"] == 0


def test_every_consumer_says_which_imports_it_did_not_judge(tree):
    q = tree[2]
    a = build_architecture(q)
    assert a["import_map"]["type_checking"] == 3
    md = render_architecture(q)
    assert "3 `TYPE_CHECKING` import(s)" in md
    assert "closed only by a non-eager import (function-local, or under `if TYPE_CHECKING:`): 1" in md
    assert "`TYPE_CHECKING` import(s)" in render_dependencies(q)
    assert "non-eager import" in render_docs(q)


def test_the_gate_is_green_and_names_what_it_read(tree):
    q = tree[2]
    contract = arch.ArchitectureContract(no_cycles=True)
    violations = arch.check_contract(q, contract)
    assert violations == []
    payload = build_check(q, contract, violations)
    assert payload["ok"] is True
    assert payload["scope"][0]["count"] == 1
    assert payload["scope"][0]["type_checking_imports"] == 3
    md = render_check(q, contract, violations)
    assert "3 import(s) under `TYPE_CHECKING` read as never running" in md


def test_no_lazy_cycles_still_gates_the_coupling(tree):
    contract = arch.ArchitectureContract(no_lazy_cycles=True)
    v = arch.check_contract(tree[2], contract)
    assert [x.rule for x in v] == ["no_lazy_cycles"]
    assert "under `if TYPE_CHECKING:`" in v[0].summary


# -- the mutation ---------------------------------------------------------------------------

def test_with_the_condition_unrecognised_the_edge_is_eager_again(tmp_path):
    """R1-C37: the check has been shown the defect. `_type_checking_branches` returning
    None for everything is the code before this change."""
    pkg = _pkg(tmp_path, {"cache": CACHE, "pipeline": "from .cache import key\nclass Config: pass\n"})
    with mock.patch.object(gx, "_type_checking_branches", lambda node: None):
        g = extract(str(pkg))
    assert _scope(g, "cache", "pipeline") == "module"
    assert Query(g).import_cycles() != [], "the red gate of issue #18"
    g = extract(str(pkg))
    assert _scope(g, "cache", "pipeline") == "type_checking"
