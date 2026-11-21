"""The lab's verified tool expertise, served to the agent (R1-C110, ``docs/design/advise.md``).

Two data files ship in the package and are published on ``main``:

- ``data/matrix.toml`` — needs × tools. Every claim (one tool, one need) carries a status from a closed
  vocabulary (``measured`` / ``probed`` / ``read`` / ``rejected``), the version and date it was checked, and
  the evidence: a heading in a research card of this repository. codemap's own coverage of each need names the
  tests that prove it.
- ``data/feed.json`` — machine-written by the lab's release watch and scouting: the latest release seen per
  tool and a news list.

``codemap advise --refresh`` caches newer copies of both from ``main``; :func:`load` serves whichever is newer
per file and says so. Nothing here installs or runs a tool, and nothing here calls a model: it is a lookup over
reviewed data.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA = 1
STATUSES = ("measured", "probed", "read", "rejected")
COVERAGE = ("covered", "partial", "none")
NEWS_KINDS = ("release", "card", "finding", "advisory", "new-tool")
WATCH_KINDS = ("pypi", "npm", "github", "none")
INTERFACES = ("cli", "mcp", "lib", "saas", "plugin", "lsp")

DATA = Path(__file__).resolve().parent / "data"
DEFAULT_BASE = "https://raw.githubusercontent.com/kogriv/codemap/main/codemap/advise/data/"

# What a claim needs, per status (design D1).
_REQUIRES = {
    "measured": ("version", "checked", "evidence", "summary"),
    "probed": ("version", "checked", "evidence", "summary"),
    "read": ("summary",),
    "rejected": ("checked", "evidence", "reason"),
}

# File extensions codemap does not read, by language (design D4). Python is the graph's own.
LANGUAGES = {
    ".py": "python", ".pyi": "python",
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript", ".cts": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".vue": "vue", ".svelte": "svelte",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".scala": "scala",
    ".rb": "ruby", ".php": "php", ".cs": "csharp", ".swift": "swift",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".sql": "sql", ".sh": "shell", ".bash": "shell", ".dart": "dart",
}
#: A tool's `languages`: real names from the map above, or "any" for a language-agnostic tool (text, tokens, an
#: LLM). An empty list means "not recorded": such a tool is never shown for a language filter.
LANGUAGE_NAMES = frozenset(LANGUAGES.values()) | {"any"}
_SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build",
              ".codemap", ".tox", ".nox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "site-packages",
              ".next", ".nuxt", "coverage", "target", "vendor", ".idea", ".vscode"}
_OUTSIDE = re.compile(r"^(?P<file>.+?(?P<ext>\.[A-Za-z]+))(?::\d+.*|::.*)?$")


# --------------------------------------------------------------------------- catalog


@dataclass
class Catalog:
    matrix: dict
    feed: dict
    source: dict  # {"matrix": "packaged"|"refreshed", "feed": ...}
    notes: list[str] = field(default_factory=list)

    @property
    def meta(self) -> dict:
        return self.matrix.get("meta", {})

    @property
    def needs(self) -> dict[str, dict]:
        return {n["id"]: n for n in self.matrix.get("need", [])}

    @property
    def tools(self) -> dict[str, dict]:
        return {t["id"]: t for t in self.matrix.get("tool", [])}

    @property
    def claims(self) -> list[dict]:
        return list(self.matrix.get("claim", []))

    @property
    def as_of(self) -> str:
        return max(self.meta.get("as_of", ""), self.feed.get("as_of", ""))

    def header(self, today: date | None = None) -> dict:
        today = today or datetime.now(timezone.utc).date()
        a = _date(self.as_of)
        return {"as_of": self.as_of, "matrix_as_of": self.meta.get("as_of"),
                "feed_as_of": self.feed.get("as_of"), "source": dict(self.source),
                "age_days": (today - a).days if a else None, "notes": list(self.notes)}


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "codemap" / "advise"


def _read_pair(directory: Path) -> tuple[dict | None, dict | None, list[str]]:
    errs: list[str] = []
    m = f = None
    try:
        m = tomllib.loads((directory / "matrix.toml").read_text(encoding="utf-8"))
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        errs.append(f"matrix.toml in {directory}: {exc}")
    try:
        f = json.loads((directory / "feed.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        errs.append(f"feed.json in {directory}: {exc}")
    return m, f, errs


def load(cache: Path | None = None, packaged: Path | None = None) -> Catalog:
    """The packaged catalog, with each file replaced by its cached copy when that is newer and the pair valid."""
    pm, pf, errs = _read_pair(packaged or DATA)
    if pm is None or pf is None:
        raise RuntimeError(f"codemap advise: packaged catalog missing or unreadable: {errs}")
    cat = Catalog(pm, pf, {"matrix": "packaged", "feed": "packaged"})
    cdir = cache if cache is not None else cache_dir()
    if not cdir.is_dir():
        return cat
    cm, cf, cerrs = _read_pair(cdir)
    cat.notes.extend(f"cache ignored: {e}" for e in cerrs)
    m, f, src = pm, pf, {"matrix": "packaged", "feed": "packaged"}
    if cm is not None and cm.get("meta", {}).get("as_of", "") > pm.get("meta", {}).get("as_of", ""):
        m, src["matrix"] = cm, "refreshed"
    if cf is not None and cf.get("as_of", "") > pf.get("as_of", ""):
        f, src["feed"] = cf, "refreshed"
    if src == cat.source:
        return cat
    problems = schema_problems(m, f)
    if problems:
        cat.notes.append(f"cached catalog ignored: {problems[0]}" + (f" (+{len(problems) - 1})" if len(problems) > 1 else ""))
        return cat
    return Catalog(m, f, src, cat.notes)


# --------------------------------------------------------------------------- validation


def _date(s) -> date | None:
    if not isinstance(s, str) or len(s) < 10:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def schema_problems(matrix: dict, feed: dict) -> list[str]:
    """Structural checks every copy must pass, packaged or downloaded (design D5, D7)."""
    p: list[str] = []
    meta = matrix.get("meta")
    if not isinstance(meta, dict):
        return ["matrix: no [meta]"]
    if meta.get("schema") != SCHEMA:
        p.append(f"matrix: schema {meta.get('schema')!r}, this codemap reads {SCHEMA}")
    if not _date(meta.get("as_of")):
        p.append("matrix: meta.as_of is not an ISO date")
    if not isinstance(meta.get("stale_after_days"), int):
        p.append("matrix: meta.stale_after_days must be an integer")
    needs, tools = {}, {}
    for n in matrix.get("need", []):
        nid = n.get("id")
        if not nid or nid in needs:
            p.append(f"need: missing or duplicate id {nid!r}")
            continue
        needs[nid] = n
        if not n.get("title"):
            p.append(f"need {nid}: no title")
        if n.get("codemap") not in COVERAGE:
            p.append(f"need {nid}: codemap {n.get('codemap')!r} not in {COVERAGE}")
        elif n["codemap"] != "none":
            if not n.get("codemap_tests"):
                p.append(f"need {nid}: codemap {n['codemap']} names no test")
            if not n.get("codemap_how"):
                p.append(f"need {nid}: codemap {n['codemap']} without codemap_how")
    for t in matrix.get("tool", []):
        tid = t.get("id")
        if not tid or tid in tools:
            p.append(f"tool: missing or duplicate id {tid!r}")
            continue
        tools[tid] = t
        if not t.get("name") or not t.get("url"):
            p.append(f"tool {tid}: name and url are required")
        w = t.get("watch", {})
        if not isinstance(w, dict) or w.get("kind") not in WATCH_KINDS:
            p.append(f"tool {tid}: watch.kind not in {WATCH_KINDS}")
        elif w["kind"] != "none" and not w.get("name"):
            p.append(f"tool {tid}: watch.kind {w['kind']} needs watch.name")
        langs = t.get("languages", [])
        if not isinstance(langs, list) or any(x not in LANGUAGE_NAMES for x in langs):
            p.append(f"tool {tid}: languages {langs!r} — use names from {sorted(LANGUAGE_NAMES)} "
                     "(free text goes to languages_note)")
        bad = [i for i in t.get("interface", []) if i not in INTERFACES]
        if bad:
            p.append(f"tool {tid}: interface {bad} not in {INTERFACES}")
    seen = set()
    for c in matrix.get("claim", []):
        key = (c.get("tool"), c.get("need"))
        where = f"claim {key[0]}×{key[1]}"
        if key in seen:
            p.append(f"{where}: duplicate")
        seen.add(key)
        if key[0] not in tools:
            p.append(f"{where}: unknown tool")
        if key[1] not in needs:
            p.append(f"{where}: unknown need")
        st = c.get("status")
        if st not in STATUSES:
            p.append(f"{where}: status {st!r} not in {STATUSES}")
            continue
        for fld in _REQUIRES[st]:
            if not c.get(fld):
                p.append(f"{where}: status {st} requires {fld}")
        on = c.get("measured_on")
        if on is not None and (not isinstance(on, list) or not on or any(x not in LANGUAGE_NAMES for x in on)):
            p.append(f"{where}: measured_on {on!r} — a non-empty list of language names")
        if c.get("checked") and not _date(c["checked"]):
            p.append(f"{where}: checked is not an ISO date")
    for tid in tools:
        if not any(c.get("tool") == tid for c in matrix.get("claim", [])):
            p.append(f"tool {tid}: no claim")
    # feed
    if feed.get("schema") != SCHEMA:
        p.append(f"feed: schema {feed.get('schema')!r}, this codemap reads {SCHEMA}")
    if not _date(feed.get("as_of")):
        p.append("feed: as_of is not an ISO date")
    for tid, rel in (feed.get("latest") or {}).items():
        if tid not in tools:
            p.append(f"feed latest: unknown tool {tid!r}")
        elif not isinstance(rel, dict) or not rel.get("version"):
            p.append(f"feed latest {tid}: no version")
    for i, item in enumerate(feed.get("news") or []):
        if item.get("kind") not in NEWS_KINDS:
            p.append(f"feed news #{i}: kind {item.get('kind')!r} not in {NEWS_KINDS}")
        if item.get("tool") is not None and item["tool"] not in tools:
            p.append(f"feed news #{i}: unknown tool {item['tool']!r}")
        if not _date(item.get("date")) or not item.get("text") or not item.get("source"):
            p.append(f"feed news #{i}: date, text and source are required")
        if not isinstance(item.get("verified"), bool):
            p.append(f"feed news #{i}: verified must be true or false")
    return p


def github_anchor(heading: str) -> str:
    """GitHub's heading anchor: markdown marks and punctuation dropped, lower case, spaces → hyphens."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading.strip())
    text = re.sub(r"[^\w\- ]", "", text.lower())
    return text.replace(" ", "-")


