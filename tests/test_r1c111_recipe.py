"""R1-C111 — the Rust recipe in the catalog (docs/design/recipe_rust.md D8, expectations E16–E19).

The guards run on the packaged catalog; each has a mutation beside it that breaks the data in memory and
expects the guard to name the break, with the unbroken data as the control.
"""

from __future__ import annotations

import copy
import json
import tomllib
from pathlib import Path

import pytest

from codemap.advise import DATA, Catalog, answer, need_answer, overview, repo_problems, schema_problems
from codemap.advise.render import answer_md

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def raw():
    m = tomllib.loads((DATA / "matrix.toml").read_text(encoding="utf-8"))
    f = json.loads((DATA / "feed.json").read_text(encoding="utf-8"))
    return m, f


def _cat(m, f) -> Catalog:
    return Catalog(m, f, {"matrix": "packaged", "feed": "packaged"})


@pytest.fixture(scope="module")
def cat(raw):
    return _cat(*raw)


def _recipe(m, need):
    return next(r for r in m["recipe"] if r["language"] == "rust" and r["need"] == need)


# --------------------------------------------------------------------------- E16: shown first, says the right thing


def test_rust_overview_starts_with_the_recipe(cat):
    a = answer({"languages": ["rust"]}, cat)
    md = answer_md(a)
    assert md.index("## Recipe for rust") < md.index("# What codemap covers")
    by = {r["need"]: r for r in a["recipe"]}
    assert [x["tool"] for x in by["rs-module-cycles"]["use"]] == ["codegraph"]
    assert {x["tool"] for x in by["rs-security-deps"]["use"]} == {"cargo-audit", "cargo-deny"}
    lab = {"codegraph", "gitnexus", "roam-code", "ontoindex", "graphlens-mcp"}
    assert not lab & {x["tool"] for x in by["rs-dead-code"]["use"]}
    assert {"gitnexus", "ontoindex", "roam-code"} <= {x["tool"] for x in by["rs-dead-code"]["avoid"]}


def test_a_need_answer_carries_its_recipe_row_only_under_the_language(cat):
    with_lang = answer({"need": "rs-impact", "languages": ["rust"]}, cat)["matches"][0]
    assert with_lang["recipe"][0]["use"][0]["tool"] == "codegraph"
    assert all("recipe" not in m for m in answer({"need": "blast radius"}, cat)["matches"])
    # A language named in the question works like --lang ("rs" is an alias of rust).
    assert answer({"need": "rust blast radius"}, cat)["matches"][0]["recipe"]
    assert "recipe" not in answer({}, cat)


def test_root_on_a_rust_tree_shows_the_recipe(cat, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.rs").write_text("pub fn f() {}\n")
    from codemap.advise import detect_languages
    langs = sorted(detect_languages(tmp_path))
    assert langs == ["rust"]
    assert answer({"languages": langs}, cat)["recipe"]


# --------------------------------------------------------------------------- E17: Rust numbers are in


def test_rust_measured_claims_cover_several_tools_and_needs(raw):
    rust = [c for c in raw[0]["claim"] if c["status"] == "measured" and "rust" in c.get("measured_on", [])]
    lab = {"codegraph", "gitnexus", "roam-code", "ontoindex", "graphlens-mcp", "jscpd"}
    assert len({c["tool"] for c in rust} & lab) >= 5
    assert len({c["need"] for c in rust}) >= 4


# --------------------------------------------------------------------------- E18: the guards bite


def test_shipped_recipes_pass_the_guards(raw):
    assert schema_problems(*raw) == []
    assert repo_problems(raw[0], ROOT) == []


@pytest.mark.parametrize("mutate, expect", [
    (lambda m: _recipe(m, "rs-module-cycles")["use"].append({"tool": "no-such-tool", "why": "x"}),
     "unknown tool 'no-such-tool'"),
    (lambda m: _recipe(m, "rs-module-cycles").__setitem__("need", "no-such-need"), "unknown need"),
    (lambda m: _recipe(m, "rs-module-cycles").__setitem__("language", "klingon"), "is not a language name"),
    (lambda m: _recipe(m, "rs-impact").pop("evidence"), "cites a number without evidence"),
    (lambda m: next(c for c in m["claim"] if c["tool"] == "codegraph" and c["need"] == "rs-impact").pop("measured_on"),
     "without measured_on ['rust']"),
])
def test_each_recipe_guard_names_its_break(raw, mutate, expect):
    m = copy.deepcopy(raw[0])
    mutate(m)
    problems = schema_problems(m, raw[1])
    assert any(expect in p for p in problems), problems


def test_recipe_evidence_must_resolve(raw):
    m = copy.deepcopy(raw[0])
    _recipe(m, "rs-layers")["evidence"] = "research/tools/_rust/README.md#no-such-heading"
    assert any("no heading #no-such-heading" in p for p in repo_problems(m, ROOT))


# --------------------------------------------------------------------------- E19: Python answers do not move


def _without_rust(m: dict) -> dict:
    m = copy.deepcopy(m)
    rs_needs = {n["id"] for n in m["need"] if n.get("languages") == ["rust"]}
    rs_tools = {t["id"] for t in m["tool"] if t.get("languages") == ["rust"]}
    m.pop("recipe", None)
    m["need"] = [n for n in m["need"] if n["id"] not in rs_needs]
    m["tool"] = [t for t in m["tool"] if t["id"] not in rs_tools]
    m["claim"] = [c for c in m["claim"]
                  if c["need"] not in rs_needs and c["tool"] not in rs_tools and "rust" not in c.get("measured_on", [])]
    return m


def test_python_answers_are_those_of_the_catalog_without_rust(raw):
    full, bare = _cat(*raw), _cat(_without_rust(raw[0]), raw[1])
    # Needs that name Python. Language-neutral needs (`duplicates`) legitimately gain Rust claims, shown under a
    # Python filter as `read` with a note; that is the measured_on downgrade of R1-C110, tested there.
    py = [nid for nid, n in bare.needs.items() if "python" in n.get("languages", [])]
    assert py
    for nid in py:
        assert need_answer(full, nid, {"python"}) == need_answer(bare, nid, {"python"}), nid
    rows = lambda c: [r for r in overview(c, ["python"])["needs"] if r["need"] in py]  # noqa: E731
    assert rows(full) == rows(bare)
    assert "recipe" not in answer({"languages": ["python"]}, full)
