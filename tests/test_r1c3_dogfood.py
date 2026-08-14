"""R1-C3 dogfood — codemap's own [architecture] contract must stay green.

codemap.toml declares codemap's real layer order; if a future edit makes a layer
import up the stack or introduces an import cycle, this test fails with the
offending edges. The contract enforces the architecture the design assumes.
"""

from __future__ import annotations

from pathlib import Path

from codemap.arch import check_contract, load_contract
from codemap.extract import extract
from codemap.query import Query

_ROOT = Path(__file__).resolve().parent.parent


def test_codemap_satisfies_its_own_architecture_contract():
    contract = load_contract(_ROOT)
    assert not contract.is_empty(), "codemap.toml [architecture] contract went missing"
    q = Query(extract(str(_ROOT / "codemap"), deep=False))  # imports only — fast tier
    violations = check_contract(q, contract)
    assert violations == [], "\n".join(
        f"{v.rule}: {v.summary} :: {v.edges or v.modules}" for v in violations)
