"""R1-C3 — architecture contracts + the `check` enforcement gate.

Synthetic layered graphs keep the rules deterministic and independent of any real
package's evolving shape. Each rule gets a violating and a clean case; the CLI gate
is checked for its exit codes (0 clean / 2 broken), which is the whole point — a
contract that can fail CI.
"""

from __future__ import annotations

import pytest

from codemap import store
from codemap.arch import (ArchitectureContract, check_contract, load_contract,
                          parse_contract)
from codemap.cli import main
from codemap.model import Edge, Graph, Node
from codemap.query import Query
from codemap.serve.check import render_check
from codemap.serve.session import Session


def _graph(edges: list[tuple[str, str]], layers=("ui", "svc", "core")) -> Graph:
    """A module import graph: each layer holds one module `pkg.<layer>.m`."""
    g = Graph(target="pkg")
    mods = {}
    for layer in layers:
        mid = f"pkg.{layer}.m"
        g.add_node(Node(id=mid, kind="module", extras={"root": "core"}))
        mods[layer] = mid
    for a, b in edges:
        g.add_edge(Edge(type="imports", source=mods[a], target=mods[b]))
    return g


def _q(edges, **kw) -> Query:
    return Query(_graph(edges, **kw))


# -- parsing ----------------------------------------------------------------

def test_parse_contract_shapes():
    c = parse_contract({
        "layers": ["ui", "core"],
        "independent": [["a", "b"], ["oops"]],   # <2 members dropped
        "forbidden": [{"from": "core", "to": "ui"}, {"bad": 1}],  # malformed dropped
        "no_cycles": True,
    })
    assert c.layers == ("ui", "core")
    assert c.independent == (("a", "b"),)
    assert c.forbidden == (("core", "ui"),)
    assert c.no_cycles and not c.exhaustive


def test_empty_contract_is_noop():
    assert ArchitectureContract().is_empty()
    assert check_contract(_q([("ui", "core")]), ArchitectureContract()) == []


def test_load_contract_absent_and_present(tmp_path):
    absent = load_contract(tmp_path)
    assert absent.is_empty() and absent.error is None   # absent is an answer, not a failure
    (tmp_path / "codemap.toml").write_text(
        '[architecture]\nlayers = ["ui", "core"]\nno_cycles = true\n', encoding="utf-8")
    c = load_contract(tmp_path)
    assert c.layers == ("ui", "core") and c.no_cycles and c.error is None


def test_malformed_toml_is_empty_but_says_so(tmp_path):
    """R1-C27: still tolerant (no raise, no rules) — but no longer silent."""
    (tmp_path / "codemap.toml").write_text("[architecture\nlayers = broken", encoding="utf-8")
    c = load_contract(tmp_path)
    assert c.is_empty()                     # unchanged: nothing to enforce
    assert c.error and "codemap.toml" in c.error
    assert "not valid TOML" in c.error


# -- rules ------------------------------------------------------------------

def test_layered_up_import_violates():
    # core imports ui — up the stack ui>svc>core → violation
    v = check_contract(_q([("core", "ui")]), parse_contract({"layers": ["ui", "svc", "core"]}))
    assert len(v) == 1 and v[0].rule == "layered"
    assert v[0].edges == (("pkg.core.m", "pkg.ui.m"),)


def test_layered_down_import_clean():
    # ui imports core — down the stack → allowed
    assert check_contract(_q([("ui", "core")]),
                          parse_contract({"layers": ["ui", "svc", "core"]})) == []


def test_independent_violation():
    v = check_contract(_q([("ui", "svc")]),
                       parse_contract({"independent": [["ui", "svc"]]}))
    assert len(v) == 1 and v[0].rule == "independent"


def test_forbidden_violation_and_direction():
    q = _q([("core", "ui")])
    assert check_contract(q, parse_contract({"forbidden": [{"from": "core", "to": "ui"}]}))
    # opposite direction is not banned
    assert check_contract(q, parse_contract({"forbidden": [{"from": "ui", "to": "core"}]})) == []


def test_no_cycles_violation():
    v = check_contract(_q([("ui", "core"), ("core", "ui")]),
                       parse_contract({"no_cycles": True}))
    assert len(v) == 1 and v[0].rule == "no_cycles" and v[0].modules


def test_exhaustive_flags_undeclared_layer():
    # graph has a 'ml' layer the contract never declares
    q = _q([("ui", "core")], layers=("ui", "core", "ml"))
    v = check_contract(q, parse_contract({"layers": ["ui", "core"], "exhaustive": True}))
    assert len(v) == 1 and v[0].rule == "exhaustive" and "ml" in v[0].modules


def test_contract_ahead_of_code_is_inert():
    # a layer named in the contract but absent from the graph breaks nothing
    assert check_contract(_q([("ui", "core")]),
                          parse_contract({"layers": ["ui", "svc", "core", "future"]})) == []


# -- rendering --------------------------------------------------------------

def test_render_clean_and_broken():
    q = _q([("ui", "core")])
    clean = render_check(q, parse_contract({"layers": ["ui", "core"]}),
                         check_contract(q, parse_contract({"layers": ["ui", "core"]})))
    assert "✅" in clean and "satisfied" in clean

    qb = _q([("core", "ui")])
    con = parse_contract({"layers": ["ui", "core"]})
    broken = render_check(qb, con, check_contract(qb, con))
    assert "❌" in broken and "layered" in broken and "pkg.core.m" in broken


# -- CLI gate ---------------------------------------------------------------

def _write(tmp_path, graph, toml):
    store.save(graph, str(tmp_path / "g.json"))
    (tmp_path / "codemap.toml").write_text(toml, encoding="utf-8")


def test_cli_check_exit_2_on_violation(tmp_path, capsys):
    _write(tmp_path, _graph([("core", "ui")]),
           '[architecture]\nlayers = ["ui", "svc", "core"]\n')
    rc = main(["check", "--graph", str(tmp_path / "g.json"), "--root", str(tmp_path)])
    assert rc == 2
    assert "❌" in capsys.readouterr().out


def test_cli_check_exit_0_on_clean(tmp_path, capsys):
    _write(tmp_path, _graph([("ui", "core")]),
           '[architecture]\nlayers = ["ui", "svc", "core"]\n')
    rc = main(["check", "--graph", str(tmp_path / "g.json"), "--root", str(tmp_path)])
    assert rc == 0
    assert "✅" in capsys.readouterr().out


def test_cli_check_no_contract_is_noop_success(tmp_path):
    store.save(_graph([("ui", "core")]), str(tmp_path / "g.json"))
    rc = main(["check", "--graph", str(tmp_path / "g.json"), "--root", str(tmp_path)])
    assert rc == 0


def test_cli_require_contract_fails_without_one(tmp_path):
    store.save(_graph([("ui", "core")]), str(tmp_path / "g.json"))
    with pytest.raises(SystemExit):
        main(["check", "--graph", str(tmp_path / "g.json"),
              "--root", str(tmp_path), "--require-contract"])


# -- serve op ---------------------------------------------------------------

def test_serve_check_op(tmp_path):
    _write(tmp_path, _graph([("core", "ui")]),
           '[architecture]\nforbidden = [{ from = "core", to = "ui" }]\n')
    env = Session(store.load(str(tmp_path / "g.json"))).handle(
        {"op": "check", "args": {"root": str(tmp_path)}})
    assert env["ok"]
    result = env["result"]
    assert result["ok"] is False
    assert result["violations"][0]["rule"] == "forbidden"
    assert result["violations"][0]["edges"] == [["pkg.core.m", "pkg.ui.m"]]
