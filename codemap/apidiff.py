"""Two-graph API diff + breaking-change detection (R1-C5).

Compare two ``graph.json`` snapshots (before/after a change) and report what moved
on the **public API surface**: symbols added / removed, and — for symbols present in
both — the signature-level changes, each classified as *breaking*, *warning*, or
*info*. "What broke between these two commits", at the API level.

The rules follow the griffe API-diff spirit (a removed parameter, a newly-required
parameter, a removed public symbol are breaking for callers). Signatures are parsed
with the stdlib ``ast`` — each stored signature string is wrapped as ``def <sig>: ...``
and its arguments read out — so the analysis is exact, not string-diff heuristics.
If a signature cannot be parsed, the change degrades to a conservative
``signature-changed`` note rather than a false "breaking".

Scope: only ``public`` symbols (``visibility == "public"``) participate — private
churn is not an API change. A public→private flip *is* an API removal.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from codemap.model import Graph, Node

# severities, most severe first
BREAKING = "breaking"
WARNING = "warning"
INFO = "info"
_ORDER = {BREAKING: 0, WARNING: 1, INFO: 2}


@dataclass(frozen=True)
class Change:
    """One classified difference on a symbol."""

    symbol: str
    kind: str          # param-removed | param-added-required | … (see _classify)
    severity: str      # breaking | warning | info
    detail: str


@dataclass
class ApiDiff:
    added: list[str] = field(default_factory=list)     # new public symbols
    removed: list[str] = field(default_factory=list)   # deleted public symbols (each breaking)
    changes: list[Change] = field(default_factory=list)  # per-symbol classified changes

    @property
    def breaking(self) -> list[Change]:
        return [c for c in self.changes if c.severity == BREAKING]

    def to_dict(self) -> dict:
        return {
            "added": sorted(self.added),
            "removed": sorted(self.removed),
            "changes": [
                {"symbol": c.symbol, "kind": c.kind, "severity": c.severity, "detail": c.detail}
                for c in sorted(self.changes, key=lambda c: (_ORDER[c.severity], c.symbol, c.kind))
            ],
            "summary": {
                "added": len(self.added),
                "removed": len(self.removed),
                "breaking": len(self.breaking),
                "changed_symbols": len({c.symbol for c in self.changes}),
            },
        }


# -- signature parsing -------------------------------------------------------

@dataclass(frozen=True)
class _Param:
    name: str
    required: bool
    annotation: str | None
    keyword_only: bool


@dataclass(frozen=True)
class _Sig:
    params: dict[str, _Param]
    has_vararg: bool          # *args present
    has_kwarg: bool           # **kwargs present
    returns: str | None
    parsed: bool              # False → signature string could not be parsed


def _ann(node) -> str | None:
    return ast.unparse(node) if node is not None else None


def _parse_signature(signature: str | None) -> _Sig:
    if not signature:
        return _Sig({}, False, False, None, parsed=False)
    try:
        tree = ast.parse(f"def {signature}: ...")
        fn = tree.body[0]
        assert isinstance(fn, ast.FunctionDef)
    except (SyntaxError, AssertionError, ValueError):
        return _Sig({}, False, False, None, parsed=False)
    a = fn.args
    params: dict[str, _Param] = {}
    positional = a.posonlyargs + a.args
    n_defaults = len(a.defaults)
    n_required = len(positional) - n_defaults
    for i, arg in enumerate(positional):
        params[arg.arg] = _Param(arg.arg, required=i < n_required,
                                  annotation=_ann(arg.annotation), keyword_only=False)
    for arg, default in zip(a.kwonlyargs, a.kw_defaults):
        params[arg.arg] = _Param(arg.arg, required=default is None,
                                 annotation=_ann(arg.annotation), keyword_only=True)
    return _Sig(params, has_vararg=a.vararg is not None,
                has_kwarg=a.kwarg is not None, returns=_ann(fn.returns), parsed=True)


# -- classification ----------------------------------------------------------

def _classify_signature(sid: str, old: Node, new: Node) -> list[Change]:
    """Breaking/warning/info changes between two versions of the same function."""
    so, sn = _parse_signature(old.signature), _parse_signature(new.signature)
    if not (so.parsed and sn.parsed):
        if (old.signature or "") != (new.signature or ""):
            return [Change(sid, "signature-changed", WARNING,
                           f"signature changed (unparsed): {old.signature!r} → {new.signature!r}")]
        return []
    out: list[Change] = []

    # removed parameters — callers passing them break (unless **kwargs can absorb a
    # keyword one, which still loses the parameter's meaning → keep it breaking).
    for name, p in so.params.items():
        if name not in sn.params:
            out.append(Change(sid, "param-removed", BREAKING, f"parameter `{name}` removed"))
    # added required parameters — existing calls omit them.
    for name, p in sn.params.items():
        if name not in so.params and p.required:
            out.append(Change(sid, "param-added-required", BREAKING,
                              f"required parameter `{name}` added"))
    # parameters that went from optional to required.
    for name, p in sn.params.items():
        old_p = so.params.get(name)
        if old_p is not None and p.required and not old_p.required:
            out.append(Change(sid, "param-made-required", BREAKING,
                              f"parameter `{name}` is now required"))
    # variadic removed (*args / **kwargs that existed).
    if so.has_vararg and not sn.has_vararg:
        out.append(Change(sid, "variadic-removed", BREAKING, "`*args` removed"))
    if so.has_kwarg and not sn.has_kwarg:
        out.append(Change(sid, "variadic-removed", BREAKING, "`**kwargs` removed"))
    # type annotation changes — not provably breaking (needs subtype reasoning), but
    # worth a reviewer's eye. Reported as warnings.
    for name, p in sn.params.items():
        old_p = so.params.get(name)
        if old_p is not None and old_p.annotation != p.annotation:
            out.append(Change(sid, "param-type-changed", WARNING,
                              f"`{name}` type {old_p.annotation} → {p.annotation}"))
    if so.returns != sn.returns:
        out.append(Change(sid, "return-type-changed", WARNING,
                          f"return type {so.returns} → {sn.returns}"))
    # new optional parameters are backward-compatible — info only.
    for name, p in sn.params.items():
        if name not in so.params and not p.required:
            out.append(Change(sid, "param-added-optional", INFO,
                              f"optional parameter `{name}` added"))
    return out


def _is_public(node: Node) -> bool:
    return node.visibility == "public"


def diff_api(old: Graph, new: Graph) -> ApiDiff:
    """Diff the public API surface of two graphs (old → new)."""
    diff = ApiDiff()
    old_nodes = {i: n for i, n in old.nodes.items() if n.kind in ("function", "class", "attribute")}
    new_nodes = {i: n for i, n in new.nodes.items() if n.kind in ("function", "class", "attribute")}

    for sid, n in new_nodes.items():
        if sid not in old_nodes and _is_public(n):
            diff.added.append(sid)

    for sid, o in old_nodes.items():
        n = new_nodes.get(sid)
        if n is None:
            if _is_public(o):
                diff.removed.append(sid)      # public symbol gone → breaking (see render)
            continue
        # present in both — classify the change
        if _is_public(o) and not _is_public(n):
            diff.changes.append(Change(sid, "made-private", BREAKING,
                                       "public symbol is now private"))
            continue
        if not _is_public(o) and not _is_public(n):
            continue  # private both sides — not an API change
        if not _is_public(o) and _is_public(n):
            diff.added.append(sid)            # newly public = new API
            continue
        # public both sides
        if o.kind != n.kind:
            diff.changes.append(Change(sid, "kind-changed", BREAKING,
                                       f"kind {o.kind} → {n.kind}"))
            continue
        if not o.is_deprecated and n.is_deprecated:
            diff.changes.append(Change(sid, "deprecated", WARNING,
                                       "symbol newly marked deprecated"))
        if n.kind == "function":
            diff.changes.extend(_classify_signature(sid, o, n))
    return diff
