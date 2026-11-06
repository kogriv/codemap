# Design — `review` names the doc pages a diff changes, and what they document

**Status:** 🟡 pre-registered (expectations below, committed before code). **Backlog:** R1-C89. **Gap:**
[`gaps/review_docs_diff_2026-11-06.md`](../../gaps/review_docs_diff_2026-11-06.md).

## D1 — a hunk in a doc page names the page

When a placed file (R1-C87) is the file of a `doc` node, its hunks name that page, not nothing. The result gains
`changed_docs`: `[{doc, file, documents: [symbol ids the page references]}]`, sorted by `doc`. Doc pages are not
dossiers in `changed`: they have no callers, contract or risk, and must not move the risk ranking or appear in
`high_risk`.

## D2 — what the summary and the markdown say

- `summary.changed_docs` counts them; `unresolved_hunks` no longer holds doc-page hunks.
- Markdown, after the symbol line: "**N changed doc page(s)** — check they still describe the code:" followed by
  one line per page, "`docs/x.md` documents a, b, c (+k more)", capped at 8 names.
- A Markdown file that is in no doc root, or names no core symbol, is not a node. It stays in `skipped_files`, as
  in R1-C87.

No graph change. The review answer gains a field; it ships with R1-C85 under **`ANSWER_FORMAT` 9**.

## Pre-registered expectations

Run on the branch against 0.0.32. E1 and E2 fail on 0.0.32.

| # | Expectation |
|---|---|
| E1 | bquant `cf039ef` (graph `--docs docs`, four consumers), diff `cf039ef^..cf039ef`: `changed_docs` names every changed `docs/api/analysis/*.md` page that is a doc node, each with its documented symbols; `unresolved_hunks` is empty; the trace log is in `skipped_files`; 0 code symbols |
| E2 | Fixture: a docs page referencing `pkg.m.f`; a diff to it → `changed_docs == [{doc, file, documents: ["pkg.m.f"]}]`, `changed == []` |
| E3 | A diff of code and a doc page: the code dossiers are identical to those of the code-only diff, the page is in `changed_docs`, and never in `high_risk` |
| E4 | Full suite passes; guards for D1 and D2 go red when reverted; a cosmetic control stays green |
