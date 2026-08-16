"""R1-C2 acceptance — universal-ctags export.

codemap's graph knows every definition's name, file, line and scope, so the
faithful ctags export is a *definitions* tags file (classes / functions / methods /
attributes). These tests pin the kind letters, scope field, signature/typeref/
access/end extension fields, the search-pattern address (+ escaping) with a
line-number fallback, pseudo-tag header + sortedness, determinism, and a real
extraction on the reporoot fixture — plus an optional check against `readtags`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from codemap.extract import extract
from codemap.model import Graph, Node
from codemap.query import Query
from codemap.serve.ctags import build_ctags

CORE = Path(__file__).resolve().parent / "fixtures" / "reporoot" / "core"


def _parse(text: str) -> dict:
    """Parse a tags text into {name: [fields...]} keyed by first occurrence's tagname.

    Returns a list of raw tag lines under ``lines`` plus a name→line dict for lookup.
    """
    tags = [l for l in text.split("\n") if l and not l.startswith("!_TAG")]
    return {"lines": tags, "by_name": {l.split("\t")[0]: l for l in tags}}


@pytest.fixture(scope="module")
def tiny() -> Graph:
    """A minimal deterministic graph exercising every kind + scope + signature."""
    g = Graph(target="pkg")
    g.add_node(Node(id="pkg", kind="module", file="pkg/__init__.py"))
    g.add_node(Node(id="pkg.mod", kind="module", file="pkg/mod.py"))
    g.add_node(Node(id="pkg.mod.Base", kind="class", file="pkg/mod.py",
                    lineno=1, endlineno=3, docstring="Base."))
    g.add_node(Node(id="pkg.mod.Base.run", kind="function", file="pkg/mod.py",
                    lineno=2, endlineno=3, signature="run(self, n: int = 0) -> int",
                    visibility="public"))
    g.add_node(Node(id="pkg.mod.top_func", kind="function", file="pkg/mod.py",
                    lineno=12, endlineno=13, signature="top_func() -> None"))
    g.add_node(Node(id="pkg.mod._hidden", kind="function", file="pkg/mod.py",
                    lineno=20, visibility="private"))
    g.add_node(Node(id="pkg.CONST", kind="attribute", file="pkg/__init__.py",
                    lineno=2, endlineno=2))
    # A re-export alias (no file) and a synthetic column must never become tags.
    g.add_node(Node(id="pkg.Base", kind="class"))  # alias, fileless
    g.add_node(Node(id="column:macd_hist", kind="column"))
    return g


# -- kind letters -------------------------------------------------------------

def test_kind_letters(tiny):
    by = _parse(build_ctags(Query(tiny)))["by_name"]
    def kind(line):  # first ext field after the ;" address terminator
        return line.split(';"\t', 1)[1].split("\t")[0]
    assert kind(by["Base"]) == "c"
    assert kind(by["run"]) == "m"          # parent is a class → method
    assert kind(by["top_func"]) == "f"     # parent is a module → function
    assert kind(by["CONST"]) == "v"        # attribute → variable


# -- scope field --------------------------------------------------------------

def test_scope_field(tiny):
    by = _parse(build_ctags(Query(tiny)))["by_name"]
    assert "\tclass:Base\t" in by["run"]        # method scoped to its class
    assert "class:" not in by["top_func"]       # top-level def: no module scope
    assert "class:" not in by["Base"]           # a top-level class has no scope


# -- signature / typeref / access / end ---------------------------------------

def test_signature_typeref_access_end(tiny):
    by = _parse(build_ctags(Query(tiny)))["by_name"]
    run = by["run"]
    assert "\tsignature:(self, n: int = 0)\t" in run
    assert "\ttyperef:typename:int\t" in run
    assert "\taccess:public\t" in run
    assert run.endswith("\tend:3")
    assert by["_hidden"].endswith("\taccess:private")   # last field, no end: (no endlineno)
    # attributes and unsignatured defs carry no signature field
    assert "signature:" not in by["CONST"]


# -- address: line-number fallback (no source root) ---------------------------

def test_line_number_fallback(tiny):
    by = _parse(build_ctags(Query(tiny)))["by_name"]
    # with no readable source, the address is a bare line number then ;"
    assert '\t1;"\t' in by["Base"]
    assert '\t12;"\t' in by["top_func"]


# -- address: search pattern + escaping ---------------------------------------

def test_pattern_address_and_escaping(tmp_path):
    src = tmp_path / "m.py"
    src.write_text('PATH = ROOT / "x$y"\n', encoding="utf-8")
    g = Graph(target="pkg")
    g.add_node(Node(id="pkg", kind="module", file="m.py"))
    g.add_node(Node(id="pkg.PATH", kind="attribute", file="m.py", lineno=1))
    by = _parse(build_ctags(Query(g), source_root=str(tmp_path)))["by_name"]
    # '/' → '\/' and '$' → '\$'; wrapped in /^…$/
    assert '/^PATH = ROOT \\/ "x\\$y"$/;"' in by["PATH"]


# -- header + sortedness ------------------------------------------------------

def test_pseudo_tags_and_sorted(tiny):
    text = build_ctags(Query(tiny))
    assert text.startswith("!_TAG_FILE_FORMAT\t2\t")
    assert "!_TAG_FILE_SORTED\t1\t" in text
    assert "!_TAG_PROGRAM_NAME\tcodemap\t" in text
    names = [l.split("\t")[0] for l in _parse(text)["lines"]]
    assert names == sorted(names)


# -- exclusions ---------------------------------------------------------------

def test_skips_modules_aliases_and_columns(tiny):
    names = {l.split("\t")[0] for l in _parse(build_ctags(Query(tiny)))["lines"]}
    assert "mod" not in names and "pkg" not in names   # modules are files, not tags
    assert "macd_hist" not in names                    # synthetic column node
    # the fileless re-export alias 'pkg.Base' must not add a second 'Base' with no location
    base_lines = [l for l in _parse(build_ctags(Query(tiny)))["lines"]
                  if l.split("\t")[0] == "Base"]
    assert len(base_lines) == 1 and "\tpkg/mod.py\t" in base_lines[0]


# -- determinism --------------------------------------------------------------

def test_deterministic(tiny):
    assert build_ctags(Query(tiny)) == build_ctags(Query(tiny))


# -- real extraction (reads real source → pattern addresses) ------------------

def test_ctags_from_real_extraction():
    g = extract(CORE)
    text = build_ctags(Query(g), source_root=str(CORE.parent))
    by = _parse(text)["by_name"]
    assert '/^class Engine:$/;"\tc\t' in by["Engine"]
    assert by["run"].split(";\"\t", 1)[1].split("\t")[0] == "m"
    assert "\tclass:Engine\t" in by["run"]              # method scope
    assert by["helper"].split(";\"\t", 1)[1].split("\t")[0] == "f"
    # only definitions with a real location; every line points into core/*.py
    for l in _parse(text)["lines"]:
        assert "\tcore/" in l


# -- optional: validate against the real `readtags` CLI -----------------------

def test_readtags_parses(tiny, tmp_path):
    readtags = shutil.which("readtags")
    if not readtags:
        pytest.skip("readtags CLI not on PATH")
    tags = tmp_path / "tags"
    tags.write_text(build_ctags(Query(tiny)), encoding="utf-8")
    res = subprocess.run([readtags, "-t", str(tags), "run"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert res.stdout.startswith("run\t")  # the reader decoded our tag