def anchors(md: str) -> set[str]:
    out: set[str] = set()
    counts: dict[str, int] = {}
    in_code = False
    for line in md.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if not m:
            continue
        a = github_anchor(m.group(1))
        n = counts.get(a, 0)
        out.add(a if n == 0 else f"{a}-{n}")
        counts[a] = n + 1
    return out


def repo_problems(matrix: dict, root: Path) -> list[str]:
    """Checks only this repository can make: evidence resolves, cited tests exist, cards are in (design D7)."""
    p: list[str] = []
    cache: dict[str, set[str] | None] = {}

    def resolves(ref: str) -> str | None:
        path, _, anchor = ref.partition("#")
        if path not in cache:
            f = root / path
            cache[path] = anchors(f.read_text(encoding="utf-8")) if f.is_file() else None
        a = cache[path]
        if a is None:
            return f"{path} does not exist"
        if anchor and anchor not in a:
            return f"no heading #{anchor} in {path}"
        return None

    for c in matrix.get("claim", []):
        if c.get("evidence"):
            err = resolves(c["evidence"])
            if err:
                p.append(f"claim {c.get('tool')}×{c.get('need')}: evidence {err}")
    for n in matrix.get("need", []):
        for t in n.get("codemap_tests", []):
            fpath, _, fn = t.partition("::")
            f = root / fpath
            if not f.is_file():
                p.append(f"need {n['id']}: test file {fpath} does not exist")
            elif fn and not re.search(rf"^\s*def {re.escape(fn)}\(", f.read_text(encoding="utf-8"), re.M):
                p.append(f"need {n['id']}: no test {fn} in {fpath}")
    named = set()
    for t in matrix.get("tool", []):
        if t.get("card"):
            named.add(t["card"])
            if not (root / t["card"]).is_file():
                p.append(f"tool {t['id']}: card {t['card']} does not exist")
    for card in sorted((root / "research" / "tools").glob("*.md")):
        rel = card.relative_to(root).as_posix()
        if card.name != "README.md" and rel not in named:
            p.append(f"card {rel} has no tool in the matrix")
    return p


