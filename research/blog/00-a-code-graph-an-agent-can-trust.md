# A code graph an agent can trust

*Agents navigating code have two bad options: grep (exact but structure-blind) and embeddings (fuzzy and perpetually stale). The third path — a precise structural graph — kept shipping as an opaque index that rots on the next commit. codemap is that third path, done diffable.*

**codemap build-story · post 0** · [Русская версия](00-a-code-graph-an-agent-can-trust.ru.md) · [Series index](README.md) · [The repo](https://github.com/kogriv/codemap)

---

> **A code graph an agent can trust: source-only, deterministic, diffable — no index to go
> stale, no LSP to provision.**

This is the launch post for a series about **[codemap](https://github.com/kogriv/codemap)**,
an open-source (MIT) tool I've been building. The rest of the series is field notes —
teardowns of rival tools, measured head-to-head, one honest surprise at a time. This post is
the *why*: what codemap is, the bet it makes, and where it sits in a crowded field.

## The itch

An AI agent working in a codebase has two well-worn options, and both are bad in a specific
way.

**grep** is exact and instant, and completely blind to structure. It will find you the
string `MACDZoneAnalyzer`, but it cannot tell you *who calls it*, *what breaks if you change
its signature*, or *which of those hits are in core versus tests*. It matches text; it
doesn't understand code.

**Embeddings / RAG** understand *meaning* — ask "where's the swing-detection logic" and a
vector search will find it without knowing the name. But the answer is fuzzy, it's
non-deterministic (run it twice, get two rankings), and it is **perpetually stale**: the
index reflects the repo as it was at embed time, and code moves every commit. You provision
a model, wait out an embedding pass, and still get a probabilistic answer to a question that
often has an exact one.

There's an obvious third path: a **precise structural graph** — real nodes and edges,
*this function calls that one*, resolved. The trouble is how it kept getting built: as an
opaque, non-diffable index (LSIF, vendor databases) that rots the moment code changes and
can't be reviewed in a pull request. The precision was real; the *artifact* was a black box.

## The bet

codemap takes the third path and fixes the artifact. Four commitments:

- **Source-only.** It reads source with griffe and jedi — no compile, no venv, no runtime
  import. It works on any package, on any machine, offline, and stays completely decoupled
  from the code it analyzes. There is no language server to bring up (a decision the very
  [first post in this series](01-the-competitor-wasnt-broken.md) turns out to be about).
- **Canonical and diffable.** The artifact is one `graph.json`: sorted, timestamp-free,
  byte-stable across runs. A graph you can `git diff`. Check it into the repo and a
  structural change shows up in code review like any other diff.
- **Provenance-aware.** Every node knows where it came from — package core, tests, docs,
  examples, scripts. So "what breaks if I change this?" has a *better* answer than a flat
  count: 2 references in core, 7 in docs, 53 in tests. That distinction is the difference
  between "this is load-bearing" and "this is well-covered."
- **Agent-native.** The graph is exposed as verbs an agent calls over MCP — `impact`,
  `callers`, `callees`, `architecture`, `review` — not a query language it has to learn.

## The arc, in four movements

codemap grew in public over roughly twenty milestones. Compressed:

1. **The graph exists.** Canonical structure (imports / exports / inherits), a query API, a
   behavioral call graph, deep call resolution via jedi, and render views (RAG chunks, an
   Obsidian vault, mermaid). The foundation: a deterministic graph out of pure source.
2. **The graph gets opinionated.** Multi-root **provenance** and impact/blast-radius;
   registry-aware call bridging; **provenance-aware dead-code** (the usefulness of vulture
   without its dominant false-positive source); per-call-site argument contracts; string-key
   column dataflow. This is where it stops being a parse tree and starts answering real
   questions.
3. **Ergonomics and altitude.** Discovery (search / families / source / resolve); soundness
   (ambiguity is *surfaced*, never silently resolved); **change-review** (a diff → a
   risk-sorted dossier); an **architecture** view (layers, coupling, god-objects, cycles).
4. **Agent-native and honest about time.** The **MCP adapter** (the graph as agent tools);
   and **freshness** — a static graph now reports its own age, tells you when it's behind the
   code, rebuilds only the modules that changed (~12× faster on a one-file edit), and can be
   reloaded into a running server without a restart. Determinism is preserved by keeping the
   build recipe in a sidecar, never in the graph.

Where it stands today: schema **0.11**, ~**369 tests** green, a warm serve surface of
**29 operations** (26 of them exposed as MCP tools), plus **SCIP export** so
Sourcegraph / Glean and other precise-code-intelligence tools light up over codemap's graph.
It interoperates outward rather than locking its graph away.

## Where it sits in the field

I didn't want to assert a niche — I wanted to measure into one. So the series' research track
placed codemap against every adjacent tool on the same axes. The under-served spot it landed
in: a **semantic (resolved) code graph** that is simultaneously **deterministic**,
**source-only**, **Python-deep**, and **agent-facing**. The neighbours each miss one axis —
embeddings tools aren't deterministic; ctags and LSIF aren't resolved; a language server is
ephemeral; the heavy graph databases (Kythe, Glean) need a compiler. None of them is *wrong*;
they're playing adjacent games. codemap's bet is to own that one intersection and
interoperate with the rest.

## The honest part

A launch post that only flatters isn't believed, and neither is a graph. The real limits:

- **No cross-boundary resolution into dependencies.** codemap is source-only *of the
  target*; it won't tell you which pandas API a call hits. Some tools can — by design, but a
  real limit. (The first teardown in this series is exactly about one of those tools.)
- **Python only.** The peers that span a dozen languages buy that breadth by leaning on
  tree-sitter or LSP. codemap's depth is bought with Python-specificity. A deliberate trade,
  not an oversight.
- **Deep resolution has variance.** The jedi-backed deep tier is bounded and
  cache-sensitive; two full deep builds can differ by a handful of edges. The
  fast/structural layers are fully deterministic — and that's the layer the "diffable" claim
  rests on.

## Try it, and catch me where I'm wrong

```bash
pip install codemap        # (name TBD — see the repo)
codemap build ./yourpkg --deep -o graph.json
codemap serve --graph graph.json            # warm process, JSON over stdin/stdout
codemap serve --graph graph.json --mcp      # …or as MCP tools for an agent
```

The next posts get concrete and adversarial: I run codemap against the nearest rival tools
on a shared target, measure five questions each, and report the surprises — including the
one where I nearly published that a competitor was broken and it turned out to be my own
mistake.

*codemap is open source (MIT): [github.com/kogriv/codemap](https://github.com/kogriv/codemap).
The full research track — every command, version, and number — is public, so you can
reproduce the comparisons or catch me where I'm wrong. Measured your tool and I got it wrong?
Open an issue. The harness is public.*
