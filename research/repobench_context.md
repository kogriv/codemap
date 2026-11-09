# Does the graph rank the context a completion needs? RepoBench without a model (R1-C93)

**Status:** pre-registered 2026-11-09, before the measured run. Harness:
[`bench/repobench_context.py`](bench/repobench_context.py) (committed with or after this text, before the run).

## 0. Question, and what this is not

`pack` has been measured against git history (V2, `pack_usefulness.md`), on traversal direction (V3,
`pack_direction.md`) and in a paid agent pilot (V4, `pack_agent_pilot.md`). Every one of those oracles came from
our own repositories. This is the first oracle **someone else built**: RepoBench (Liu et al., ICLR 2024), Python
v1.1, the set used for cross-file line completion by later work such as arXiv 2611.07510.

Each RepoBench row is a file cut just before a line (`next_line`), plus the in-repository definitions the file
imports (`context`, the candidates). One candidate is marked gold: the definition `next_line` uses. The task here
is RepoBench-R's: **rank the candidates so that gold is first.** No model is involved. Every number re-derives
from the pinned dataset revision, the pinned clone commits and the pinned codemap commit.

**What this does not measure.** Whether a model completes the line better with codemap's context (that half is
R1-C61's paid door and stays closed). And `pack` itself is not called: `pack` orders a budgeted slice by
`Query.rank(seeds, direction="both")`. This measures that rank, the thing `pack` orders by, on candidates the
dataset supplies.

## 1. Inputs, fixed

- **Dataset:** `tianyang/repobench_python_v1.1`, revision `8a7cf0c8942cc1aa066bf261839650ac55a2ff79`, splits
  `cross_file_first` (both shards) and `cross_file_random`. `in_file` is out: its gold is `-1`. Licence: CC
  (RepoBench states BY-NC-ND 4.0). The data is not redistributed; results name rows by split, shard, row index,
  repository and path, and carry no code.
- **Source:** the dataset ships no repository and no commit. Each repository is cloned anonymously from GitHub,
  and the tree is the **last commit before 2024-01-01** (rows were created 2023-10-07 … 2023-12-31). A row is
  used only if that commit's file contains `next_line` and the last 300 characters of `cropped_code` (A2 below).
  The commit of every repository is recorded in the results.
- **codemap:** the commit the harness is committed at, fast tier (no `--deep`), `PYTHONHASHSEED=0`.

**Sample.** All repositories that appear in either split, sorted, shuffled with `random.Random(93)`. Repositories
are taken in that order until each split has **300 eligible rows**, or 600 repositories have been tried. From one
repository at most **3 rows per split** are used, picked with the same seeded generator before any eligibility
check. Repositories with more than 2000 tracked `.py` files are skipped and counted.

**Eligibility, in order; every drop is counted (attrition table):**
- **A1** the clone succeeds;
- **A2** the file at the dated commit matches the row (above);
- **A3** the file lies inside a regular package: the topmost ancestor directory `D` such that `D` and every
  directory from `D` down to the file hold `__init__.py`. `D` is what codemap builds; node ids start with its
  name;
- **A4** at least two candidates;
- **A5** the truncated file parses (below);
- **A6** `codemap build D` exits 0.

**No leakage.** The graph must not see `next_line` or anything after it. The file is replaced, in the clone, by
its lines before `next_line` (the cursor line is the first line equal to `next_line` that follows the matched
`cropped_code` tail). If that does not parse, one line `pass` at `next_line`'s indentation is appended; if it
still does not parse, the row drops at A5. Every other file stays as at the dated commit.

**Seed.** The innermost function or class node of the truncated module whose `lineno … endlineno` contains the
last kept line; if none, the module node.

**Candidate → node.** A candidate's path, relative to `D`'s parent, gives a module id; the node is
`<module>.<identifier>`, or the module node itself if the identifier names that module. A candidate outside `D`
or with no such node has no node. It scores below every node and is not dropped. That is codemap's failure, and
it is counted (column "gold has a node").

## 2. Rankers

Ties in every ranker are broken by one generator seeded per row (`random.Random(f"{split}:{shard}:{index}")`),
the same for all rankers. A ranker that cannot score a candidate gives it −1.

| Ranker | Score of a candidate |
|---|---|
| **graph** | `Query.rank(seeds=[seed], direction="both")[node]` |
| global | `Query.rank()[node]`: the same graph, no seed (does the seed matter?) |
| random | constant (ties only) |
| jaccard | Jaccard of `\w+` token sets: `cropped_code` vs the candidate's snippet (RepoBench-R's lexical baseline) |
| unused | 1 if the identifier does not occur as a word in `cropped_code`, else 0 |
| recency | character offset of the identifier's last word occurrence in `cropped_code`, −1 if none |
| unused+graph | `unused`, ties broken by **graph** before the random generator |

`unused` matters on `cross_file_first`: there gold is the first use of an imported name, so by construction gold
is a name not used yet. A graph that does not beat that rule adds nothing the import list does not already say.

**Metrics.** acc@1 and acc@3 per split. 95 % intervals by bootstrap over repositories (10 000 resamples, seed 93),
for each ranker and for the paired difference graph − X. Also, without being given the candidates: the position
of the gold node in `graph`'s order over **all** nodes outside the truncated file (recall@10, recall@20), the
question `pack` actually answers.

**Controls.**
- **C1 leak control:** the same rows, with the graph built on the **untruncated** file. The edge from the
  enclosing code to gold now exists, so graph acc@1 on `cross_file_first` must rise. This is the check that the
  scoring is wired to the graph, and that truncation is what holds it down.
- **C2 determinism:** the whole run twice; per-row results identical.

## 3. Pre-registered expectations

At least one must fail if the harness does nothing: C1 (P6) and the graph-vs-random gap (P2) cannot both hold
for a ranker that ignores the graph.

- **P1 coverage.** Eligible rows / rows drawn: 30–60 % per split. A3 (no regular package) is the largest single
  drop. Probe on 20 repositories before this text: 19 cloned, 32/36 rows matched at the dated commit, about half
  of the repositories had no regular package around the file.
- **P2.** `cross_file_first`: graph acc@1 > random, interval of the difference excludes 0.
- **P3.** `cross_file_first`: graph acc@1 **<** unused. I expect the first-use structure to beat the graph.
- **P4.** `cross_file_random`: recency is the strongest non-graph ranker, and graph acc@1 is below it.
- **P5.** graph > global on both splits, interval excludes 0 (the seed matters).
- **P6 (C1).** Untruncated graph acc@1 on `cross_file_first` is at least 15 points above the truncated one.
- **P7 (C2).** Identical per-row results across two runs.
- **P8.** `cross_file_first`: unused+graph > unused by at least 3 points acc@1. The realistic use: the graph on
  top of a cheap rule, not instead of it. This is the one I am least sure of.

**What would count as "the graph helps here":** graph, or unused+graph, beats the best non-graph ranker on a
split, with the interval of the difference excluding 0. I predict that holds at most for P8.

Anything not listed goes under surprises in the reconciliation.

## 4. Reconciliation

Not run yet.
