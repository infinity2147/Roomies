---
name: graph-locate
description: One-shot graph-aware function localizer for the repository in /workspace. Given the issue text, returns the top-10 most likely functions/methods to edit (file:function, line range, score, reason), found by BM25 + exact identifier/traceback hits and a call/def graph expansion, reranked by a learned scorer.
---

# graph-locate

Run it with run_skill_script: skill_name graph-locate, file_path scripts/graph_locate.py, args with key issue set to the issue text (title, identifiers, error message, file names; plain text, no backticks needed).

Output (about 14 lines): numbered `file:Class.function (lines a-b) score reason`, best first, then the files in order.
The reason says why a candidate is listed (name or traceback in the issue, BM25 score, or "callee/caller/sibling of X" when it was reached through the call graph).
Read only the top 1-2 ranges with `sed -n 'START,ENDp' FILE`. Run it once per task; do not re-run with the same text.
