# codemap — gap: attribute nodes have no inbound edges (`impact` on a field = false "none")

**Date:** 2026-08-22
**Source:** GitHub issue [#1](https://github.com/kogriv/codemap/issues/1), found dogfooding codemap on
`bquant` to plan a dataclass **field rename** (the G16 work) — exactly the case one reaches for `impact`.
**Type:** soundness / honesty gap (a misleading affirmative), not a "can't answer" gap.
**Related:** `deep_dogfood_2026-07-29.md` (F6/F7 dataflow), `newfeatures_dogfood_2026-08-22.md` (F-DOG-1),
the closed edge-vocabulary (R1-C7, `model.EDGE_TYPES`).
**Design:** [docs/design/attribute_edges.md](../docs/design/attribute_edges.md).

## 1. The gap

`impact` on a **class attribute** returns `refs: []` and **`risk: "none"`** even when the field has many
real read/write sites. Attribute nodes are extracted and located correctly, but **nothing in the graph
ever points at them**, so the answer reads as an affirmative "nothing depends on this" rather than the
honest "this relationship is not modelled."

For a *function* or *class*, empty `refs` is a real (if lower-bound) signal — the call/reference layer does
target them. For an *attribute*, empty `refs` means **codemap does not model attribute access at all**, yet
the surface presents the two identically. That is the defect: **not missing data, but a missing distinction**
— `risk="none"` is affirmatively wrong where it should be `unknown`/`unmodelled`.

## 2. Evidence (from the graph, not guessed)

Target: `bquant` (public), standard dogfood graph.

```
search("peak_prominence")
→ { id: "bquant…SwingThresholds.peak_prominence", kind: "attribute",
    file: ".../swing/thresholds.py", lineno: 18 }        # node exists, located right

impact("bquant…SwingThresholds.peak_prominence")
→ { refs: [], by_root: {}, max_distance: 0, risk: "none" }
```

Ground truth at that moment: **9 sites** — 6 in `thresholds.py` (two constructions, two assignments in
`_apply_thresholds_to_strategy`, one in `_thresholds_to_dict`) + 3 in
`tests/analysis/zones/test_swing_thresholds.py`.

Not a hard-locals problem — a plain `self.` read in the attribute's own class is missed too:

```
impact("bquant…FindPeaksSwingStrategy.distance") → { refs: [], risk: "none" }   # self.distance read several times
```

Root cause: `stats` shows `reads: 575 / writes: 1829`, so those edge types **are** populated — but every one
targets a `column:*` node (DataFrame-column lineage, M12). **No edge in the graph targets a Python
attribute node.** The impact set (`_IMPACT_EDGES = calls/references/inherits/imports/decorated_by`) doesn't
include `reads`/`writes` at all, and nothing emits attribute-targeted edges of any type.

## 3. Why it matters

- **The scenario is the reason `impact` exists.** "What breaks if I rename/retype this field?" is a top
  refactor question; codemap answering "nothing" here is worse than answering "unknown" — it invites a
  broken rename. During G16 the field rename had to be planned with grep (9 sites), not the graph.
- **It's an honesty regression relative to codemap's own contract.** Every other partial answer carries a
  lower-bound disclaimer / `epistemic` label (R1-C13). Attribute `impact` carries `risk:"none"`, the one
  place the tool sounds *certain* while being blind.
- **Attributes are first-class nodes** (kind `attribute`, with `annotation`, dataclass-field membership) —
  they earn real relational answers, like classes/functions got in M4–M7.

## 4. Scope of a full (non-truncated) solution

The minimal patch — flag attribute `impact` as `unmodelled` — removes the *lie* but leaves the *blindness*.
The full solution **models attribute access as graph edges** so `impact` / `callers`-style questions answer
truthfully for fields, mirroring what M12 did for string-keyed columns:

- **Extract** attribute read/write sites (a bounded AST pass, `dataflow.py`-style): `self.attr` (Load/Store)
  inside methods → the enclosing class's attribute; `ClassName.attr`; `obj.attr` on a local whose type is
  known (deep/jedi tier); dataclass-field construction kwargs (`Cls(field=…)`). Cross-root (tests/…) too.
- **Model** them as edges to the attribute node (edge-type choice is a design decision — reuse
  `reads`/`writes`, or a dedicated kind; must update `model.EDGE_TYPES`, R1-C7).
- **Wire** attribute-targeted edges into `impact` / `references_to` so blast-radius spans them; honest
  `resolution` labels (`self` exact vs `deep` vs `unresolved`), per codemap's "resolved-or-flagged" rule.
- **Fallback**: an attribute with no *modelled* inbound edge reports `unknown`/`unmodelled`, never `none`
  (this half also fixes the honesty bug directly, and ships first).

Boundaries, resolution tiers, determinism, and the edge-type decision are worked out in the design-doc.
Backlog: **R1-C20** (see `BACKLOG.md`).
