"""Runtime and report controls for bindings retained by decorators and external dispatch."""

import ast
import subprocess
import sys
from textwrap import dedent

import griffe
import pytest

from codemap.extract import extract, extract_repo
from codemap.incremental import update_graph
from codemap.model import Graph
from codemap.query import Query
from codemap.scope import resolve_scope
from codemap.serve.audit import build_behavior, build_dead_code, render_dead_code

HELPERS = dedent("""\
    def old_body():
        return "old"

    def new_body():
        return "new"

""")

RETAINED = dedent("""\
    registry = []

    def retain(fn):
        registry.append(fn)
        return fn

    @retain
    def retained():
        return old_body()

    @retain
    def retained():
        return new_body()

    def mixed():
        return 1

    @retain
    def mixed():
        return 2

    def mixed():
        return 3

    def later_only():
        return 1

    @retain
    def later_only():
        return 2
    """)


def _package(tmp_path, source):
    pkg = tmp_path / "example106"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "sample.py").write_text(source)
    return pkg


def _lines(source, name):
    return [n.lineno for n in ast.parse(source).body
            if isinstance(n, ast.FunctionDef) and n.name == name]


def _run(path, code):
    subprocess.run([sys.executable, "-c", code], cwd=path, check=True)


@pytest.mark.parametrize("deep", [False, True])
def test_replaced_bindings_and_reports(tmp_path, deep):
    core_source = HELPERS + RETAINED
    pkg = _package(tmp_path, core_source)
    consumer = tmp_path / "examples"
    consumer.mkdir()
    consumer_source = "from example106.sample import old_body, new_body\n" + RETAINED
    (consumer / "example.py").write_text(consumer_source)
    _run(tmp_path, """\
from example106.sample import registry
from examples.example import registry as consumer_registry
for entries in (registry, consumer_registry):
    assert [fn() for fn in entries if fn.__name__ == "retained"] == ["old", "new"]
""")

    graph = extract_repo(pkg, consumers=(consumer,), mode="full", deep=deep)
    query = Query(graph)
    report = build_dead_code(query)
    text = render_dead_code(query)
    assert report["shadowed"] == query.shadowed_definitions()
    expected = {}
    for prefix, source in (("example106.sample", core_source),
                           ("examples.example", consumer_source)):
        for name in ("retained", "mixed", "later_only"):
            node = graph.nodes[f"{prefix}.{name}"]
            lines = _lines(source, name)
            assert node.extras["shadows"] == lines[:-1]
            if name == "retained":
                assert node.extras["decorated_shadows"] == lines[:1]
                assert f"`{node.id}` — defined at line" not in text
            else:
                expected[node.id] = lines[:1]
                assert (f"`{node.id}` — defined at line {node.lineno} shadows the "
                        f"definition at line {lines[0]}.") in text
        calls = {e.target for e in graph.edges
                 if e.source == f"{prefix}.retained" and e.type == "calls"}
        assert calls == {"example106.sample.new_body"}
    assert {row["id"]: row["shadows"] for row in report["shadowed"]} == expected
    # Core totals conserve calls even in the omitted earlier body.
    sites = build_behavior(query)["call_sites"]
    assert sites["shadowed_not_walked"] >= 1
    assert sites["out"] + sites["shadowed_not_walked"] == sum(
        isinstance(node, ast.Call) for node in ast.walk(ast.parse(core_source))
    )


def test_incremental_repeat_and_old_graph(tmp_path):
    source = HELPERS + RETAINED
    pkg = _package(tmp_path, source)
    (pkg / "external.py").write_text(STDLIB)
    for name in ("a", "b", "c", "d"):
        (pkg / f"{name}.py").write_text("")
    original = extract(pkg, repeat=2)
    node = "example106.sample.retained"
    assert original.nodes[node].extras["decorated_shadows"] == _lines(source, "retained")[:1]
    old = Graph.from_dict(original.to_dict())
    del old.nodes[node].extras["decorated_shadows"]
    assert node in {row["id"] for row in Query(old).shadowed_definitions()}

    scope = resolve_scope(pkg, use_git=False)
    unchanged, info = update_graph(original, pkg, scope, scope, repeat=2)
    assert info["mode"] == "unchanged"
    assert build_dead_code(Query(unchanged))["shadowed"] == build_dead_code(Query(original))["shadowed"]

    graph = original
    for module, content, reported in (
        ("a.py", "x = 1\n", False),
        ("sample.py", source.replace("@retain\ndef retained", "def retained", 1), True),
        ("sample.py", source, False),
    ):
        (pkg / module).write_text(content)
        updated = resolve_scope(pkg, use_git=False)
        graph, info = update_graph(graph, pkg, scope, updated, repeat=2)
        assert info["mode"] == "incremental"
        full = extract(pkg)
        actual = Query(graph)
        assert build_dead_code(actual) == build_dead_code(Query(full))
        assert graph.nodes["example106.external.Child._format_usage"].extras[
            "external_override"] == "argparse.HelpFormatter._format_usage"
        assert render_dead_code(actual) == render_dead_code(Query(full))
        assert (node in {row["id"] for row in actual.shadowed_definitions()}) is reported
        scope = updated


