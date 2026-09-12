"""M1 acceptance tests — queryable graph on bquant.

DoD (BACKLOG M1): answers the §1 catalog; import + re-export resolution correct.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap import store
from codemap.extract import extract
from codemap.query import Query
from tests.frozen import frozen

# Real-bquant acceptance target: the bquant repo checked out as a sibling
# (../bquant/bquant is the package). Whole module skips when absent (FOSS CI).
BQUANT = Path(__file__).resolve().parents[2] / "bquant" / "bquant"
pytestmark = pytest.mark.skipif(not BQUANT.is_dir(), reason="bquant sibling repo not present")
PIPELINE = "bquant.analysis.zones.pipeline"
MODELS = "bquant.analysis.zones.models"


@pytest.fixture(scope="module")
def graph():
    if not BQUANT.is_dir():
        pytest.skip(f"bquant package not found at {BQUANT}")
    return extract(BQUANT)


@pytest.fixture(scope="module")
def q(graph):
    return Query(graph)


def test_export_edge_reexport(graph):
    # bquant.analysis.zones re-exports analyze_zones from pipeline (§2.1).
    exports = [
        e for e in graph.edges
        if e.type == "export"
        and e.source == "bquant.analysis.zones"
        and e.extras.get("as") == "analyze_zones"
    ]
    assert exports, "expected an export edge for analyze_zones on the zones package"
    assert exports[0].target == f"{PIPELINE}.analyze_zones"


def test_import_edges_resolved(graph):
    # Deep relative import resolved to an absolute module→module edge (§3.1).
    imports = {(e.source, e.target) for e in graph.edges if e.type == "imports"}
    assert (PIPELINE, MODELS) in imports


def test_where_defined_resolves_reexport(q):
    defined = q.where_defined("analyze_zones")
    assert f"{PIPELINE}.analyze_zones" in defined


def test_dependencies_both_ways(q):
    assert MODELS in q.dependencies(PIPELINE)
    assert PIPELINE in q.dependents(MODELS)


def test_cycle_detection(q, graph):
    """The three kinds partition cleanly, and each is closed by the scope it claims.

    This test used to name one concrete pair of the target's modules — `pipeline ↔
    cache`, closed by an import under `if TYPE_CHECKING:` — pinning first the R1-C48 /
    R1-C49 defect and then their fix. On 2026-09-07 the target removed that annotation
    as dead, and the assertion went red over a change in **someone else's tree** that
    codemap had answered correctly. R1-C25's lesson arriving from the other side: a test
    that names the target's content measures the target. The concrete pairs of each kind
    live in the synthetic, mutation-verified fixtures (`test_r1c48_*`, `test_r1c49_*`);
    what belongs here is that the partition holds on a real tree of ~90 modules.
    """
    eager = {frozenset(c) for c in q.import_cycles()}
    lazy = {frozenset(c) for c in q.lazy_import_cycles()}
    type_only = {frozenset(c) for c in q.type_only_import_cycles()}
    assert not (eager & lazy) and not (eager & type_only) and not (lazy & type_only), \
        "a cycle has exactly one kind — the weakest scope that closes it (R1-C49)"
    assert set(q.import_map()) == {"module_level", "function_local", "type_checking"}
    assert q.import_map()["module_level"] > 0

    scopes: dict[tuple[str, str], set[str]] = {}
    for e in graph.edges:
        if e.type == "imports":
            scopes.setdefault((e.source, e.target), set()).add(
                e.extras.get("scope", "module"))
    def closing(cycle, scope):  # noqa: E306 — reads as part of the assertion below
        members = set(cycle)
        return any(scope in s for (src, dst), s in scopes.items()
                   if src in members and dst in members)
    for c in lazy:
        assert closing(c, "function"), f"a lazy cycle needs a function-local edge: {c}"
    for c in type_only:
        assert closing(c, "type_checking"), f"a type-only cycle needs one: {c}"


def test_orphan_modules(q):
    """An invariant, not a name: `bquant.cli` was the example until the target grew a
    `__main__.py` that imports it, and the assertion started measuring the target
    rather than the query (R1-C25 — the second time in this suite, after
    `test_cycle_detection`). What must hold on any tree: an orphan is a module the
    import graph has no inbound edge for."""
    orphans = q.orphan_modules()
    assert isinstance(orphans, list) and orphans, "the dogfood tree has orphans"
    for mod in orphans:
        assert q.graph.nodes[mod].kind == "module"
        assert not [e for e in q.graph.edges
                    if e.type == "imports" and e.target == mod], f"{mod} is imported"


def test_determinism_with_edges():
    """On a **frozen** snapshot: a moving target makes this test measure the target
    (R1-C25 — see tests/frozen.py)."""
    src = frozen(BQUANT)
    assert store.dumps(extract(src)) == store.dumps(extract(src))
