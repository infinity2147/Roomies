# graph-locate offline localization eval

Labels: gold function = function (def/method, nested defs folded into the parent) whose line range in the base snapshot contains a line removed/inserted by the gold patch; gold file = existing .py file edited by the patch. Function metrics use tasks with >=1 gold function, file metrics tasks with >=1 gold .py file.
Code: `src/localize/` (prep.py, learn.py, eval_repo_locate.py, report.py); tool: `skills/graph-locate/scripts/graph_locate.py`; raw numbers `results/graph_locate/{cv,test,repo_locate}.json`. Seeded (seed 0).

## 1. Cross-validation on the train pool (public valid 107 + proxy train half 67; folds grouped by repo: fastapi, rich are leave-one-repo-out, the other 18 repos balanced into 4 folds). n_fn=155, n_file=173

| method | fn@1 | fn@3 | fn@5 | fn@10 | nDCG@10 | file@1 | file@3 | file@5 | file@10 |
|---|---|---|---|---|---|---|---|---|---|
| repo-locate (existing skill, 10 files) | 0.265 | 0.355 | 0.426 | 0.516 | - | 0.532 | 0.769 | 0.879 | 0.919 |
| BM25 only (function chunks) | 0.303 | 0.458 | 0.535 | 0.632 | 0.405 | 0.514 | 0.647 | 0.734 | 0.856 |
| hand weights, no graph (top-100 seeds) | 0.316 | 0.510 | 0.555 | 0.619 | 0.430 | 0.538 | 0.705 | 0.775 | 0.856 |
| LambdaRank-linear, no graph | 0.342 | 0.516 | 0.581 | 0.639 | 0.441 | 0.538 | 0.734 | 0.815 | 0.844 |
| LambdaRank-GBDT, no graph | 0.342 | 0.503 | 0.555 | 0.626 | 0.437 | 0.555 | 0.717 | 0.798 | 0.850 |
| graph expand + hand weights (B=0) | 0.336 | 0.497 | 0.548 | 0.613 | 0.434 | 0.555 | 0.734 | 0.763 | 0.809 |
| graph expand + hand weights (B=10) | 0.329 | 0.477 | 0.523 | 0.574 | 0.419 | 0.561 | 0.728 | 0.780 | 0.838 |
| graph + LambdaRank-linear (B=0) | 0.394 | 0.535 | 0.587 | 0.632 | 0.458 | 0.555 | 0.734 | 0.786 | 0.815 |
| graph + LambdaRank-linear (B=10) | 0.387 | 0.529 | 0.574 | 0.645 | 0.459 | 0.549 | 0.740 | 0.798 | 0.867 |
| graph + LambdaRank-GBDT (B=0) | 0.342 | 0.510 | 0.581 | 0.619 | 0.439 | 0.543 | 0.746 | 0.780 | 0.815 |
| graph + LambdaRank-GBDT (B=10) | 0.336 | 0.510 | 0.574 | 0.645 | 0.447 | 0.538 | 0.763 | 0.815 | 0.861 |
| graph + REINFORCE policy + linear scorer (B=0) | 0.394 | 0.535 | 0.587 | 0.632 | 0.458 | 0.555 | 0.734 | 0.786 | 0.815 |
| graph + REINFORCE policy + linear scorer (B=10) | 0.374 | 0.529 | 0.587 | 0.652 | 0.458 | 0.561 | 0.734 | 0.786 | 0.850 |
| graph + REINFORCE policy + GBDT scorer (B=0) | 0.342 | 0.510 | 0.581 | 0.619 | 0.439 | 0.543 | 0.746 | 0.780 | 0.815 |
| graph + REINFORCE policy + GBDT scorer (B=10) | 0.329 | 0.516 | 0.568 | 0.632 | 0.443 | 0.538 | 0.751 | 0.803 | 0.838 |

### recall of the gold function vs expansion budget B (CV): nDCG@10

| method | B=0 | B=1 | B=2 | B=5 | B=10 | B=20 |
|---|---|---|---|---|---|---|
| graph expand + hand weights | 0.434 | 0.388 | 0.417 | 0.413 | 0.419 | 0.428 |
| graph + LambdaRank-linear | 0.458 | 0.454 | 0.458 | 0.456 | 0.459 | 0.455 |
| graph + LambdaRank-GBDT | 0.439 | 0.446 | 0.444 | 0.441 | 0.447 | 0.445 |
| graph + REINFORCE policy + linear scorer | 0.458 | 0.460 | 0.459 | 0.459 | 0.458 | 0.456 |
| graph + REINFORCE policy + GBDT scorer | 0.439 | 0.444 | 0.446 | 0.444 | 0.443 | 0.445 |

### fn Hit@10 vs B (CV)

| method | B=0 | B=1 | B=2 | B=5 | B=10 | B=20 |
|---|---|---|---|---|---|---|
| graph expand + hand weights | 0.613 | 0.581 | 0.594 | 0.587 | 0.574 | 0.600 |
| graph + LambdaRank-linear | 0.632 | 0.632 | 0.639 | 0.652 | 0.645 | 0.639 |
| graph + LambdaRank-GBDT | 0.619 | 0.632 | 0.639 | 0.639 | 0.645 | 0.632 |
| graph + REINFORCE policy + linear scorer | 0.632 | 0.639 | 0.645 | 0.645 | 0.652 | 0.645 |
| graph + REINFORCE policy + GBDT scorer | 0.619 | 0.632 | 0.639 | 0.632 | 0.632 | 0.645 |

