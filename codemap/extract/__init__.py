"""Extractors: source -> neutral graph. v1 ships the Python (griffe) extractor.

Extractors are the only language-aware layer (DESIGN §12): each emits into the
neutral model, so adding a language later is additive, not a core rewrite.
"""

from codemap.extract.griffe_extractor import extract

__all__ = ["extract"]
