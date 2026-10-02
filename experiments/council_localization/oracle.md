## Oracle analyses (n=117 tasks with >=1 gold node; 95% bootstrap CI)

### (a) BM25 top-N recall / hit

| N | recall@N | hit@N |
|---|---|---|
| 1 | 0.183 [0.12,0.25] | 0.282 [0.21,0.37] |
| 5 | 0.384 [0.30,0.47] | 0.513 [0.43,0.61] |
| 10 | 0.457 [0.38,0.54] | 0.573 [0.49,0.67] |
| 20 | 0.569 [0.49,0.65] | 0.692 [0.61,0.78] |
| 50 | 0.685 [0.61,0.76] | 0.803 [0.73,0.87] |
| 100 | 0.771 [0.70,0.84] | 0.846 [0.78,0.91] |

BM25 MRR = 0.398 [0.33,0.48]

### (b,c) Graph expansion of seed sets (undirected, non-test nodes)

| seeds | hops | cand. size median (p90) | recall | hit | BM25 equal-budget recall | BM25 eq-budget hit | gold reachable only via graph (not in BM25 top-100) |
|---|---|---|---|---|---|---|---|
| bm25top5 | 0 | 5 (5) | 0.384 | 0.513 | 0.384 | 0.513 | 0 |
| bm25top5 | 1 | 14 (29) | 0.474 | 0.598 | 0.503 | 0.641 | 4 |
| bm25top5 | 2 | 53 (206) | 0.621 | 0.709 | 0.687 | 0.786 | 18 |
| bm25top10 | 0 | 10 (10) | 0.457 | 0.573 | 0.457 | 0.573 | 0 |
| bm25top10 | 1 | 29 (52) | 0.566 | 0.667 | 0.592 | 0.709 | 8 |
| bm25top10 | 2 | 97 (300) | 0.730 | 0.812 | 0.744 | 0.821 | 25 |
| bm25top20 | 0 | 20 (20) | 0.569 | 0.692 | 0.569 | 0.692 | 0 |
| bm25top20 | 1 | 55 (90) | 0.660 | 0.761 | 0.680 | 0.786 | 13 |
| bm25top20 | 2 | 149 (411) | 0.832 | 0.897 | 0.782 | 0.846 | 31 |
| anchor | 0 | 0 (7) | 0.191 | 0.256 | 0.209 | 0.291 | 3 |
| anchor | 1 | 0 (35) | 0.250 | 0.291 | 0.336 | 0.402 | 6 |
| anchor | 2 | 0 (90) | 0.297 | 0.316 | 0.398 | 0.444 | 7 |
| anchor+bm25top5 | 0 | 5 (10) | 0.416 | 0.538 | 0.408 | 0.538 | 3 |
| anchor+bm25top5 | 1 | 17 (50) | 0.528 | 0.632 | 0.569 | 0.684 | 8 |
| anchor+bm25top5 | 2 | 68 (228) | 0.668 | 0.744 | 0.707 | 0.795 | 21 |

Tasks with >=1 anchor seed: 58/117; median #anchor seeds (when >0): 3

### (d) Shortest undirected path from BM25 seeds to nearest gold node

| distance | from top-1 | from top-5 (min) | from anchor seeds (min) |
|---|---|---|---|
| 0 | 33 | 60 | 30 |
| 1 | 11 | 10 | 4 |
| 2 | 14 | 13 | 3 |
| 3 | 9 | 10 | 7 |
| 4 | 18 | 8 | 4 |
| 5 | 2 | 4 | 10 |
| 6 | 4 | 4 | 0 |
| unreached(>8 / no seeds) | 26 | 8 | 59 |

Median undirected degree: BM25 top-5 nodes 2.0, gold nodes 3.0.

### RL-addressable set

- BM25 misses all gold in top-5 on 57/117 tasks (48.7%).
- among those 57: gold in BM25 top-6..20 (pure re-rank, no graph needed): **21** (17.9% of all tasks)
- among those 57: gold in BM25 top-21..50 (re-rank of top-50): **13** (11.1% of all tasks)
- among those 57: gold in BM25 top-51..100: **5** (4.3% of all tasks)
- among those 57: gold <=1 hop of BM25 top-5: **10** (8.5% of all tasks)
- among those 57: gold <=2 hops of BM25 top-5: **23** (19.7% of all tasks)
- among those 57: gold <=1 hop of anchor/top-5 seeds: **14** (12.0% of all tasks)
- among those 57: gold <=2 hops of anchor/top-5 seeds: **27** (23.1% of all tasks)
- among those 57: gold <=2 hops of top-5/anchors AND not in BM25 top-50 (graph-unique): **6** (5.1% of all tasks)
- among those 57: gold <=2 hops of top-5/anchors AND not in BM25 top-100 (graph-unique): **5** (4.3% of all tasks)
- among those 57: gold <=1 hop of top-5/anchors AND not in BM25 top-50 (graph-unique, cheap): **1** (0.9% of all tasks)
- among those 57: unreachable: >2 hops and not in top-100: **13** (11.1% of all tasks)

### Ceilings (oracle ordering inside a candidate set)

| candidate set | median size | oracle hit@5 = oracle MRR ceiling* | oracle Recall@5 | gain over BM25 hit@5 / R@5 |
|---|---|---|---|---|
| BM25 top-5 (= BM25 itself) | 5 | 0.513 | 0.384 | +0.000 / +0.000 |
| BM25 top-20 | 20 | 0.692 | 0.559 | +0.179 / +0.174 |
| BM25 top-50 | 50 | 0.803 | 0.660 | +0.291 / +0.276 |
| BM25 top-100 | 100 | 0.846 | 0.730 | +0.333 / +0.345 |
| bm25top5 +1 hop | 14 | 0.598 | 0.472 | +0.085 / +0.087 |
| bm25top5 +2 hop | 53 | 0.709 | 0.605 | +0.197 / +0.221 |
| anchor+bm25top5 +1 hop | 17 | 0.632 | 0.510 | +0.120 / +0.126 |
| anchor+bm25top5 +2 hop | 68 | 0.744 | 0.637 | +0.231 / +0.253 |
| bm25top10 +1 hop | 29 | 0.667 | 0.549 | +0.154 / +0.164 |
| bm25top10 +2 hop | 97 | 0.812 | 0.698 | +0.299 / +0.314 |
| re-rank pool (BM25 top-50 U 1hop(top-10) U anchors) | 64 | 0.821 | 0.683 | +0.308 / +0.299 |

*oracle MRR = 1 whenever any gold is in the set. BM25 hit@5=0.513, R@5=0.384, MRR=0.398.

### Per-repo

| repo | n | BM25 hit@5 | hit@50 | top5+2hop hit (size med) | dist_top5<=2 & miss@50 |
|---|---|---|---|---|---|
| fastapi | 60 | 0.483 | 0.817 | 0.650 (38) | 2 |
| rich | 45 | 0.467 | 0.756 | 0.733 (148) | 4 |
| requests | 11 | 0.818 | 0.909 | 0.909 (45) | 0 |
| httpx | 1 | 1.000 | 1.000 | 1.000 (44) | 0 |
