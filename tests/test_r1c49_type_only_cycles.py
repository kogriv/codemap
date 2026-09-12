"""R1-C49 — a cycle has three kinds, by the weakest scope that closes it.

From [issue #18](https://github.com/kogriv/codemap/issues/18), the second half: R1-C48
took an import under `if TYPE_CHECKING:` out of the eager graph and dropped it into the
lazy bucket — where the consumer's second rule was waiting. For the one tree of three
with both rules on, the release changed one red into another:

    codmap 0.0.12   no_cycles       gate_metrics → rolling_calib → gate_metrics   exit 2
    codmap 0.0.13   no_lazy_cycles  the same chain                                exit 2

`no_lazy_cycles` exists against a lazy import used to walk *around* `no_cycles` — a
runtime dependency that was deferred. An import under `TYPE_CHECKING` is not that: it
never executes, so there is no runtime dependency to defer. Two different things were
being counted as one number, and the second rule was refusing the standard typing idiom.

What is pinned (design `docs/design/type_only_cycles.md`):

1. The partition is by the **weakest scope that closes the cycle** — a pair coupled
   through a function-local import stays *lazy* however many type imports also run
   between them, or a tree could hide runtime coupling by adding one.
2. `no_lazy_cycles` narrows back to function-local; `no_type_only_cycles` is the opt-in
   rule for the third kind.
3. Every consumer prints all three counts, zero included (R1-C28), and the scope line
   names only what *this* contract left unjudged.
"""

from __future__ import annotations

import pytest

from codemap import arch
from codemap.extract import extract
from codemap.query import Query
from codemap.serve.architecture import build_architecture, render_architecture
from codemap.serve.audit import build_dependencies, render_dependencies
from codemap.serve.check import build_check, render_check
from codemap.serve.livingdocs import render_docs

TYPED_A = '''from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .typed_b import B


def score(b: "B") -> int:
    return 1
'''
TYPED_B = '''from .typed_a import score


class B:
    def go(self):
        return score(self)
'''
LAZY_A = '''def use():
    from .lazy_b import B
    return B
'''
LAZY_B = '''from .lazy_a import use


class B:
    pass
'''
# runtime coupling AND a type import between the same pair: the walk-around
MIXED_A = '''from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .mixed_b import M


def use(m: "M"):
    from .mixed_b import M as _M
    return _M
'''
MIXED_B = '''from .mixed_a import use


class M:
    pass
'''


def _pkg(tmp_path, files):
    pkg = tmp_path / "bp"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    for name, body in files.items():
        (pkg / f"{name}.py").write_text(body)
    return pkg


@pytest.fixture(scope="module")
def both(tmp_path_factory):
    """One cycle of each non-eager kind, in one tree."""
    pkg = _pkg(tmp_path_factory.mktemp("r1c49"),
               {"typed_a": TYPED_A, "typed_b": TYPED_B, "lazy_a": LAZY_A, "lazy_b": LAZY_B})
    return Query(extract(str(pkg)))


def _flat(cycles):
    return sorted(sorted(c) for c in cycles)


# -- D1: the partition ------------------------------------------------------------------

def test_the_three_kinds_are_disjoint_and_named(both):
    assert both.import_cycles() == []
    assert _flat(both.lazy_import_cycles()) == [["bp.lazy_a", "bp.lazy_b"]]
    assert _flat(both.type_only_import_cycles()) == [["bp.typed_a", "bp.typed_b"]]


def test_a_type_import_does_not_launder_runtime_coupling(tmp_path):
    """The walk-around: the pair is coupled at run time *and* imports each other's types.
    Weakest-scope-that-closes makes it lazy — presence of a type edge would make it
    type-only, and a tree could then hide real coupling by adding one."""
    q = Query(extract(str(_pkg(tmp_path, {"mixed_a": MIXED_A, "mixed_b": MIXED_B}))))
    assert _flat(q.lazy_import_cycles()) == [["bp.mixed_a", "bp.mixed_b"]]
    assert q.type_only_import_cycles() == []


def test_an_eager_cycle_stays_eager_whatever_else_runs(tmp_path):
    q = Query(extract(str(_pkg(tmp_path, {
        "a": "from typing import TYPE_CHECKING\nfrom .b import y\nif TYPE_CHECKING:\n    from .b import Y\nx = 1\n",
        "b": "from .a import x\ny = 2\n"}))))
    assert _flat(q.import_cycles()) == [["bp.a", "bp.b"]]
    assert q.lazy_import_cycles() == [] and q.type_only_import_cycles() == []


# -- D2: the rules ----------------------------------------------------------------------

def test_the_typing_idiom_alone_passes_both_old_rules(tmp_path):
    """The consumer's case: a tree whose only non-eager cycle is a type-only one used to
    fail `no_lazy_cycles`. It is green now, and the new rule is what refuses it."""
    q = Query(extract(str(_pkg(tmp_path, {"typed_a": TYPED_A, "typed_b": TYPED_B}))))
    contract = arch.ArchitectureContract(no_cycles=True, no_lazy_cycles=True)
    assert arch.check_contract(q, contract) == []
    stricter = arch.ArchitectureContract(no_cycles=True, no_lazy_cycles=True,
                                         no_type_only_cycles=True)
    v = arch.check_contract(q, stricter)
    assert [x.rule for x in v] == ["no_type_only_cycles"]
    assert {m for chain in v[0].modules for m in chain.split(" → ")} == {"bp.typed_a", "bp.typed_b"}
    assert "`if TYPE_CHECKING:`" in v[0].summary


