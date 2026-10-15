#!/usr/bin/env python3
"""Build repo universe + exclusions. Reads only the 'id' field of dell_ground_truth.jsonl."""
import json,os,re,subprocess
W='/workspace'
def norm(u):
    u=u.strip().lower().rstrip('/'); u=re.sub(r'\.git$','',u); return u.replace('http://','https://').replace('git@github.com:','https://github.com/')
gt=set(json.loads(l)['id'] for l in open(f'{W}/wt-retrain-v2/functest/dell_ground_truth.jsonl'))
hold={norm(u) for u in open(f'{W}/wt-v3-prep/eval/hancore_holdout/plugin_ids.txt') if u.strip()}
rows=[json.loads(l) for l in open(f'{W}/wt-retrain-v2/dell/sweep/corpus.jsonl')]
uni={}; excl={}
def add(u,src,pid):
    n=norm(u)
    if n in hold: excl[n]='holdout'; return
    if pid in gt: excl[n]='dell_gt_id'; return
    uni.setdefault(n,set()).add(src)
for r in rows:
    if r.get('is_plugin') and not r.get('unrunnable'):
        if r.get('plugin_id') in gt or r.get('dell_name') in gt: excl[norm(r['url'])]='dell_gt_id'
for r in rows:
    if r.get('is_plugin') and not r.get('unrunnable'): add(r['url'],'sweep',None)
for d in os.listdir(f'{W}/registry_repos'):
    try: u=subprocess.check_output(['git','-C',f'{W}/registry_repos/{d}','remote','get-url','origin'],text=True).strip()
    except Exception: continue
    if d in gt: excl[norm(u)]='dell_gt_id'
    add(u,'registry',d)
# final pass: gt/holdout repos removed even if added via another path
for n in list(uni):
    if n in excl: del uni[n]
json.dump(dict(repos=sorted(uni),excluded=excl),open('data/universe.json','w'),indent=1)
print(len(uni),'repos;',len(excl),'excluded urls', {v:list(excl.values()).count(v) for v in set(excl.values())})
