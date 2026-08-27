"""R1-C27 — a config file the tool could not read is not a config file the user did not write.

The defect: three loaders collapsed `OSError`, `ValueError` and `ModuleNotFoundError` into one
silent empty result, and each caller rendered that as *the user configured nothing*. Since
`tomllib.TOMLDecodeError` subclasses `ValueError`, deleting one `]` from a contract that
reported 14 violations turned `codemap check` into "nothing to enforce", **exit 0** — a typo
painting a CI gate green.

What these tests pin, in both directions:

- the **tolerance is unchanged** — nothing raises, no rules are invented, an absent file is
  still a perfectly quiet answer (over-firing here would be its own dishonesty);
- the **silence is gone** — the reason survives to every surface that renders a conclusion,
  and the gate's exit code stops saying "proceed".

Seventh application of the rule that `unknown` is never rendered as `none` (#1 `risk:"none"`,
#3, #5, #7, R1-C23, R1-C26) — and the first aimed at codemap's own configuration rather than
at a target's source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap import store
from codemap.arch import check_contract, load_contract
from codemap.cli import main
from codemap.integrations.gate import load_config
from codemap.model import Edge, Graph, Node
from codemap.query import Query
from codemap.serve.audit import load_dead_code_whitelist, render_dead_code
from codemap.serve.check import build_check, render_check
from codemap.serve.session import Session
from codemap.tomlio import read_toml

BROKEN = '[architecture]\nlayers = ["ui", "svc", "core"\n'      # one `]` short
VALID = '[architecture]\nlayers = ["ui", "svc", "core"]\n'


def _graph(edges: list[tuple[str, str]]) -> Graph:
    g = Graph(target="pkg")
    mods = {}
    for layer in ("ui", "svc", "core"):
        mid = f"pkg.{layer}.m"
        g.add_node(Node(id=mid, kind="module", extras={"root": "core"}))
        mods[layer] = mid
    for a, b in edges:
        g.add_edge(Edge(type="imports", source=mods[a], target=mods[b]))
    return g


def _write(tmp_path: Path, toml: str | None, edges=(("core", "ui"),)) -> Path:
    """A graph that *violates* `VALID`, plus whatever codemap.toml is under test."""
    store.save(_graph(list(edges)), str(tmp_path / "g.json"))
    if toml is not None:
        (tmp_path / "codemap.toml").write_text(toml, encoding="utf-8")
    return tmp_path / "g.json"


# -- the shared reader -------------------------------------------------------

def test_read_toml_absent_is_not_an_error(tmp_path):
    assert read_toml(tmp_path / "codemap.toml") == ({}, None)


def test_read_toml_valid(tmp_path):
    p = tmp_path / "codemap.toml"
    p.write_text('[a]\nb = 1\n', encoding="utf-8")
    data, error = read_toml(p)
    assert data == {"a": {"b": 1}} and error is None


def test_read_toml_malformed_names_the_file_and_the_position(tmp_path):
    p = tmp_path / "codemap.toml"
    p.write_text(BROKEN, encoding="utf-8")
    data, error = read_toml(p)
    assert data == {}
    assert "codemap.toml" in error and "not valid TOML" in error


def test_read_toml_unreadable_is_reported_not_swallowed(tmp_path):
    """A directory where a file should be — the `OSError` branch, kept distinct."""
    (tmp_path / "codemap.toml").mkdir()
    data, error = read_toml(tmp_path / "codemap.toml")
    assert data == {} and error is None   # not a file at all → absent, still quiet

    p = tmp_path / "other.toml"
    p.write_bytes(b"\xff\xfe\x00broken")  # not UTF-8
    data, error = read_toml(p)
    assert data == {} and error and "cannot read other.toml" in error


def test_read_toml_never_raises(tmp_path):
    """The whole point of the tolerance: a bad file must not wedge a plain build."""
    for content in (b"\xff\xfe", b"= = =", b"[unclosed", b""):
        p = tmp_path / "x.toml"
        p.write_bytes(content)
        read_toml(p)          # no exception is the assertion


# -- the gate: exit codes ----------------------------------------------------

def test_cli_check_exits_2_on_a_contract_it_could_not_read(tmp_path, capsys):
    """The headline regression: this used to be exit 0."""
    g = _write(tmp_path, BROKEN)
    rc = main(["check", "--graph", str(g), "--root", str(tmp_path)])
    assert rc == 2
    out = capsys.readouterr().out
    assert "not valid TOML" in out
    assert "nothing to enforce" not in out       # the exact old lie


def test_cli_check_still_exits_0_when_there_is_genuinely_no_contract(tmp_path, capsys):
    """The other direction — the fix must not turn absence into a failure."""
    g = _write(tmp_path, None)
    rc = main(["check", "--graph", str(g), "--root", str(tmp_path)])
    assert rc == 0
    assert "nothing to enforce" in capsys.readouterr().out


def test_cli_check_unchanged_on_a_readable_contract(tmp_path, capsys):
    """Same file, one character restored → a real verdict about the graph again."""
    g = _write(tmp_path, VALID)
    rc = main(["check", "--graph", str(g), "--root", str(tmp_path)])
    assert rc == 2
    assert "rule(s) broken" in capsys.readouterr().out


def test_require_contract_is_not_satisfied_by_an_unreadable_one(tmp_path, capsys):
    """`--require-contract` asks "is a contract in force?" — an unparsed one is not."""
    g = _write(tmp_path, BROKEN)
    rc = main(["check", "--graph", str(g), "--root", str(tmp_path), "--require-contract"])
    assert rc == 2
    assert "not valid TOML" in capsys.readouterr().out


# -- the JSON surface --------------------------------------------------------

def test_build_check_is_not_ok_when_the_contract_was_not_read(tmp_path):
    """CLI-AI-first: the machine-readable path carried the same lie as the markdown."""
    (tmp_path / "codemap.toml").write_text(BROKEN, encoding="utf-8")
    q = Query(_graph([("core", "ui")]))
    contract = load_contract(tmp_path)
    payload = build_check(q, contract, check_contract(q, contract))
    assert payload["ok"] is False
    assert payload["contract_error"] and "not valid TOML" in payload["contract_error"]
    assert payload["violations"] == []      # honestly empty: no rule ever ran


def test_build_check_ok_stays_true_on_a_clean_run(tmp_path):
    (tmp_path / "codemap.toml").write_text(VALID, encoding="utf-8")
    q = Query(_graph([("ui", "core")]))     # obeys the layering
    contract = load_contract(tmp_path)
    payload = build_check(q, contract, check_contract(q, contract))
    assert payload["ok"] is True and payload["contract_error"] is None


def test_serve_check_op_reports_the_read_failure(tmp_path):
    g = _write(tmp_path, BROKEN)
    env = Session(store.load(str(g))).handle(
        {"op": "check", "args": {"root": str(tmp_path)}})
    assert env["ok"]                        # the op itself succeeded…
    assert env["result"]["ok"] is False     # …and answered "do not proceed"
    assert "not valid TOML" in env["result"]["contract_error"]


def test_render_check_does_not_claim_an_absent_contract(tmp_path):
    (tmp_path / "codemap.toml").write_text(BROKEN, encoding="utf-8")
    out = render_check(Query(_graph([("core", "ui")])), load_contract(tmp_path), [])
    assert "Contract not read" in out and "nothing was enforced" in out
    assert "No `[architecture]` contract found" not in out


# -- the other two loaders ---------------------------------------------------

def test_whitelist_says_nothing_was_suppressed(tmp_path):
    (tmp_path / "codemap.toml").write_text("[dead_code\nwhitelist = [", encoding="utf-8")
    items, error = load_dead_code_whitelist(str(tmp_path))
    assert items == () and error and "not valid TOML" in error

    out = render_dead_code(Query(_graph([("ui", "core")])), whitelist=items,
                           whitelist_error=error)
    assert "Whitelist not read" in out and "nothing is suppressed" in out


def test_dead_code_report_is_quiet_without_a_whitelist_problem(tmp_path):
    """No warning when there is nothing to warn about — the over-firing check."""
    out = render_dead_code(Query(_graph([("ui", "core")])))
    assert "Whitelist not read" not in out


def test_integration_config_keeps_the_opt_in_invariant_and_the_reason(tmp_path):
    (tmp_path / "codemap.toml").write_text("[integrations\nenabled = [", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.enabled == frozenset()       # a broken file still enables nothing
    assert cfg.is_enabled("gitnexus") is False
    assert cfg.error and "not valid TOML" in cfg.error


def test_route_names_the_read_failure_instead_of_advising_the_obvious(tmp_path, capsys):
    """Telling the user to enable a tool in codemap.toml is bad advice when it has a typo."""
    (tmp_path / "codemap.toml").write_text("[integrations\nenabled = [", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["route", "semantic-search", "x", "--root", str(tmp_path)])
    assert "not valid TOML" in str(exc.value)
