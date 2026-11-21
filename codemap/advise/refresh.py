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

from codemap.advise import DEFAULT_BASE, cache_dir, load, schema_problems

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
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "matrix.toml").write_bytes(mraw)
    (cdir / "feed.json").write_bytes(fraw)
    after = load(cache=cdir)
    out.update(updated=True, after=after.header())
    return out
