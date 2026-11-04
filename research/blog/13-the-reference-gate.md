# The reference gate agreed with my graph to the last edge. Then the question I asked it caught me too.

*import-linter is the architecture gate Python teams already use. Its import graph matched my 266-edge truth
exactly, and on my test project's contract its verdicts matched mine on every tree. It has three ways to
pass without checking, all about configuration. I predicted two of them from the source. The third question,
asked of my own gate, found the same hole in mine.*

---

I build [codemap](https://github.com/kogriv/codemap), a static analyzer whose `codemap check` enforces an
architecture contract in CI. Two posts ago I probed a rival's gate for silent passes and found three in mine.
This time the rival is the incumbent.

## The tool

[import-linter](https://github.com/seddonym/import-linter) (2.15, BSD-2-Clause, since 2019) reads contracts
from `.importlinter`, `setup.cfg` or `pyproject.toml`: `layers`, `forbidden`, `independence`, `protected`,
`acyclic_siblings`. `lint-imports` exits 1 when one is broken. The import graph comes from
[grimp](https://github.com/python-grimp/grimp) (3.18), which has a Rust core.

## The graph: exactly the truth

The same tree as the rest of the series: 280 files of one Python repository, pinned commit. The truth is 266
module dependencies and 45 cycles, from codemap. Expectations were committed before the first run.

| | grimp 3.18 |
|---|---|
| modules | 89 of 89 |
| edges | **266 of 266**, no false edge |
| by scope | module 240/240, inside functions 25/25, under `TYPE_CHECKING` 1/1 |
| cycles | **45 of 45**, none false |
| three builds | identical, 0.11 s each |

I had predicted at least 95 %. Two engines that share no code produced the same module graph, edge for
edge. That is the strongest outside check my truth set has had. It is corroboration, not proof: both could
share a blind spot this tree does not exercise. Still, after a series in which every other tool lost edges
somewhere, this one lost none.

## The gate: everything my probe asked

On a three-layer fixture (`high > mid > low`), each probe a fresh copy with one change:
- an upward import is caught at module level, inside a function, under `TYPE_CHECKING` (with an opt-out),
  spelled `import gp.high.h`, and inside an `__init__.py`;
- a misspelled required key, source module, layer name or boolean is an error;
- an `ignore_imports` line that matches nothing is an error;
- the cache invalidates when a file changes.

Every one of these is a question my own gate failed at least once in the last month. import-linter passes all
of them.

## Three ways to pass without checking

Two were predicted from reading the source before the run:
- **An unknown option in a contract is ignored.** The contract reads its own fields from the config and never
  looks at the rest. So `exhaustiv = True` (a typo for `exhaustive`) runs the contract without it:
  `gp layers KEPT`, exit 0, no warning. The correct spelling breaks the same tree.
- **A misspelled forbidden module is dropped.** `forbidden_modules = gp.hihg` keeps the contract while
  `low` really imports `high`. This one was already reported upstream (#386) and is fixed on `main`, not yet
  released.

The third I only recorded:
- **Zero contracts pass.** A config with no contract prints `Contracts: 0 kept, 0 broken.` and exits 0. The
  realistic way to get there is a table name in `pyproject.toml`: `[[tool.importlinter.contract]]`, singular,
  is read as no contracts at all. With `contracts`, the same file breaks.

I filed the two that are still open, after re-checking both on `main`:
[#392](https://github.com/seddonym/import-linter/issues/392) and
[#393](https://github.com/seddonym/import-linter/issues/393).

## Then I asked mine

The third question has an obvious codemap version: what if the table name is wrong?

```
[architectur]
forbidden = [{from = "core", to = "analysis"}]
```

`codemap check` printed "No `[architecture]` contract found", and exit 0. Two posts ago I closed the schema
*inside* `[architecture]`: an unknown key there is refused, with a suggestion. The table name itself stayed
the one typo that turned the gate green. `--require-contract` catches it, but that is a flag you have to know
about.

Fixed and released in 0.0.26: a table whose name is a near miss of `[architecture]` is refused, exit 2, even
when a real `[architecture]` sits beside it. Other tables are left alone. On both projects that use my gate,
the output did not change by a byte.

That is the second time a question I wrote for someone else's gate found a hole in mine. I am starting to
think that is what such questions are for.

## The same verdict, different reach

On my test project's real contract (seven layers, eight forbidden pairs), both gates agree on every tree: the
tree as it is, and three mutations that add `core → analysis` at module level, inside a function, and under
`TYPE_CHECKING`. They disagree on how much one edge breaks:
- import-linter forbids **chains**, so `data → core → analysis` breaks the `data` contract too. One
  mutation breaks **four** contracts;
- codemap names the **one edge** that points up.

Both are right by their own definition. Theirs tells you how far the damage reaches; mine tells you which line
to change. "No chain from `data` to `analysis`" is the rule people usually mean, and it is a note in my
backlog.

## When you would pick import-linter, and when codemap

**import-linter fits when:**
- **You need a gate and nothing else.** It is mature, fast, and right on every import shape I tried.
- **You want indirect rules,** or `protected` (only these modules may import that one), which codemap does
  not have.

**codemap fits when:**
- **Cycles are part of the contract.** import-linter checks cycles only between siblings. codemap has a rule
  per import scope: eager, type-only, lazy.
- **The same artifact answers other questions:** who calls this, what breaks if this signature changes, what
  a diff touches.

On a contract both can express, they agree. I would not ask anyone to switch.

## What I did not check

- `independence`, `protected` and `acyclic_siblings` beyond their docs.
- A large codebase, namespace packages, external packages.
- Whether my truth and grimp share a blind spot. They cannot tell each other about it.

---

*codemap is MIT, source-only, and does not import the code it analyses.*

```bash
pip install codmap         # the distribution; the command and the import are `codemap`
codemap check --build ./yourpkg --require-contract
```

*The import-linter card, with every expectation written before the run:
[`research/tools/import-linter.md`](../tools/import-linter.md). The fix to my own gate:
[`docs/design/contract_table_typo.md`](../../docs/design/contract_table_typo.md).*

*Previous post: [The most-starred code graph got my imports right and my cycles wrong.](12-right-imports-wrong-cycles.md)*
