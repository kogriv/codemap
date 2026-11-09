# Does the graph rank the context a completion needs? RepoBench without a model (R1-C93)

**Status:** ✅ **done** (2026-11-09, reconciled below: negative result). Pre-registered in c2f66d6, before the measured run. Harness:
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

## 4. Reconciliation (2026-11-09, harness 2533e1f, codemap 0.0.35 @2533e1f)

Per-row results: [`bench/repobench_context_results.jsonl`](bench/repobench_context_results.jsonl) (1760 drawn rows
from 448 repositories; no code). `report` prints every table below from that file.

**Before the measured run.** The first attempt (f77a5dc) crashed before writing any result: one
`cross_file_random` row has `gold_snippet_index` outside its candidate list. 2533e1f counts such rows as stage
`A4-gold` (one row) and turns any per-repository exception into a counted stage `error` (none occurred). No result
was seen before the fix.

**`cross_file_first`**: 300 eligible of 857 drawn (35 %), 193 repositories, 7.6 candidates on average. Drops: A3
288, A2 127, A5 75, A1 55, A6 6, size 6.

| ranker | acc@1 [95 %] | acc@3 | graph − ranker [95 %] |
|---|---|---|---|
| graph | 0.183 [0.140, 0.230] | 0.513 | — |
| global | 0.173 [0.133, 0.218] | 0.470 | +0.010 [−0.026, +0.047] |
| random (observed; expected 0.218) | 0.203 [0.158, 0.252] | 0.580 | −0.020 [−0.059, +0.018] |
| jaccard | 0.163 [0.123, 0.205] | 0.523 | +0.020 [−0.038, +0.081] |
| **unused** | **0.350** [0.294, 0.409] | 0.697 | −0.167 [−0.220, −0.113] |
| recency | 0.117 [0.080, 0.155] | 0.457 | +0.067 [+0.023, +0.113] |
| unused+graph | 0.340 [0.287, 0.397] | 0.663 | −0.157 [−0.203, −0.112] |

**`cross_file_random`**: 300 eligible of 856 drawn (35 %), 187 repositories, 7.3 candidates. Drops: A3 275,
A2 106, A5 105, A1 61, A6 2, size 6, A4-gold 1.

| ranker | acc@1 [95 %] | acc@3 | graph − ranker [95 %] |
|---|---|---|---|
| graph | 0.270 [0.221, 0.320] | 0.683 | — |
| global | 0.263 [0.213, 0.316] | 0.660 | +0.007 [−0.038, +0.052] |
| random (expected 0.228) | 0.200 [0.154, 0.250] | 0.597 | +0.070 [+0.020, +0.122] |
| jaccard | 0.283 [0.234, 0.332] | 0.603 | −0.013 [−0.075, +0.050] |
| unused | 0.117 [0.082, 0.153] | 0.470 | +0.153 [+0.096, +0.211] |
| **recency** | **0.500** [0.439, 0.560] | 0.803 | −0.230 [−0.296, −0.163] |
| unused+graph | 0.110 [0.076, 0.146] | 0.477 | +0.160 [+0.110, +0.210] |

Without the candidates (`pack`'s own question, gold among all nodes outside the file): recall@10 / @20 = 0.107 /
0.203 on `first`, 0.277 / 0.367 on `random`.

| # | Result |
|---|---|
| P1 | ✅ 35 % on both splits, inside 30–60 %. A3 is the largest drop: 288 of 557 (`first`), 275 of 556 (`random`) |
| P2 | ❌ `first`: graph − random −0.020 [−0.059, +0.018]. The graph is not better than chance on first uses |
| P3 | ✅ `first`: graph 0.183 < unused 0.350 |
| P4 | ✅ `random`: recency 0.500 is the strongest ranker; graph 0.270 is below it |
| P5 | ❌ graph − global includes 0 on both splits (+0.010, +0.007). **The seed adds nothing measurable**; on `random` the gain over chance (+0.070) is the gain of global centrality |
| P6 | ✅ C1: untruncated +0.197 [+0.140, +0.254] on `first` (≥ 0.15), +0.147 on `random`. The scoring is wired to the graph, and what the graph knows about the line is the line itself |
| P7 | ✅ C2: the two full runs give identical per-row results |
| P8 | ❌ unused+graph − unused −0.010 [−0.048, +0.026] on `first`. The graph does not even break the cheap rule's ties well |

**Verdict.** On this benchmark codemap's seeded rank **does not help** pick the definition a completion needs. On
first uses it is at chance, a one-line rule ("an imported name not used yet") doubles it, and on repeat uses
"the most recently used name" doubles it. Where the rank beats chance, global centrality does the same. The one
expectation I was least sure of (P8) failed too. This is a negative result, and it stands as one: no rescoring,
no subset was chosen after the fact to change it.

**Exploratory, not pre-registered.** Restricted to rows whose gold has a node (216 / 217): `first` graph 0.185 vs
random 0.204, `random` graph 0.313 vs global 0.304. The picture does not change, so the 28 % of rows where gold
has no node is not what holds the graph down.

**Surprises.**
- **Coverage is the bigger finding.** Only 35 % of drawn rows survive, and the largest drop (about half of all
  drops) is A3: the file is not inside a regular package (scripts at the root, directories without
  `__init__.py`). codemap cannot build such a repository at all. In 28 % of eligible rows the gold candidate
  lies outside the built package and has no node. For research-code repositories like RepoBench's, the
  package-only build is the binding limit, before any question of ranking.
- **A6: codemap's build crashed on 8 rows of 5 repositories.** Three repositories: `Could not resolve alias …`
  for a name re-exported from an uninstalled third-party package. One: a facade-layout refusal. One: a
  non-UTF-8 source file. A build should degrade on these, not exit non-zero.
- A5 (the truncated file still does not parse after one `pass`) dropped 75 + 105 rows, more than expected: an
  open bracket or a string at the cut needs more than a block body.

**What follows.** The rank is not worth tuning for this task. The two build gaps go to the backlog as their own
items (R1-C94: repositories without a regular package; R1-C95: build crashes on an unresolvable alias and on
non-UTF-8 source). R1-C61's paid door gains nothing from this run: it gives no reason to open it.
