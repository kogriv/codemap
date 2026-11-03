"""R1-C69 — a contract the gate cannot fully read is refused, not partly enforced.

From the probe in gap `contract_silent_passes_2026-11-03` (rows P1–P2d), modelled on grafema's
predicate typo that passes (upstream #484). Design `docs/design/contract_validation.md`.

Pinned:
1. Each row V1–V4: exit 2, and the message names the key (and the item index).
2. A valid rule beside an invalid one is not enforced either (D2, V1b). That was the partial pass.
3. MCP returns `ok: false` with `contract_error` (V5).
4. Valid contracts, absent names and an absent contract answer as before (V6, D3).
5. Mutation: drop the unknown-key check or the type check, and a test goes red (V7).
"""

from __future__ import annotations

from unittest import mock

import pytest

from codemap import arch
from codemap.cli import main
from codemap.extract import extract
from codemap.query import Query
from codemap.serve.check import build_check


@pytest.fixture(scope="module")
def pkg(tmp_path_factory):
    root = tmp_path_factory.mktemp("r1c69") / "vpkg"
    for d in (root, root / "core", root / "analysis"):
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").write_text("")
    (root / "analysis" / "b.py").write_text("X = 1\n")
    (root / "core" / "a.py").write_text("from vpkg.analysis import b\n")
    return root


def _check(tmp_path, pkg, toml: str, capsys) -> tuple[int, str]:
    (tmp_path / "codemap.toml").write_text(toml)
    rc = main(["check", "--build", str(pkg), "--root", str(tmp_path)])
    return rc, capsys.readouterr().out


@pytest.mark.parametrize("toml, needles", [
    ('[architecture]\nforbiden = [{from="core", to="analysis"}]\n', ["`forbiden`", "did you mean `forbidden`"]),
    ('[architecture]\nforbiden = [{from="core", to="analysis"}]\nno_cycles = true\n', ["`forbiden`"]),
    ('[architecture]\nforbidden = [{from="core", too="analysis"}]\n', ["`forbidden[0]`", "`too`", "missing `to`"]),
    ('[architecture]\nindependent = [["core"]]\n', ["`independent[0]`", "at least 2"]),
    ('[architecture]\nno_cycles = "false"\n', ["`no_cycles`", "true or false"]),
    ('[architecture]\nlayers = "core"\n', ["`layers`", "list of strings"]),
    ('architecture = 1\n', ["must be a table"]),
    ('[architecture]\nforbiden = []\nno_cycles = "false"\n', ["`forbiden`", "`no_cycles`"]),
], ids=["V1", "V1b", "V2", "V2b", "V2c", "V2d", "V3", "V4"])
def test_an_invalid_contract_exits_2_and_names_every_problem(tmp_path, pkg, capsys, toml, needles):
    rc, out = _check(tmp_path, pkg, toml, capsys)
    assert rc == 2
    assert "nothing was enforced" in out
    for needle in needles:
        assert needle in out, (needle, out)


def test_mcp_check_says_not_ok_and_why(tmp_path):
    """V5 — the JSON surface carries the same refusal."""
    q = Query(extract(str(_mini(tmp_path))))
    c = arch.parse_contract({"forbiden": [{"from": "core", "to": "analysis"}]})
    payload = build_check(q, c, arch.check_contract(q, c))
    assert payload["ok"] is False
    assert "`forbiden`" in payload["contract_error"]


def _mini(tmp_path):
    root = tmp_path / "mpkg"
    (root / "core").mkdir(parents=True)
    for d in (root, root / "core"):
        (d / "__init__.py").write_text("")
    return root


def test_valid_contracts_and_absent_names_answer_as_before(tmp_path, pkg, capsys):
    """V6 / D3: a valid contract is enforced; an absent name is reported, not refused."""
    rc, out = _check(tmp_path, pkg, '[architecture]\nforbidden = [{from="core", to="analysis"}]\n', capsys)
    assert rc == 2 and "`vpkg.core.a` → `vpkg.analysis.b`" in out
    rc, out = _check(tmp_path, pkg, '[architecture]\nforbidden = [{from="core", to="analysys"}]\n', capsys)
    assert rc == 0 and "1 declared, 0 applicable" in out


def test_an_empty_list_is_still_an_empty_rule():
    c = arch.parse_contract({"forbidden": [], "layers": []})
    assert c.error is None and c.is_empty()


# -- V7 mutation ----------------------------------------------------------------------

def test_mutation_without_the_unknown_key_check_the_typo_passes(tmp_path, pkg, capsys):
    toml = '[architecture]\nforbiden = [{from="core", to="analysis"}]\n'
    with mock.patch.object(arch, "_KNOWN_KEYS", ("forbiden",) + arch._KNOWN_KEYS):
        rc, _ = _check(tmp_path, pkg, toml, capsys)
    assert rc == 0, "without the check, the typo is an absent contract again"
    assert _check(tmp_path, pkg, toml, capsys)[0] == 2


def test_mutation_without_the_type_check_false_switches_the_rule_on():
    with mock.patch.object(arch, "_FLAGS", ()):
        c = arch.parse_contract({"no_cycles": "false"})
    assert c.no_cycles is True, "bool('false') — the inverted reading"
    assert arch.parse_contract({"no_cycles": "false"}).error
