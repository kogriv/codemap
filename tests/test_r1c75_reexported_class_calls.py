"""R1-C75 — a call through a class name that came in by a package re-export.

`from pkg.indicators import LibraryManager` + `LibraryManager.create_indicator()` was unresolved in the
fast tier, while the same call after a direct import of the defining module resolved, and so did a bare
`LibraryManager()` through the re-export. Design: docs/design/reexported_class_calls.md.
"""
from codemap.extract import extract

FILES = {
    "__init__.py": "",
    "indicators/__init__.py": "from .library.manager import LibraryManager\n",
    "indicators/library/__init__.py": "",
    "indicators/library/manager.py": (
        "class LibraryManager:\n"
        "    @classmethod\n    def create_indicator(cls, name):\n        return name\n\n"
        "    @staticmethod\n    def load_all():\n        return 1\n"),
    "analysis/__init__.py": "",
    "analysis/s/__init__.py": "",
    "analysis/s/direct.py": (
        "from ...indicators.library.manager import LibraryManager\n\n\n"
        "def direct():\n    return LibraryManager.create_indicator('x')\n"),
    "analysis/s/viare.py": (
        "from ...indicators import LibraryManager\n\n\n"
        "def via_reexport():\n    return LibraryManager.create_indicator('x'), LibraryManager.load_all()\n\n\n"
        "def construct():\n    return LibraryManager()\n"),
    "analysis/s/absre.py": (
        "from rpkg.indicators import LibraryManager\n\n\n"
        "def absolute_reexport():\n    return LibraryManager.create_indicator('x')\n"),
}
M = "rpkg.indicators.library.manager.LibraryManager"


def _graph(tmp_path):
    root = tmp_path / "rpkg"
    for rel, body in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return extract(str(root))


def _calls(g, src):
    return sorted(e.target for e in g.edges if e.type == "calls" and e.source == src)


def test_a_method_of_a_reexported_class_resolves(tmp_path):
    g = _graph(tmp_path)
    assert _calls(g, "rpkg.analysis.s.viare.via_reexport") == [f"{M}.create_indicator", f"{M}.load_all"]
    assert _calls(g, "rpkg.analysis.s.absre.absolute_reexport") == [f"{M}.create_indicator"]
    for fn, n in (("viare.via_reexport", 2), ("absre.absolute_reexport", 1)):
        c = g.nodes[f"rpkg.analysis.s.{fn}"].extras["calls"]
        assert (c["resolved"], c["unresolved"]) == (n, 0)


def test_the_direct_import_and_the_bare_constructor_are_unchanged(tmp_path):
    g = _graph(tmp_path)
    assert _calls(g, "rpkg.analysis.s.direct.direct") == [f"{M}.create_indicator"]
    assert _calls(g, "rpkg.analysis.s.viare.construct") == [M]
