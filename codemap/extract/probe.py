"""Does each dependency still answer a known question correctly? (R1-C64)

griffe and jedi do work codemap never re-checks: griffe resolves re-export aliases into the
structure, jedi types a local variable into a call target. Both are hard dependencies, so the
only "check" they ever got was that ``import`` did not fail. That is the wrong check for the
failure that matters: a jedi that stopped resolving after an upgrade does not break a build —
``_resolve_jedi`` reads any exception as ``unresolved`` — it turns every deep call into a
fast-tier one, and the graph is simply poorer. Measured: with ``jedi.Script`` answering
nothing, a deep build of a real 89-module tree exited 0 with ``calls`` equal to the fast tier's
to the edge, while still declaring ``tier: deep``.

The probe is the shape `jg doctor` uses (research/tools/jevgrep.md, S2): a synthetic input
whose correct answer is known, and a backend that answers it wrongly is refused rather than
counted as present. One fact per dependency, through the real pipeline — not a benchmark,
which would be noisy and get switched off.

Design: ``docs/design/dependency_probe.md``.
"""

from __future__ import annotations

import importlib
import tempfile
from pathlib import Path

PROBE_PACKAGE = "codemap_probe"

#: The probe tree. ``engine.run()`` needs a local variable's type (jedi only — the fast tier
#: does not build that edge); ``ph()`` goes through a re-export alias whose target griffe
#: resolves (``Alias.target_path``), which is where the ``export`` edge comes from.
PROBE_FILES = {
    "__init__.py": f"from {PROBE_PACKAGE}.core import helper as public_helper\n",
    "core.py": ("class Engine:\n"
                "    def run(self):\n"
                "        return 1\n\n\n"
                "def helper():\n"
                "    return 2\n"),
    "app.py": (f"from {PROBE_PACKAGE} import public_helper as ph\n"
               f"from {PROBE_PACKAGE}.core import Engine\n\n\n"
               "def main():\n"
               "    engine = Engine()\n"
               "    engine.run()\n"
               "    return ph()\n"),
}

#: Outcomes. ``wrong`` is the case this module exists for: present, answering, mistaken.
OK, WRONG, ABSENT, ERROR, NOT_RUN = "ok", "wrong", "absent", "error", "not-run"

#: dependency → (edge type, source, target, resolution or None, what the fact means)
EXPECTED = {
    "griffe": ("export", PROBE_PACKAGE, f"{PROBE_PACKAGE}.core.helper", None,
               f"the re-export `{PROBE_PACKAGE}.public_helper` resolves to "
               f"`{PROBE_PACKAGE}.core.helper`"),
    "jedi": ("calls", f"{PROBE_PACKAGE}.app.main", f"{PROBE_PACKAGE}.core.Engine.run", "deep",
             f"`engine.run()` on a local `Engine()` resolves to "
             f"`{PROBE_PACKAGE}.core.Engine.run`"),
}


def write_probe(directory: str | Path) -> Path:
    """Write the probe package under ``directory`` and return its path."""
    pkg = Path(directory) / PROBE_PACKAGE
    pkg.mkdir(parents=True, exist_ok=True)
    for name, body in PROBE_FILES.items():
        (pkg / name).write_text(body, encoding="utf-8")
    return pkg


def _version(name: str) -> str | None:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def holds(graph, dependency: str) -> bool:
    """Is the dependency's fact an edge of ``graph``?"""
    etype, source, target, resolution, _ = EXPECTED[dependency]
    return any(e.type == etype and e.source == source and e.target == target
               and (resolution is None or e.extras.get("resolution") == resolution)
               for e in graph.edges)


def _expected_str(dependency: str) -> str:
    etype, source, target, resolution, _ = EXPECTED[dependency]
    return f"{etype} {source} → {target}" + (f" ({resolution})" if resolution else "")


def _row(dependency: str, status: str, detail: str) -> dict:
    return {"dependency": dependency, "version": _version(dependency), "status": status,
            "fact": EXPECTED[dependency][4], "expected": _expected_str(dependency),
            "detail": detail}


def _importable(name: str) -> str | None:
    """``None`` when ``name`` imports; otherwise why it does not."""
    try:
        importlib.import_module(name)
    except Exception as exc:  # ImportError, or a broken install raising anything else
        return f"not importable ({type(exc).__name__}: {exc})"
    return None


def _check(dependency: str, build) -> tuple[dict, bool]:
    """Run one probe. Returns the row and whether its build produced a graph at all."""
    why = _importable(dependency)
    if why:
        return _row(dependency, ABSENT, why), False
    try:
        graph = build()
    except Exception as exc:
        return _row(dependency, ERROR, f"the probe build raised {type(exc).__name__}: {exc}"), False
    if holds(graph, dependency):
        return _row(dependency, OK, "answered as expected"), True
    return _row(dependency, WRONG, f"expected edge `{_expected_str(dependency)}` is not in "
                                   "the graph — the dependency imports and answers, and the "
                                   "answer is wrong"), True


def run_probes() -> dict:
    """Build the probe twice (fast for griffe, deep for jedi) and grade each dependency.

    jedi's probe stands on griffe's structure: when the fast build already failed, a deep
    result would mean nothing, so jedi is ``not-run`` — unknown, not wrong.
    """
    from codemap.extract import extract
    with tempfile.TemporaryDirectory(prefix="codemap-probe-") as tmp:
        pkg = write_probe(tmp)
        griffe_row, built = _check("griffe", lambda: extract(str(pkg)))
        if not built:
            jedi_row = _row("jedi", NOT_RUN, "not run: the structural pass it stands on "
                                             f"did not produce a graph ({griffe_row['status']})")
        else:
            jedi_row, _ = _check("jedi", lambda: extract(str(pkg), deep=True))
    rows = [griffe_row, jedi_row]
    return {"ok": all(r["status"] == OK for r in rows), "probes": rows}


def render(report: dict) -> str:
    """Plain text, one line per dependency, then a verdict line."""
    lines = ["codemap doctor — does each dependency still answer a known question correctly?", ""]
    for r in report["probes"]:
        name = f"{r['dependency']} {r['version'] or '(version unknown)'}"
        lines.append(f"{name:<22} {r['status'].upper():<8} {r['fact']}")
        if r["status"] != OK:
            lines.append(f"{'':<22} {'':<8} {r['detail']}")
    lines.append("")
    lines.append("✅ every probe answered as expected." if report["ok"] else
                 "❌ at least one dependency is absent or answers wrongly — a graph built "
                 "here may be poorer than its tier declares.")
    return "\n".join(lines) + "\n"
