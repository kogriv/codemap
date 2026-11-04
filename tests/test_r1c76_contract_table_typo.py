"""R1-C76 — a misspelled `[architecture]` table is refused, not read as "no contract".

Found by asking codemap the question its import-linter card asked of import-linter (zero contracts pass).
Design `docs/design/contract_table_typo.md`.
"""

from __future__ import annotations

import pytest

from codemap import arch
from codemap.cli import main
from codemap.extract import extract
from codemap.query import Query
from codemap.serve.check import build_check

RULE = 'forbidden = [{from="core", to="analysis"}]\n'


@pytest.fixture(scope="module")
def pkg(tmp_path_factory):
    root = tmp_path_factory.mktemp("r1c76") / "tpkg"
    for d in (root, root / "core", root / "analysis"):
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").write_text("")
    (root / "analysis" / "b.py").write_text("X = 1\n")
    (root / "core" / "a.py").write_text("from tpkg.analysis import b\n")
    return root


def _check(tmp_path, pkg, toml, capsys, *extra) -> tuple[int, str]:
    if toml is not None:
        (tmp_path / "codemap.toml").write_text(toml)
    rc = main(["check", "--build", str(pkg), "--root", str(tmp_path), *extra])
    return rc, capsys.readouterr().out


@pytest.mark.parametrize("toml, name", [
    (f"[architectur]\n{RULE}", "architectur"),
    (f"[Architecture]\n{RULE}", "Architecture"),
    (f"[archtecture]\n{RULE}", "archtecture"),
    (f"[architecture]\nno_cycles = true\n\n[architectur]\n{RULE}", "architectur"),
], ids=["A1", "A2-case", "A2-letter", "A3-both"])
def test_a_near_miss_table_is_refused(tmp_path, pkg, capsys, toml, name):
    rc, out = _check(tmp_path, pkg, toml, capsys)
    assert rc == 2, out
    assert f"`[{name}]`" in out and "`[architecture]`" in out


def test_mcp_check_carries_the_refusal(tmp_path, pkg):
    (tmp_path / "codemap.toml").write_text(f"[architectur]\n{RULE}")
    c = arch.load_contract(tmp_path)
    q = Query(extract(str(pkg)))
    payload = build_check(q, c, arch.check_contract(q, c))
    assert payload["ok"] is False
    assert "`[architectur]`" in payload["contract_error"]


def test_what_was_valid_or_absent_answers_as_before(tmp_path, pkg, capsys):
    rc, out = _check(tmp_path, pkg, f"[architecture]\n{RULE}", capsys)
    assert rc == 2 and "1 rule(s) broken" in out                      # a real violation, as before
    rc, out = _check(tmp_path, pkg, '[integrations]\nenabled = []\n', capsys)
    assert rc == 0 and "No `[architecture]` contract found" in out    # unrelated table: still absent
    with pytest.raises(SystemExit, match="no \\[architecture\\] contract found"):
        _check(tmp_path, pkg, None, capsys, "--require-contract")     # still opt-in for absence (exit 1)
    (tmp_path / "codemap.toml").unlink()
    rc, out = _check(tmp_path, pkg, None, capsys)
    assert rc == 0 and "No `[architecture]` contract found" in out    # no file at all
