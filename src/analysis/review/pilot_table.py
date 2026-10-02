import json, collections
from pathlib import Path
R=Path('results/kaggle'); runs=['c1_n30','c2_n30','c3_n30','c4_n30','c5a_n30','c5b_n30','c6a_n30','c6b_n30']
valid=set(Path('data/derived/valid_tasks.txt').read_text().split())
tab={}; 
for r in runs:
    rows=[json.loads(l) for l in open(R/r/'results'/r/'task_results.jsonl')]
    ids=[x['instance_id'] for x in rows]
    print(r, len(rows), len(set(ids)), sum(x['resolved'] for x in rows), 'errs', collections.Counter((x['error'] or '')[:30] for x in rows if x['error']).most_common(3))
    tab[r]={x['instance_id']:x for x in rows}
sets=[frozenset(tab[r]) for r in runs]; print('same task set', len(set(sets))==1)
ids=sorted(tab[runs[0]])
print('pilot ids not in valid set:', [i for i in ids if i not in valid])
print('repo mix', collections.Counter(i.rsplit('_',1)[0] for i in ids))
for i in ids:
    print(f"{i:16}", ''.join('1' if tab[r][i]['resolved'] else '.' for r in runs), 'valid' if i in valid else 'INVALID', tab['c6a_n30'][i]['test_exit_code'])
