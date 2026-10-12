# C26 feasibility probe: deterministic lexical locate (2026-10-12, offline, no GPU)
Script: src/analysis/locate_lexical_probe.py (BM25 over non-test .py files at base_commit, query = problem statement + hints,
path tokens x3). Tasks: px 152 minus those without gold .py source file / repo snapshot -> n=107; solve rate = C25 s1+s2 mean.

| subset | n | recall@1 | recall@3 | recall@5 | C25 solve rate |
|---|---|---|---|---|---|
| all | 107 | 0.58 | 0.87 | 0.93 | 0.46 |
| repo <30 py files | 73 | 0.63 | 0.89 | 0.95 | 0.49 |
| 30-100 | 16 | 0.56 | 0.88 | 0.88 | 0.56 |
| >=100 | 18 | 0.39 | 0.78 | 0.89 | 0.31 |

Reading: a zero-LLM file-level locate puts a gold file in the top-3 for 87% of tasks (top-5 93%), and tasks where it misses are
solved less (0.36 vs 0.49 at k=3), i.e. gold-file recall is not the bottleneck of C25. Caveats: proxy repos are small (median 22 files);
hidden Google-style repos are larger (recall@1 drops to 0.39 at >=100 files) and gold-file recall is file-level, not function-level.
Implication for C26: replace the 60-call LLM analyzer (61% duplicate calls) by "top-5 files by BM25 + their def/class outline" fed
straight into the one thinking planner; worth building only with a go (directive: one problem at a time). Gate: <=4.5 min/task L4,
acc >= c23 + 0.05 paired.
