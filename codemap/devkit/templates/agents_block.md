<!-- codemap-devkit:begin v{{devkit_version}} — managed by the codemap devkit: edit outside this block; an edit inside is kept and reported until `codemap devkit update --force` -->
## codemap — the code graph of `{{package_name}}`

codemap answers structural questions about `{{package}}` from a static graph (`{{graph}}`), through the MCP
server `codemap` or the CLI. When the question is about structure — who calls, what depends, what a change
reaches — ask the graph instead of reading files or grepping.

**When to call what**
- Who calls X → `callers` (MCP), not grep: grep cannot tell a call from a mention, nor one class's method
  from another class's method of the same name.
- What X uses → `callees` (MCP). Where X is and what it is → `query` (MCP). The source of one symbol →
  `source` (MCP), instead of opening a long file.
- Before changing a public function, a model or a signature → `impact` (MCP). Write the reach (modules,
  callers, tests) into the task or the review.
- Which tests to run for X → `tests` (MCP). A symbol that is registered under a name and called by a string
  is not seen through that string: say so rather than conclude it is untested.
- The shape of the system → `architecture` (MCP) and `communities` (MCP).
- Before a merge → `git diff main... | codemap review --graph {{graph}}`, and attach the output.

**Read before trusting an answer**
- `currency: behind` — the graph is older than the tree. Rebuild (`codemap refresh {{graph}}`) or say the
  answer is about the older tree.
- `resolved.ambiguous` — the short name matched several symbols; ask again by the full name.
- `limit.truncated: true` — the list is not complete.
- In `source`, use code with `result.status: verified`. Rebuild and reload when the
  status is `behind` or `unverified` before relying on the recorded line range.

**The architecture contract** — `[architecture]` in `codemap.toml`, run as
`codemap check --graph {{graph}} --root . --require-contract --require-current`.
In MCP, set `require_contract` and `require_current`, then read `result.ok`. `allowed` there is a
ratchet: every import between two layers must be a listed pair. A red `allowed` means a new dependency
between layers: remove the import, or add the pair by hand inside the generated region **with a comment
giving the reason**, and let the review judge it. `codemap devkit ratchet --tighten` removes the pairs
nothing uses any more.

**Beyond the Python graph** — codemap reads Python only{{outside_languages}}. For other languages, and for
needs codemap does not cover (duplicates, security patterns, complexity, DB query counts), call `advise`
(MCP) or `codemap advise "<need>"`: the codemap lab's catalog of other tools. Each claim there is `measured`,
`probed`, `read` (nobody in the lab ran it) or `rejected`: say which when you rely on it, and check a `read`
tool on a question whose answer you know first. A not-found answer carrying `outside_graph` means the file
is not in the graph, not that nothing uses it.

**A defect in codemap** — a wrong answer, a missing edge, a false alarm, a crash: tell the codemap
maintainers, and file an issue at https://github.com/kogriv/codemap/issues with a minimal example on invented
names. The tracker is public: no code, names or paths of this project. Give the question, codemap's answer,
the right answer and why, and the output of `codemap --version`.

**Upkeep** — the pinned codemap version is this project's decision. `codemap devkit status` says what is
behind; `codemap devkit update` brings this block, the MCP entry and the hook to the installed devkit.
<!-- codemap-devkit:end -->
