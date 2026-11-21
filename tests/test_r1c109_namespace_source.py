"""R1-C109 — modules of a namespace subpackage carry their source (design ``namespace_source.md``).

E1: a function-local import in a module under a directory without ``__init__.py`` is an edge (griffe's
``visit`` does not fill ``lines_collection``; codemap now does, as griffe's loader does). E2: a file whose stem
is not an identifier (``0001_x.py``) is read there, as griffe reads it in a regular package.
"""

from __future__ import annotations

from codemap.extract import extract
from codemap.diagnostics import diagnostics


def _tree(root, files):
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return root / "p"


FILES = {
    "p/__init__.py": "",
    "p/reg/__init__.py": "",
    "p/reg/t.py": "def g():\n    return 1\n",
    "p/nsp/m.py": "def f():\n    from p.reg.t import g\n    return g()\n",
    "p/nsp/k.py": "class C:\n    def ready(self):\n        if True:\n            from p.reg import t\n        return t\n",
    "p/nsp/migrations/__init__.py": "",
    "p/nsp/migrations/0001_x.py": "from p.reg import t\n",
}


def _imports(g):
    return {(e.source, e.target, e.extras.get("scope")) for e in g.edges if e.type == "imports"}


def test_e1_function_local_imports_in_a_namespace_subpackage_are_edges(tmp_path):
    g = extract(str(_tree(tmp_path, FILES)))
    imps = _imports(g)
    assert ("p.nsp.m", "p.reg.t", "function") in imps
    assert ("p.nsp.k", "p.reg.t", "function") in imps          # a method, inside an `if`


def test_e2_a_migration_named_by_number_is_read_under_a_namespace_app(tmp_path):
    g = extract(str(_tree(tmp_path, FILES)))
    assert "p.nsp.migrations.0001_x" in g.nodes
    assert any(s == "p.nsp.migrations.0001_x" for s, _, _ in _imports(g))
    unread = [d for d in diagnostics(g) if d.get("code") == "unread_inputs"]
    assert not unread, unread


def test_a_dotted_stem_and_a_non_identifier_directory_stay_out(tmp_path):
    files = {**FILES, "p/nsp/a.b.py": "x = 1\n", "p/my-dir/q.py": "y = 1\n"}
    g = extract(str(_tree(tmp_path, files)))
    assert not any(n.startswith("p.nsp.a") for n in g.nodes)
    assert not any("my-dir" in n for n in g.nodes)
