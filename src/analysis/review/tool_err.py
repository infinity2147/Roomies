import json, collections, glob, sys
for run in sys.argv[1:]:
    cnt=collections.Counter(); calls=0; sb_errs=0
    for f in glob.glob(f'results/kaggle/{run}/results/{run}/traces/*.json'):
        t=json.load(open(f))
        for s in t['steps']:
            tc=s.get('tool_calls') or []; calls+=len(tc)
            obs=s.get('observation') or ''
            o=json.dumps(obs); sb_errs+=o.count('\\"status\\": \\"error\\"')+o.count('"error_code"')
            if not tc: continue
            c=obs.get('content') if isinstance(obs,dict) else obs
            try: d=json.loads(c)
            except Exception: cnt['nonjson']+=1; continue
            if not isinstance(d,dict) or d.get('status')!='error': continue
            det=d.get('details') or {}
            cmd=tc[0]['arguments'].get('command','') if tc else ''
            ec=det.get('exit_code')
            fn=tc[0]['function_name']
            if fn=='run_command' and ec==1 and ('grep' in cmd or 'rg ' in cmd) and not det.get('stderr'): k='grep_nomatch_exit1'
            elif fn=='run_command' and ec in (1,2) and 'pytest' in cmd: k='pytest_nonzero'
            elif fn=='run_command' and ec is not None: k=f'cmd_exit_{ec}'
            else: k=f"{fn}:{d.get('error_type')}"
            cnt[k]+=1
    tot=sum(v for k,v in cnt.items() if k!='nonjson')
    print(run,'calls',calls,'scoreboard_errs',sb_errs,'rate',round(sb_errs/calls,3),'parsed_errs',tot, cnt.most_common(8))
