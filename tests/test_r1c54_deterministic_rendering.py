"""R1-C54 — the same graph renders the same text, whatever the hash seed.

[Issue #20](https://github.com/kogriv/codemap/issues/20), filed by the lab while raising
their pin 0.0.16 → 0.0.17. The graph was inert exactly as promised — 1904 nodes, 4652
edges, the whole JSON byte-identical but for `provenance.version` — and the *printed cycle
chains* differed between runs. They nearly recorded it as a behavioural change in the
release, and did not only because they re-measured within one version first.

`nx.simple_cycles` enters a cycle wherever its traversal happens to, and that follows
set-iteration order, i.e. string hashes. `arch.py` sorted the cycles by `(len, c)`, which
looked like canonicalisation but could not be: the key moves with the rotation.

Gap: `gaps/cycle_rotation_nondeterminism_2026-09-12.md`. The perimeter measured there is
wider than the report: three consumers of one source, one of them the **structured** MCP
`architecture` answer, while `report dependencies` and the living docs were already stable
because they print counts rather than chains.

The guard has to spawn processes — `PYTHONHASHSEED` is read once at interpreter start, so
an in-process monkeypatch cannot produce the condition. Its positive control is twofold:
the rotation unit test below fails if canonicalisation is removed, and the cross-seed test
was measured red on the pre-fix code (3 distinct outputs for each of three surfaces across
8 seeds — recorded in the gap with the numbers).
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from codemap import store
from codemap.extract import extract
from codemap.query import Query, _canonical_cycles

PKG = {
    "__init__.py": "",
    # one lazy cycle over three modules: a → b → c → a, each closed in a function
    "a.py": "def f():\n    from .b import g\n    return g()\n",
    "b.py": "def g():\n    from .c import h\n    return h()\n",
    "c.py": "def h():\n    from .a import f\n    return f()\n",
    # a second, shorter cycle so the *order of cycles* is exercised too
    "d.py": "def p():\n    from .e import q\n    return q()\n",
    "e.py": "def q():\n    from .d import p\n    return p()\n",
}

_PROBE = textwrap.dedent('''
    import hashlib, json, sys
    from codemap import arch, store
    from codemap.query import Query
    from codemap.serve.architecture import build_architecture, render_architecture
    from codemap.serve.audit import render_dependencies
    from codemap.serve.livingdocs import render_docs

    q = Query(store.load(sys.argv[1]))
    h = lambda s: hashlib.md5(s.encode()).hexdigest()
    c = arch.ArchitectureContract(no_cycles=True, no_lazy_cycles=True,
                                  no_type_only_cycles=True)
    print(json.dumps({
        "architecture_md": h(render_architecture(q)),
        "architecture_json": h(json.dumps(build_architecture(q))),
        "dependencies_md": h(render_dependencies(q)),
        "docs_md": h(render_docs(q)),
        "check": h(json.dumps([[v.rule, v.summary, list(v.modules)]
                               for v in arch.check_contract(q, c)])),
        "graph_bytes": h(store.dumps(q.graph)),
        "cycles": h(json.dumps(q.lazy_import_cycles())),
    }))
''')


@pytest.fixture(scope="module")
def graph_file(tmp_path_factory):
    root = tmp_path_factory.mktemp("r1c54")
    pkg = root / "cycpkg"
    pkg.mkdir()
    for name, body in PKG.items():
        (pkg / name).write_text(body)
    path = root / "g.json"
    store.save(extract(pkg), path)
    return path


# -- the unit control: rotation in, one form out -----------------------------------------

def test_every_rotation_of_a_cycle_canonicalises_to_one_form():
    rotations = [["a", "b", "c"], ["b", "c", "a"], ["c", "a", "b"]]
    assert {tuple(_canonical_cycles([r])[0]) for r in rotations} == {("a", "b", "c")}


def test_the_order_of_cycles_is_canonical_too(graph_file):
    """D2: rotating without sorting would leave the *list* order on the traversal."""
    q = Query(store.load(graph_file))
    cycles = q.lazy_import_cycles()
    assert cycles == sorted(cycles, key=lambda c: (len(c), c))
    assert all(c[0] == min(c) for c in cycles), "each starts at its smallest node"
    assert len(cycles) == 2, "the fixture carries both a 3-cycle and a 2-cycle"


def test_without_canonicalisation_the_rotations_stay_three_answers():
    """R1-C37: the thing the fix must reject, shown to the check. This is what all three
    consumers were printing — one cycle, three texts."""
    raw = [["b", "c", "a"], ["c", "a", "b"], ["a", "b", "c"]]
    assert len({tuple(c) for c in raw}) == 3, "three renderings of one cycle"
    assert len({tuple(c) for c in (_canonical_cycles([c])[0] for c in raw)}) == 1


# -- the integration guard: across hash seeds, in separate processes ----------------------

def _run(graph_file, seed: int) -> dict:
    probe = Path(graph_file).parent / "probe.py"
    probe.write_text(_PROBE)
    out = subprocess.run([sys.executable, str(probe), str(graph_file)],
                         capture_output=True, text=True, check=True,
                         env={"PYTHONHASHSEED": str(seed), "PATH": "/usr/bin:/bin",
                              "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
    return json.loads(out.stdout)


@pytest.mark.parametrize("surface", ["architecture_md", "architecture_json", "check",
                                     "dependencies_md", "docs_md", "graph_bytes", "cycles"])
def test_one_graph_one_rendering_across_hash_seeds(graph_file, surface):
    """Six surfaces, eight seeds, one answer each. The three that were already stable are
    in here on purpose: a regression in them must fail too, and leaving them out would make
    this guard narrower than the claim it defends (README: "deterministic ... diffable").
    """
    seen = {_run(graph_file, seed)[surface] for seed in range(8)}
    assert len(seen) == 1, f"{surface} rendered {len(seen)} different ways across 8 seeds"
