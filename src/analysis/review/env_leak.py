import re, collections
from pathlib import Path
runs=['c1_n30','c2_n30','c3_n30','c4_n30','c5a_n30','c5b_n30','c6a_n30','c6b_n30']
hits=collections.defaultdict(set); errs=collections.defaultdict(set)
for r in runs:
    for f in Path(f'results/kaggle/{r}/results/{r}/test_outputs').glob('*.log'):
        s=re.sub(r'\x1b\[[0-9;]*m','',f.read_text(errors='ignore'))
        tid=f.stem
        for m in re.findall(r'dist-packages/(fastapi|rich|httpx|requests|starlette|pydantic|pygments|markdown_it)/', s):
            hits[tid].add(m)
        for m in re.findall(r'(ModuleNotFoundError: No module named \S+|ImportError: [^\n]{0,80}|fixture \S+ not found)', s):
            errs[tid].add(m)
for t in sorted(set(hits)|set(errs)):
    print(t, sorted(hits[t]), sorted(errs[t])[:3])
