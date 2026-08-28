"""A result limit is partiality too — and every op that has one says so (R1-C28).

codemap's standing commitment is **resolved-or-honestly-flagged**: an approximation
may be lossy, but the answer must say that it is. ``_PARTIAL_OPS`` (session.py) already
stamps ``epistemic: "partial"`` on the ops whose *call resolution* is a lower bound.

A limit is a **second, independent source of lower-boundness**, and it is invisible to
that machinery: ``callers`` is flagged and takes no limit, while ``search`` takes a
limit and was flagged by nothing at all — it answered `50 of 1259` under an envelope
that said only ``{"ok": true}``. That is the familiar failure one notch weaker than the
confident empty: a **confident partial**, complete-looking and undetectable.

Found by measuring someone else's tool (`research/tools/codegraph.md`, T2) and then
asking the same question of ourselves. Gap: `gaps/limit_truncation_2026-08-28.md`.

The rule, in one line: **whenever an op accepts a limit, the envelope carries a
``limit`` block — always, including when nothing was cut.** A caller must never have to
distinguish "not truncated" from "this build does not report truncation", which is
exactly what an only-on-truncation field forces it to do.

``total`` and ``truncated`` may be ``None``. That is deliberate and is not the same as
omitting them: an unknown total is a *fact* about the answer (the count was not
affordable, or the cut happened upstream in a tool we merely called), and stating it
lets a caller widen the limit instead of trusting a number that was never observed.
"""

from __future__ import annotations


def limit_block(applied: int, returned: int, total: int | None,
                *, truncated: bool | None = None, note: str | None = None) -> dict:
    """Build the envelope block: ``{applied, returned, total, truncated, note?}``.

    ``applied``   the limit that was in force (the default, if the caller passed none)
    ``returned``  how many entries the answer actually carries
    ``total``     how many existed before the limit — ``None`` when not observable
    ``truncated`` derived from ``total`` unless given; ``None`` means *unknown*, which
                  happens only when ``total`` is unknown and the answer is exactly full
    """
    if truncated is None and total is not None:
        truncated = total > returned
    elif truncated is None and returned < applied:
        # Fewer than we asked for: nothing was cut, whatever the unknown total is.
        truncated = False
    block: dict = {"applied": applied, "returned": returned,
                   "total": total, "truncated": truncated}
    if note:
        block["note"] = note
    return block


def limit_footer(block: dict | None) -> str | None:
    """One human line for the CLI, or ``None`` when nothing was cut.

    The CLI is the one surface where always-on would be noise rather than honesty: a
    person re-reads the command they just typed, a machine consumer cannot.
    """
    if not block or block.get("truncated") is False:
        return None
    returned, total = block["returned"], block.get("total")
    if block.get("truncated") is None:
        return (f"_{returned} shown at --limit {block['applied']}; the tool applied the "
                f"limit itself, so the pre-limit total is unknown — pass --limit to widen._")
    return (f"_{returned} of {total} shown — pass --limit to widen._")