# --------------------------------------------------------------------------- answers

_RANK = {s: i for i, s in enumerate(STATUSES)}


def _norm_version(v) -> str:
    s = str(v or "").strip().lstrip("vV")
    while s.endswith(".0") and s.count(".") > 1:
        s = s[:-2]
    return s


def evidence_url(cat: Catalog, ref: str | None) -> str | None:
    if not ref:
        return None
    base = cat.meta.get("repo", "https://github.com/kogriv/codemap").rstrip("/")
    return f"{base}/blob/main/{ref}"


def _claim_view(cat: Catalog, c: dict, languages: set[str] | None = None) -> dict:
    t = cat.tools.get(c["tool"], {})
    out = {"tool": c["tool"], "name": t.get("name", c["tool"]), "url": t.get("url"),
           "license": t.get("license"), "interface": t.get("interface", []), "status": c["status"]}
    # A measurement is about the language it ran on (the lab's truth so far is Python). Asked about another
    # language, the claim is only what the tool says about itself: `read`, with where it was measured.
    if c["status"] in ("measured", "probed"):
        on = c.get("measured_on", ["python"])
        out["measured_on"] = list(on)
        if languages and not (set(on) & languages):
            out["status"] = "read"
            out["status_note"] = f"{c['status']} on {', '.join(on)} only; not run on {', '.join(sorted(languages))}"
    for k in ("version", "checked", "summary", "vs_codemap", "reason", "probe"):
        if c.get(k):
            out[k] = c[k]
    if not out.get("probe") and out["status"] in ("read", "probed"):
        out["probe"] = "not scored by the lab: check it on a question whose answer you know first"
    if isinstance(c.get("rank"), int):
        out["_rank"] = c["rank"]
    if c.get("evidence"):
        out["evidence"] = evidence_url(cat, c["evidence"])
    a, ch = _date(cat.meta.get("as_of")), _date(c.get("checked"))
    if a and ch and c["status"] != "read" and (a - ch).days > cat.meta.get("stale_after_days", 180):
        out["stale"] = True
    latest = (cat.feed.get("latest") or {}).get(c["tool"])
    if latest and c.get("version") and c["status"] in ("measured", "probed") \
            and _norm_version(latest.get("version")) != _norm_version(c["version"]):
        out["drift"] = {"measured": c["version"], "latest": latest["version"], "latest_date": latest.get("date")}
    return out


