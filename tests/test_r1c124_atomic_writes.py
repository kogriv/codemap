"""R1-C124 — a failed write leaves the previous graph and the previous catalog pair whole.

Expectations E1–E2 are in BACKLOG.md (R1-C124), written before the change (external audit F-10, F-11).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from codemap import atomic, store
from codemap.advise import DATA, load
from codemap.advise.refresh import publish_pair
from codemap.extract import extract


def _graph(tmp_path: Path, name: str):
    d = tmp_path / name
    (d / "pkg").mkdir(parents=True)
    (d / "pkg/__init__.py").write_text(f"def {name}():\n    return 1\n")
    return extract(str(d / "pkg"))


def test_e1_an_interrupted_save_leaves_the_old_graph(tmp_path, monkeypatch):
    path = tmp_path / "g.json"
    store.save(_graph(tmp_path, "old"), path)
    before = path.read_bytes()

    def torn(fd):                                         # the disk fills up between write and rename
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(os, "fsync", torn)
    with pytest.raises(OSError):
        store.save(_graph(tmp_path, "new"), path)
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".g.json.")] == []   # no temp left


def test_e1_save_replaces_in_one_step(tmp_path, monkeypatch):
    path = tmp_path / "g.json"
    store.save(_graph(tmp_path, "old"), path)
    seen = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (seen.append((Path(a).parent, Path(b))), real(a, b)))
    store.save(_graph(tmp_path, "new"), path)
    assert seen == [(tmp_path, path)] and "new" in path.read_text()


def _pair(as_of: str) -> tuple[bytes, bytes]:
    m = (DATA / "matrix.toml").read_text(encoding="utf-8").replace(
        next(ln for ln in (DATA / "matrix.toml").read_text(encoding="utf-8").splitlines()
             if ln.startswith("as_of")), f'as_of = "{as_of}"', 1)
    f = json.loads((DATA / "feed.json").read_text(encoding="utf-8"))
    f["as_of"] = as_of
    return m.encode(), json.dumps(f).encode()


def test_e2_a_failure_between_the_two_files_keeps_the_old_pair(tmp_path, monkeypatch):
    cdir = tmp_path / "cache"
    publish_pair(cdir, *_pair("2099-01-01"))
    assert load(cache=cdir).source == {"matrix": "refreshed", "feed": "refreshed"}
    real = atomic.write_bytes

    def second_fails(path, data):
        if Path(path).name == "feed.json":
            raise OSError("interrupted")
        real(path, data)
    monkeypatch.setattr(atomic, "write_bytes", second_fails)
    with pytest.raises(OSError):
        publish_pair(cdir, *_pair("2099-06-01"))
    cat = load(cache=cdir)
    assert cat.meta["as_of"] == "2099-01-01" and cat.feed["as_of"] == "2099-01-01"
    assert len(list(cdir.glob("gen-*"))) == 1                       # the torn generation is gone


def test_e2_a_legacy_top_level_pair_is_still_read_and_replaced(tmp_path):
    cdir = tmp_path / "cache"
    cdir.mkdir()
    m, f = _pair("2099-01-01")
    (cdir / "matrix.toml").write_bytes(m)
    (cdir / "feed.json").write_bytes(f)
    assert load(cache=cdir).meta["as_of"] == "2099-01-01"
    publish_pair(cdir, *_pair("2099-02-01"))
    assert load(cache=cdir).meta["as_of"] == "2099-02-01" and not (cdir / "matrix.toml").exists()
