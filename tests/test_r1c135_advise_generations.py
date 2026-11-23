"""R1-C135 — generations of the advise cache: two publishers and a reader.

Follow-up audit FU-03. Expectations E1–E6 are in BACKLOG.md (R1-C135), written before the change; on 0.0.46 two
publishers brought together at the pointer write left `current` naming a removed generation, and `load` served
the packaged catalog without a word.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from codemap import atomic
from codemap.advise import CURRENT, _read_pair, _served_dir, load
from codemap.advise.refresh import GRACE_SECONDS, collect, publish_pair
from tests.test_r1c124_atomic_writes import _pair


def _served_whole(cdir: Path) -> str:
    name = (cdir / CURRENT).read_text().strip()
    assert (cdir / name / "matrix.toml").is_file() and (cdir / name / "feed.json").is_file(), sorted(os.listdir(cdir))
    return name


def test_e1_two_publishers_meeting_at_the_pointer_leave_it_on_a_whole_generation(tmp_path, monkeypatch):
    cdir = tmp_path / "cache"
    publish_pair(cdir, *_pair("2099-01-01"))
    barrier = threading.Barrier(2)
    real = atomic.write_text

    def write_text(path, text, *a, **k):
        real(path, text, *a, **k)
        if Path(path).name == CURRENT:
            barrier.wait(timeout=10)                     # both pointers written before either cleans up
    monkeypatch.setattr(atomic, "write_text", write_text)
    errors = []

    def publish(as_of):
        try:
            publish_pair(cdir, *_pair(as_of))
        except Exception as exc:                         # noqa: BLE001 - surfaced below
            errors.append(exc)
    ts = [threading.Thread(target=publish, args=(d,)) for d in ("2099-02-01", "2099-03-01")]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors
    _served_whole(cdir)
    cat = load(cache=cdir)
    assert cat.source == {"matrix": "refreshed", "feed": "refreshed"}, cat.notes
    assert cat.meta["as_of"] in ("2099-02-01", "2099-03-01")


def test_e2_a_reader_holding_the_old_generation_reads_it_whole_after_a_publish(tmp_path):
    cdir = tmp_path / "cache"
    publish_pair(cdir, *_pair("2099-01-01"))
    held, note = _served_dir(cdir)                       # the reader took the path ...
    assert note is None and held != cdir
    publish_pair(cdir, *_pair("2099-02-01"))             # ... a publish lands ...
    m, f, errs = _read_pair(held)                        # ... and the reader goes on
    assert not errs and m["meta"]["as_of"] == "2099-01-01" and f["as_of"] == "2099-01-01"


def test_e3_old_generations_are_collected_and_the_served_one_never(tmp_path):
    cdir = tmp_path / "cache"
    for d in ("2099-01-01", "2099-02-01", "2099-03-01"):
        publish_pair(cdir, *_pair(d))
    gens = sorted(cdir.glob("gen-*"))
    assert len(gens) == 3                                # all young: none removed yet
    past = time.time() - GRACE_SECONDS - 60
    for g in gens:
        os.utime(g, (past, past))
    served = (cdir / CURRENT).read_text().strip()
    gone = collect(cdir)
    assert sorted(gone) == sorted(g.name for g in gens if g.name != served)
    assert [g.name for g in cdir.glob("gen-*")] == [served]
    publish_pair(cdir, *_pair("2099-04-01"))             # the next publish collects as it goes: the old served
    assert [g.name for g in cdir.glob("gen-*")] == [_served_whole(cdir)]   # one is old and no longer named
    assert load(cache=cdir).meta["as_of"] == "2099-04-01"


def test_e6_a_pointer_to_a_missing_generation_is_said(tmp_path):
    cdir = tmp_path / "cache"
    publish_pair(cdir, *_pair("2099-01-01"))
    (cdir / CURRENT).write_text("gen-gone\n")
    cat = load(cache=cdir)
    assert cat.source == {"matrix": "packaged", "feed": "packaged"}
    assert any("names 'gen-gone', which is not there" in n for n in cat.header()["notes"]), cat.notes


def test_a_split_read_is_retried(tmp_path, monkeypatch):
    """One file read from a generation removed before the second: load reads again, it does not mix."""
    import codemap.advise as adv
    cdir = tmp_path / "cache"
    publish_pair(cdir, *_pair("2099-01-01"))
    real = adv._read_pair
    calls = []

    def first_split(directory):
        m, f, errs = real(directory)
        if cdir not in Path(directory).parents and Path(directory) != cdir:
            return m, f, errs                            # the packaged pair
        calls.append(directory)
        return (m, None, errs) if len(calls) == 1 else (m, f, errs)
    monkeypatch.setattr(adv, "_read_pair", first_split)
    cat = load(cache=cdir)
    assert cat.source == {"matrix": "refreshed", "feed": "refreshed"} and len(calls) == 2
