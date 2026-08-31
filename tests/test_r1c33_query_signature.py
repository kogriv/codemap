"""R1-C33 — the declared signature travels with the dossier.

Not a defect report: this came from auditing the "what we'd take" list in the CodeGraph
разбор (`research/tools/codegraph.md`) and finding that three of its four items had been
closed while item 2 had never been carded at all. It sat for three days as an invisible
line inside prose, because a list without status reads as done — the same blindness
R1-C28 is about, turned on our own notes instead of an answer envelope.

The substance is small and one-directional: a caller who has just learned *where* a
symbol is asks next *how it is called*, and `Node.signature` was already in the graph
(`serve/api_surface.py` reads it). Getting it meant a second op — `call_contract` — which
answers a different question.

Two lines this file holds:

* **`signature` (declared) is not `call_contract` (called in fact).** The first is a node
  field; the second is per-call-site argument shape. Keeping the names apart is the point.
* **Absent means absent.** A node with nothing to say omits the key rather than emitting
  `null` — a class has no signature of its own (only functions get one), so it carries its
  own `__init__` under `constructor`, and an *inherited* constructor is not resolved here.
  Saying nothing about it is the honest answer (unknown != none), and this file pins that
  rather than leaving it to be "fixed" later by a guess.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from codemap.extract import extract
from codemap.query import Query
from codemap.serve.session import Session, build_query_result
from codemap.store import save

SRC = {
    "__init__.py": "",
    "shapes.py": (
        '"""Shapes."""\n'
        "\n"
        "\n"
        "class Base:\n"
        "    def __init__(self, name: str, size: int = 1) -> None:\n"
        "        self.name = name\n"
        "        self.size = size\n"
        "\n"
        "\n"
        "class Derived(Base):\n"
        '    """No __init__ of its own — the constructor is inherited."""\n'
        "\n"
        "    def area(self) -> float:\n"
        "        return 0.0\n"
    ),
    "api.py": (
        '"""Api."""\n'
        "\n"
        "from warnings import deprecated\n"
        "\n"
        "\n"
        "def run(target: str, *, retries: int = 3) -> bool:\n"
        '    """Do the thing."""\n'
        "    return bool(target) and retries > 0\n"
        "\n"
        "\n"
        "@deprecated('use run')\n"
        "def run_old(target):\n"
        "    return run(target)\n"
    ),
}


@pytest.fixture(scope="module")
def pkg(tmp_path_factory):
    root = tmp_path_factory.mktemp("src") / "pkg"
    root.mkdir()
    for name, src in SRC.items():
        (root / name).write_text(src)
    return root


@pytest.fixture(scope="module")
def graph(pkg):
    return extract(str(pkg))


@pytest.fixture(scope="module")
def q(graph):
    return Query(graph)


def _match(q, name, node_id=None):
    ms = build_query_result(q, name)["matches"]
    if node_id:
        ms = [m for m in ms if m["id"] == node_id]
    assert ms, f"no match for {name}"
    return ms[0]


# -- the declared signature --------------------------------------------------

def test_a_function_carries_its_declared_signature(q):
    m = _match(q, "run")
    assert m["signature"] == "run(target: str, *, retries: int = 3) -> bool"


def test_the_signature_is_the_node_field_not_a_recomputation(q, graph):
    """If these ever diverge, one of the two is inventing something."""
    m = _match(q, "run")
    assert m["signature"] == graph.nodes["pkg.api.run"].signature


def test_annotations_and_defaults_survive(q):
    """The half a caller actually needs: it is not just the parameter names."""
    sig = _match(q, "run")["signature"]
    assert ": str" in sig and "retries: int = 3" in sig and "-> bool" in sig


# -- absent means absent -----------------------------------------------------

def test_a_module_has_no_signature_key_at_all(q):
    m = _match(q, "api", node_id="pkg.api")
    assert m["kind"] == "module"
    assert "signature" not in m and "constructor" not in m


def test_a_class_reports_its_own_constructor_under_its_own_name(q):
    m = _match(q, "Base")
    assert m["kind"] == "class"
    # Never dressed up as the class's signature — the class has none.
    assert "signature" not in m
    assert m["constructor"] == "__init__(self, name: str, size: int = 1) -> None"


def test_an_inherited_constructor_is_not_claimed(q):
    """`Derived` has no `__init__` of its own. We do not walk bases to find one, and
    guessing would be worse than the silence: the honest answer is no field."""
    m = _match(q, "Derived")
    assert "constructor" not in m and "signature" not in m


def test_no_field_is_ever_null(q):
    for name in ("run", "Base", "Derived", "api", "area"):
        for m in build_query_result(q, name)["matches"]:
            assert m.get("signature", "x") is not None
            assert m.get("constructor", "x") is not None


# -- deprecation, since it is on the same node -------------------------------

def test_a_deprecated_symbol_says_so(q):
    assert _match(q, "run_old").get("deprecated") is True


def test_a_live_symbol_carries_no_deprecated_key(q):
    assert "deprecated" not in _match(q, "run")


# -- one builder: CLI, warm serve and MCP cannot drift apart -----------------

def test_warm_serve_and_the_cli_return_the_same_dossier(graph, q, tmp_path):
    out = tmp_path / "g.json"
    save(graph, str(out))
    cli = subprocess.run([sys.executable, "-m", "codemap.cli", "query", "run",
                          "--graph", str(out), "--format", "json"],
                         capture_output=True, text=True)
    assert cli.returncode == 0, cli.stderr
    served = Session(graph).handle({"op": "query", "args": {"name": "run"}})
    assert served["ok"]
    assert json.loads(cli.stdout)["matches"] == served["result"]["matches"]


def test_the_text_form_prints_the_signature_and_labels_a_constructor(graph, tmp_path):
    out = tmp_path / "g.json"
    save(graph, str(out))

    def run_text(name):
        r = subprocess.run([sys.executable, "-m", "codemap.cli", "query", name,
                            "--graph", str(out), "--format", "text"],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout

    text = run_text("run")
    assert '"signature"' not in text, "this must exercise the text renderer, not json"
    assert "      run(target: str, *, retries: int = 3) -> bool" in text
    assert "constructor: __init__(self, name: str, size: int = 1) -> None" in run_text("Base")
    assert "[deprecated]" in run_text("run_old")
