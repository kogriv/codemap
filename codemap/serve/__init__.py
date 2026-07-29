"""Serve layer: views/reports over the canonical graph (DESIGN §4)."""

from codemap.serve.api_surface import render_api_surface
from codemap.serve.audit import render_behavior, render_dead_code, render_dependencies
from codemap.serve.impact import render_impact
from codemap.serve.mermaid import render_mermaid
from codemap.serve.rag import build_chunks, render_rag
from codemap.serve.session import Session, build_query_result
from codemap.serve.vault import build_vault

__all__ = [
    "Session",
    "build_query_result",
    "render_api_surface",
    "render_dependencies",
    "render_dead_code",
    "render_behavior",
    "render_impact",
    "render_mermaid",
    "render_rag",
    "build_chunks",
    "build_vault",
]