STDLIB = dedent("""\
    from argparse import HelpFormatter as Formatter

    class Parent(Formatter):
        pass

    class Child(Parent):
        def _format_usage(self, *args):
            return "runtime dispatch proof"

        def _unused(self):
            pass

        def _format_action(self, action):
            pass

        def callback(self):
            return self._format_action

    class Local:
        def _hook(self):
            pass

        def run(self):
            return self._hook()

    class Override(Local):
        def _hook(self):
            pass
    """)


@pytest.mark.parametrize("deep", [False, True])
def test_stdlib_external_override(tmp_path, deep):
    pkg = _package(tmp_path, STDLIB)
    _run(tmp_path, r"""
from example106.sample import Child
formatter = Child("example")
formatter.add_usage(None, [], [])
assert formatter.format_help() == "runtime dispatch proof\n"
""")
    graph = extract(pkg, deep=deep)
    query = Query(graph)
    base = "example106.sample."
    candidates = {c["id"]: c for c in query.dead_code()}
    target = base + "Child._format_usage"
    declaration = "argparse.HelpFormatter._format_usage"
    assert graph.nodes[target].extras["external_override"] == declaration
    assert candidates[target]["confidence"] == "medium"
    reason = candidates[target]["reasons"][0]
    assert declaration in reason and "external source" in reason
    assert reason in render_dead_code(query)
    report = build_dead_code(query)
    assert candidates[target] in report["candidates"]
    assert report["uncalled_public"]["listed"] is False
    assert target not in {c["id"] for c in build_dead_code(query, min_confidence="high")["candidates"]}
    assert candidates[base + "Child._unused"]["confidence"] == "high"
    assert candidates[base + "Child._format_action"]["confidence"] == "low"
    assert candidates[base + "Override._hook"]["confidence"] == "low"


@pytest.mark.parametrize("deep", [False, True])
def test_installed_source_without_execution(tmp_path, monkeypatch, deep):
    installed = tmp_path / "site"
    installed.mkdir()
    dependency = installed / "toy106"
    dependency.mkdir()
    marker = tmp_path / "executed"
    tripwire = f"open({str(marker)!r}, 'w').close()\nraise RuntimeError('executed dependency')\n"
    (dependency / "__init__.py").write_text("from .hooks import Hook as Exported\n" + tripwire)
    (dependency / "hooks.py").write_text(dedent("""\
        from .ancestor import Ancestor as Parent

        class Hook(Parent):
            pass
        """) + tripwire)
    (dependency / "ancestor.pyi").write_text("class Ancestor:\n    def _handle(self): ...\n")
    monkeypatch.syspath_prepend(str(installed))
    pkg = _package(tmp_path, dedent("""\
        from toy106 import Exported as Hook
        from missing106 import Missing

        class Consumer(Hook):
            def _handle(self):
                pass

            def _other(self):
                pass

        class Unresolved(Missing):
            def _handle(self):
                pass

        class Unbound(toy106.Exported):
            def _handle(self):
                pass
        """))
    (dependency / "unrelated.py").write_text("class Other: pass\n" + tripwire)
    visit = griffe.visit
    parsed = set()

    def track_visit(name, path, code, **kwargs):
        if path.parent == dependency:
            parsed.add(path.name)
        return visit(name, path, code, **kwargs)

    monkeypatch.setattr(griffe, "visit", track_visit)
    graph = extract(pkg, deep=deep)
    assert parsed == {"__init__.py", "hooks.py", "ancestor.pyi"}
    if not deep:
        repeated = extract(pkg, repeat=2)
        assert build_dead_code(Query(repeated)) == build_dead_code(Query(graph))
    query = Query(graph)
    candidates = {c["id"]: c for c in query.dead_code()}
    prefix = "example106.sample."
    target = prefix + "Consumer._handle"
    assert graph.nodes[target].extras["external_override"] == "toy106.ancestor.Ancestor._handle"
    assert candidates[target]["confidence"] == "medium"
    for name in ("Consumer._other", "Unresolved._handle", "Unbound._handle"):
        assert candidates[prefix + name]["confidence"] == "high"
    assert not marker.exists()
