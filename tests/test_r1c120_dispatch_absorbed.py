"""R1-C120 — dispatch by name, a known cycle absorbed into a larger one, the Russian languages tail.

Expectations A1–A3, B1–B3, C1 are in BACKLOG.md (R1-C120), written before the change.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from codemap import arch
from codemap.devkit import install, template
from codemap.devkit.ratchet import edit_cycles_region, tangles_now
from codemap.extract import extract_repo
from codemap.query import Query
from codemap.serve.audit import build_dead_code
from codemap.serve.check import render_check

RUNNER = {
    "f": 'import importlib\n\n\ndef load(short):\n    m = importlib.import_module(f"pkg.tools.{short}")\n'
         '    fn = getattr(m, "run", None)\n    return fn and fn()\n',
    "plus": 'import importlib\n\n\ndef load(short):\n    m = importlib.import_module("pkg.tools." + short)\n'
            '    return getattr(m, "run")()\n',
    "noprefix": 'import importlib\n\n\ndef load(name):\n    m = importlib.import_module(name)\n'
                '    return getattr(m, "run")()\n',
    "nogetattr": 'import importlib\n\n\ndef load(short):\n    return importlib.import_module(f"pkg.tools.{short}")\n',
    # R1-C120/f1: the consumer's shape — a factory, and the getattr calls in other functions of the module
    "factory": 'import importlib\nfrom types import ModuleType\n\n\ndef module_for(short) -> ModuleType:\n'
               '    return importlib.import_module(f"pkg.tools.{short}")\n\n\n'
               'def emptiness(module: ModuleType):\n    return getattr(module, "empty", None)\n\n\n'
               'class Session:\n    def go(self, short):\n        module = module_for(short)\n'
               '        probe = getattr(module, "run", None)\n        return probe()\n',
}


def _q(tmp_path: Path, runner: str) -> Query:
    files = {"pkg/__init__.py": "", "pkg/runner.py": runner, "pkg/tools/__init__.py": "",
             "pkg/tools/a.py": "def run():\n    return 1\n\n\ndef helper():\n    return 2\n",
             "pkg/tools/b.py": "def run():\n    return 3\n",
             "tests/test_a.py": "from pkg.tools import a\n\n\ndef test_a():\n    assert a.run() == 1\n"}
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    return Query(extract_repo(str(tmp_path / "pkg"), consumers=[str(tmp_path / "tests")]))


def test_a1_a_runner_reaches_every_run_under_its_prefix(tmp_path):
    for i, shape in enumerate(("f", "plus", "factory")):
        q = _q(tmp_path / str(i), RUNNER[shape])
        out = build_dead_code(q, public=True)
        public = {c["id"] for c in out["uncalled_public"]["candidates"]}
        outside = {c["id"] for c in out["called_only_from_outside"]}
        assert "pkg.tools.b.run" not in public and "pkg.tools.a.run" not in outside, (shape, public, outside)
        assert "pkg.tools.a.helper" in public                       # control: not named by the getattr
        refs = [e for e in q.graph.edges if e.type == "references" and e.extras.get("resolution") == "dispatch"]
        assert {e.target for e in refs} == {"pkg.tools.a.run", "pkg.tools.b.run"}


def test_a2_a3_no_claim_without_both_halves(tmp_path):
    for i, shape in enumerate(("noprefix", "nogetattr")):
        q = _q(tmp_path / str(i), RUNNER[shape])
        assert not [e for e in q.graph.edges if e.extras.get("resolution") == "dispatch"], shape
        public = {c["id"] for c in build_dead_code(q, public=True)["uncalled_public"]["candidates"]}
        assert "pkg.tools.b.run" in public


LAZY = "def f():\n    from pkg import {0}\n    return {0}\n"
EAGER = "import pkg.{0}\n"


def _cyc(tmp_path: Path, files: dict[str, str]) -> Query:
    for rel, text in {"pkg/__init__.py": "", **files}.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    return Query(extract_repo(str(tmp_path / "pkg")))


def test_b1_b2_an_absorbed_group_is_kept_and_said_apart(tmp_path):
    # known pair (s, p); a third module w joins: s → p (eager), p ⇢ w, w ⇢ s — one tangle of three
    q = _cyc(tmp_path, {"pkg/s.py": EAGER.format("p"), "pkg/p.py": LAZY.format("w"), "pkg/w.py": LAZY.format("s")})
    (tmp_path / "codemap.toml").write_text('[architecture]\n'
                                           '# >>> codemap-devkit cycles v5 — test\n'
                                           'known_lazy_cycles = [\n  ["pkg.p", "pkg.s"],\n]\n'
                                           'known_type_only_cycles = [\n]\n# <<< codemap-devkit cycles\n')
    c = arch.load_contract(tmp_path)
    vs = arch.check_contract(q, c)
    assert vs and "grew from the known (pkg.p, pkg.s)" in vs[0].modules[0]
    md = render_check(q, c, vs)
    assert "is absorbed into a larger new tangle (pkg.p, pkg.s, pkg.w)" in md and "--tighten" not in md, md
    assert arch.known_stale(q, c) == {}
    now = tangles_now(q)
    edit_cycles_region(tmp_path, {k: [] for k in now} | {"known_lazy_cycles": now["known_lazy_cycles"]},
                       tighten=True)
    kept = arch.load_contract(tmp_path).known_lazy_cycles
    assert frozenset({"pkg.p", "pkg.s"}) in kept and frozenset({"pkg.p", "pkg.s", "pkg.w"}) in kept


def test_b3_a_group_that_is_gone_is_still_stale(tmp_path):
    q = _cyc(tmp_path, {"pkg/s.py": "x = 1\n", "pkg/p.py": "y = 2\n"})
    c = arch.parse_contract(tomllib.loads('[architecture]\nknown_lazy_cycles = [["pkg.p", "pkg.s"]]\n')["architecture"])
    assert arch.known_stale(q, c) == {"known_lazy_cycles": [frozenset({"pkg.p", "pkg.s"})]}
    assert "--tighten" in render_check(q, c, [])


def test_c1_the_russian_block_names_other_languages_in_russian(tmp_path):
    (tmp_path / "web").mkdir()
    (tmp_path / "web/app.js").write_text("export const x = 1;\n")
    assert install.outside_languages(tmp_path, "ru") == "; в этом репозитории есть ещё javascript, их codemap не читает"
    assert "which it does not read" in install.outside_languages(tmp_path)
    assert "{{outside_languages}}" in template("agents_block.ru.md")


def test_c123_partial_overlap_is_not_absorption(tmp_path):
    """R1-C123 (audit F-08): known `{p,s,c}`, now `{p,s,d}` — `c` left the cycle. Stale, tightened away; the
    ratchet adds `{p,s,d}`, so the `p↔s` part stays covered."""
    q = _cyc(tmp_path, {"pkg/s.py": EAGER.format("p"), "pkg/p.py": LAZY.format("d"), "pkg/d.py": LAZY.format("s"),
                        "pkg/c.py": "x = 1\n"})
    (tmp_path / "codemap.toml").write_text('[architecture]\n'
                                           '# >>> codemap-devkit cycles v6 — test\n'
                                           'known_lazy_cycles = [\n  ["pkg.c", "pkg.p", "pkg.s"],\n]\n'
                                           'known_type_only_cycles = [\n]\n# <<< codemap-devkit cycles\n')
    c = arch.load_contract(tmp_path)
    assert arch.known_absorbed(q, c) == {}
    assert arch.known_stale(q, c) == {"known_lazy_cycles": [frozenset({"pkg.c", "pkg.p", "pkg.s"})]}
    md = render_check(q, c, arch.check_contract(q, c))
    assert "absorbed" not in md and "--tighten" in md
    now = tangles_now(q)
    edit_cycles_region(tmp_path, now, tighten=True)
    kept = arch.load_contract(tmp_path).known_lazy_cycles
    assert kept == (frozenset({"pkg.d", "pkg.p", "pkg.s"}),)
    q2 = _cyc(tmp_path / "later", {"pkg/s.py": EAGER.format("p"), "pkg/p.py": LAZY.format("s")})
    assert arch.check_contract(q2, arch.load_contract(tmp_path)) == []      # p↔s after d is gone: still known
