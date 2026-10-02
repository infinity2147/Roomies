"""Find tests that pass locally with an EMPTY patch (pass-to-pass candidates) but fail on Kaggle in
EVERY one of the 8 pilot runs -> evidence the Kaggle eval environment breaks the task independent of the agent."""
import json, re
from pathlib import Path
runs = ['c1_n30','c2_n30','c3_n30','c4_n30','c5a_n30','c5b_n30','c6a_n30','c6b_n30']
strip = lambda s: re.sub(r'\x1b\[[0-9;]*m', '', s)
def failed(s): return set(re.findall(r'^(?:FAILED|ERROR) (\S+)', s, re.M))
ids = sorted(json.loads(l)['instance_id'] for l in open('results/kaggle/c1_n30/results/c1_n30/task_results.jsonl'))
for i in ids:
    sets = []
    for r in runs:
        p = Path(f'results/kaggle/{r}/results/{r}/test_outputs/{i}.log')
        if p.exists(): sets.append(failed(strip(p.read_text(errors='ignore'))))
    if not sets: continue
    always = set.intersection(*sets)
    loc_empty = failed(strip(Path(f'results/verify_empty/logs/{i}.log').read_text(errors='ignore')))
    loc_gold = failed(strip(Path(f'results/verify_gold/logs/{i}.log').read_text(errors='ignore')))
    sus = sorted(t for t in always if t not in loc_empty and t not in loc_gold)
    if sus: print(f"{i}: {len(sus)} tests fail on Kaggle in all {len(sets)} logged runs but pass locally with empty AND gold patch: {sus[:3]}")
