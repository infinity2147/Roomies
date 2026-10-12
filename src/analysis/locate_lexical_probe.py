"""Offline probe for C26: can a deterministic lexical repo-locate (BM25 over .py files at base_commit,
query = problem statement) find the gold-patch source files? Compares recall@k with the C25 agent's
patch-hits-gold rate. No GPU, no model; run on login node in <5 min."""
import json, math, re, subprocess, sys, collections, os
ROOT = 'data/derived/proxy'
STOP = set('the a an and or of to in is it for on with as be this that not are was by from at if when can has have but will should would error self none true false return def class import'.split())
def toks(s):
    out = []
    for w in re.findall(r'[A-Za-z_][A-Za-z0-9_]+', s):
        parts = re.sub(r'([a-z])([A-Z])', r'\1 \2', w).replace('_', ' ').lower().split()
        out += [p for p in parts if len(p) > 2 and p not in STOP]
    return out
def git(repo, *a):
    return subprocess.run(['git', '-C', repo, *a], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode('utf-8', 'replace')
def gold_files(patch):
    return [f for f in re.findall(r'^\+\+\+ b/(\S+)', patch, re.M) if f.endswith('.py') and '/test' not in f and not f.startswith('test')]
def main(ids_from):
    tasks = {}
    for l in open(f'{ROOT}/tasks.jsonl'):
        r = json.loads(l); tasks[r['instance_id']] = r
    solved = {}
    for d in ids_from:
        for s in range(8):
            p = f'{d}/s{s}/task_results.jsonl'
            if os.path.exists(p):
                for l in open(p):
                    r = json.loads(l); solved.setdefault(r['instance_id'], []).append(r['resolved'])
    res = []
    for iid in sorted(solved):
        t = tasks.get(iid)
        if not t: continue
        repo = f"{ROOT}/repos/{t['repo'].split('/')[-1]}"
        if not os.path.isdir(repo): continue
        gf = gold_files(t['patch'])
        if not gf: continue
        files = [f for f in git(repo, 'ls-tree', '-r', '--name-only', t['base_commit']).splitlines()
                 if f.endswith('.py') and not re.search(r'(^|/)(tests?|docs?|examples?)(/|$)', f)]
        if not files: continue
        docs = {}
        for f in files:
            body = git(repo, 'show', f"{t['base_commit']}:{f}")[:200000]
            docs[f] = collections.Counter(toks(body) + 3 * toks(f))
        df = collections.Counter(w for c in docs.values() for w in c)
        N = len(docs); avg = sum(sum(c.values()) for c in docs.values()) / N
        q = collections.Counter(toks(t['problem_statement'] + ' ' + t.get('hints_text', '')))
        sc = {}
        for f, c in docs.items():
            ln = sum(c.values()); s = 0.0
            for w, qn in q.items():
                if w in c:
                    idf = math.log(1 + (N - df[w] + .5) / (df[w] + .5))
                    s += idf * c[w] * 2.2 / (c[w] + 1.2 * (.25 + .75 * ln / avg)) * min(qn, 3)
            sc[f] = s
        rank = sorted(sc, key=sc.get, reverse=True)
        pos = [rank.index(g) + 1 for g in gf if g in rank]
        res.append((iid, t['repo'], min(pos) if pos else 999, len(files), sum(solved[iid]) / len(solved[iid])))
    n = len(res)
    for k in (1, 3, 5, 10):
        print(f'recall@{k} (any gold file in top-k): {sum(r[2] <= k for r in res)}/{n} = {sum(r[2] <= k for r in res)/n:.2f}')
    for k in (3, 5):
        hit = [r for r in res if r[2] <= k]; miss = [r for r in res if r[2] > k]
        f = lambda xs: sum(x[4] for x in xs) / max(1, len(xs))
        print(f'C25 solve rate when BM25 top-{k} hits: {f(hit):.2f} (n={len(hit)}); misses: {f(miss):.2f} (n={len(miss)})')
    print('median repo size (.py non-test files):', sorted(r[3] for r in res)[n // 2])
    json.dump(res, open('results/locate_lexical_probe.json', 'w'))
if __name__ == '__main__':
    main(sys.argv[1:])
