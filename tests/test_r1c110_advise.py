"""R1-C110 — `advise`: the lab's tool expertise for agents (docs/design/advise.md).

The guards of D7 run on the packaged catalog; each has a mutation test beside it that breaks the data in
memory and expects the guard to name the break (E4).
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import threading
import tomllib
from datetime import date
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import pytest

from codemap.advise import (DATA, Catalog, anchors, answer, detect_languages, github_anchor, load,
                            match_needs, outside_graph, repo_problems, schema_problems)
from codemap.advise.render import answer_md, matrix_md

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def raw():
    m = tomllib.loads((DATA / "matrix.toml").read_text(encoding="utf-8"))
    f = json.loads((DATA / "feed.json").read_text(encoding="utf-8"))
    return m, f


@pytest.fixture(scope="module")
def cat(tmp_path_factory):
    return load(cache=tmp_path_factory.mktemp("nocache") / "absent")


# --------------------------------------------------------------------------- D7 guards on the shipped data


def test_packaged_catalog_passes_its_schema(raw):
    assert schema_problems(*raw) == []


def test_every_evidence_resolves_and_every_cited_test_exists(raw):
    assert repo_problems(raw[0], ROOT) == []


def test_research_matrix_md_is_the_render(cat):
    got = (ROOT / "research" / "matrix.md").read_text(encoding="utf-8")
    assert got == matrix_md(cat), "research/matrix.md is generated: run `codemap advise --matrix > research/matrix.md`"


def test_every_card_has_a_tool_with_a_hands_on_claim(raw):
    m = raw[0]
    cards = {p.relative_to(ROOT).as_posix() for p in (ROOT / "research" / "tools").glob("*.md")
             if p.name != "README.md"}
    by_card = {t["card"]: t["id"] for t in m["tool"] if t.get("card")}
    assert cards <= set(by_card)
    for card in cards:
        tid = by_card[card]
        st = {c["status"] for c in m["claim"] if c["tool"] == tid}
        assert st & {"measured", "probed", "rejected"}, f"{tid} has a card but only read-only claims"


def test_memo_tools_are_in_and_uncarded_ones_are_read_only(raw):
    """E1: the tools a hand-written adoption memo recommended are in, and none is promoted past what was run."""
    m = raw[0]
    tools = {t["id"]: t for t in m["tool"]}
    for tid in ("jscpd", "semgrep", "bandit", "knip", "radon", "lizard", "gitnexus", "codegraph", "import-linter"):
        assert tid in tools, tid
        if not tools[tid].get("card"):
            # Without a card, a claim past `read` must carry its own evidence (jscpd: the Rust benchmark, R1-C112).
            for c in m["claim"]:
                if c["tool"] == tid and c["status"] != "read":
                    assert c.get("evidence"), (tid, c["need"])


# --------------------------------------------------------------------------- E2, E3: the answers


def test_ts_call_graph_is_not_codemap_and_not_measured(cat):
    a = answer({"need": "ts call graph"}, cat)
    assert [x["need"] for x in a["matches"]] == ["multi-lang-graph"]
    row = a["matches"][0]
    assert row["codemap"]["coverage"] == "none"
    by = {v["tool"]: v for v in row["tools"]}
    for tid in ("gitnexus", "codegraph"):
        assert by[tid]["status"] == "read", f"{tid} was never run on TypeScript here"


def test_import_gate_is_codemap_and_import_linter_measured_first(cat):
    a = answer({"need": "import-gate"}, cat)
    row = a["matches"][0]
    assert row["codemap"]["coverage"] == "covered" and row["codemap"]["tests"]
    first = row["tools"][0]
    assert first["tool"] == "import-linter" and first["status"] == "measured"
    assert "266/266" in first["summary"].replace(" ", "") and "45/45" in first["summary"].replace(" ", "")
    assert first["evidence"].startswith("https://github.com/kogriv/codemap/blob/main/research/tools/")


def test_unknown_need_is_a_refusal_with_the_list(cat):
    a = answer({"need": "zzzz qqqq"}, cat)
    assert a["error"].startswith("no need matches") and "py-callers" in a["needs"]
    assert "matches" not in a


def test_db_query_count_says_no_static_tool(cat):
    row = answer({"need": "db-query-count"}, cat)["matches"][0]
    assert row["codemap"]["coverage"] == "none" and "static" in row["note"]


def test_overview_filtered_by_language(cat):
    o = answer({"languages": ["ts"]}, cat)["overview"]
    ids = {r["need"] for r in o["needs"]}
    assert "multi-lang-graph" in ids and "frontend-dead-exports" in ids and "py-callers" not in ids


def test_tool_answer_and_markdown(cat):
    a = answer({"tool": "import-linter", "news_days": 3650}, cat)
    assert a["tool"]["claims"] and "catalog" in a
    text = answer_md(a)
    assert "import-linter" in text and "Catalog as of" in text


def test_match_prefers_exact_id(cat):
    assert match_needs(cat, "py-callers") == ["py-callers"]


# --------------------------------------------------------------------------- staleness and drift


def _mini():
    m = {"meta": {"schema": 1, "as_of": "2026-11-21", "stale_after_days": 100, "repo": "https://example.org/r"},
         "need": [{"id": "n", "title": "N", "codemap": "none"}],
         "tool": [{"id": "t", "name": "T", "url": "https://example.org/t", "watch": {"kind": "none"}}],
         "claim": [{"tool": "t", "need": "n", "status": "measured", "version": "1.2", "checked": "2026-01-01",
                    "evidence": "research/x.md#a", "summary": "s"}]}
    f = {"schema": 1, "as_of": "2026-11-21T00:00:00Z", "latest": {"t": {"version": "1.3.0", "date": "2026-10-01"}},
         "news": []}
    return m, f


def test_stale_and_drift_are_computed_against_the_catalog_not_today():
    m, f = _mini()
    c = Catalog(m, f, {"matrix": "packaged", "feed": "packaged"})
    v = answer({"need": "n"}, c)["matches"][0]["tools"][0]
    assert v["stale"] is True  # 324 days before as_of, threshold 100
    assert v["drift"] == {"measured": "1.2", "latest": "1.3.0", "latest_date": "2026-10-01"}
    m["claim"][0]["checked"] = "2026-11-01"
    f["latest"]["t"]["version"] = "1.2.0"
    v = answer({"need": "n"}, Catalog(m, f, {}))["matches"][0]["tools"][0]
    assert "stale" not in v and "drift" not in v  # 1.2 == 1.2.0


# --------------------------------------------------------------------------- E4: every guard bites


def _first(m, status):
    return next(c for c in m["claim"] if c["status"] == status and c.get("evidence"))


def test_m1_renamed_anchor_is_named(raw):
    m = copy.deepcopy(raw[0])
    c = _first(m, "measured")
    c["evidence"] = c["evidence"].split("#")[0] + "#no-such-heading"
    assert any("no heading #no-such-heading" in p for p in repo_problems(m, ROOT))


def test_m2_measured_without_evidence_is_named(raw):
    m = copy.deepcopy(raw[0])
    c = _first(m, "measured")
    del c["evidence"]
    assert any("requires evidence" in p for p in schema_problems(m, raw[1]))


def test_m3_cited_test_that_does_not_exist_is_named(raw):
    m = copy.deepcopy(raw[0])
    n = next(n for n in m["need"] if n["codemap"] == "covered")
    n["codemap_tests"] = [n["codemap_tests"][0].split("::")[0] + "::test_that_was_never_written"]
    assert any("no test test_that_was_never_written" in p for p in repo_problems(m, ROOT))


def test_m4_matrix_edit_without_render_is_caught(raw, tmp_path):
    m = copy.deepcopy(raw[0])
    m["need"][0]["title"] += " (edited)"
    edited = Catalog(m, raw[1], {"matrix": "packaged", "feed": "packaged"})
    assert matrix_md(edited) != (ROOT / "research" / "matrix.md").read_text(encoding="utf-8")


def test_m5_feed_item_naming_an_unknown_tool_is_named(raw):
    f = copy.deepcopy(raw[1])
    f.setdefault("news", []).append({"date": "2026-11-21", "kind": "release", "tool": "no-such-tool",
                                     "text": "x", "source": "https://example.org", "verified": True})
    assert any("unknown tool 'no-such-tool'" in p for p in schema_problems(raw[0], f))


def test_m6_status_outside_the_vocabulary_is_named(raw):
    m = copy.deepcopy(raw[0])
    m["claim"][0]["status"] = "verified"
    assert any("status 'verified' not in" in p for p in schema_problems(m, raw[1]))


def test_covered_without_a_test_is_named(raw):
    m = copy.deepcopy(raw[0])
    n = next(n for n in m["need"] if n["codemap"] == "covered")
    n["codemap_tests"] = []
    assert any("names no test" in p for p in schema_problems(m, raw[1]))


def test_card_without_a_tool_is_named(raw):
    m = copy.deepcopy(raw[0])
    m["tool"] = [t for t in m["tool"] if t.get("card") != "research/tools/import-linter.md"]
    m["claim"] = [c for c in m["claim"] if c["tool"] != "import-linter"]
    assert any("research/tools/import-linter.md has no tool" in p for p in repo_problems(m, ROOT))


# --------------------------------------------------------------------------- anchors


def test_github_anchor_rules():
    assert github_anchor("§1 — The graph (266 / 266)") == "1--the-graph-266--266"
    assert github_anchor("Разбор: что взять") == "разбор-что-взять"
    assert github_anchor("`ccc` and [link](x.md)") == "ccc-and-link"
    assert anchors("# A\n## A\n```\n# not\n```\n") == {"a", "a-1"}


# --------------------------------------------------------------------------- E5: refresh


@pytest.fixture
def served(tmp_path):
    root = tmp_path / "srv"
    root.mkdir()
    httpd = HTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=str(root)))
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    yield root, f"http://127.0.0.1:{httpd.server_port}/"
    httpd.shutdown()


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):  # noqa: D401
        pass


def _publish(root: Path, m_text: str, f_obj: dict):
    (root / "matrix.toml").write_text(m_text, encoding="utf-8")
    (root / "feed.json").write_text(json.dumps(f_obj), encoding="utf-8")


def test_refresh_newer_older_invalid_absent(served, tmp_path, raw):
    from codemap.advise.refresh import refresh
    root, url = served
    cache = tmp_path / "cache"
    m_text = (DATA / "matrix.toml").read_text(encoding="utf-8")
    f = copy.deepcopy(raw[1])

    # older (same as packaged) → not newer
    _publish(root, m_text, f)
    r = refresh(url, cache)
    assert not r["updated"] and "not newer" in r["reason"]

    # invalid → refused, packaged kept
    _publish(root, m_text, {**f, "as_of": "2999-01-01T00:00:00Z", "schema": 99})
    r = refresh(url, cache)
    assert not r["updated"] and "invalid" in r["reason"]
    assert load(cache=cache).source == {"matrix": "packaged", "feed": "packaged"}

    # newer feed → refreshed, served from cache
    f2 = {**f, "as_of": "2999-01-01T00:00:00Z",
          "news": [{"date": "2999-01-01", "kind": "finding", "tool": None, "text": "from the future",
                    "source": "https://example.org", "verified": False}]}
    _publish(root, m_text, f2)
    r = refresh(url, cache)
    assert r["updated"], r
    c = load(cache=cache)
    assert c.source == {"matrix": "packaged", "feed": "refreshed"}
    assert answer({"news_days": 10**6}, c)["news"][0]["text"] == "from the future"

    # no server → reason, no exception
    r = refresh("http://127.0.0.1:9/", tmp_path / "other")
    assert not r["updated"] and r["reason"].startswith("download failed")


def test_corrupt_cache_falls_back_to_packaged(tmp_path, raw):
    cache = tmp_path / "c"
    cache.mkdir()
    (cache / "matrix.toml").write_text("not = [valid", encoding="utf-8")
    (cache / "feed.json").write_text(json.dumps({**raw[1], "as_of": "2999-01-01T00:00:00Z", "news": [{}]}),
                                     encoding="utf-8")
    c = load(cache=cache)
    assert c.source == {"matrix": "packaged", "feed": "packaged"}
    assert any("ignored" in n for n in c.notes)


# --------------------------------------------------------------------------- D4, E7: the boundary in answers


@pytest.mark.parametrize("name,lang", [("web/app.ts", "typescript"), ("src/x.tsx:12", "typescript"),
                                       ("cmd/main.go::Run", "go"), ("lib.rs", "rust"), ("src/x.c", "c")])
def test_outside_graph_names_the_language(name, lang):
    assert outside_graph(name) == {"language": lang, "advise": {"languages": [lang]}}


@pytest.mark.parametrize("name", ["pkg.mod.func", "pkg/mod.py", "no_such_python_name", "a.b.c", "pkg.mod.go", "x.c", ""])
def test_python_names_get_no_outside_graph(name):
    assert outside_graph(name) is None


def test_session_not_found_carries_outside_graph_only_for_foreign_files():
    from codemap.model import ANSWER_FORMAT
    from codemap.serve.session import Session
    from codemap.extract import extract
    s = Session(extract(ROOT / "tests" / "fixtures" / "flatpkg"))
    ts = s.handle({"op": "query", "args": {"name": "web/app.ts"}})
    py = s.handle({"op": "query", "args": {"name": "no_such_python_name"}})
    assert ts["answer_format"] == ANSWER_FORMAT == 12
    assert ts["resolved"]["found"] is False and ts["resolved"]["outside_graph"]["language"] == "typescript"
    assert py["resolved"]["found"] is False and "outside_graph" not in py["resolved"]
    adv = s.handle({"op": "advise", "args": {"need": "duplicates"}})
    assert adv["ok"] and adv["result"]["matches"][0]["need"] == "duplicates"


def test_advise_is_an_mcp_tool():
    from codemap.serve.mcp_server import _INSTRUCTIONS, MCP_TOOLS
    assert "advise" in MCP_TOOLS and "`advise`" in _INSTRUCTIONS


# --------------------------------------------------------------------------- E10: languages of a repository


def test_detect_languages_skips_vendored(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "app.ts").write_text("export const a = 1\n")
    (tmp_path / "web" / "b.tsx").write_text("export const b = 1\n")
    (tmp_path / "node_modules" / "dep").mkdir(parents=True)
    (tmp_path / "node_modules" / "dep" / "i.js").write_text("")
    assert detect_languages(tmp_path) == {"python": 1, "typescript": 2}


def test_cli_root_names_typescript_and_what_codemap_does_not_cover(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "app.ts").write_text("export const a = 1\n")
    r = subprocess.run([sys.executable, "-m", "codemap", "advise", "--root", str(tmp_path)],
                       capture_output=True, text=True, cwd=ROOT, env=_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "typescript 1" in r.stdout and "multi-lang-graph" in r.stdout
    assert "codemap reads only the Python" in r.stdout


def test_cli_need_json_and_refusal_exit(tmp_path):
    r = subprocess.run([sys.executable, "-m", "codemap", "advise", "zzzz qqqq", "--format", "json"],
                       capture_output=True, text=True, cwd=ROOT, env=_env(tmp_path))
    assert r.returncode == 1 and json.loads(r.stdout)["error"].startswith("no need matches")


def _env(tmp_path):
    import os
    return {**os.environ, "XDG_CACHE_HOME": str(tmp_path / "xdg")}


def test_news_window(raw):
    c = Catalog(raw[0], {**raw[1], "news": [
        {"date": "2026-11-20", "kind": "release", "tool": None, "text": "a", "source": "s", "verified": True},
        {"date": "2026-01-01", "kind": "release", "tool": None, "text": "b", "source": "s", "verified": True}]}, {})
    from codemap.advise import news
    assert [n["text"] for n in news(c, 30, today=date(2026, 11, 21))] == ["a"]


def test_readme_counts_are_the_catalog(cat):
    """D8: the README states the counts the matrix renders; a catalog change updates them in the same commit."""
    o = answer({}, cat)["overview"]
    c = o["claims"]
    want = (f"{len(o['needs'])} needs, {o['tools']} tools, claims\n{c['measured']} measured · {c['probed']} probed · "
            f"{c['read']} read · {c['rejected']} rejected")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert " ".join(want.split()) in " ".join(readme.split()), f"README must say: {want}"


def test_matrix_as_of_is_a_timestamp(raw):
    """Two catalogs published on one day must order: a date-only `as_of` let a same-day matrix look not newer,
    and the newer feed that names its tools was then refused as a pair (found reconciling E11)."""
    assert "T" in raw[0]["meta"]["as_of"] and raw[0]["meta"]["as_of"].endswith("Z")
    assert "T" in raw[1]["as_of"] and raw[1]["as_of"].endswith("Z")


# --------------------------------------------------------------------------- language filter (found 2026-11-21)


def test_language_filter_never_recommends_a_tool_for_a_language_it_does_not_read(cat):
    """Asked for Rust, `complexity` used to offer radon (Python only) and `duplicates` fallow (TS/JS only)."""
    for need in ("complexity", "duplicates"):
        row = answer({"need": need, "languages": ["rust"]}, cat)["matches"][0]
        shown = {v["tool"] for v in row["tools"]}
        assert not shown & {"radon", "wily", "fallow"}, (need, shown)
        assert all("rust" in cat.tools[t]["languages"] or "any" in cat.tools[t]["languages"] for t in shown)
    ex = answer({"need": "complexity", "languages": ["rust"]}, cat)["matches"][0]["excluded"]
    assert "radon" in {x["tool"] for x in ex}


def test_a_python_measurement_is_read_only_for_another_language(cat):
    rust = answer({"need": "semantic-search", "languages": ["rust"]}, cat)["matches"][0]
    jg = next(v for v in rust["tools"] if v["tool"] == "jevgrep")
    assert jg["status"] == "read" and "measured on python only" in jg["status_note"]
    py = answer({"need": "semantic-search", "languages": ["python"]}, cat)["matches"][0]
    assert next(v for v in py["tools"] if v["tool"] == "jevgrep")["status"] == "measured"
    plain = answer({"need": "semantic-search"}, cat)["matches"][0]
    assert next(v for v in plain["tools"] if v["tool"] == "jevgrep")["status"] == "measured"


def test_tool_languages_are_a_closed_vocabulary(raw):
    m = copy.deepcopy(raw[0])
    m["tool"][0]["languages"] = ["multi (tree-sitter)"]
    assert any("languages ['multi (tree-sitter)']" in p for p in schema_problems(m, raw[1]))
    m = copy.deepcopy(raw[0])
    _first(m, "measured")["measured_on"] = ["klingon"]
    assert any("measured_on" in p for p in schema_problems(m, raw[1]))
