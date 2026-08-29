"""R1-C30-f1 — a call to a re-exported name, and the flat-layout re-export itself (#13).

Filed off the second real target the day R1-C30 landed, as its narrowest residual: on that
tree, `import registry as _r` inside a function resolved five of six calls through `_r`, and
the sixth differed only in that `registry` re-exports it from a sibling. The reporter's own
framing is why it was worth a fix rather than a doc line:

    the failure is silent and asymmetric — the neighbouring call on the same line resolves,
    so nothing in the output hints that one edge is missing.

Reproducing it found the case was wider than reported. It is not about the alias, and not
about the local import: the fast tier dropped **every** call to a re-exported name, in all
four import forms — including `from pkg.api import run` where `api/__init__.py` re-exports
`run`, which is the most ordinary shape in Python. The deep tier followed the alias, which
made it look like a type-inference question. It was not: the re-export was already an edge
in the graph, and nobody read it. One call site on the reporter's tree, 6 on bquant and 19
on codemap itself.

Underneath sat a second, narrower defect that would have kept the fix from reaching the
reporter at all: on a **flat** layout no `export` edge existed to follow. R1-C21 taught the
`imports` pass to recognise a bare sibling; the alias pass was never given the same rule, so
every re-export in such a tree was filed as external and vanished.
"""

from __future__ import annotations

import pytest

from codemap.extract import extract


def _calls(graph):
    return {(e.source, e.target) for e in graph.edges if e.type == "calls"}


def _exports(graph):
    return {(e.source, e.target, e.extras.get("as")) for e in graph.edges if e.type == "export"}


def _flat(tmp_path, files: dict[str, str]):
    """A flat tree: modules are siblings, the directory itself is on `sys.path`."""
    core = tmp_path / "core"
    core.mkdir()
    (core / "__init__.py").write_text("")
    for name, src in files.items():
        (core / name).write_text(src)
    return core


@pytest.fixture
def issue_13(tmp_path):
    """The reporter's three files, verbatim in shape: two calls in one expression through
    one alias, one of which is a re-export."""
    return _flat(tmp_path, {
        "inner.py": "def helper():\n    return 1\n",
        "registry.py": "from inner import helper  # noqa: F401\n\n\ndef own():\n    return 2\n",
        "user.py": "def go():\n    import registry as _r\n    return _r.own() + _r.helper()\n",
    })


# -- the reported case -------------------------------------------------------

def test_both_calls_in_the_expression_resolve_on_fast(issue_13):
    calls = _calls(extract(str(issue_13)))
    assert ("core.user.go", "core.registry.own") in calls      # was already green
    assert ("core.user.go", "core.inner.helper") in calls      # the dropped one


def test_the_two_tiers_now_agree_on_that_expression(issue_13):
    """The asymmetry that made this look like a type-inference gap: deep resolved the
    re-export by following the alias, fast dropped it silently."""
    assert _calls(extract(str(issue_13))) == _calls(extract(str(issue_13), deep=True))


def test_a_flat_layout_re_export_is_an_edge_at_all(issue_13):
    """Nothing above is reachable without this: the alias pass filed a bare-sibling
    re-export as external, so on a flat tree there was no `export` edge to follow."""
    assert ("core.registry", "core.inner.helper", "helper") in _exports(extract(str(issue_13)))


def test_the_flat_re_export_is_labelled_as_the_inference_it_is(issue_13):
    edge = next(e for e in extract(str(issue_13)).edges if e.type == "export")
    assert edge.extras["resolution"] == "flat"


# -- the wider case the repro turned up: every import form ------------------

@pytest.fixture
def packaged(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "inner.py").write_text("def helper():\n    return 1\n")
    (pkg / "api.py").write_text("from pkg.inner import helper  # noqa: F401\n")
    (pkg / "user.py").write_text(
        "from pkg.api import helper\n"
        "\n\n"
        "def module_form():\n"
        "    return helper()\n"
        "\n\n"
        "def local_form():\n"
        "    from pkg.api import helper\n"
        "    return helper()\n"
        "\n\n"
        "def attribute_form():\n"
        "    from pkg import api\n"
        "    return api.helper()\n"
        "\n\n"
        "def aliased_form():\n"
        "    import pkg.api as a\n"
        "    return a.helper()\n"
    )
    return pkg


@pytest.mark.parametrize("caller", ["module_form", "local_form", "attribute_form", "aliased_form"])
def test_every_import_form_reaches_the_definition(packaged, caller):
    """`pkg.api.helper` names no definition — `helper` lives in `pkg.inner`. Each of these
    resolved to that non-node and was dropped by the soundness guard."""
    assert (f"pkg.user.{caller}", "pkg.inner.helper") in _calls(extract(str(packaged)))


def test_a_chain_of_re_exports_is_followed(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "inner.py").write_text("def helper():\n    return 1\n")
    (pkg / "mid.py").write_text("from pkg.inner import helper  # noqa: F401\n")
    (pkg / "api.py").write_text("from pkg.mid import helper  # noqa: F401\n")
    (pkg / "user.py").write_text("from pkg.api import helper\n\n\ndef go():\n    return helper()\n")
    assert ("pkg.user.go", "pkg.inner.helper") in _calls(extract(str(pkg)))


def test_mutual_re_exports_do_not_hang(tmp_path):
    """Nothing forbids a source tree from re-exporting in a circle; the walk must stop."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text("from pkg.b import thing  # noqa: F401\n")
    (pkg / "b.py").write_text("from pkg.a import thing  # noqa: F401\n")
    (pkg / "user.py").write_text("from pkg.a import thing\n\n\ndef go():\n    return thing()\n")
    extract(str(pkg))          # the assertion is that this returns


# -- and it must not invent a target ----------------------------------------

def test_a_name_the_module_does_not_re_export_stays_unresolved(tmp_path):
    """The follow only ever walks an `export` edge the structural pass recorded. A name
    that is simply absent must not be routed to a plausible neighbour."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "inner.py").write_text("def helper():\n    return 1\n")
    (pkg / "api.py").write_text("def other():\n    return 2\n")
    (pkg / "user.py").write_text("def go():\n    from pkg import api\n    return api.helper()\n")
    calls = _calls(extract(str(pkg)))
    assert ("pkg.user.go", "pkg.inner.helper") not in calls
    assert not [t for s, t in calls if s == "pkg.user.go"]


def test_a_re_exported_symbol_used_as_a_value_is_referenced(tmp_path):
    """`references` reads the same resolver, so the dispatch-table form follows — and that
    is what keeps a re-exported callable out of the dead-code bands."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "inner.py").write_text("def helper(x):\n    return x\n")
    (pkg / "api.py").write_text("from pkg.inner import helper  # noqa: F401\n")
    (pkg / "user.py").write_text(
        "from pkg.api import helper\n"
        "\n\n"
        "def go(items):\n"
        "    return map(helper, items)\n"          # named, not called
    )
    refs = {(e.source, e.target) for e in extract(str(pkg)).edges if e.type == "references"}
    assert ("pkg.user.go", "pkg.inner.helper") in refs
