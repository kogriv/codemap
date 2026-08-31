"""R1-C35 — `check` says which file it looked in, and that a miss exits 0.

From the lab, reported as a lost minute rather than a bug: they reached for
`check --config codemap.toml`, there is no such flag, and the message they got back was

    No `[architecture]` contract found in codemap.toml — nothing to enforce.

which is true, unactionable, and identical whether the project has no contract or the
command was run one directory away from it. Their own framing is why it belongs to this
line of work rather than to the docs alone:

    дефолт (отсутствие контракта = тихий успех) считаю правильным, но именно поэтому
    `--require-contract` стоит упоминать рядом с примером: без него легко получить
    зелёное на пустом месте — тот же класс, из-за которого началась вся линия.

The default is right — a project without a contract must not fail — so the fix is not the
exit code. It is that the *only* run whose output nobody reads is the green one, and this
particular green says "enforced nothing". So the line now names the absolute path it
looked in, says out loud that it exits 0, and names the flag that turns it into a failure.

`--require-contract` already existed; this is about the run where you did not know you
needed it.
"""

from __future__ import annotations

import json

import pytest

from codemap.arch import check_contract, load_contract
from codemap.query import Query
from codemap.serve.check import build_check, render_check
from codemap.extract import extract

CONTRACT = """
[architecture]
layers = ["api", "core"]
no_cycles = true
"""


@pytest.fixture(scope="module")
def graph(tmp_path_factory):
    pkg = tmp_path_factory.mktemp("src") / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "core.py").write_text("def helper():\n    return 1\n")
    (pkg / "api.py").write_text("from pkg.core import helper\n\n\ndef run():\n    return helper()\n")
    return extract(str(pkg))


def _run(graph, root):
    contract = load_contract(root)
    violations = check_contract(Query(graph), contract)
    return contract, render_check(Query(graph), contract, violations), \
        build_check(Query(graph), contract, violations)


def test_a_missing_contract_names_the_file_it_looked_for(graph, tmp_path):
    _, text, _ = _run(graph, tmp_path)
    assert str(tmp_path / "codemap.toml") in text


def test_the_path_is_absolute_so_it_is_readable_from_any_cwd(graph, tmp_path):
    contract, _, payload = _run(graph, tmp_path)
    assert contract.path == str((tmp_path / "codemap.toml").resolve())
    assert payload["contract_path"] == contract.path


def test_a_missing_contract_says_it_exits_zero(graph, tmp_path):
    """The run nobody reads is the green one, and this green enforced nothing."""
    _, text, payload = _run(graph, tmp_path)
    assert "exits 0" in text
    assert "--require-contract" in text
    assert payload["ok"] is True and payload["contract_empty"] is True


def test_a_present_contract_still_reports_what_it_enforced(graph, tmp_path):
    (tmp_path / "codemap.toml").write_text(CONTRACT)
    contract, text, payload = _run(graph, tmp_path)
    assert not contract.is_empty()
    assert "Contract satisfied" in text and "no_cycles" in text
    assert payload["contract_empty"] is False
    # R1-C30-f2 stays: a satisfied gate still declares what it did not judge.
    assert payload["scope"]


def test_an_unparsable_contract_names_the_file_to_fix(graph, tmp_path):
    (tmp_path / "codemap.toml").write_text("[architecture\nlayers = [")
    contract, text, payload = _run(graph, tmp_path)
    assert contract.error and contract.path == str((tmp_path / "codemap.toml").resolve())
    assert str(tmp_path / "codemap.toml") in text
    # R1-C27 unchanged: unreadable is a failure, not an absent contract.
    assert payload["ok"] is False


def test_the_path_travels_in_the_json_surface(graph, tmp_path):
    _, _, payload = _run(graph, tmp_path)
    json.dumps(payload)  # must stay serialisable
    assert set(("contract_empty", "contract_error", "contract_path")) <= set(payload)
