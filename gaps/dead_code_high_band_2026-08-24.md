# codemap — gap: the `high` dead-code band is wrong 39% of the time (references the source shows, the graph misses)

**Date:** 2026-08-24
**Source:** GitHub issue [#7](https://github.com/kogriv/codemap/issues/7), found while verifying the flat-layout
fixes (`520728a`) on the second real target — *"a working graph is what made this visible"*. Not
flat-layout-specific: it reproduces on a packaged core, and on **codemap's own package**.
**Type:** soundness / honesty — a confident affirmative (`high` = "no inbound edge of any kind") over a
reference that is plainly visible in the same module, two lines below the definition.
**Related:** `attribute_impact_gap_2026-08-22.md` (same shape — the surface reports certainty where the graph
is merely blind), R1-C8 (the graded dead-code this regrades), R1-C13 (lower-bound labels).
**Design:** [docs/design/source_visible_references.md](../docs/design/source_visible_references.md).
**Backlog:** R1-C22.
**Status:** ✅ **closed same day** (2026-08-24, no schema change) — all three mechanisms modelled. The
`high` band went **46 → 29** on codemap and **5 → 2** on bquant, i.e. exactly the 31 candidates this audit
called genuinely unreferenced; additions only (bquant +364 edge pairs, **0 removed**). Two surprises worth
carrying: most name-loads turned out to be *annotations*, now labelled apart from the dispatch form; and
D3's feared cost was a phantom (5202 call sites → 21 new edges). The accuracy benchmark's `c10_closure`
ground truth had to be corrected — it recorded the old limitation as the right answer.

## 1. The gap

`report dead-code` grades an uncalled private function **high** — *"no inbound calls, references, or
decorators"* — when the function **is** referenced in its own module, by a form the graph does not model.
`high` is the band a reader acts on, and `--min-confidence high` is exactly the filter that keeps them.

The reporter's audit: **9 of 10** high candidates on their repo were live. Independently measured here, the
rate holds and the *causes* turn out to be three, not one.

## 2. Evidence — three mechanisms, measured on two real packages

Every `high` candidate on both packages was classified by what the source actually does with the name:

| package | `high` | ① function-as-value | ② module-level call | ③ call inside a nested def | genuinely unreferenced |
|---|---|---|---|---|---|
| **codemap** (own package) | 46 | **13** | 0 | **4** | 29 |
| **bquant** | 5 | 0 | **2** | **1** | 2 |
| **total** | **51** | 13 | 2 | 5 | 31 |

**20 of 51 (39%) are false positives** — and note that each package only exhibits *two* of the three, which
is why one dogfood target could not have found this.

### ① Function-as-value — the form the issue reports

```python
def _panel_a(v): ...
PANELS = {"a": _panel_a}                       # named, never called here
def dump(o): return json.dumps(o, default=_json_default)   # handed to a callee
```

A bare `Name` load produces no edge of any kind: `calls` covers the callee position only, and nothing else
targets a function *as a value*. On codemap this is every `_cmd_*` CLI handler — dispatched through a table.

### ② Module-level call — the reference is a call, at import time

```python
# bquant/indicators/__init__.py:106-107
_register_all_indicators()
_check_library_availability()
```

`extract/behavior.py` walks `_named_functions(tree)` only, so **statements at module level are never
visited** and their calls produce nothing. Import-time side effects — registration, availability probes,
singleton construction — are invisible to the call graph as a class, not just to dead-code.

### ③ Call inside a nested def

```python
def _create_indicator_class_dynamically(...):
    class Generated(...):
        def calculate(self, ...):
            if _needs_generated_names(result_df.columns):   # ← this call
```

`behavior.py` drops the whole function when its id is not a graph node (`# nested closure — not a definition
node`), so every call *inside* a closure or a dynamically-built class is discarded along with it. On
codemap this hides calls to `_resolve`, `_resolve_jedi`, `_cap_list` — core functions of the extractor
itself, reported as dead by its own tool.

## 3. Why it matters

- **`high` is the actionable band.** The reader deletes what is in it. The failure mode is not an import
  error but a runtime one — the first render, the first `json.dumps` of a non-serializable value, the first
  indicator registration that never happened.
- **It is an affirmative, not an omission.** The section's disclaimer covers *dynamic dispatch*; none of
  these three need dynamism to be seen. The name is a plain `Name` node in the same file. "No inbound
  references" is a claim the graph is not entitled to make.
- **It is not confined to dead-code.** ② and ③ are missing **`calls`** edges: `impact`, `callers`, `flows`
  and the architecture views are all reading a call graph with import-time and closure-level work cut out of
  it. Dead-code is where the hole became visible, not where it lives.
- **codemap fails it on itself.** 17 of its own 46 high candidates are false — the dogfood target could not
  reveal that, because bquant exhibits the other two mechanisms.

## 4. Scope of a full solution

Three independent repairs, each closing one mechanism; the grader needs **no change** — `_grade_dead`
already demotes to `low` on any inbound edge (`references_to`), so every fix flows through automatically.

1. **① as-value `references` edges** (small: ~69 edges on codemap, ~149 on bquant) — model the relationship
   rather than special-casing the report, exactly as R1-C20 chose for attributes.
2. **② module-level calls** (small: 27 / 137 call sites) — visit module-level statements, source the edge
   from the module node. Closes a whole blind class (import-time behaviour), not just these candidates.
3. **③ nested-def calls** (**large**: 619 / **5202** call sites) — attribute a call inside a closure to the
   nearest enclosing graph node. Correct in principle, but the volume means it will move real numbers in
   every existing graph, so it is costed and decided separately in the design.

Byte-identity is **not** an acceptance criterion here (unlike R1-C21): these fixes deliberately add true
edges. The criterion is *additions only, each traceable to a source-visible reference, and the measured
false-positive counts above go to zero*.

Design decisions and sizing: [docs/design/source_visible_references.md](../docs/design/source_visible_references.md).

---

## 5. Follow-up (issue #9) — the mirror: over-attribution

**Reported 2026-08-24 on `b105d33`**, after the reporter verified the fix end-to-end on the same repo:
**10 of 10 now graded correctly** (was 9 of 10 wrong), and both ways the fix could have overshot were
checked and clean — a name appearing only in a docstring/string literal creates no reference, and neither
does a name that is only ever *stored*. Cross-root edges still verify: 1248 of them, 0 false.

**The remaining case.** A **Load of a locally-bound name** that happens to match a module-level function was
attributed to that function:

```python
def unrelated():
    _dead_shadowed = 1      # binds the name for the whole scope
    return _dead_shadowed   # reads the LOCAL, not the function
```

Python binds per *scope*, not per statement, so `unrelated` never touches the function — yet the graph grew
`unrelated → _dead_shadowed`, and an equally dead function hid in `low` instead of `high`. Bounded harm
(nothing live is deleted; `--min-confidence high` just misses one), and it is the exact mirror of §1: the
same question — *does this name occurrence actually resolve to that function?* — answered "too often"
instead of "not often enough".

**Wider than reported.** The issue names assignment, and expects parameters to be already handled. Measured
here, **four** binding forms produced false edges — assignment, **parameter**, `for`-target and `with ... as`
— plus `except ... as` and a nested `def` of the same name. The parameter case looked correct in the
reporter's test only because the parameter name did not collide.

**One thing the obvious rule got wrong.** Treating *function-local imports* as shadowing dropped a **real**
edge on bquant: `register_builtin_indicators → IndicatorFactory`, where the function imports that class in
its own body. An import binds the name to the symbol it imports — which is precisely what the edge records —
so unlike an assignment it must not suppress. Caught by measuring the delta, not by review.

Fixed in R1-C22-f1: `_local_bindings` per function scope (`global`/`nonlocal` opt back out; module scope is
never filtered, since rebinding there is the same symbol). Verified inert on real code — **0 edges
suppressed** on codemap and on bquant.

Issue [#9](https://github.com/kogriv/codemap/issues/9).

