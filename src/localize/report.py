"""Render reports/graph_locate_eval.md tables from results/graph_locate/{cv,test,repo_locate}.json"""
import json
from pathlib import Path

R = Path(__file__).resolve().parents[2]
cv = json.load(open(R / "results/graph_locate/cv.json"))["pooled"]
te = json.load(open(R / "results/graph_locate/test.json"))
rl = json.load(open(R / "results/graph_locate/repo_locate.json"))
NAMES = [("bm25", "BM25 only (function chunks)", [0]), ("hand_nograph", "hand weights, no graph (top-100 seeds)", [0]),
         ("nograph_lin", "LambdaRank-linear, no graph", [0]), ("nograph_gbdt", "LambdaRank-GBDT, no graph", [0]),
         ("graph_hand", "graph expand + hand weights", [0, 10]), ("lambdarank_lin", "graph + LambdaRank-linear", [0, 10]),
         ("lambdarank_gbdt", "graph + LambdaRank-GBDT", [0, 10]), ("reinforce_lin", "graph + REINFORCE policy + linear scorer", [0, 10]),
         ("reinforce_gbdt", "graph + REINFORCE policy + GBDT scorer", [0, 10])]


def row(label, x):
    return "| %s | %.3f | %.3f | %.3f | %.3f | %.3f | %.3f | %.3f | %.3f | %.3f |" % (
        label, x["fn_hit@1"], x["fn_hit@3"], x["fn_hit@5"], x["fn_hit@10"], x["ndcg@10"], x["file_hit@1"], x["file_hit@3"], x["file_hit@5"], x["file_hit@10"])


H = "| method | fn@1 | fn@3 | fn@5 | fn@10 | nDCG@10 | file@1 | file@3 | file@5 | file@10 |\n|---|---|---|---|---|---|---|---|---|---|"


def main_table(res, rlrow):
    out = [H]
    out.append("| repo-locate (existing skill, 10 files) | %.3f | %.3f | %.3f | %.3f | - | %.3f | %.3f | %.3f | %.3f |" % (
        rlrow["fn_hit@1"], rlrow["fn_hit@3"], rlrow["fn_hit@5"], rlrow["fn_hit@10"], rlrow["file_hit@1"], rlrow["file_hit@3"], rlrow["file_hit@5"], rlrow["file_hit@10"]))
    for k, lab, Bs in NAMES:
        for B in Bs:
            if str(B) in res[k]:
                out.append(row(lab + ("" if k in ("bm25", "hand_nograph", "nograph_lin", "nograph_gbdt") else " (B=%d)" % B), res[k][str(B)]))
    return "\n".join(out)


def budget_table(res, key):
    out = ["| method | " + " | ".join("B=%d" % b for b in [0, 1, 2, 5, 10, 20]) + " |", "|---|" + "---|" * 6]
    for k, lab, _ in NAMES:
        if "20" in res[k]:
            out.append("| %s | " % lab + " | ".join("%.3f" % res[k][str(b)][key] for b in [0, 1, 2, 5, 10, 20]) + " |")
    return "\n".join(out)


n = cv["bm25"]["0"]
md = ["# graph-locate offline localization eval", "",
      "Labels: gold function = function (def/method, nested defs folded into the parent) whose line range in the base snapshot contains a line removed/inserted by the gold patch; gold file = existing .py file edited by the patch. Function metrics use tasks with >=1 gold function, file metrics tasks with >=1 gold .py file.",
      "Code: `src/localize/` (prep.py, learn.py, eval_repo_locate.py, report.py); tool: `skills/graph-locate/scripts/graph_locate.py`; raw numbers `results/graph_locate/{cv,test,repo_locate}.json`. Seeded (seed 0).", "",
      "## 1. Cross-validation on the train pool (public valid 107 + proxy train half 67; folds grouped by repo: fastapi, rich are leave-one-repo-out, the other 18 repos balanced into 4 folds). n_fn=%d, n_file=%d" % (n["n_fn"], n["n_file"]), "",
      main_table(cv, rl["train_pool"]), "",
      "### recall of the gold function vs expansion budget B (CV): nDCG@10", "", budget_table(cv, "ndcg@10"), "",
      "### fn Hit@10 vs B (CV)", "", budget_table(cv, "fn_hit@10"), "",
      "### Gold function revealed (reach) vs B (CV; fraction of gold functions inside the revealed candidate set, before ranking)", "",
      "| method | B=0 | B=1 | B=2 | B=5 | B=10 | B=20 |\n|---|---|---|---|---|---|---|\n| graph (pool of 20 seeds + expansions) | " + " | ".join("%.3f" % cv["graph_hand"][str(b)]["reach"] for b in [0, 1, 2, 5, 10, 20]) + " |\n| REINFORCE policy | " + " | ".join("%.3f" % cv["reinforce_lin"][str(b)]["reach"] for b in [0, 1, 2, 5, 10, 20]) + " |\n| no-graph candidate set (top-100 seeds) | %.3f | | | | | |" % cv["nograph_lin"]["0"]["reach"], "",
      "## 2. FINAL: proxy TEST half (held out; models trained on the whole train pool, evaluated once). n_fn=%d n_file=%d" % (te["results"]["bm25"]["0"]["n_fn"], te["results"]["bm25"]["0"]["n_file"]), "",
      main_table(te["results"], rl["test_half"]), "",
      "### nDCG@10 vs B (TEST)", "", budget_table(te["results"], "ndcg@10"), "",
      "### fn Hit@1 vs B (TEST)", "", budget_table(te["results"], "fn_hit@1"), "",
      "### fn Hit@10 vs B (TEST)", "", budget_table(te["results"], "fn_hit@10"), ""]
open(R / "reports/graph_locate_eval.md", "w").write("\n".join(md) + "\n")
