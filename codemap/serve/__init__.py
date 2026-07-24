"""Serve layer: views/reports over the canonical graph (DESIGN §4)."""

from codemap.serve.api_surface import render_api_surface
from codemap.serve.audit import render_dead_code, render_dependencies

__all__ = ["render_api_surface", "render_dependencies", "render_dead_code"]
