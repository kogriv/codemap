"""``codemap advise --refresh``: newer catalog files from ``main``, without a codemap release (design D5).

A plain GET of two public files. They are written to the cache only when both parse, pass
:func:`codemap.advise.schema_problems` together, and at least one is newer than what is served now. Any
failure leaves the served catalog as it was and says why; it never raises to the caller.
"""

from __future__ import annotations

import json
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from codemap.advise import CURRENT, DEFAULT_BASE, cache_dir, load, schema_problems

TIMEOUT = 10


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "codemap-advise"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 — https/http base given by the user
        return r.read()


def refresh(base: str | None = None, cache: Path | None = None) -> dict:
    base = (base or DEFAULT_BASE).rstrip("/") + "/"
    cdir = cache if cache is not None else cache_dir()
    before = load(cache=cdir)
    out = {"from": base, "cache": str(cdir), "before": before.header(), "updated": False}
    try:
        mraw, fraw = _get(base + "matrix.toml"), _get(base + "feed.json")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        out["reason"] = f"download failed: {exc}"
        return out
    try:
        m = tomllib.loads(mraw.decode("utf-8"))
        f = json.loads(fraw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        out["reason"] = f"downloaded catalog does not parse: {exc}"
        return out
    problems = schema_problems(m, f)
    if problems:
        out["reason"] = f"downloaded catalog is invalid: {problems[0]}" + (
            f" (+{len(problems) - 1})" if len(problems) > 1 else "")
        return out
    newer_m = m["meta"]["as_of"] > before.meta.get("as_of", "")
    newer_f = f["as_of"] > before.feed.get("as_of", "")
    if not (newer_m or newer_f):
        out["reason"] = (f"downloaded catalog is not newer (matrix {m['meta']['as_of']}, feed {f['as_of']}; "
                         f"served {before.meta.get('as_of')}, {before.feed.get('as_of')})")
        return out
    publish_pair(cdir, mraw, fraw)
    after = load(cache=cdir)
    out.update(updated=True, after=after.header())
    return out


#: R1-C135: a generation is removed only once it is this old and `current` does not name it — a reader that took
#: its path a moment ago, or a second publisher that has just pointed `current` at it, still finds it whole.
GRACE_SECONDS = 600


def publish_pair(cdir: Path, mraw: bytes, fraw: bytes) -> None:
    """Publish matrix + feed as one generation (R1-C124): both files go to a new directory, then the pointer
    file ``current`` is replaced atomically. A failure before that leaves the previous pair served whole; a reader
    never sees one file of one generation beside the other file of another.

    Old generations are collected by :func:`collect`, not all at once (R1-C135): two publishers each removing
    every generation but its own left `current` naming a removed one."""
    import shutil
    import tempfile

    from codemap import atomic
    cdir.mkdir(parents=True, exist_ok=True)
    gen = Path(tempfile.mkdtemp(prefix="gen-", dir=cdir))
    try:
        atomic.write_bytes(gen / "matrix.toml", mraw)
        atomic.write_bytes(gen / "feed.json", fraw)
        atomic.write_text(cdir / CURRENT, gen.name + "\n")
    except BaseException:
        shutil.rmtree(gen, ignore_errors=True)
        raise
    collect(cdir)
    for legacy in ("matrix.toml", "feed.json"):          # a pre-0.0.46 pair at the top level (load retries a split read)
        try:
            (cdir / legacy).unlink()
        except FileNotFoundError:
            pass


def collect(cdir: Path, now: float | None = None) -> list[str]:
    """Remove generations `current` does not name *now* and that are older than :data:`GRACE_SECONDS`; the names."""
    import shutil
    import time

    now = time.time() if now is None else now
    try:
        served = (cdir / CURRENT).read_text(encoding="utf-8").strip()
    except OSError:
        served = None
    gone = []
    for old in sorted(cdir.glob("gen-*")):
        try:
            young = now - old.stat().st_mtime < GRACE_SECONDS
        except OSError:
            continue
        if old.is_dir() and old.name != served and not young:
            shutil.rmtree(old, ignore_errors=True)
            gone.append(old.name)
    return gone
