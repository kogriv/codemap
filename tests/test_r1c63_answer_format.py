"""R1-C63 — the artifact is versioned; the answer, which is what consumers diff, was not.

`SCHEMA_VERSION` versions `graph.json`. In 0.0.20 the graph stayed byte-identical and the gate's
output and the architecture report changed completely — a cycle answer became a tangle. On a text
diff that is indistinguishable from the #20 defect, where the rendered text moved *between runs of
one version* because of hash order, and nobody had decided anything. One was a deliberate change
of shape, the other a bug; the only thing that told the consumer apart was a message written by
hand.

So the answer gets its own version, independent of the schema: bumped when the structure a
consumer sees changes, not when prose is edited. Two surfaces, one per consumer — a one-line
trailer on CLI markdown (what a text diff shows) and `answer_format` in the serve/MCP envelope
(what a machine reads).

The pinned hash below is the other half: it does not know whether a text change is structural —
that judgement cannot be automated — it only refuses to let one pass **silently**. Design:
`docs/design/answer_format_version.md`.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from codemap.arch import check_contract, parse_contract
from codemap.cli import main
from codemap.extract import extract
from codemap.model import ANSWER_FORMAT, SCHEMA_VERSION
from codemap.query import Query
from codemap.serve.api_surface import render_api_surface
from codemap.serve.architecture import render_architecture
from codemap.serve.audit import render_behavior, render_dead_code, render_dependencies
from codemap.serve.check import render_check
from codemap.serve.session import Session

# Bump together with ANSWER_FORMAT when a change of answer *structure* is intended.
# The fixture is owned by this test on purpose: pinned against the live dogfood tree the hash
# would move whenever somebody edits that tree, and the test would be measuring the target
# instead of the tool (R1-C25 — the mistake `tests/frozen.py` exists to prevent).
# Re-pinned without a bump by R1-C60 (2026-10-14): one more item in dead-code's existing
# blind-spot line — wording inside an existing note, not a change of structure.
# Re-pinned with a bump to 3 (2026-11-03, R1-C69/R1-C70): the refusal of an invalid contract and
# the three states of the `check --graph` currency line join the pinned surfaces.
# Re-pinned with a bump to 4 (2026-11-03, R1-C74): `report behavior` names its scopes.
RENDERED_SHA = "32a160c89e31af252873c0703d0e903397c6d470013fad5889b9194e2a3a2eb8"

FILES = {
    "__init__.py": "",
    "core/__init__.py": "",
    "core/util.py": "def helper():\n    return 1\n\n\ndef unused():\n    return 2\n",
    "api/__init__.py": "",
    "api/route.py": ("from pkg.core.util import helper\n\n\n"
                     "class Handler:\n"
                     "    def run(self, n: int) -> int:\n"
                     "        return helper() + n\n"),
}
CONTRACT = {"layers": ["api", "core"], "no_cycles": True, "exhaustive": True}


@pytest.fixture(scope="module")
def pkg(tmp_path_factory):
    root = tmp_path_factory.mktemp("r1c63") / "pkg"
    for rel, body in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return Query(extract(str(root)))


def _rendered(query) -> str:
    """Every markdown surface a consumer reads, concatenated in a fixed order."""
    contract = parse_contract(CONTRACT)
    return "\n@@\n".join([
        render_check(query, contract, check_contract(query, contract)),
        # format 3 (R1-C69, R1-C70): the refusal of an invalid contract, and the currency line
        # of `check --graph` in each of its three states — blocks the pin did not cover before.
        render_check(query, parse_contract({"forbiden": [], "no_cycles": "false"}), []),
        render_check(query, contract, [], currency={"status": "current", "scope_id": "sha256:" + "0" * 64}),
        render_check(query, contract, [], currency={"status": "behind", "recorded": "sha256:a",
                                                    "current": "sha256:b", "added": 1, "removed": 0,
                                                    "changed": 2}),
        render_check(query, contract, [], currency={"status": "unknown",
                                                    "reason": "no build recipe beside the graph"}),
        render_architecture(query),
        render_api_surface(query.graph),
        render_dead_code(query),
        render_dependencies(query),
        render_behavior(query),
    ])


# -- the version itself ------------------------------------------------------------------

def test_the_answer_format_is_its_own_version(pkg):
    assert isinstance(ANSWER_FORMAT, int) and ANSWER_FORMAT >= 1
    assert ANSWER_FORMAT != SCHEMA_VERSION, "two different facts, two different fields"


def test_the_envelope_carries_it_on_every_answer(pkg):
    """Machine-readable half, and always present: a field that appears only when something
    changed cannot be read (R1-C28)."""
    session = Session(pkg.graph)
    for op, args in (("stats", {}), ("architecture", {}), ("query", {"name": "helper"})):
        env = session.handle({"op": op, "args": args})
        assert env["answer_format"] == ANSWER_FORMAT, op


# -- the CLI trailer ---------------------------------------------------------------------

def test_the_cli_trailer_names_both_versions(pkg, tmp_path, capsys, monkeypatch):
    from codemap import store
    out = tmp_path / "g.json"
    store.save(pkg.graph, str(out))
    monkeypatch.chdir(tmp_path)                      # no codemap.toml here: empty contract
    assert main(["check", "--graph", str(out)]) == 0
    tail = capsys.readouterr().out.rstrip().splitlines()[-1]
    assert tail == f"_answer format {ANSWER_FORMAT} · schema {SCHEMA_VERSION}_"


def test_the_trailer_is_on_reports_too(pkg, tmp_path, capsys):
    from codemap import store
    out = tmp_path / "g.json"
    store.save(pkg.graph, str(out))
    main(["report", "architecture", "--graph", str(out)])
    assert capsys.readouterr().out.rstrip().endswith(
        f"_answer format {ANSWER_FORMAT} · schema {SCHEMA_VERSION}_")


def test_json_output_has_no_trailer(pkg, tmp_path, capsys):
    """The trailer is presentation. A `--format json` answer must stay parseable."""
    from codemap import store
    out = tmp_path / "g.json"
    store.save(pkg.graph, str(out))
    main(["report", "architecture", "--graph", str(out), "--format", "json"])
    json.loads(capsys.readouterr().out)              # raises if a trailer leaked in


# -- the guard that makes a silent change impossible --------------------------------------

def test_rendered_answers_match_the_pin(pkg):
    """Six markdown surfaces over a fixture this test owns, hashed.

    This does not decide whether a change is structural — that judgement is a human's, and
    pretending to automate it would be the R1-C37 defect in a new place. It only refuses to let
    the shape of an answer move **silently**.
    """
    got = hashlib.sha256(_rendered(pkg).encode()).hexdigest()
    assert got == RENDERED_SHA, (
        "the rendered answers changed.\n"
        "  • intended change of structure? bump ANSWER_FORMAT in codemap/model.py, update\n"
        "    RENDERED_SHA here in the same commit, and say so in the release note\n"
        "  • only wording? update RENDERED_SHA alone — the version is about structure\n"
        "  • neither? this is a regression, and the pin just caught it\n"
        f"  expected {RENDERED_SHA}\n  got      {got}")


def test_the_pin_is_over_a_fixture_this_test_owns(pkg):
    """Positive control for the pin: it must not be hashing the live dogfood tree."""
    assert pkg.graph.target == "pkg"
    assert len(pkg.graph.nodes) < 40, "a fixture, not a real package"


# -- format 5 (R1-C80): the `tests` answer joins the pinned surfaces ---------------------------
# Consumers act on it ("what to run before a change"), and until format 5 its shape could move
# without any pin noticing: none of the six surfaces above is `tests`. Its own fixture, so the
# repo-scoped build does not move the pin above.
TESTS_SHA = "0cc68942719b8050213cc1b03b5ce19c1e9eae858c71bbda8618b6c283b199bd"

REPO_FILES = {
    "pkg/__init__.py": "",
    "pkg/core.py": "def act():\n    return 1\n\n\ndef wrap():\n    return act()\n",
    "tests/test_a.py": ("from pkg.core import act, wrap\n\n\n"
                        "def _helper():\n    return act()\n\n\n"
                        "def test_direct():\n    assert act() == 1\n\n\n"
                        "def test_through_helper():\n    assert _helper() == 1\n\n\n"
                        "def test_far():\n    assert wrap() == 1\n"),
}


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    from codemap.extract import extract_repo
    root = tmp_path_factory.mktemp("r1c63_tests")
    for rel, body in REPO_FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return Query(extract_repo(str(root / "pkg"), consumers=(str(root / "tests"),), mode="full"))


def _tests_answers(query) -> str:
    session = Session(query.graph)
    out = []
    for args in ({"symbol": "pkg.core.act"}, {"symbol": "pkg.core.act", "all_bands": True},
                 {"symbol": "pkg.core.wrap"}):
        env = session.handle({"op": "tests", "args": args})
        out.append(json.dumps(env["result"], sort_keys=True))
    return "\n@@\n".join(out)


def test_the_tests_answer_matches_its_pin(repo):
    got = hashlib.sha256(_tests_answers(repo).encode()).hexdigest()
    assert got == TESTS_SHA, (
        "the `tests` answer changed shape or content — bump ANSWER_FORMAT if structural, "
        f"and re-pin.\n  expected {TESTS_SHA}\n  got      {got}\n{_tests_answers(repo)}")
