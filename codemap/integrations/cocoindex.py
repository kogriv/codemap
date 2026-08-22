"""cocoindex-code adapter (DESIGN §13.1, mode 3 — adapter / retrieval).

cocoindex-code (`ccc`, github.com/cocoindex-io/cocoindex-code) is an **Apache-2.0**
semantic code-search CLI: tree-sitter chunking + local embeddings, an embedded
index (no DB, no API key). codemap has no fuzzy/semantic layer by design, so this
is the first tool that fills that gap — and because its license is permissive, it
can be an **adapter** (we translate its output into codemap's own contract), not a
router. See ``research/tools/cocoindex-code.md``.

The "translation" is the whole point: `ccc` returns fuzzy locations
(``file`` + line range + score); codemap resolves each to the **exact symbol** at
that location via its graph (:func:`codemap.integrations.semantic.semantic_search`).
So a concept query comes back as ranked codemap symbols — the "fuzzy retrieval →
exact structure" composition neither tool gives alone.

This module only builds the argv and returns raw hits; enrichment against the graph
lives in the semantic module (the adapter never needs the graph). Opt-in (the
registry gates on ``codemap.toml``); reached only when `ccc` is installed. Anything
wrong — missing binary, non-JSON — degrades to "no hits" (``run_json`` → None).

`ccc` keys off its per-repo index in the working directory, so the caller passes the
repo ``root`` as the subprocess cwd (that's where ``ccc index`` was run).
"""

from __future__ import annotations

from typing import Any

from .base import Integration, IntegrationMode
from .registry import register
from .transport import run_json, which

_BINARY = "ccc"


class CocoIndexAdapter(Integration):
    name = "cocoindex"
    mode = IntegrationMode.ADAPTER
    license = "Apache-2.0"
    capabilities = ("semantic-search",)

    def is_available(self) -> bool:
        return which(_BINARY) is not None

    def _argv(self, query: str, limit: int) -> list[str]:
        """`ccc search <query> --limit N --json` (version-tolerant; drift → no hits)."""
        return [_BINARY, "search", query, "--limit", str(limit), "--json"]

    def search(self, capability: str, query: str, **kw: Any) -> list[dict[str, Any]]:
        """Run `ccc search` in the repo ``root`` and return raw location hits.

        Returns ``[{file, start_line, end_line, score}, …]`` (already sorted by score
        by `ccc`); enrichment to codemap symbols happens in the semantic module.
        """
        if capability not in self.capabilities:
            raise ValueError(f"cocoindex does not provide {capability!r}")
        root = kw.get("root")
        limit = int(kw.get("limit", 10))
        payload = run_json(self._argv(query, limit),
                           timeout=float(kw.get("timeout", 120.0)), cwd=root)
        if not isinstance(payload, dict) or not payload.get("success"):
            return []
        hits = []
        for r in payload.get("results", []):
            fp = r.get("file_path")
            sl = r.get("start_line")
            if fp is None or sl is None:
                continue  # a hit we can't anchor is useless for enrichment
            hits.append({
                "file": fp,
                "start_line": int(sl),
                "end_line": r.get("end_line"),
                "score": float(r.get("score", 0.0)),
            })
        return hits


register(CocoIndexAdapter())
