"""R1-C21 acceptance — flat module layout, issues #4 and #5.

Two failure modes of one layout (a directory of sibling modules importing each other by
bare name, valid at runtime because the directory itself is on ``sys.path``):

- **#4** — without ``__init__.py`` griffe reports a *namespace package*, whose
  ``filepath`` is a ``list[Path]``; five separate consumers fed that straight to
  ``Path()``. The build crashed, and the message named neither directory nor cause.
- **#5** — with ``__init__.py`` the build *succeeded* and emitted **zero** ``imports``
  edges, after which ``architecture`` reported "no layer violations / acyclic" and
  ``dead-code`` called every live module an orphan. Absence rendered as health.

So the tests come in two halves: the layout is now **understood** (edges exist, labelled
``resolution="flat"`` because it is an inference about ``sys.path``), and — independently
— a vacuous graph **announces itself** wherever it is presented. The honesty half must
hold even if resolution never had.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap import store
from codemap.diagnostics import NAMESPACE_TARGET, NO_IMPORT_EDGES, diagnostics
from codemap.extract import extract
from codemap.query import Query
from codemap.serve.architecture import render_architecture
from codemap.serve.audit import render_dead_code, render_dependencies
from codemap.serve.session import Session

FIX = Path(__file__).resolve().parent / "fixtures" / "flatpkg"
BQUANT = Path(__file__).resolve().parents[2] / "bquant" / "bquant"


def _namespace_copy(tmp_path: Path) -> Path:
    """The same fixture with ``__init__.py`` removed — the #4 shape."""
    dst = tmp_path / "nspkg"
    dst.mkdir()
    for src in sorted(FIX.glob("*.py")):
        if src.name != "__init__.py":
            (dst / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dst


def _imports(graph) -> dict[tuple[str, str], dict]:
    return {(e.source, e.target): e.extras for e in graph.edges if e.type == "imports"}


# -- #4: the namespace-package crash -----------------------------------------

def test_namespace_directory_builds_without_crashing(tmp_path):
    """The exact reproducer from issue #4 — `TypeError: ... not 'list'`."""
    graph = extract(_namespace_copy(tmp_path))  # must not raise
    assert graph.nodes


def test_namespace_root_has_no_file_but_children_do(tmp_path):
    """`None` is the honest answer for a directory with no single source file — and the
    modules inside it keep real files, so nothing else degrades."""
    graph = extract(_namespace_copy(tmp_path))
    assert graph.nodes["nspkg"].file is None
    assert graph.nodes["nspkg.alpha"].file is not None


def test_behavioral_passes_survive_a_namespace_target(tmp_path):
    """Patching `_rel` alone was not enough: the same list shape crashed four more
    consumers (behavior/attrflow/dataflow/dispatch). If any still choked, the calls
    layer would be empty here."""
    graph = extract(_namespace_copy(tmp_path))
    calls = {(e.source, e.target) for e in graph.edges if e.type == "calls"}
    assert ("nspkg.beta.doubled", "nspkg.alpha.base_width") in calls


# -- #5: flat sibling imports ------------------------------------------------

@pytest.fixture(scope="module")
def flat():
    return extract(FIX)


def test_flat_sibling_import_resolves(flat):
    """`from alpha import base_width` inside flatpkg — the edge that used to vanish."""
    assert ("flatpkg.beta", "flatpkg.alpha") in _imports(flat)


def test_flat_module_import_resolves(flat):
    """The `import beta` form, not just `from beta import x`."""
    assert ("flatpkg.gamma", "flatpkg.beta") in _imports(flat)


def test_flat_edges_are_labelled_as_inferred(flat):
    """It is an inference about sys.path, so it is labelled — never silently exact."""
    assert _imports(flat)[("flatpkg.beta", "flatpkg.alpha")] == {"resolution": "flat"}


def test_package_qualified_import_stays_exact(flat):
    """`from flatpkg.alpha import WIDTH` in gamma resolves in pass A and must NOT be
    labelled — an exact edge and an inferred one have to stay distinguishable."""
    assert _imports(flat)[("flatpkg.gamma", "flatpkg.alpha")] == {}


def test_namespace_variant_resolves_the_same_way(tmp_path):
    """Both halves of the layout end at the same graph — the `__init__.py` should not
    decide whether the import graph exists."""
    graph = extract(_namespace_copy(tmp_path))
    assert _imports(graph)[("nspkg.beta", "nspkg.alpha")] == {"resolution": "flat"}


def test_downstream_reports_recover(flat):
    """The point of the fix: the import graph is no longer empty, so the modules that
    were called orphan are not."""
    q = Query(flat)
    assert q.import_graph.number_of_edges() >= 2
    assert "flatpkg.alpha" not in q.orphan_modules_by_root().get("core", [])


@pytest.mark.skipif(not BQUANT.is_dir(), reason="bquant sibling repo not present")
def test_a_real_package_is_untouched():
    """The regression guard behind design D2: on a correctly-laid-out package the
    inference must fire **zero** times, so no existing graph can shift under it.
    (Measured on bquant + codemap before shipping: 0 rewrites, graphs byte-identical.)"""
    graph = extract(BQUANT)
    assert not [e for e in graph.edges if e.extras.get("resolution") == "flat"]
    assert not diagnostics(graph)  # a real package trips neither check


# -- the honesty half (D5): a vacuous graph announces itself ------------------

def _lonely(tmp_path: Path) -> Path:
    """A package whose modules genuinely never import each other."""
    d = tmp_path / "lonely"
    d.mkdir()
    (d / "__init__.py").write_text("", encoding="utf-8")
    (d / "a.py").write_text("A = 1\n", encoding="utf-8")
    (d / "b.py").write_text("B = 2\n", encoding="utf-8")
    return d


def test_zero_import_edges_is_flagged(tmp_path):
    codes = [d["code"] for d in diagnostics(extract(_lonely(tmp_path)))]
    assert NO_IMPORT_EDGES in codes


def test_single_module_package_is_not_flagged(tmp_path):
    """One module legitimately has nobody to import — flagging it would be noise."""
    d = tmp_path / "solo"
    d.mkdir()
    (d / "__init__.py").write_text("X = 1\n", encoding="utf-8")
    assert not diagnostics(extract(d))


def test_namespace_target_is_named(tmp_path):
    """D4's "say what happened": the build states which directory has no __init__.py."""
    diag = [d for d in diagnostics(extract(_namespace_copy(tmp_path)))
            if d["code"] == NAMESPACE_TARGET]
    assert diag and "__init__.py" in diag[0]["message"]


def test_flagged_graph_is_not_flagged_once_it_has_imports(flat):
    """flatpkg resolves now, so it must NOT carry the empty-import warning."""
    assert NO_IMPORT_EDGES not in [d["code"] for d in diagnostics(flat)]


@pytest.mark.parametrize("render", [render_architecture, render_dead_code,
                                    render_dependencies])
def test_reports_refuse_to_look_clean_on_an_empty_import_graph(tmp_path, render):
    """The failure that made this expensive: "no layer violations", "acyclic" and an
    orphan list all read as findings. Each report must say the graph is empty first."""
    md = render(Query(extract(_lonely(tmp_path))))
    assert "0 import edges across 3 modules" in md
    assert "unknown" in md.lower()


def test_stats_surfaces_diagnostics(tmp_path):
    """Same contract as `freshness` (#3): the surface says when it may be lying."""
    res = Session(extract(_lonely(tmp_path))).handle({"op": "stats"})["result"]
    assert NO_IMPORT_EDGES in [d["code"] for d in res["diagnostics"]]


def test_stats_is_quiet_on_a_sound_graph(flat):
    assert "diagnostics" not in Session(flat).handle({"op": "stats"})["result"]


def test_build_warns_on_stderr(tmp_path, capsys):
    """A build that produces a vacuous graph must not exit quietly."""
    from codemap.cli import main
    out = tmp_path / "g.json"
    assert main(["build", str(_lonely(tmp_path)), "-o", str(out)]) == 0
    assert "0 import edges" in capsys.readouterr().err
    assert store.load(str(out)).nodes  # and still writes a usable graph
