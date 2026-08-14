# PyCG

**Verdict:** learn (the academic reference for Python call-graph accuracy) · **Feeds:** R1-C13 (benchmark) ·
**Card status:** spike (2026-08-14) — **does not run on Python 3.12**; used as a *methodology* reference, not a live oracle.

_Tested version: **PyCG 0.0.8** (PyPI, the last release; Salis et al., "PyCG: Practical Call Graph Generation
in Python", ICSE 2021). Probed in an isolated `uv venv --python 3.12` (Python 3.12.3)._

## What we wanted from it

R1-C13 asked us to state codemap's call-graph accuracy against an **independent oracle** and to declare the
honest ceiling openly. PyCG is the natural oracle: it is the reference research tool for Python call graphs
and ships a hand-labeled **micro-benchmark** (≈112 tiny programs with expected call edges) that the field
cites for the ~99% precision / ~70% recall figure — the practical ceiling of *any* sound static tool on
Python's dynamism (higher-order functions, `getattr` dispatch, dynamic attributes).

## What happened — three layered breakages on Python 3.12

PyCG 0.0.8 is a 2021 tool that reverse-engineers CPython's import machinery; that machinery has since moved.
Each fix surfaced the next:

1. **Case-mismatched package.** The wheel installs the package as `PyCG/` but the code does
   `from pycg import formats` — an `ImportError` on any case-sensitive filesystem (Linux). Worked around with
   a lowercase symlink.
2. **`pkg_resources` gone.** `formats/fasten.py` does `from pkg_resources import Requirement`; modern
   setuptools (≥81) dropped `pkg_resources`. Pinned `setuptools<80` to get it back.
3. **Import-hook collision (fatal).** PyCG installs a custom `SourceLoader` and manipulates
   `sys.path_hooks`. On 3.12 the loader fires for the entry module before PyCG has created its graph node
   (`ImportManagerError: Can't add edge to a non existing node`) — even on a **3-line toy file**. Patching
   that ordering then hit a second, deeper collision: PyCG's path-hook surgery shadows the stdlib
   `importlib.metadata`, raising `ImportError: cannot import name 'FreezableDefaultDict'` from inside
   `importlib`'s own machinery.

Breakage #3 is not a one-line fix — it is a structural incompatibility between PyCG's import-system
monkey-patching and the 3.12 stdlib. Resurrecting it would mean porting PyCG's import layer: the same
"hubris zone" the [graphlens integration spike](graphlens.md) hit. **We stopped** (spike-negative, per the
project's spike-first discipline).

## The pivot — a hand-labeled oracle instead of a broken one

Rather than trust a *second imperfect static tool* as ground truth, R1-C13 replaced "PyCG as oracle" with a
small **hand-labeled micro-suite we own** ([`research/bench/callgraph_truth/`](../bench/callgraph_truth/),
10 cases spanning direct/self/cross-module/higher-order/decorator/inheritance/getattr/local-var/registry/
closure). Each case's true call edges are known by construction, so codemap's extractor is measured directly
against them — reproducible, deterministic, zero third-party dependency. This is *more* honest than a
PyCG cross-check: the labels are auditable and the undecidable cases are marked as such, making the ceiling
explicit instead of implicit. Harness: [`research/bench/callgraph_accuracy.py`](../bench/callgraph_accuracy.py).

We still **cite PyCG's published ceiling** (~99% precision / ~70% recall on its own benchmark) as the
field's reference point — see [`docs/accuracy.md`](../../docs/accuracy.md). We just don't run it.

## What we'd learn from it if it ran (deferred, not dismissed)

PyCG's micro/macro benchmark corpus is a genuinely valuable labeled dataset. If a maintained fork (or a
3.12-compatible reimplementation of its import layer) appears, adopting its corpus to widen our micro-suite
is worth revisiting. Tracked under R1-C13; not a router/adapter candidate (PyCG is a batch CLI, not a
service, and its value here is the *labels*, not a live capability).
