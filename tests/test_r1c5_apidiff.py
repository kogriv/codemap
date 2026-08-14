"""R1-C5 — two-graph API diff + breaking-change detection.

Synthetic before/after graphs exercise each classification rule (removed symbol,
made-private, required-param added / made-required, variadic removed, type +
return changes, compatible additions) plus the CLI gate, serve op and the review
integration.
"""

from __future__ import annotations

from codemap import store
from codemap.apidiff import BREAKING, INFO, WARNING, diff_api
from codemap.cli import main
from codemap.model import Graph, Node
from codemap.serve.apidiff import build_apidiff, render_apidiff
from codemap.serve.session import Session


def _g(nodes: list[Node]) -> Graph:
    g = Graph(target="pkg")
    for n in nodes:
        g.add_node(n)
    return g


def _fn(id, sig, vis="public", dep=False):
    return Node(id=id, kind="function", signature=sig, visibility=vis, is_deprecated=dep)


def _changes(old, new):
    return {(c.kind, c.symbol): c for c in diff_api(_g(old), _g(new)).changes}


# -- symbol-level ------------------------------------------------------------

def test_removed_public_symbol():
    d = diff_api(_g([_fn("pkg.a", "a()")]), _g([]))
    assert d.removed == ["pkg.a"]


def test_added_public_symbol():
    d = diff_api(_g([]), _g([_fn("pkg.a", "a()")]))
    assert d.added == ["pkg.a"]


def test_private_symbols_ignored():
    d = diff_api(_g([_fn("pkg._x", "_x()", vis="private")]),
                 _g([]))  # private removed → not an API change
    assert d.removed == [] and not d.changes


def test_made_private_is_breaking():
    c = _changes([_fn("pkg.a", "a()")], [_fn("pkg.a", "a()", vis="private")])
    assert ("made-private", "pkg.a") in c
    assert c[("made-private", "pkg.a")].severity == BREAKING


def test_kind_changed_is_breaking():
    old = [_fn("pkg.a", "a()")]
    new = [Node(id="pkg.a", kind="class", visibility="public")]
    c = _changes(old, new)
    assert c[("kind-changed", "pkg.a")].severity == BREAKING


def test_newly_deprecated_is_warning():
    c = _changes([_fn("pkg.a", "a()")], [_fn("pkg.a", "a()", dep=True)])
    assert c[("deprecated", "pkg.a")].severity == WARNING


# -- signature-level ---------------------------------------------------------

def test_param_removed_breaking():
    c = _changes([_fn("pkg.f", "f(a, b)")], [_fn("pkg.f", "f(a)")])
    assert c[("param-removed", "pkg.f")].severity == BREAKING


def test_added_required_param_breaking():
    c = _changes([_fn("pkg.f", "f(a)")], [_fn("pkg.f", "f(a, b)")])
    assert c[("param-added-required", "pkg.f")].severity == BREAKING


def test_made_required_breaking():
    c = _changes([_fn("pkg.f", "f(a, b=1)")], [_fn("pkg.f", "f(a, b)")])
    assert c[("param-made-required", "pkg.f")].severity == BREAKING


def test_added_optional_param_is_compatible():
    c = _changes([_fn("pkg.f", "f(a)")], [_fn("pkg.f", "f(a, b=1)")])
    assert c[("param-added-optional", "pkg.f")].severity == INFO


def test_variadic_removed_breaking():
    c = _changes([_fn("pkg.f", "f(a, **kw)")], [_fn("pkg.f", "f(a)")])
    assert c[("variadic-removed", "pkg.f")].severity == BREAKING


def test_type_and_return_changes_are_warnings():
    c = _changes([_fn("pkg.f", "f(a: int) -> int")], [_fn("pkg.f", "f(a: str) -> bool")])
    assert c[("param-type-changed", "pkg.f")].severity == WARNING
    assert c[("return-type-changed", "pkg.f")].severity == WARNING


def test_unparsable_signature_degrades_to_warning():
    # a signature ast can't parse → conservative 'signature-changed', never a false breaking
    c = _changes([_fn("pkg.f", "f(@@@)")], [_fn("pkg.f", "f(###)")])
    assert ("signature-changed", "pkg.f") in c
    assert c[("signature-changed", "pkg.f")].severity == WARNING


def test_identical_signature_no_change():
    assert not diff_api(_g([_fn("pkg.f", "f(a, b=1) -> int")]),
                        _g([_fn("pkg.f", "f(a, b=1) -> int")])).changes


# -- structured + render -----------------------------------------------------

def test_build_apidiff_ok_flag_counts_removed():
    d = build_apidiff(_g([_fn("pkg.a", "a()")]), _g([]))
    assert d["ok"] is False and d["summary"]["breaking_total"] == 1


def test_render_clean_and_breaking():
    clean = render_apidiff(_g([_fn("pkg.a", "a()")]), _g([_fn("pkg.a", "a()")]))
    assert "✅" in clean
    broken = render_apidiff(_g([_fn("pkg.f", "f(a)")]), _g([_fn("pkg.f", "f(a, b)")]))
    assert "❌" in broken and "breaking" in broken.lower()


# -- CLI + serve + review ----------------------------------------------------

def test_cli_diff_exit_code(tmp_path):
    store.save(_g([_fn("pkg.f", "f(a)")]), str(tmp_path / "old.json"))
    store.save(_g([_fn("pkg.f", "f(a, b)")]), str(tmp_path / "new.json"))
    assert main(["diff", str(tmp_path / "old.json"), str(tmp_path / "new.json")]) == 0
    assert main(["diff", str(tmp_path / "old.json"), str(tmp_path / "new.json"),
                 "--exit-code"]) == 1


def test_cli_diff_clean_exit_zero(tmp_path):
    store.save(_g([_fn("pkg.f", "f(a)")]), str(tmp_path / "g.json"))
    assert main(["diff", str(tmp_path / "g.json"), str(tmp_path / "g.json"),
                 "--exit-code"]) == 0


def test_serve_diff_op(tmp_path):
    store.save(_g([_fn("pkg.a", "a()"), _fn("pkg.f", "f(x)")]), str(tmp_path / "old.json"))
    new = _g([_fn("pkg.f", "f(x, y)")])   # a removed, f gained required y
    env = Session(new).handle({"op": "diff", "args": {"base": str(tmp_path / "old.json")}})
    assert env["ok"]
    r = env["result"]
    assert r["removed"] == ["pkg.a"] and r["ok"] is False
    assert any(c["kind"] == "param-added-required" for c in r["changes"])


def test_serve_diff_needs_base():
    env = Session(_g([])).handle({"op": "diff", "args": {}})
    assert "error" in env["result"]


def test_review_base_integration(tmp_path):
    from codemap.query import Query
    from codemap.serve.review import build_review
    store.save(_g([_fn("pkg.a", "a()"), _fn("pkg.f", "f(x, y)")]), str(tmp_path / "old.json"))
    new = _g([_fn("pkg.f", "f(x)")])       # a removed, f lost y
    rv = build_review(Query(new), symbols=["pkg.f"], base_graph=store.load(str(tmp_path / "old.json")))
    assert "api_diff" in rv
    assert rv["api_diff"]["removed"] == ["pkg.a"]
    assert rv["api_diff"]["summary"]["breaking_total"] >= 1
