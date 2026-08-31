"""R1-C34 — the stored signature keeps parameter *kind*, so it can be called.

Found while doing R1-C33 (putting the declared signature into the `query` dossier): the
first test asserted the signature of `def run(target: str, *, retries: int = 3) -> bool`
and got back `run(target: str, retries: int = 3) -> bool`. The renderer dropped kind
entirely, and had since M0:

    def f(a, /, b, *args, c: int = 1, **kw)  ->  f(a, b, args = (), c: int = 1, kw = {})
    def h(*args, **kw)                       ->  h(args = (), kw = {})

Two different failures in one string. The `*` and `/` markers vanish, so a keyword-only
parameter reads as positional — write the call the signature describes and Python raises
TypeError. And the variadics come back as ordinary parameters carrying the *runtime*
default griffe reports (`()` / `{}`), which is not written anywhere in the source: a
function that accepts anything renders as one taking two optional positionals.

It mattered beyond cosmetics because three consumers read this string as if it were the
declaration: `report api-surface`, the exports, and `apidiff`, which re-parses it as
`def <sig>: …`. In `apidiff` the loss silently disabled three of its own rules —
`has_vararg`, `has_kwarg` and `_Param.keyword_only` could never be true, so "`*args`
removed" was unreachable, and `def f(a, b)` → `def f(a, *, b)`, which breaks every
positional caller, was classified as no change at all. The data to catch it had been
parsed all along and could not be trusted, which is why the rule that reads it lands
here rather than in its own change.

The strong test in this file is the round-trip: render, re-parse, and compare parameter
kinds against the source. A signature that does not survive that is not a declaration,
it is a description of one.
"""

from __future__ import annotations

import ast

import pytest

from codemap.apidiff import BREAKING, INFO, diff_api
from codemap.extract import extract
from codemap.model import Graph, Node

# (source line, expected rendering) — the shapes that carry kind.
CASES = [
    ("def plain(a, b=2): ...", "plain(a, b=2)"),
    ("def annotated(a: int, b: str = 'x') -> bool: ...", "annotated(a: int, b: str = 'x') -> bool"),
    ("def kwonly(a, *, b=2): ...", "kwonly(a, *, b=2)"),
    ("def kwonly_required(*, only): ...", "kwonly_required(*, only)"),
    ("def posonly(a, /): ...", "posonly(a, /)"),
    ("def posonly_then(a, /, b): ...", "posonly_then(a, /, b)"),
    ("def variadic(*args, **kw): ...", "variadic(*args, **kw)"),
    ("def variadic_typed(*args: int, **kw: str) -> None: ...", "variadic_typed(*args: int, **kw: str) -> None"),
    ("def everything(a, /, b, *args, c: int = 1, **kw) -> None: ...",
     "everything(a, /, b, *args, c: int = 1, **kw) -> None"),
    ("def star_then_kwarg(*args, c=1, **kw): ...", "star_then_kwarg(*args, c=1, **kw)"),
]


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    pkg = tmp_path_factory.mktemp("src") / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "api.py").write_text("\n".join(src for src, _ in CASES) + "\n")
    graph = extract(str(pkg))
    return {n.id.rsplit(".", 1)[-1]: n.signature
            for n in graph.nodes.values() if n.kind == "function"}


def _kinds(sig_or_def: str) -> list[tuple[str, str]]:
    """(kind, name) per parameter, from a `def` statement."""
    fn = ast.parse(sig_or_def if sig_or_def.startswith("def ") else f"def {sig_or_def}: ...").body[0]
    a = fn.args
    out = [("positional_only", p.arg) for p in a.posonlyargs]
    out += [("positional_or_keyword", p.arg) for p in a.args]
    if a.vararg:
        out.append(("var_positional", a.vararg.arg))
    out += [("keyword_only", p.arg) for p in a.kwonlyargs]
    if a.kwarg:
        out.append(("var_keyword", a.kwarg.arg))
    return out


@pytest.mark.parametrize("src,expected", CASES, ids=[s.split("(")[0][4:] for s, _ in CASES])
def test_the_signature_renders_as_written(rendered, src, expected):
    name = src.split("(")[0][len("def "):]
    assert rendered[name] == expected


@pytest.mark.parametrize("src,_expected", CASES, ids=[s.split("(")[0][4:] for s, _ in CASES])
def test_round_trip_preserves_every_parameter_kind(rendered, src, _expected):
    """Render → re-parse → the kinds are the source's. This is the property; the exact
    strings above are only how it happens to be spelled."""
    name = src.split("(")[0][len("def "):]
    assert _kinds(rendered[name]) == _kinds(src)


@pytest.mark.parametrize("src,_expected", CASES, ids=[s.split("(")[0][4:] for s, _ in CASES])
def test_every_signature_parses_as_a_def(rendered, src, _expected):
    """apidiff's contract: it reads the stored string back as `def <sig>: ...`."""
    name = src.split("(")[0][len("def "):]
    ast.parse(f"def {rendered[name]}: ...")


def test_a_variadic_does_not_acquire_an_invented_default(rendered):
    """griffe reports `()` / `{}` for *args / **kw — the collection the callee receives,
    not something written in the source."""
    assert "= ()" not in rendered["variadic"] and "= {}" not in rendered["variadic"]
    assert rendered["variadic"] == "variadic(*args, **kw)"


def test_accepting_anything_does_not_look_like_two_optional_positionals(rendered):
    """The old rendering of `def h(*args, **kw)` was `h(args = (), kw = {})` — a
    different function, and a callable-looking one."""
    assert _kinds(rendered["variadic"]) == [("var_positional", "args"), ("var_keyword", "kw")]


def test_pep8_spacing_annotated_and_bare(rendered):
    assert "b=2" in rendered["plain"]                       # bare default: no spaces
    assert "b: str = 'x'" in rendered["annotated"]          # annotated: spaces


# -- the consumer that could not see it --------------------------------------

def _g(sig: str) -> Graph:
    g = Graph(target="pkg")
    g.add_node(Node(id="pkg.f", kind="function", file="pkg/api.py", signature=sig))
    return g


def test_making_a_parameter_keyword_only_is_breaking():
    d = diff_api(_g("f(a, b)"), _g("f(a, *, b)"))
    kinds = {(c.kind, c.severity) for c in d.changes}
    assert ("param-made-keyword-only", BREAKING) in kinds


def test_dropping_the_keyword_only_marker_only_widens():
    d = diff_api(_g("f(a, *, b)"), _g("f(a, b)"))
    kinds = {(c.kind, c.severity) for c in d.changes}
    assert ("param-made-positional", INFO) in kinds
    assert not any(c.severity == BREAKING for c in d.changes)


def test_removing_a_variadic_is_now_reachable():
    """`has_vararg` was dead: nothing ever rendered a `*`, so it was False on both sides
    of every real diff."""
    d = diff_api(_g("f(a, *args)"), _g("f(a)"))
    assert ("variadic-removed", BREAKING) in {(c.kind, c.severity) for c in d.changes}


def test_an_unchanged_signature_is_still_silent():
    assert diff_api(_g("f(a, /, b, *args, c=1, **kw)"), _g("f(a, /, b, *args, c=1, **kw)")).changes == []