### Gold function revealed (reach) vs B (CV; fraction of gold functions inside the revealed candidate set, before ranking)

| method | B=0 | B=1 | B=2 | B=5 | B=10 | B=20 |
|---|---|---|---|---|---|---|
| graph (pool of 20 seeds + expansions) | 0.604 | 0.630 | 0.642 | 0.671 | 0.703 | 0.749 |
| REINFORCE policy | 0.604 | 0.633 | 0.655 | 0.679 | 0.707 | 0.758 |
| no-graph candidate set (top-100 seeds) | 0.843 | | | | | |

## 2. FINAL: proxy TEST half (held out; models trained on the whole train pool, evaluated once). n_fn=78 n_file=85

| method | fn@1 | fn@3 | fn@5 | fn@10 | nDCG@10 | file@1 | file@3 | file@5 | file@10 |
|---|---|---|---|---|---|---|---|---|---|
| repo-locate (existing skill, 10 files) | 0.321 | 0.487 | 0.615 | 0.654 | - | 0.729 | 0.929 | 0.953 | 0.965 |
| BM25 only (function chunks) | 0.436 | 0.705 | 0.731 | 0.808 | 0.590 | 0.694 | 0.918 | 0.941 | 0.941 |
| hand weights, no graph (top-100 seeds) | 0.500 | 0.692 | 0.731 | 0.859 | 0.624 | 0.765 | 0.882 | 0.941 | 0.953 |
| LambdaRank-linear, no graph | 0.526 | 0.692 | 0.769 | 0.821 | 0.631 | 0.765 | 0.918 | 0.929 | 0.941 |
| LambdaRank-GBDT, no graph | 0.551 | 0.718 | 0.769 | 0.821 | 0.643 | 0.718 | 0.894 | 0.929 | 0.941 |
| graph expand + hand weights (B=0) | 0.500 | 0.679 | 0.731 | 0.821 | 0.615 | 0.765 | 0.882 | 0.929 | 0.929 |
| graph expand + hand weights (B=10) | 0.500 | 0.654 | 0.705 | 0.769 | 0.599 | 0.765 | 0.871 | 0.918 | 0.918 |
| graph + LambdaRank-linear (B=0) | 0.500 | 0.667 | 0.744 | 0.808 | 0.615 | 0.753 | 0.918 | 0.929 | 0.929 |
| graph + LambdaRank-linear (B=10) | 0.513 | 0.667 | 0.756 | 0.808 | 0.616 | 0.776 | 0.906 | 0.929 | 0.929 |
| graph + LambdaRank-GBDT (B=0) | 0.538 | 0.718 | 0.769 | 0.795 | 0.636 | 0.729 | 0.918 | 0.929 | 0.929 |
| graph + LambdaRank-GBDT (B=10) | 0.551 | 0.731 | 0.782 | 0.821 | 0.644 | 0.729 | 0.894 | 0.918 | 0.941 |
| graph + REINFORCE policy + linear scorer (B=0) | 0.500 | 0.667 | 0.744 | 0.808 | 0.615 | 0.753 | 0.918 | 0.929 | 0.929 |
| graph + REINFORCE policy + linear scorer (B=10) | 0.500 | 0.679 | 0.769 | 0.821 | 0.616 | 0.741 | 0.929 | 0.941 | 0.941 |
| graph + REINFORCE policy + GBDT scorer (B=0) | 0.538 | 0.718 | 0.769 | 0.795 | 0.636 | 0.729 | 0.918 | 0.929 | 0.929 |
| graph + REINFORCE policy + GBDT scorer (B=10) | 0.564 | 0.731 | 0.795 | 0.833 | 0.647 | 0.741 | 0.906 | 0.929 | 0.941 |

### nDCG@10 vs B (TEST)

| method | B=0 | B=1 | B=2 | B=5 | B=10 | B=20 |
|---|---|---|---|---|---|---|
| graph expand + hand weights | 0.615 | 0.529 | 0.592 | 0.595 | 0.599 | 0.607 |
| graph + LambdaRank-linear | 0.615 | 0.626 | 0.629 | 0.619 | 0.616 | 0.632 |
| graph + LambdaRank-GBDT | 0.636 | 0.642 | 0.644 | 0.641 | 0.644 | 0.644 |
| graph + REINFORCE policy + linear scorer | 0.615 | 0.621 | 0.628 | 0.617 | 0.616 | 0.629 |
| graph + REINFORCE policy + GBDT scorer | 0.636 | 0.643 | 0.656 | 0.650 | 0.647 | 0.645 |

### fn Hit@1 vs B (TEST)