def _order(views: list[dict]) -> list[dict]:
    """Status first (measured before probed before read); within a status the explicit ``rank``, then the
    most recently checked; then the id, so the order is stable."""
    def key(v):
        d = _date(v.get("checked"))
        return (_RANK[v["status"]], v.get("_rank", 99), -(d.toordinal() if d else 0), v["tool"])
    return sorted(views, key=key)


def _codemap_view(n: dict) -> dict:
    out = {"coverage": n["codemap"]}
    for k in ("codemap_how", "codemap_caveat"):
        if n.get(k):
            out[k[len("codemap_"):]] = n[k]
    if n.get("codemap_tests"):
        out["tests"] = list(n["codemap_tests"])
    return out


def _speaks(tool: dict, langs: set[str]) -> bool:
    have = set(tool.get("languages", []))
    return "any" in have or bool(have & langs)


def need_answer(cat: Catalog, nid: str, languages: set[str] | None = None) -> dict:
    """One need. With ``languages``, a tool whose recorded languages include none of them is left out and
    listed in ``excluded`` — never recommended for a language it does not read."""
    n = cat.needs[nid]
    views, excluded = [], []
    for c in cat.claims:
        if c["need"] != nid:
            continue
        t = cat.tools.get(c["tool"], {})
        if languages and not _speaks(t, languages):
            excluded.append({"tool": c["tool"], "status": c["status"], "languages": t.get("languages", []),
                             **({"languages_note": t["languages_note"]} if t.get("languages_note") else {})})
            continue
        views.append(_claim_view(cat, c, languages))
    usable = _order([v for v in views if v["status"] != "rejected"])
    rejected = sorted((v for v in views if v["status"] == "rejected"), key=lambda v: v["tool"])
    for v in usable + rejected:
        v.pop("_rank", None)
    out = {"need": nid, "title": n["title"], "languages": n.get("languages", []), "codemap": _codemap_view(n),
           "tools": usable, "rejected": rejected}
    if languages:
        out["language_filter"] = sorted(languages)
        out["excluded"] = sorted(excluded, key=lambda x: x["tool"])
    if n.get("note"):
        out["note"] = n["note"]
    return out


_ALIASES = {"ts": "typescript", "tsx": "typescript", "js": "javascript", "jsx": "javascript", "py": "python",
            "golang": "go", "rs": "rust", "c#": "csharp", "c++": "cpp"}


def _tokens(s: str) -> list[str]:
    return [_ALIASES.get(w, w) for w in re.findall(r"[\w#+]+", s.lower())]


def match_needs(cat: Catalog, query: str) -> list[str]:
    """Need ids that match ``query``: an exact id first; else the needs sharing most words with it."""
    q = query.strip().lower()
    if q in cat.needs:
        return [q]
    words = set(_tokens(q))
    if not words:
        return []
    scored = []
    for nid, n in cat.needs.items():
        hay = set(_tokens(" ".join([nid.replace("-", " "), n.get("title", ""), " ".join(n.get("keywords", [])),
                                    " ".join(n.get("languages", []))])))
        s = len(words & hay)
        if s:
            scored.append((s, nid))
    if not scored:
        return []
    best = max(s for s, _ in scored)
    return sorted(nid for s, nid in scored if s == best)


