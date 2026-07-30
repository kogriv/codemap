# research

A planned track (not yet active): survey adjacent code-analysis / code-graph tools and work out how
codemap should relate to each — **direct integration**, a **thin wrapper/adapter**, or just a
**reference/comparison**. The reuse strategy and the exact write-up format are open; the current
intention is a simple set of Markdown reports, one per tool or theme.

This track starts only after the core (P1 graph + serve surface) reaches a natural stopping point, so
the comparison is grounded in a working baseline rather than done up front.

## Scope sketch (to be filled in)

- Landscape: what similar tools exist (static graph builders, call-graph/impact tools, doc/RAG-from-code,
  LSP-backed indexers), and where each sits relative to codemap's source-only / deterministic / CLI-AI-first
  stance.
- Per tool: what it does well, its data model, its boundaries — and whether codemap should integrate it,
  wrap it, or merely learn from it.
- Findings feed back into [../BACKLOG.md](../BACKLOG.md) and the [axis register](../gaps/dogfood_axes.md)
  as concrete capabilities, not speculative features.

_Placeholder — add reports here as the track opens._
