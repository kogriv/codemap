# My determinism test went red. The tool was fine.

*"Same source in, byte-identical graph out" is codemap's headline claim. A test pins it. One afternoon it failed — and the extractor was innocent. The half-hour of chasing the wrong bug turned into the thing the tool had been missing since day one.*

**codemap build-story · post 4** · [Русская версия](04-the-determinism-test-that-was-right.ru.md) · [Series index](README.md) · [The repo](https://github.com/kogriv/codemap)

---

> **A code graph an agent can trust: source-only, deterministic, diffable — no index to go
> stale, no LSP to provision.**

Every other post in this series measures codemap against a rival. This one is about being
wrong on my own turf, and about a property I had spent months building and had never made
*checkable*.

## The claim, and the test that guards it

codemap writes a canonical `graph.json`: sorted, **timestamp-free**, no machine-local paths.
That's what makes it diffable — you can put it in a pull request and read what changed. The
guard is embarrassingly simple:

```python
def test_determinism_with_edges():
    assert store.dumps(extract(BQUANT)) == store.dumps(extract(BQUANT))
```

Build the dogfood target twice, compare the bytes. It had been green for months.

On 24 August, in the middle of an unrelated fix, it went red.

## Chasing the wrong bug

The obvious reading is that the extractor is nondeterministic. Some dict ordering, some set
iteration, some cache warmth. And that reading had a precedent I'd already documented: the
jedi-backed **deep tier** genuinely is cache-sensitive — two full deep builds of the same
tree can differ by a handful of edges, because bounded type inference resolves a chain on a
warm cache that it gives up on when cold. So I went looking in my own sorting code.

It wasn't that.

Another process was editing the target **between the two builds**. A neighbouring agent was
committing to the sibling repo while my test read it; a file I had just seen vanished
before the second `extract()` call. The tool was behaving perfectly. The input had moved.

Here's the part that stung: **nothing in either artifact could tell those two explanations
apart.** Two `graph.json` files that differ, and no field in either one says which tool read
which tree at which revision. Settling it took a manual rebuild on a frozen copy of the same
sources — byte-identical, as it should be.

Half an hour to answer a question the file should have answered by existing.

## Then I asked the question properly, and it got worse

If the artifact can't identify its input, can it identify its *producer*? Take a **frozen**
tree — nothing moving, byte-identical input — and build it with codemap at two commits four
apart:

| | edges | `report dead-code` **high** |
|---|---|---|
| built at `4858899` | 30 | **12** |
| built at `16fe7de` | 38 | **7** |

Five functions that one graph calls dead and the other calls live. And **both files declare
`codemap_schema: "0.11"`**. The current tool loaded either one without a word — answering
with today's confidence over yesterday's blindness.

Now, the tempting conclusion is "the schema version was wrong". It wasn't. The change in
between ([post-3-era work](README.md) on dead-code references) added no node kind and no
edge type — only new keys under `extras`, which the model deliberately leaves open. **The
semantics changed correctly, and the version field correctly did not move.**

Which is the actual finding, and it took me longer to accept than to discover:

> A schema version describes the **shape** of a file. Nothing described the **process** that
> produced it. Provenance is not schema.

For completeness, I ran the one tool that exists for comparing two snapshots:

```
$ codemap diff old.json new.json
# API diff — `src` → `src`

✅ **No breaking changes.** 0 added, 0 removed, 0 changed.
```

Correct — the public API really didn't change — and precisely why it could not be the safety
net. Two graphs that disagree about which functions are dead are, to `diff`, the same
program.

## "But you already had provenance"

I did, and this is the part worth dwelling on, because the fix looked already-shipped.

`codemap build -o graph.json` also writes `graph.json.meta.json`: the exact `argv`, a
`built_at` timestamp, the working directory, and a scope manifest with a content-hash
`scope_id` over every input file. Real provenance, built months earlier.

Four reasons it didn't close the hole:

1. **It's a separate file.** Every way a graph actually travels — attached to a ticket,
   committed to a sibling repo, pasted to an agent, copied into a container — moves
   `graph.json` and leaves the sidecar behind.
2. **It's `.gitignore`d.** So it is exactly the half you cannot share.
3. **It's best-effort.** The sidecar sitting in my own working tree had no `scope` key at
   all. Provenance that is sometimes absent can't be relied on by a consumer.
4. **It records `cwd`** — an absolute personal path. Which makes it the one file that must
   *not* be published, an awkward home for the data that's supposed to travel with the
   artifact.

The lesson generalises past this bug: *having* the data is not the same as the data being
**where the claim is read**.

## The fix, and the two rules it had to obey

A `provenance` block **inside** the graph — the first change since 0.11 that genuinely
earned a schema bump, since a new top-level key is a shape change:

```json
{
  "codemap_schema": "0.12",
  "target": "codemap",
  "provenance": {
    "inputs": {"python_files": 48},
    "scope_id": "sha256:8fbd05f2d27f3e269851cd2760ee465b55173e904747c535c95964a016fabb44",
    "source": {"commit": "407967c102be", "dirty": false, "ref": "main", "vcs": "git"},
    "tier": "fast",
    "tool": {"commit": "407967c", "dirty": false, "name": "codemap", "version": "0.0.2"}
  },
  "nodes": [], "edges": []
}
```

*(That is a real block, from `codemap build codemap`, keys sorted as the canonical
serializer writes them.)*

Two constraints, and they're the interesting part:

**No clock.** A `built_at` field would destroy the byte-identity this block exists to make
checkable. Two builds of a frozen tree must serialise identically *including* provenance —
so it carries a content hash and a commit, never a timestamp. Wall time stays in the
sidecar.

**No absolute paths.** The graph is the half that travels, so a personal path in it is a
leak. `build_provenance` raises on one and a test enforces it across the whole serialised
file.

Two smaller consequences fell out:

- **`codemap_schema` is finally read.** It had been written and never checked. A mismatch
  now raises a warning through the same channel every other build diagnostic uses — CLI,
  `stats`, and the report headers. A *warning*, never a refusal: every graph stored before
  0.12 predates the block, and turning an upgrade into an outage is not the honest option.
- **`diff` compares provenance before symbols**, and says when a pair was built by different
  tools, tiers or scopes. Differences below may be tool changes, not code changes.

## The finding I couldn't have gone looking for

With the block in place, a question became askable that I had no way to phrase before: what
does `build --incremental` do when the **tool** changes and the source doesn't?

It decided from the source tree alone. No `.py` changed → return the old graph, `mode:
unchanged`. Which is exactly wrong after an upgrade: the same source read by a different
extractor is a different graph. It would have handed back yesterday's graph, built by
yesterday's extractor, and reported that nothing needed doing.

It now compares the recorded builder — tool identity and tier — and falls back to a full
rebuild when they differ. A graph with no provenance counts as a different builder, which is
the conservative direction: a needless full rebuild costs a minute, a silently stale graph
costs a wrong answer.

That's the argument for provenance in one paragraph. It didn't just explain a red test; it
made a whole class of question expressible.

## The lesson, and where I'd been sloppy

**A test that reads a moving target measures the target.** Four of my `test_determinism_*`
tests built the live sibling checkout twice. They now build a frozen snapshot — the same
discipline the provenance block applies one level up. Freeze the input, or you're measuring
something else.

And the sharper half:

> **Determinism is a claim about a pair of builds. Without the input's identity in the
> artifact, it is unfalsifiable.**

I had spent months making the output reproducible and had never made it *checkable*. The
property was real the whole time. It just wasn't something a reader — human or agent — could
verify without taking my word for it, which is the one thing this project is not supposed to
ask for.

## The honest limits

- **`tool.commit` is absent from a wheel install.** Running from a source checkout, codemap
  records its own short HEAD. Installed from a wheel there is no commit, and the field is
  **missing** — not `"unknown"`, not a guess. That leaves a wheel-installed build identified
  only by a package version that moves rarely: every graph in the R1-C20…R1-C22 series was
  built by version `0.0.2`, which is the reason `commit` exists at all. The answer is release
  discipline, not a fabricated field.
- **The schema check catches a *declared* mismatch, not a semantic one.** It cannot prove two
  graphs are equivalent — the whole reason this post exists is that semantics change *without*
  a schema bump, because `extras` is open by design. That's what `tool.commit` is for.
- **The deep tier still has variance.** jedi's bounded inference is cache-sensitive; two full
  `--deep` builds can differ by a handful of edges. Provenance doesn't fix that — it makes it
  *attributable*, which is a different and smaller thing. The diffability claim rests on the
  fast/structural layers, which are fully deterministic.
- **`source.dirty` covers the scanned roots, not the whole repo.** A change outside the target
  package won't flip it.

## Try the falsifiable version

```bash
codemap build ./yourpkg -o graph.json
python -c "import json; print(json.load(open('graph.json'))['provenance'])"

codemap build ./yourpkg -o graph2.json
cmp graph.json graph2.json && echo "byte-identical, provenance included"
```

If it isn't byte-identical on the fast tier, something is wrong and I'd like to know. That's
the difference between a property you assert and one you can be caught on.

*codemap is open source (MIT): [github.com/kogriv/codemap](https://github.com/kogriv/codemap).
The full research track — every command, version, and number — is public, so you can
reproduce the comparisons or catch me where I'm wrong. Measured your tool and I got it wrong?
Open an issue. The harness is public.*