def test_each_rule_names_only_its_own_kind(both):
    v = arch.check_contract(both, arch.ArchitectureContract(
        no_cycles=True, no_lazy_cycles=True, no_type_only_cycles=True))
    by_rule = {x.rule: x for x in v}
    assert set(by_rule) == {"no_lazy_cycles", "no_type_only_cycles"}
    named = lambda x: {m for chain in x.modules for m in chain.split(" → ")}
    assert named(by_rule["no_lazy_cycles"]) == {"bp.lazy_a", "bp.lazy_b"}
    assert named(by_rule["no_type_only_cycles"]) == {"bp.typed_a", "bp.typed_b"}


def test_the_new_rule_is_off_by_default_and_read_from_the_contract(tmp_path):
    assert arch.ArchitectureContract().no_type_only_cycles is False
    (tmp_path / "codemap.toml").write_text(
        "[architecture]\nno_cycles = true\nno_type_only_cycles = true\n")
    c = arch.load_contract(tmp_path)
    assert c.no_type_only_cycles is True and c.is_empty() is False


def test_a_contract_with_only_the_new_rule_is_not_empty():
    assert arch.ArchitectureContract(no_type_only_cycles=True).is_empty() is False


# -- D3: disclosure ---------------------------------------------------------------------

def test_the_scope_line_names_only_what_this_contract_left_out(both):
    c = arch.ArchitectureContract(no_cycles=True)
    s = build_check(both, c, arch.check_contract(both, c))["scope"][0]
    assert (s["lazy"], s["type_only"], s["count"]) == (1, 1, 2)
    assert s["lazy_gated"] is False and s["type_only_gated"] is False
    md = render_check(both, c, arch.check_contract(both, c))
    assert "function-local import (runtime coupling" in md and "`if TYPE_CHECKING:`" in md

    gated = arch.ArchitectureContract(no_cycles=True, no_lazy_cycles=True)
    s = build_check(both, gated, arch.check_contract(both, gated))["scope"][0]
    assert (s["lazy"], s["type_only"]) == (0, 1), "a gated kind is no longer 'not judged'"
    md = render_check(both, gated, arch.check_contract(both, gated))
    assert "function-local import (runtime coupling" not in md
    assert "no_type_only_cycles = true` gates them" in md


def test_nothing_is_left_unjudged_when_all_three_rules_are_on(both):
    c = arch.ArchitectureContract(no_cycles=True, no_lazy_cycles=True,
                                  no_type_only_cycles=True)
    assert build_check(both, c, arch.check_contract(both, c))["scope"] == []


def test_the_reports_carry_both_kinds_and_say_zero(both, tmp_path):
    a = build_architecture(both)
    assert _flat(a["type_only_cycles"]) == [["bp.typed_a", "bp.typed_b"]]
    md = render_architecture(both)
    assert "Dependency cycles closed only by a function-local import: 1" in md
    assert ("Dependency cycles closed only by an import that never runs "
            "(`if TYPE_CHECKING:` or a `.pyi`): 1") in md
    dep = render_dependencies(both)
    assert "1 further cycle(s) close through a function-local import" in dep
    assert "1 through an import that never runs" in dep
    assert _flat(build_dependencies(both)["type_only_import_cycles"]) == [["bp.typed_a", "bp.typed_b"]]
    docs = render_docs(both)
    assert "closed only by a function-local import" in docs
    assert "closed only by an import that never runs" in docs

    quiet = Query(extract(str(_pkg(tmp_path, {"a": "from .b import x\n", "b": "x = 1\n"}))))
    assert build_architecture(quiet)["type_only_cycles"] == []
    assert "and 0 through an import that never runs" in render_dependencies(quiet)


# -- f1: a rule that ran must name itself ---------------------------------------------------

def test_every_enforced_rule_names_itself_in_the_passing_line(tmp_path):
    """Reported by the consumer the day they took 0.0.14: `no_type_only_cycles` was
    enforced and absent from "Rules enforced", and a contract holding only that rule
    printed "Rules enforced: ." — the R1-C30-f2 defect from the other side. The loop is
    over the contract's own fields, so a rule added later without a line here fails."""
    import dataclasses
    quiet = Query(extract(str(_pkg(tmp_path, {"a": "from .b import x\n", "b": "x = 1\n"}))))
    skip = {"error", "path"}
    names = [f.name for f in dataclasses.fields(arch.ArchitectureContract) if f.name not in skip]
    assert "no_type_only_cycles" in names
    for name in names:
        value = {"layers": ("core",), "independent": (("core", "data"),),
                 "forbidden": (("core", "data"),)}.get(name, True)
        contract = arch.ArchitectureContract(**{name: value})
        assert not contract.is_empty(), f"{name} alone must be a contract"
        md = render_check(quiet, contract, arch.check_contract(quiet, contract))
        assert "Contract satisfied" in md, f"{name} alone should pass on a two-module tree"
        listed = md.split("Rules enforced:")[1].split(".\n")[0]
        assert listed.strip(), f"{name} ran and the line named nothing"
        stem = {"layers": "layered", "independent": "independent",
                "forbidden": "forbidden"}.get(name, name)
        assert stem in listed, f"{name} was enforced but is missing from {listed!r}"

