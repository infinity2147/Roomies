"""Re-measure the DEPLOYED (c6a) locate.py without overwriting results/locate_skill_eval.jsonl."""
import json
from concurrent.futures import ProcessPoolExecutor
from src.dataio.loaders import ROOT, load_tasks
from src.eval.eval_locate_skill import run_one
if __name__ == "__main__":
    skill = str(ROOT / "submissions" / "c6a" / "skills" / "repo-tools")
    valid = set((ROOT / "data/derived/valid_tasks.txt").read_text().split())
    with ProcessPoolExecutor(12) as ex:
        rows = [r for r in ex.map(run_one, [(t, skill, 1500, 12) for t in load_tasks()]) if r["has_gold_file"]]
    for name, rs in (("all", rows), ("valid107", [r for r in rows if r["instance_id"] in valid])):
        print(name, len(rs), {k: round(sum(r[k] for r in rs) / len(rs), 3) for k in ("file_hit1", "file_hit3", "file_hit6", "node_hit5")})
