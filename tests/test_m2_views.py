"""M2 acceptance tests — human/AI views (RAG, Obsidian vault, mermaid).

Views over the existing graph (no new extraction). Small synthetic fixture for
structure + a couple of real-bquant sanity checks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codemap.extract import extract
from codemap.query import Query
from codemap.serve import build_vault, render_mermaid, render_rag

FIX = Path(__file__).resolve().parent / "fixtures" / "deeppkg"
BQUANT = Path(__file__).resolve().parents[2] / "bquant"


@pytest.fixture(scope="module")
def fix_q():
    return Query(extract(FIX, deep=True))


@pytest.fixture(scope="module")
def bq_q():
    if not BQUANT.is_dir():
        pytest.skip("bquant not found")
    return Query(extract(BQUANT))


# -- M2.1 RAG -----------------------------------------------------------------

def test_rag_jsonl_chunks(fix_q):
    lines = render_rag(fix_q).splitlines()
    chunks = [json.loads(l) for l in lines]
    by_id = {c["id"]: c for c in chunks}
    run = by_id["deeppkg.core.Engine.run"]
    assert run["kind"] == "function"
    assert run["signature"].startswith("run(")
    # neighborhood carries the graph edges an AI can't cheaply get from source
    assert "deeppkg.core.Engine._step" in run["neighbors"]["calls"]
    assert "deeppkg.app.main" in run["neighbors"]["called_by"]
    assert "Engine" in run["text"] and "Calls:" in run["text"]


def test_rag_is_valid_jsonl(bq_q):
    lines = render_rag(bq_q).splitlines()
    assert len(lines) > 500
    for l in lines[:50]:
        json.loads(l)  # every line parses


# -- M2.2 Obsidian vault ------------------------------------------------------

def test_vault_notes_and_wikilinks(fix_q):
    vault = build_vault(fix_q)
    assert "index.md" in vault
    note = vault["deeppkg.core.Engine.run.md"]
    assert "#function" in note
    assert "[[deeppkg.core.Engine._step|_step]]" in note  # calls wikilink
    assert "[[deeppkg.app.main|main]]" in note             # called-by wikilink


def test_vault_class_note_links_bases(bq_q):
    vault = build_vault(bq_q)
    note = vault["bquant.indicators.base.CustomIndicator.md"]
    assert "[[bquant.indicators.base.BaseIndicator|BaseIndicator]]" in note


# -- M2.3 mermaid -------------------------------------------------------------

def test_mermaid_class_diagram(fix_q):
    out = render_mermaid(fix_q, "class")
    assert out.startswith("```mermaid\nclassDiagram")
    assert out.rstrip().endswith("```")


def test_mermaid_deps_scoped(bq_q):
    out = render_mermaid(bq_q, "deps", scope="bquant.analysis.zones")
    assert "graph LR" in out
    # every node line is within the scope
    for line in out.splitlines():
        if line.strip().startswith("bquant_") and "[" in line:
            assert "bquant_analysis_zones" in line


def test_mermaid_calls_rooted(bq_q):
    out = render_mermaid(bq_q, "calls", root="analyze_zones", depth=1)
    assert "graph LR" in out
    assert "analyze_zones" in out


def test_mermaid_calls_needs_root(fix_q):
    with pytest.raises(ValueError):
        render_mermaid(fix_q, "calls")
