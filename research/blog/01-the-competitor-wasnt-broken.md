# The competitor wasn't broken. We were.

*I almost published that a rival code-graph tool's impact analysis was broken. It returned zero callers for a class mine mapped in full. The bug was my PATH — and the hour I spent proving myself wrong is the most honest paragraph in the whole comparison.*

**codemap build-story · post 1** · [Русская версия](01-the-competitor-wasnt-broken.ru.md) · [Series index](README.md) · [The repo](https://github.com/kogriv/codemap)

---

> This is one post in a series on building **codemap** — a static code graph an agent can
> trust: source-only, deterministic, diffable — no index to go stale, no LSP to provision.
> The series has a rule: *measurements, not verdict.* This is the post where that rule saved
> me from being wrong in public.

I build a tool called [codemap](https://github.com/kogriv/codemap). It turns a Python
package's **source** — no build, no venv, no runtime import — into a deterministic code
graph you can query: *who calls this, what breaks if I change that signature, which of
those references are in core vs tests vs docs.* It hands those answers to an AI agent over
MCP.

To know whether it's any good, I have to measure it against the field. So I run a
**разбор** — a hands-on teardown — of every adjacent tool, on the *same* target package,
with the *same* five questions, before I build the matching capability myself. The rule I
inherited for these: you come with measurements, not a verdict. The other author is a
potential collaborator, not a review target.

This is the story of the разбор that nearly broke that rule — and what it cost to keep it.

## The nearest twin

The tool is **graphlens-mcp**: a code-graph-for-agents, over MCP, just like codemap. But
where codemap deliberately provisions *nothing*, graphlens is ambitious about its backend —
it drives Astral's `ty` (an LSP-grade type checker) plus tree-sitter, and persists to
SQLite. On paper this is the tool that *should* beat me at impact analysis. If precise
type resolution is what makes "who calls this" trustworthy, graphlens has more of it than I
do.

So I gave it a fair scope — the exact six directories codemap indexes on my dogfood target,
the `bquant` package — and let it work. It indexed in **12 seconds**. Fast. Promising.

Then I asked it the core question, the one the whole category exists to answer:

> *Who calls `MACDZoneAnalyzer`?*

It came back **empty**. Zero callers. Zero references.

codemap answered the same question with a full breakdown — references split by where they
live in the tree. graphlens returned nothing at all.

## The cheap verdict I almost shipped

I had my card half-written in my head: *graphlens degrades to grep on a real source tree.
Learn-only. Nothing to take.* It's a clean, quotable finding. It flatters my tool. And it
would have been the kind of thing you write at the end of a long day and push before you
sleep.

One detail stopped me.

graphlens's own response hadn't *lied*. Buried in the payload was a field:

```json
"resolver_status": "degraded"
```

The tool was **telling me** its type resolver never came up. It wasn't claiming a
confident empty answer — it was flagging that it had fallen back to something less. And a
tool this carefully built — bundling `ty`, persisting to SQLite, exposing an honest status
field — does not ship with impact analysis that simply *doesn't work*. Either the author
shipped something broken, or **I was holding it wrong.**

"It returned nothing" is a hypothesis. It is not a finding. So I opened the hood.

## One line

The Python resolver spawns `ty` like this:

```python
ty_bin = shutil.which("ty") or "ty"        # graphlens_python/_resolver.py:34
```

graphlens *bundles* its own `ty` binary — it ships inside the installed tool. But
`uv tool install` only puts the package's declared entry point (`graphlens-mcp`) on your
`PATH`. It does **not** put the bundled `ty` there. So `shutil.which("ty")` returned
`None`, the code fell back to the bare string `"ty"`, the spawn raised `FileNotFoundError`
— and a broad `except Exception:` in `prepare()` swallowed it and quietly dropped to
tree-sitter-only.

**Silent degrade.** The empty impact wasn't graphlens's weakness. It was my environment.
The bundled resolver was sitting right there on disk, never invoked, because a `which()`
call couldn't see it.

The fix was one line: put the bundled binary's directory on `PATH` before launching.

## What happened when I ran it fair

`ty server` came up. `resolver_status` flipped to **`ok`**. And the tool became a
completely different thing:

| | tree-sitter only (broken) | **ty-resolved (fixed)** |
|---|---|---|
| index time | 12 s | **2 m 20 s** (12×) |
| DB size | 17.5 MB | 31 MB |
| nodes / edges | 16 796 / 20 889 | **32 399 / 55 691** |
| `relations(MACDZoneAnalyzer)` | **empty** | **9 callers + 1 callee + 2 refs** |

Those extra ~35 000 edges are exactly the resolved calls and references that were missing.
The impact engine was never broken. It had **never run.** My twelve-second index was
twelve seconds because two-thirds of the work never happened.

## The honest head-to-head

Now I could do the comparison I'd come for — same target, same question, both tools
working:

- **codemap** `impact(MACDZoneAnalyzer)`: **31 references, one resolved call**, split by
  provenance — core 2 · docs 7 · examples 1 · scripts 2 · **tests 19**.
- **graphlens** `relations(MACDZoneAnalyzer)`: **9 callers + 1 callee + 2 refs**, with
  `resolver_status: ok`.

At first the numbers look far apart — until you read graphlens's source. It
**auto-hides test call-sites by default**, and it's a *deliberate* choice, commented right
there:

```python
# lean.py:53 — keep an agent's context budget from drowning in test call-sites
```

That's not a bug or an evasion. It's a design opinion: an agent has a finite context
window, and burying the real answer under fifty test references is its own kind of failure.
codemap makes the opposite choice — it *keeps* the tests and **tags** them, so you can ask
"what breaks in core?" and "what breaks in tests?" separately. Different bets, both
defensible.

And on the part where the two models actually overlap — the **non-test resolved call
graph** — they nearly agree: codemap 12, graphlens ~9–11. The engine is **sound.** The
disagreement was never about correctness. It was about what each tool chooses to show.

*(Reproducibility note: these numbers were measured on a pinned `bquant` revision recorded
in the graphlens card; `bquant` has since restructured that module, so treat the figures as
a dated snapshot, not today's `bquant`. The point of the story is the method, and the
method reproduces on any target.)*

## What I take, and what I keep

The разбор rule is: come away with what you'd **take** and what you'd **keep** — not a
scoreboard.

**Take (learn from it):**
- **Cross-boundary resolution into dependencies.** graphlens can tell you *what pandas API
  this call hits.* codemap is source-only-*of-the-target* and can't — a real capability I
  lack.
- **The context-budget test-de-emphasis heuristic.** Hiding tests by default is a
  legitimate answer to the agent-context problem, even though I solve it differently.
- **Watch-mode incremental re-index** — which fed straight into my own freshness work.

**Keep (my edge — now measured against a *working* competitor, not a broken one):**
- **Determinism you can `git diff`:** a ~3.6 MB canonical, timestamp-free JSON graph versus
  a 31 MB SQLite database. You can review my graph in a pull request.
- **Single-call, provenance-complete impact** — the core/tests/docs split in one answer.
- **Provisions nothing.** No LSP to bring up, works offline. (The irony is not lost on me:
  the entire incident was a resolver that failed to provision. A tool with no resolver to
  provision can't degrade that way.)
- **Capabilities graphlens has no tool for** — per-call-site argument contracts, and a
  whole-system architecture view (layers, coupling, cycles).

**Verdict:** not "nothing to take." A **competent peer** — one I learn from but don't
integrate, because the theses overlap and its half is heavier, non-deterministic, and
LSP-dependent. Which is a far more useful — and far more *true* — thing to be able to say
than "it's broken."

## The three lessons (the reusable part)

1. **A graph tool can silently degrade to grep.** The single most important thing to check
   before you *trust* — or *benchmark* — any resolved-graph tool is: *did the resolver
   actually come up?* Look for the `resolver_status == ok` (or equivalent) before you
   believe a single edge. This is now a hard gate in my benchmark harness. An empty answer
   from a degraded resolver looks identical to a confident "there's nothing here" — and
   those are opposite facts.

2. **"It returned nothing" is a hypothesis, not a finding.** The cheap verdict —
   *competitor is broken* — was wrong, and would have been unfair to a well-built tool and
   its author. The extra hour turned a false takedown into a real, respectful comparison.
   In a field this young, the reputational cost of a confident-and-wrong teardown is paid by
   everyone.

3. **Bundling a binary but resolving it via `shutil.which` is a trap.** If you ship a
   companion executable, don't look it up on the user's `PATH` — resolve it relative to your
   own install location, and fall back to `PATH` only as a courtesy. This is a genuine,
   reportable packaging bug, and the friendly thing to do is send the author a note, not a
   subtweet.

---

I set out to measure a competitor and instead spent an hour proving my own first result
wrong. That hour is the most honest paragraph in the whole comparison — and it's the reason
I trust the rest of the numbers. A tool that claims to be a code graph you can *trust* has
to be built by someone willing to distrust his own screenshot.

*codemap is open source (MIT): [github.com/kogriv/codemap](https://github.com/kogriv/codemap).
The full teardown — every command, version, and number — lives in the research track's
comparison hub, so you can reproduce it or catch me where I'm wrong. Measured your tool and
I got it wrong? Open an issue. The harness is public.*