| method | B=0 | B=1 | B=2 | B=5 | B=10 | B=20 |
|---|---|---|---|---|---|---|
| graph expand + hand weights | 0.500 | 0.333 | 0.487 | 0.487 | 0.500 | 0.500 |
| graph + LambdaRank-linear | 0.500 | 0.526 | 0.526 | 0.500 | 0.513 | 0.538 |
| graph + LambdaRank-GBDT | 0.538 | 0.551 | 0.551 | 0.551 | 0.551 | 0.551 |
| graph + REINFORCE policy + linear scorer | 0.500 | 0.513 | 0.526 | 0.500 | 0.500 | 0.526 |
| graph + REINFORCE policy + GBDT scorer | 0.538 | 0.551 | 0.564 | 0.564 | 0.564 | 0.551 |

### fn Hit@10 vs B (TEST)

| method | B=0 | B=1 | B=2 | B=5 | B=10 | B=20 |
|---|---|---|---|---|---|---|
| graph expand + hand weights | 0.821 | 0.782 | 0.795 | 0.782 | 0.769 | 0.795 |
| graph + LambdaRank-linear | 0.808 | 0.821 | 0.821 | 0.821 | 0.808 | 0.808 |
| graph + LambdaRank-GBDT | 0.795 | 0.808 | 0.808 | 0.808 | 0.821 | 0.833 |
| graph + REINFORCE policy + linear scorer | 0.808 | 0.821 | 0.821 | 0.821 | 0.821 | 0.821 |
| graph + REINFORCE policy + GBDT scorer | 0.795 | 0.808 | 0.833 | 0.833 | 0.833 | 0.833 |


## 3. Analysis (honest summary)

* Setup caveats. n is small (about 155 CV tasks / 78 test tasks with a gold function): one task is about 0.013 Hit@k on the test half, and the standard error of any Hit@k is about 0.04-0.06. Differences below about 0.05 are noise. The train pool is dominated by fastapi (67) and rich (48); the test half is 16 other repos. repo-locate was scored on the first 10 files it prints, with its function lines mapped onto the same nodes (functions it prints but the AST index calls differently, e.g. classes, count as misses at function level); it was fed the first 4000 chars of the issue.
* BM25 over function chunks already beats the existing repo-locate at function level (test fn@1 0.436 vs 0.321, fn@10 0.808 vs 0.654) and is level with it at file level (file@10 0.94 vs 0.96).
* The learned reranker is the component that helps: LambdaRank (linear or GBDT) lifts fn Hit@1 from 0.436 (BM25) to about 0.50-0.56 on the held-out test half and from 0.30 to 0.37-0.40 in CV; nDCG@10 +0.03 to +0.05. Hit@10 is limited by candidate recall and barely moves (CV 0.63 -> 0.65).
* Graph expansion is NOT clearly useful in our numbers. Expansion raises the reach (gold function inside the revealed set) monotonically with B (CV 0.60 at B=0 -> 0.75 at B=20; REINFORCE policy 0.76 at B=20), but the extra revealed nodes are not ranked high enough to turn into Hit@k gains: Hit@k and nDCG are flat in B within noise, and the "no graph" ablation (static features only, reranking the top-100 seeds, reach 0.84) is as good as or better than every graph variant at B>0 (test fn@1 0.526/0.551 for linear/GBDT vs 0.50-0.56). The only graph-derived feature that seemed to help in CV is the static neighbour-evidence feature (nbr_max/nbr_cnt: B=0 graph-linear fn@1 0.394 vs no-graph-linear 0.342 in CV), which is a graph feature but needs no expansion; on the test half this edge disappears (0.500 vs 0.526). So the evidence for "graph" in this experiment is weak, and the evidence for "learned reranking of lexical features" is moderate.
* REINFORCE added essentially nothing over greedy hand-policy expansion once a learned scorer is used (mean sampled reward moves from 0.50 to 0.50 over 40 epochs; CV nDCG 0.456-0.459 vs 0.455-0.459 for the hand policy). It does raise the reach at B>=10 (0.70 vs 0.70-0.71 at B=10, 0.76 vs 0.75 at B=20), i.e. the policy learns slightly better expansions, but not enough to matter after ranking. The reward is dominated by whether BM25 seeds already contain the gold function.
* Shipped configuration (chosen by CV, not by test): linear LambdaRank scorer + REINFORCE policy, B=10 (weights in `skills/graph-locate/scripts/weights.json`). The GBDT scorer looked better on test (fn@1 0.56) but worse in CV (0.33-0.35 vs 0.37-0.39), so it was not shipped. Some learned weights look spurious (e.g. a negative weight on traceback hits, which are rare in the data, and a large positive path-depth weight) and the linear model has not been regularised hard; the numbers above include that.
* Tool runtime: 1-4 s for an index of 1.5k-5.7k functions (adk_python, the biggest proxy repo), pure stdlib; output is 14 lines.
* Not done: file/function metrics on the public set alone with a repo split of the 107 public tasks (only pooled train-pool CV is reported; repo-locate public-only numbers are in `results/graph_locate/repo_locate.json`), multi-seed repeats, and no end-to-end agent evidence yet: whether any of this changes resolve rate is what the queued px_c16 vs px_c9e_evalhalf runs measure.
