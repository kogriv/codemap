"""R1-C73 — `codemap --version`, from the identity the graph records.

Design `docs/design/cli_version.md`. Pinned: V1 (agrees with `importlib.metadata` and with
`provenance.tool`), V3 (the flag wins over a subcommand), V4 (no arguments is still an error), V5 (no other
command pays for `tool_identity()`), and V6 (a fixed string goes red). V2, the wheel outside the source
tree, is the CI wheel job's ground and was measured by hand at acceptance.
"""

from __future__ import annotations

import importlib.metadata
from unittest import mock

import pytest

from codemap import cli, provenance
from codemap.model import ANSWER_FORMAT, SCHEMA_VERSION


def _version_out(capsys, *argv) -> tuple[int, str]:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version", *argv])
    return exc.value.code, capsys.readouterr().out.strip()


def test_it_agrees_with_the_metadata_and_with_provenance(capsys):
    rc, out = _version_out(capsys)
    assert rc == 0
    ident = provenance.tool_identity()
    assert out.startswith(f"codemap {importlib.metadata.version('codmap')}")
    if ident.get("commit"):
        assert f"@{ident['commit']}" in out
    assert out.endswith(f"· answer format {ANSWER_FORMAT} · schema {SCHEMA_VERSION}")
    assert ("(dirty)" in out) == bool(ident.get("dirty"))


def test_the_flag_wins_over_a_subcommand(capsys):
    rc, out = _version_out(capsys, "build", "x")
    assert rc == 0 and out.startswith("codemap ")


def test_no_arguments_is_still_an_error(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


def test_an_uninstalled_tool_says_so_rather_than_inventing_a_number():
    with mock.patch.object(provenance, "tool_identity", lambda: {"name": "codemap"}):
        line = cli.version_line()
    assert line.startswith("codemap version unknown (not installed as a distribution)")


def test_no_other_command_pays_for_the_identity(tmp_path, capsys):
    """V5: building the parser must not call git; only the flag does."""
    pkg = tmp_path / "vpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    g = tmp_path / "g.json"
    assert cli.main(["build", str(pkg), "-o", str(g)]) == 0
    with mock.patch.object(provenance, "tool_identity", side_effect=AssertionError("called")):
        assert cli.main(["query", "vpkg", "--graph", str(g)]) in (0, 1)
        assert cli.main(["report", "dependencies", "--graph", str(g)]) in (0, None)


def test_mutation_a_fixed_string_goes_red(capsys):
    """V6: an action that prints a frozen version disagrees with the metadata."""
    with mock.patch.object(cli, "version_line", lambda: "codemap 9.9.9 · answer format 1 · schema 0.1"):
        _, out = _version_out(capsys)
    assert not out.startswith(f"codemap {importlib.metadata.version('codmap')}")
    _, out = _version_out(capsys)
    assert out.startswith(f"codemap {importlib.metadata.version('codmap')}")
