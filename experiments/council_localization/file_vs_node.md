## File vs node level

### Offline: BM25 (graph nodes, issue+hints) vs deployed locate.py (issue[:1500]) on n=117 common tasks

| system | file hit@1 | file hit@3 | file hit@5/6 | node hit@1 | node hit@5 |
|---|---|---|---|---|---|
| BM25 (node ranking -> files) | 0.496 | 0.667 | 0.786 | 0.282 | 0.513 |
| locate.py skill | 0.487 | 0.667 | 0.795 (k=6 files) | 0.282 | 0.479 |

Skill over all 128 tasks with a gold file: file@1 0.484, file@3 0.664, file@6 0.781, node@5 0.438.

Conditional: given BM25 puts a gold file in top-3 files (78 tasks), BM25 node hit@5 = 0.744; # gold nodes per task median 1, files per task median 1.

### End-to-end (8 Kaggle runs x 30 tasks = 240 task-runs)

- task-runs with a non-test patch: 166; of these the patch touches >=1 gold file: 140 (84.3%).
- P(resolved | touched gold file) = 68/140 = 0.486; P(resolved | patched only non-gold files) = 1/26.
- locate.py skill calls per run: {'c1': 46, 'c2': 35, 'c3': 4, 'c4': 2, 'c5a': 0, 'c5b': 3, 'c6a': 6, 'c6b': 3} (total 99 over 240 task-runs).

Per-task (n=30) outcome split by offline localization quality (mean over 8 runs):

| offline signal | group | n tasks | mean solve rate | mean P(agent touches gold file) |
|---|---|---|---|---|
| BM25 file hit@1 | hit | 11 | 0.261 | 0.614 |
| BM25 file hit@1 | miss | 15 | 0.233 | 0.517 |
| BM25 file hit@3 | hit | 17 | 0.199 | 0.544 |
| BM25 file hit@3 | miss | 9 | 0.333 | 0.583 |
| BM25 node hit@5 | hit | 14 | 0.286 | 0.580 |
| BM25 node hit@5 | miss | 12 | 0.198 | 0.531 |
| skill file hit@1 | hit | 13 | 0.394 | 0.721 |
| skill file hit@1 | miss | 16 | 0.219 | 0.500 |
| skill file hit@3 | hit | 19 | 0.355 | 0.691 |
| skill file hit@3 | miss | 10 | 0.188 | 0.425 |
| skill node hit@5 | hit | 16 | 0.375 | 0.688 |
| skill node hit@5 | miss | 13 | 0.202 | 0.490 |

Spearman (n=26): solve-rate vs BM25 node MRR 0.10; touch-rate vs BM25 node MRR 0.30; solve vs #gold files 0.03.

Tasks where the agent touches a gold file in >=6/8 runs: 13/30; their mean solve rate 0.558. Tasks touched in <=2/8 runs: 8/30 (solve rate 0.031).
