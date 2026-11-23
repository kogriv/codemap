"""R1-C126 — the input identity includes each file's role. E1–E3 in BACKLOG.md (R1-C126), audit F-07."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from codemap.scope import LEGACY_PREFIX, ROLE_PREFIX, matches, resolve_scope
from codemap.serve.currency import graph_currency


def _tree(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/__init__.py").write_text("def f():\n    return 1\n")
    (tmp_path / "t").mkdir()
    (tmp_path / "t/test_a.py").write_text("from pkg import f\n\n\ndef test_f():\n    assert f() == 1\n")
    return tmp_path


def test_e1_the_same_files_in_another_role_are_another_input(tmp_path):
    root = _tree(tmp_path)
    as_consumer = resolve_scope(str(root / "pkg"), consumers=(str(root / "t"),))
    as_docs = resolve_scope(str(root / "pkg"), docs=(str(root / "t"),))
    assert as_consumer["scope_id_legacy"] == as_docs["scope_id_legacy"]      # what 0.0.45 compared
    assert as_consumer["scope_id"] != as_docs["scope_id"]
    assert as_consumer["scope_id"].startswith(ROLE_PREFIX)


def test_e2_the_same_recipe_is_the_same_input(tmp_path):
    root = _tree(tmp_path)
    a = resolve_scope(str(root / "pkg"), consumers=(str(root / "t"),))
    b = resolve_scope(str(root / "pkg"), consumers=(str(root / "t"),))
    assert a["scope_id"] == b["scope_id"] and matches(a["scope_id"], b)


def test_e3_a_graph_recorded_with_the_old_formula_is_not_called_behind(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    monkeypatch.chdir(root)
    g = root / "g.json"
    subprocess.run([sys.executable, "-m", "codemap", "build", "pkg", "--consumer", "t", "-o", str(g)],
                   check=True, capture_output=True)
    now = resolve_scope(str(root / "pkg"), consumers=(str(root / "t"),))
    # rewrite the record as 0.0.45 wrote it: role-blind, `sha256:` prefix
    data = json.loads(g.read_text())
    data["provenance"]["scope_id"] = now["scope_id_legacy"]
    g.write_text(json.dumps(data))
    meta = json.loads(Path(str(g) + ".meta.json").read_text())
    meta["scope"]["scope_id"] = now["scope_id_legacy"]
    Path(str(g) + ".meta.json").write_text(json.dumps(meta))
    assert now["scope_id_legacy"].startswith(LEGACY_PREFIX)
    assert graph_currency(str(g), now["scope_id_legacy"], base=str(root))["status"] == "current"
    (root / "pkg/__init__.py").write_text("def f():\n    return 2\n")       # control: a real change shows
    assert graph_currency(str(g), now["scope_id_legacy"], base=str(root))["status"] == "behind"
    assert not matches("md5:whatever", now)