def _applies(n: dict, languages: set[str]) -> bool:
    langs = set(n.get("languages", []))
    return not langs or "any" in langs or bool(langs & languages)


def overview(cat: Catalog, languages: list[str] | None = None) -> dict:
    langs = {_ALIASES.get(x.lower(), x.lower()) for x in (languages or [])}
    rows = []
    for nid, n in cat.needs.items():
        if langs and not _applies(n, langs):
            continue
        a = need_answer(cat, nid, langs or None)
        best = a["tools"][0] if a["tools"] else None
        rows.append({"need": nid, "title": n["title"], "codemap": n["codemap"],
                     "best": ({"tool": best["tool"], "status": best["status"]} if best else None),
                     "tools": len(a["tools"])})
    counts = {s: sum(1 for c in cat.claims if c["status"] == s) for s in STATUSES}
    return {"needs": rows, "claims": counts, "tools": len(cat.tools),
            "languages": sorted(langs) if langs else None}


def tool_answer(cat: Catalog, tid: str) -> dict:
    t = cat.tools[tid]
    claims = [_claim_view(cat, c) | {"need": c["need"]} for c in cat.claims if c["tool"] == tid]
    claims.sort(key=lambda v: (_RANK[v["status"]], v["need"]))
    for v in claims:
        v.pop("_rank", None)
    out = {k: t[k] for k in ("id", "name", "url", "license", "languages", "interface") if k in t}
    if t.get("card"):
        out["card"] = evidence_url(cat, t["card"])
    out["claims"] = claims
    latest = (cat.feed.get("latest") or {}).get(tid)
    if latest:
        out["latest"] = latest
    out["news"] = [n for n in cat.feed.get("news", []) if n.get("tool") == tid]
    return out


def news(cat: Catalog, days: int | None = None, today: date | None = None) -> list[dict]:
    today = today or datetime.now(timezone.utc).date()
    items = sorted(cat.feed.get("news", []), key=lambda n: n["date"], reverse=True)
    if days is not None:
        floor = date.fromordinal(max(1, today.toordinal() - days))
        items = [n for n in items if (_date(n["date"]) or today) >= floor]
    return items


def detect_languages(root: Path, limit: int = 200_000) -> dict[str, int]:
    """File counts per language under ``root``, skipping vendored and generated directories."""
    counts: dict[str, int] = {}
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            lang = LANGUAGES.get(os.path.splitext(fn)[1].lower())
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
            seen += 1
            if seen >= limit:
                return counts
    return counts


def outside_graph(name: str) -> dict | None:
    """``{language, advise}`` when ``name`` points at a source file codemap does not read (design D4)."""
    if not isinstance(name, str):
        return None
    m = _OUTSIDE.match(name.strip())
    if not m:
        return None
    # A dotted Python name can end in `.c` or `.go` too. Without a path separator, only a single-dot name
    # with an extension of two letters or more reads as a file (`app.ts`), never `pkg.mod.c`.
    path, ext = m.group("file"), m.group("ext")
    if "/" not in path and "\\" not in path and (path.count(".") != 1 or len(ext) < 3):
        return None
    lang = LANGUAGES.get(ext.lower())
    if lang is None or lang == "python":
        return None
    return {"language": lang, "advise": {"languages": [lang]}}


def answer(args: dict, cat: Catalog | None = None) -> dict:
    """The MCP/serve entry point: ``{need?, languages?, tool?, news_days?}`` → one answer."""
    cat = cat or load()
    out: dict = {"catalog": cat.header()}
    tool, need, langs = args.get("tool"), args.get("need"), args.get("languages")
    if isinstance(langs, str):
        langs = [langs]
    if tool:
        if tool not in cat.tools:
            out["error"] = f"unknown tool {tool!r}"
            out["tools"] = sorted(cat.tools)
            return out
        out["tool"] = tool_answer(cat, tool)
    elif need:
        ids = match_needs(cat, need)
        if langs:
            want = {_ALIASES.get(x.lower(), x.lower()) for x in langs}
            ids = [i for i in ids if _applies(cat.needs[i], want)] or ids
        if not ids:
            out["error"] = f"no need matches {need!r}"
            out["needs"] = sorted(cat.needs)
            return out
        want = {_ALIASES.get(x.lower(), x.lower()) for x in langs} if langs else None
        out["matches"] = [need_answer(cat, i, want) for i in ids]
    else:
        out["overview"] = overview(cat, langs)
    if args.get("news_days") is not None:
        out["news"] = news(cat, int(args["news_days"]))
    return out
