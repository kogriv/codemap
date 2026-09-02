"""Build-level diagnostics derived from a graph (R1-C21 / design D5).

A graph can be *well-formed and vacuous*: if the extractor did not understand the
target's layout, whole edge classes come out empty and every conclusion drawn from
them inverts. The worst case found in the wild (issues #4/#5) was a flat module
directory: 0 ``imports`` edges, after which ``architecture`` reports "no layer
violations / acyclic" and ``dead-code`` calls every live module an orphan. Absence of
data rendered as a clean bill of health.

These checks name that condition wherever the graph is presented. They are
**derived, never stored** — ``graph.json`` keeps no diagnostic field, so there is
nothing to keep in sync, and any consumer recomputes the signal from the graph it
already holds.
"""

from __future__ import annotations

NO_IMPORT_EDGES = "no_import_edges"
NAMESPACE_TARGET = "namespace_target"
NO_CROSS_ROOT_EDGES = "no_cross_root_edges"
SCHEMA_MISMATCH = "schema_mismatch"
UNREAD_INPUTS = "unread_inputs"
MODULE_COUNT_MISMATCH = "module_count_mismatch"
SCOPE_MEMBERSHIP = "scope_membership"
DEEP_TIER_UNSTABLE = "deep_tier_unstable"

#: A ``warning`` invalidates the conclusions a surface draws from the graph — read them as
#: unknown. A ``note`` states a fact about how the graph was built and invalidates nothing.
#: Each check owns its own ``consequence`` sentence: presenters must not supply one, or a
#: correct result ends up captioned with another check's meaning (issue #8).
WARNING = "warning"
NOTE = "note"


def import_graph_diagnostic(graph) -> dict | None:
    """Flag an empty import graph over a multi-module target, else ``None``.

    A single-module package legitimately has no imports, so the check needs ≥2
    modules; beyond that, a Python package whose modules never import one another
    is far rarer than a layout the extractor failed to parse.
    """
    modules = sum(1 for n in graph.nodes.values() if n.kind == "module")
    if modules < 2:
        return None
    if any(e.type == "imports" for e in graph.edges):
        return None
    return {
        "code": NO_IMPORT_EDGES,
        "severity": WARNING,
        "modules": modules,
        "consequence": ("Findings below are derived from that empty import graph — read "
                        "them as **unknown**, not as a clean bill of health."),
        "message": (
            f"0 import edges across {modules} modules — the import graph is empty, so "
            "layers, cycles, coupling and orphan detection are vacuous rather than clean. "
            "This usually means a layout the extractor did not understand (e.g. a flat "
            "module directory whose files import each other by bare name)."
        ),
    }


def namespace_target_diagnostic(graph) -> dict | None:
    """Flag a target that is a **namespace package** (a directory with no ``__init__.py``).

    Derived, like the rest: griffe gives such a directory no source file, so the target's
    own module node carries ``file=None`` while its children have real files. Worth naming
    because the layout is a silent fork in behaviour — sibling imports resolve only by the
    flat-layout inference (labelled ``resolution="flat"`` on the edge), not by packaging.
    """
    root = graph.nodes.get(graph.target)
    if root is None or root.kind != "module" or root.file is not None:
        return None
    children = [n for n in graph.nodes.values() if n.kind == "module" and n.id != root.id]
    if not children:
        return None
    return {
        "code": NAMESPACE_TARGET,
        "severity": NOTE,   # a fact about provenance; it invalidates nothing (issue #8)
        "target": graph.target,
        "message": (
            f"`{graph.target}` has no __init__.py — it is a namespace package, so its "
            "modules are only a package by directory. Imports between them are resolved "
            "by codemap's flat-layout inference (edges labelled resolution=\"flat\"), "
            "not by packaging."
        ),
    }


def cross_root_diagnostic(graph) -> dict | None:
    """Flag consumer/doc roots that reach the core **not at all** (R1-C21-f1, issue #6).

    ``--consumer`` exists so ``impact`` can answer "who uses X across the whole repo".
    If roots were supplied and *nothing* in them references the core, the answer to that
    question is a confident zero — and the far likelier cause is that their imports were
    not understood than that four directories of code genuinely use none of it.

    Deliberately separate from :func:`import_graph_diagnostic`: the case that prompted it
    had 75 import edges (so the "empty graph" check stayed quiet) and none of them crossing
    a root boundary. One check per dimension, rather than one check trying to be general.
    """
    root_of = {n.id: (n.extras.get("root") or "core") for n in graph.nodes.values()}
    outer = sorted({r for r in root_of.values() if r != "core"})
    if not outer:
        return None  # single-package graph: no boundary to cross
    for e in graph.edges:
        if root_of.get(e.source, "core") != "core" and root_of.get(e.target, "core") == "core":
            return None
    return {
        "code": NO_CROSS_ROOT_EDGES,
        "severity": WARNING,
        "roots": outer,
        "consequence": ("Any cross-root finding below — who uses a symbol outside its own "
                        "root — is **unknown**, not empty."),
        "message": (
            f"{len(outer)} non-core root(s) supplied ({', '.join(outer)}) but not one "
            "reference from them reaches the core — cross-root `impact` will read as "
            "\"isolated\" for every symbol. Usually an import form the scanner did not "
            "understand, not an unused core."
        ),
    }


