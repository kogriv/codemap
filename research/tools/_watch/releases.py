"""Layer 1 of the lab flow (R1-C110 D6): the latest release of every watched tool.

    python research/tools/_watch/releases.py            # report only
    python research/tools/_watch/releases.py --write    # update codemap/advise/data/feed.json
    python research/tools/_watch/releases.py --report   # also: claims drifted from the latest or stale

Sources: PyPI JSON, the npm registry, GitHub releases (tags when a repository publishes no releases). Set
GITHUB_TOKEN to raise GitHub's anonymous rate limit. A source that fails is printed as a failure and leaves the
tool's last known release in place; nothing is skipped in silence. A new version adds a `release` news item
(verified: the registry is the source). Lab-side: this script is not shipped in the package.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "codemap" / "advise" / "data"
TIMEOUT = 15


def _get_json(url: str) -> object:
    headers = {"User-Agent": "codemap-lab-release-watch", "Accept": "application/json"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {tok}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def clean_tag(tag: str) -> str:
    """A release tag as a version: `v1.2` → `1.2`, `github-release/3.2.3` → `3.2.3`,
    `Release_1_18_0` → `1.18.0`. A tag with no version in it is kept as it is."""
    m = re.search(r"(\d+(?:[._]\d+)+[\w.+-]*)$", tag)
    if not m:
        return tag.lstrip("v")
    v = m.group(1)
    return v.replace("_", ".") if "." not in v else v


def latest(kind: str, name: str) -> dict:
    """{version, date, source} or raises."""
    if kind == "pypi":
        d = _get_json(f"https://pypi.org/pypi/{name}/json")
        v = d["info"]["version"]
        files = d.get("releases", {}).get(v) or []
        date = min((f["upload_time_iso_8601"] for f in files), default=None)
        return {"version": v, "date": (date or "")[:10] or None, "source": f"https://pypi.org/project/{name}/{v}/"}
    if kind == "npm":
        d = _get_json(f"https://registry.npmjs.org/{name}")
        v = d["dist-tags"]["latest"]
        return {"version": v, "date": (d.get("time", {}).get(v) or "")[:10] or None,
                "source": f"https://www.npmjs.com/package/{name}/v/{v}"}
    if kind == "github":
        try:
            d = _get_json(f"https://api.github.com/repos/{name}/releases/latest")
            return {"version": clean_tag(d["tag_name"]), "date": (d.get("published_at") or "")[:10] or None,
                    "source": d.get("html_url") or f"https://github.com/{name}/releases"}
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        tags = _get_json(f"https://api.github.com/repos/{name}/tags?per_page=1")
        if tags:
            return {"version": clean_tag(tags[0]["name"]), "date": None,
                    "source": f"https://github.com/{name}/tags"}
        # No releases and no tags: the last commit on the default branch is the only "version" there is.
        commits = _get_json(f"https://api.github.com/repos/{name}/commits?per_page=1")
        if not commits:
            raise LookupError("no releases, no tags, no commits")
        c = commits[0]
        return {"version": f"commit-{c['sha'][:7]}", "date": (c["commit"]["committer"]["date"] or "")[:10] or None,
                "source": c.get("html_url") or f"https://github.com/{name}/commits"}
    raise ValueError(f"unknown watch kind {kind!r}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="update feed.json")
    ap.add_argument("--report", action="store_true", help="list drifted and stale claims")
    ap.add_argument("--data", default=str(DATA))
    a = ap.parse_args(argv)
    data = Path(a.data)
    matrix = tomllib.loads((data / "matrix.toml").read_text(encoding="utf-8"))
    feed = json.loads((data / "feed.json").read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    known = feed.setdefault("latest", {})
    news = feed.setdefault("news", [])
    failures, new = [], []
    for t in matrix.get("tool", []):
        w = t.get("watch", {})
        if w.get("kind", "none") == "none":
            continue
        try:
            rel = latest(w["kind"], w["name"])
        except Exception as exc:  # noqa: BLE001 — every failure is reported by name
            failures.append(f"{t['id']} ({w['kind']}:{w['name']}): {type(exc).__name__}: {exc}")
            print(f"FAIL  {t['id']:<22} {w['kind']}:{w['name']} — {type(exc).__name__}: {exc}")
            continue
        prev = known.get(t["id"], {}).get("version")
        mark = "same" if prev == rel["version"] else ("NEW " if prev else "init")
        print(f"{mark}  {t['id']:<22} {rel['version']:<14} {rel['date'] or '?':<10} (was {prev or '—'})")
        known[t["id"]] = {"version": rel["version"], "date": rel["date"], "seen": now.date().isoformat()}
        if prev and prev != rel["version"]:
            new.append(t["id"])
            news.append({"date": rel["date"] or now.date().isoformat(), "kind": "release", "tool": t["id"],
                         "text": f"{t['name']} {rel['version']} released (previous seen: {prev}).",
                         "source": rel["source"], "verified": True})
    if a.report:
        from codemap.advise import Catalog, _claim_view  # noqa: PLC0415 — the lab script runs from the repo
        cat = Catalog(matrix, feed, {"matrix": "packaged", "feed": "packaged"})
        print("\n# claims to re-measure")
        for c in cat.claims:
            v = _claim_view(cat, c)
            if v.get("drift") or v.get("stale"):
                why = []
                if v.get("drift"):
                    why.append(f"measured {v['drift']['measured']}, latest {v['drift']['latest']}")
                if v.get("stale"):
                    why.append(f"checked {c['checked']}")
                print(f"- {c['tool']} × {c['need']} ({c['status']}): {'; '.join(why)}")
    print(f"\n{len(known)} tool(s) known, {len(new)} new release(s), {len(failures)} failure(s).")
    if a.write:
        feed["as_of"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        feed["news"] = sorted(news, key=lambda n: (n["date"], n.get("tool") or ""), reverse=True)
        (data / "feed.json").write_text(json.dumps(feed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {data / 'feed.json'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
