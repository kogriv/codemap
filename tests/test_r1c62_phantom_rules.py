"""R1-C62 — a rule with nothing to cover was counted as enforced.

Measured on a two-layer package (`api`, `core`) with a contract in which every name is
fictional:

    layers = ["frontend", "middleware", "persistence"]
    independent = [["frontend", "middleware"]]
    forbidden = [{ from = "middleware", to = "persistence" }]

    ✅ Contract satisfied. Rules enforced: layered (3), independent (1), forbidden (1), no_cycles.
    exit 0

Six rules reported as enforced; five of them cannot fire. The inertness itself is **not** the
defect — it is a documented decision (`codemap/arch.py`: rules naming an absent layer are
inert, so a contract can be written ahead of the code), and breaking it would turn a
legitimate practice red on other people's trees. The defect is the report: "Rules enforced:
layered (3)" is a claim of fact and it is false, and the green tick reads as coverage. R1-C28's
family — a rule covering nothing is partiality, and partiality must be declared.

The question came from outside: a third-party repo about requirements that stop being true
(`research/05_curated_sources.md` §4a). Design: `docs/design/vacuous_contract_rules.md`.
"""

from __future__ import annotations

import pytest

from codemap.arch import applicability, check_contract, parse_contract
from codemap.extract import extract
from codemap.query import Query
from codemap.serve.check import build_check, render_check

PHANTOM = {
    "layers": ["frontend", "middleware", "persistence"],
    "independent": [["frontend", "middleware"]],
    "forbidden": [{"from": "middleware", "to": "persistence"}],
    "no_cycles": True,
}
HEALTHY = {
    "layers": ["api", "core"],
    "forbidden": [{"from": "core", "to": "api"}],
    "no_cycles": True,
    "exhaustive": True,
}


@pytest.fixture(scope="module")
def two_layers(tmp_path_factory):
    """`api` imports `core`; nothing else. Layers present: exactly `api` and `core`."""
    pkg = tmp_path_factory.mktemp("r1c62") / "pkg"
    (pkg / "core").mkdir(parents=True)
    (pkg / "api").mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "core" / "__init__.py").write_text("")
    (pkg / "core" / "util.py").write_text("def helper():\n    return 1\n")
    (pkg / "api" / "__init__.py").write_text("")
    (pkg / "api" / "route.py").write_text(
        "from pkg.core.util import helper\n\n\ndef handler():\n    return helper()\n")
    return Query(extract(str(pkg)))


def _render(query, section):
    contract = parse_contract(section)
    return contract, render_check(query, contract, check_contract(query, contract))


# -- D1: applicability is counted, and disclosed only when it differs --------------------

def test_a_phantom_rule_is_not_counted_as_applicable(two_layers):
    _, md = _render(two_layers, PHANTOM)
    assert "layered (3 declared, 0 applicable)" in md
    assert "independent (1 declared, 0 applicable)" in md
    assert "forbidden (1 declared, 0 applicable)" in md


def test_the_absent_names_are_named(two_layers):
    _, md = _render(two_layers, PHANTOM)
    for name in ("frontend", "middleware", "persistence"):
        assert f"`{name}`" in md
    assert "could not apply" in md
    assert "no_phantom_rules = true" in md, "the note points at the opt-in"


def test_a_healthy_contract_does_not_move_a_byte(two_layers):
    """The control, and the reason the second half is conditional: this text is diffed by
    consumers, so a green run on a sound contract must read exactly as before."""
    _, md = _render(two_layers, HEALTHY)
    assert "Rules enforced: layered (2), forbidden (1), no_cycles, exhaustive." in md
    assert "applicable" not in md
    assert "absent from the graph" not in md


def test_applicability_is_precise_about_partial_names(two_layers):
    """One end present is not enough: `independent` needs two members, `forbidden` two ends."""
    a = applicability(two_layers, parse_contract({
        "layers": ["api", "core", "ghost"],
        "independent": [["api", "ghost"], ["api", "core"]],
        "forbidden": [{"from": "api", "to": "ghost"}, {"from": "api", "to": "core"}],
    }))
    assert a["layers"] == {"declared": 3, "applicable": 2}
    assert a["independent"] == {"declared": 2, "applicable": 1}
    assert a["forbidden"] == {"declared": 2, "applicable": 1}
    assert a["absent_names"] == ("ghost",)


# -- D2: turning a phantom into a failure is opt-in --------------------------------------

def test_the_opt_in_makes_it_a_violation(two_layers):
    contract = parse_contract({**PHANTOM, "no_phantom_rules": True})
    violations = check_contract(two_layers, contract)
    assert [v.rule for v in violations] == ["no_phantom_rules"]
    assert violations[0].modules == ("frontend", "middleware", "persistence")


def test_the_opt_in_is_silent_on_a_sound_contract(two_layers):
    """Positive control: the rule must not fire where every name exists."""
    contract = parse_contract({**HEALTHY, "no_phantom_rules": True})
    assert check_contract(two_layers, contract) == []


def test_the_note_is_not_repeated_when_the_rule_is_enforced(two_layers):
    _, md = _render(two_layers, {**PHANTOM, "no_phantom_rules": True})
    assert "`no_phantom_rules`" in md, "the violation says it"
    assert "could not apply; they are counted" not in md, "and the note does not say it again"


def test_off_by_default(two_layers):
    """A contract that does not ask for it keeps exiting 0 on phantoms — the documented
    write-ahead use must not become red on an upgrade."""
    contract = parse_contract(PHANTOM)
    assert contract.no_phantom_rules is False
    assert check_contract(two_layers, contract) == []


# -- D3: the structured answer carries it too --------------------------------------------

def test_the_payload_carries_applicability(two_layers):
    contract = parse_contract(PHANTOM)
    payload = build_check(two_layers, contract, check_contract(two_layers, contract))
    a = payload["applicability"]
    assert a["layers"] == {"declared": 3, "applicable": 0}
    assert a["absent_names"] == ["frontend", "middleware", "persistence"]
    assert payload["ok"] is True, "disclosure is not a failure by itself"


def test_the_payload_declares_it_on_a_sound_contract_too(two_layers):
    """R1-C28: a field that appears only when there is something to say cannot be read —
    a machine consumer could not tell "nothing phantom" from "this build does not report it"."""
    contract = parse_contract(HEALTHY)
    a = build_check(two_layers, contract, check_contract(two_layers, contract))["applicability"]
    assert a is not None and a["absent_names"] == []
    assert a["layers"] == {"declared": 2, "applicable": 2}


# -- the semantics did not change --------------------------------------------------------

def test_a_real_violation_still_fires_next_to_phantoms(two_layers):
    """Phantom names must not shadow a rule that *can* fire: `core` importing `api` is
    still caught while three fictional layers sit in the same contract."""
    contract = parse_contract({
        "layers": ["core", "api", "ghost"],          # deliberately inverted: api → core is "up"
        "forbidden": [{"from": "ghost", "to": "api"}],
        "no_cycles": True,
    })
    violations = check_contract(two_layers, contract)
    assert [v.rule for v in violations] == ["layered"]
    assert violations[0].edges == (("pkg.api.route", "pkg.core.util"),)