def schema_diagnostic(graph) -> dict | None:
    """Flag a stored graph whose schema is not the running tool's (R1-C25 / D3).

    ``codemap_schema`` was written and never read: a graph built before an extraction
    change was consumed by a later tool without a word, and answered with that tool's
    confidence over the older tool's blindness. Measured: one frozen tree, two codemap
    builds four commits apart — 30 edges vs 38, and ``dead-code high`` 12 vs 7 — with
    **both files declaring 0.11**, because only open ``extras`` had changed. So the
    check cannot prove semantic equivalence; what it can do is stop a *known* mismatch
    from passing silently.

    Only fires for a graph that came from a file (``loaded_schema is None`` on a fresh
    build). Never a refusal: every stored graph in existence predates 0.12, and turning
    an upgrade into an outage is not the honest option — a labelled answer is (R1-C13).
    """
    from codemap.model import SCHEMA_VERSION
    from codemap.provenance import MATCH, NEWER, OLDER, describe, schema_status
    if graph.loaded_schema is None:
        return None
    status = schema_status(graph.loaded_schema or None, SCHEMA_VERSION)
    if status == MATCH:
        return None
    declared = graph.loaded_schema or "none declared"
    direction = {OLDER: "predates this tool",
                 NEWER: "is newer than this tool"}.get(status, "declares no usable version")
    return {
        "code": SCHEMA_MISMATCH,
        "severity": WARNING,
        "loaded": graph.loaded_schema,
        "running": SCHEMA_VERSION,
        "status": status,
        "provenance": describe(graph.provenance),
        "consequence": ("Findings below may differ from a fresh build of the same source "
                        "— rebuild before trusting a close call."),
        "message": (
            f"graph declares schema {declared}, this codemap writes {SCHEMA_VERSION} "
            f"— the artifact {direction}. Extraction semantics change without a schema "
            f"bump (open `extras`), so the two are not interchangeable. "
            f"Built by: {describe(graph.provenance)}."
        ),
    }


def unread_inputs_diagnostic(graph) -> dict | None:
    """Flag input files the extractor could not read (R1-C23 / design D2).

    A file with a syntax error or a non-UTF-8 byte used to vanish from the graph in
    silence, after which every report answered over a tree it had not fully seen —
    the same shape as issue #5, where absence of data rendered as a clean bill of health.
    """
    skipped = ((graph.provenance or {}).get("inputs") or {}).get("skipped") or []
    if not skipped:
        return None
    by_reason = {}
    for s in skipped:
        by_reason.setdefault(s.get("reason", "unread"), []).append(s.get("path"))
    listed = ", ".join(f"{len(v)} {k}" for k, v in sorted(by_reason.items()))
    sample = ", ".join(sorted(p for v in by_reason.values() for p in v)[:5])
    return {
        "code": UNREAD_INPUTS,
        "severity": WARNING,
        "skipped": skipped,
        "consequence": ("Anything those files define or depend on is **missing**, not "
                        "absent — dead-code, layers and impact are all short by that much."),
        "message": (
            f"{len(skipped)} input file(s) produced no module ({listed}): {sample}"
            + (" …" if len(skipped) > 5 else "")
        ),
    }


def deep_tier_diagnostic(graph) -> dict | None:
    """State the deep tier's noise floor on the artifact itself (R1-C42).

    A **note**, not a warning: nothing here is wrong, and no finding below is invalid.
    What was missing is that the tier's instability was known — measured at R1-C9, and
    the reason the CI determinism job runs the fast tier only — while living exclusively
    in a comment in a workflow file. A consumer read "deterministic" and built a
    two-release comparison on it; the difference they saw was the tool, not the code.

    Measured on two trees: ten deep builds of an unchanged tree produced **two** distinct
    artifacts (7/3), differing in two per-symbol call counters and no edges; on a larger
    tree one build in seven lost one real call edge of 9524. The cause is jedi's
    per-script execution budget — an inference that runs out of it returns nothing, and
    that reads as `unresolved` rather than as an error.
    """
    if (graph.provenance or {}).get("tier") != "deep":
        return None
    return {
        "code": DEEP_TIER_UNSTABLE,
        "severity": NOTE,
        "tier": "deep",
        "consequence": ("Everything here is a lower bound as usual; treat a difference "
                        "of a few jedi-resolved edges between two deep graphs as tool "
                        "noise rather than a change in the code."),
        "message": (
            "built on the deep (jedi) tier, which is not byte-stable: two builds of an "
            "unchanged tree can differ by a few jedi-resolved edges — measured at roughly "
            "one run in three on two trees: two per-symbol call counters on one, one "
            "`accesses` edge of 12190 on the other."
        ),
    }


