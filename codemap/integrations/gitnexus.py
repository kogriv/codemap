"""GitNexus router (DESIGN §13.1, mode 4 — passthrough).

GitNexus (github.com/…/gitnexus) is a TS/Node code-graph tool with capabilities
codemap lacks: **BM25 + local-embedding semantic search (RRF)**, Leiden community
clusters, and process/flow tracing. It is licensed **PolyForm Noncommercial 1.0.0**,
so per DESIGN §13.1 it can only be a **router**: we forward the question and return
its answer untouched — never absorb it into our graph (that would require a
permissive license), never bundle it (calling ≠ distributing, п.1).

This module only builds the argv and wraps the reply; it is opt-in (the registry
gates on ``codemap.toml``) and reached only when the user has ``gitnexus`` installed.
Anything wrong — missing binary, bad flag, non-JSON — degrades to "unavailable"
(``transport.run_json`` returns None), never wrong data.

GitNexus ships as an npm package; a plain ``npm install gitnexus`` puts the binary
in a local ``node_modules/.bin`` (1.7 GB of native modules), **not** on the global
PATH — so ``which('gitnexus')`` alone would report "unavailable" even right after a
successful install. ``_launcher`` therefore prefers a global binary but falls back
to ``npx --no-install gitnexus``, which runs a locally-installed package **without**
triggering a surprise network download (if it isn't installed, ``npx --no-install``
fails and we degrade to None — on-brand: no egress, no bundling).

CLI flag details are version-specific (measured against v1.6.9, see
``research/tools/gitnexus.md``); the graceful-degrade contract means a flag drift
surfaces as "no answer", not a crash.
"""

from __future__ import annotations

from typing import Any

from .base import Integration, IntegrationMode, RawAnswer
from .registry import register
from .transport import run_json, which

_BINARY = "gitnexus"

# capability → the GitNexus verb that serves it (documented verbs, v1.6.9).
_VERB = {
    "semantic-search": "search",   # BM25 + local embeddings + RRF
    "flow-narrative": "trace",     # process/flow tracing from entry points
    "community-clusters": "check",  # Leiden clusters (with --clusters)
}


class GitNexusRouter(Integration):
    name = "gitnexus"
    mode = IntegrationMode.ROUTER
    license = "PolyForm-Noncommercial-1.0.0"
    capabilities = tuple(_VERB)

    def _launcher(self) -> list[str] | None:
        """How to invoke gitnexus, or None if it can't be reached.

        Global binary on PATH wins; else ``npx --no-install gitnexus`` (serves a
        local ``npm install gitnexus`` without a global install and without a
        surprise download); else None → the capability is unavailable.
        """
        if which(_BINARY) is not None:
            return [_BINARY]
        if which("npx") is not None:
            return ["npx", "--no-install", _BINARY]
        return None

    def is_available(self) -> bool:
        return self._launcher() is not None

    def _verb_argv(self, capability: str, question: str) -> list[str]:
        """The gitnexus-specific argv tail (verb + args), launcher-independent."""
        verb = _VERB[capability]
        argv = [verb]
        if capability == "community-clusters":
            argv += ["--clusters"]
        else:
            argv += [question]
        return argv + ["--json"]

    def _argv(self, capability: str, question: str, launcher: list[str]) -> list[str]:
        """Full argv = how-to-invoke + what-to-run (best-effort, version-specific)."""
        return launcher + self._verb_argv(capability, question)

    def route(self, capability: str, question: str, **kw: Any) -> RawAnswer:
        if capability not in self.capabilities:
            raise ValueError(f"gitnexus does not provide {capability!r}")
        launcher = self._launcher()
        payload = None if launcher is None else run_json(
            self._argv(capability, question, launcher),
            timeout=float(kw.get("timeout", 120.0)))
        return RawAnswer(source=self.name, payload=payload,
                         disclaimer=self.disclaimer())


register(GitNexusRouter())