def scope_membership_diagnostic(graph) -> dict | None:
    """Flag files the graph was built from that the input manifest never listed (R1-C41).

    Sibling of the conservation law above, and it catches what that one provably cannot:
    the count compares the *extractor's* walk against the graph, so when both agree and
    only the **manifest** disagrees — an untracked or gitignored module, a file leaked in
    from outside the target — it stays silent, correctly. Reported by the second real
    target (issue #15), who found a sidecar listing 47 files with a hash on each beside a
    graph built from 48.

    Derived from ``provenance.inputs.unlisted``, which the build records because the
    comparison needs the scope manifest and a consumer may hold only the graph. Absent
    field means the build could not compare (no manifest resolved) — that is *unknown*,
    not zero, so it is not reported as a clean result.
    """
    unlisted = ((graph.provenance or {}).get("inputs") or {}).get("unlisted") or {}
    count = unlisted.get("count") or 0
    if not count:
        return None
    sample = ", ".join(unlisted.get("sample") or [])
    where = (" (at least one lies outside the scope root entirely)"
             if unlisted.get("outside_root") else "")
    return {
        "code": SCOPE_MEMBERSHIP,
        "severity": WARNING,
        "unlisted": count,
        "consequence": ("The manifest and `scope_id` describe a different input than this "
                        "graph was built from, so read the input identity as **unknown** — "
                        "and with it `--incremental` and `watch`, which key off that value."),
        "message": (
            f"{count} file(s) in this graph are not listed in the input manifest{where}: "
            f"{sample}" + (" …" if count > len(unlisted.get("sample") or []) else "")
        ),
    }


def module_count_diagnostic(graph) -> dict | None:
    """Conservation law over the build: modules cannot outnumber the files that define
    them, nor silently fall short of them (R1-C23 / design D6).

    Deliberately not a heuristic and deliberately not tuned — both directions are
    *provably* wrong states, so there is no threshold to argue about. It is the check
    that catches a cause we have not met yet: it flags the symlink-cycle explosion
    without knowing what a symlink is, and an unexplained shortfall without knowing what
    a syntax error is. It would have fired on issue #5.
    """
    inputs = (graph.provenance or {}).get("inputs") or {}
    expected = inputs.get("python_files")
    if expected is None:
        return None  # pre-0.12 graph, or a build that recorded no input count
    # Core only: ``inputs`` counts the extractor's walk of the target package, so a
    # repo-scoped graph's consumer modules (``--consumer tests``) are not in that number
    # and must not be compared against it.
    from_py = sum(1 for n in graph.nodes.values()
                  if n.kind == "module" and (n.file or "").endswith(".py")
                  and (n.extras.get("root") or "core") == "core")
    skipped = len(inputs.get("skipped") or [])
    if from_py > expected:
        direction = (f"{from_py} modules built from {expected} input file(s) — a module "
                     "cannot outnumber the files that define it. The tree was probably "
                     "walked more than once (a directory symlink into its own ancestry).")
    elif from_py < expected - skipped:
        direction = (f"{from_py} modules built from {expected} input file(s), only "
                     f"{skipped} of which are accounted for as unreadable — "
                     f"{expected - skipped - from_py} file(s) went missing unexplained.")
    else:
        return None
    return {
        "code": MODULE_COUNT_MISMATCH,
        "severity": WARNING,
        "modules": from_py,
        "input_files": expected,
        "consequence": ("Every aggregate below — counts, layers, cycles, hotspots, "
                        "dead-code — is computed over that graph, so read it as "
                        "**unknown**."),
        "message": direction,
    }


def diagnostics(graph) -> list[dict]:
    """Every diagnostic that applies to ``graph`` (empty list when it looks sound)."""
    checks = (import_graph_diagnostic(graph), namespace_target_diagnostic(graph),
              cross_root_diagnostic(graph), schema_diagnostic(graph),
              unread_inputs_diagnostic(graph), module_count_diagnostic(graph),
              scope_membership_diagnostic(graph), deep_tier_diagnostic(graph))
    return [d for d in checks if d is not None]


def render_lines(graph) -> list[str]:
    """Markdown blockquote lines for a report header (empty when the graph looks sound).

    Presenters call this instead of formatting diagnostics themselves — a caption that
    belongs to one check must never end up under another (issue #8: the namespace *note*
    was rendered with the empty-import-graph *warning*'s "everything below is unknown",
    on a graph with 404 import edges).
    """
    lines: list[str] = []
    for d in diagnostics(graph):
        mark = "⚠️" if d.get("severity", WARNING) == WARNING else "ℹ️"
        text = " ".join(part for part in (d["message"], d.get("consequence")) if part)
        lines.extend([f"> {mark} {text}", ""])
    return lines
