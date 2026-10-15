#!/usr/bin/env python3
"""Round-2 verification: same gates as 05_report.py (judge true, conf>=0.7, defect_line in [pre_line-1,pre_end+1], mechanical match from step 03).
Writes data/verified_pairs_2.jsonl (verified_pairs.jsonl untouched) and data/summary.json (combined round1+round2 plus round-2 only)."""
import json,subprocess,collections,os
cands={(c['repo'],c['commit'],c['file'],c['pre_line']):c for c in map(json.loads,open('data/candidates_round2.jsonl'))}
V={}
for l in open('data/llm_verdicts_2.jsonl'):
    v=json.loads(l); V[(v['repo'],v['commit'],v['file'],v['pre_line'])]=v
def lic(repo):
    for f in ('LICENSE','LICENSE.md','LICENSE.txt','COPYING','license'):
        r=subprocess.run(['git','-C','/workspace/vh_repos/'+repo,'show','HEAD:'+f],capture_output=True,text=True,errors='replace')
        if r.returncode==0:
            t=r.stdout[:3000].lower()
            for k,n in (('mit license','MIT'),('permission is hereby granted, free of charge','MIT'),('apache license','Apache-2.0'),('gnu general public license','GPL'),('gnu lesser general','LGPL'),('gnu affero','AGPL'),('bsd','BSD'),('mozilla public','MPL-2.0'),('unlicense','Unlicense'),('isc license','ISC')):
                if k in t: return n
            return 'other-license-file'
    return 'none-found'
u=json.load(open('data/universe.json')); excl=set(u['excluded'])
rows=[];stats=collections.Counter();rej=collections.Counter();L={}
for k,c in cands.items():
    v=V.get(k)
    if not v: stats['not_judged']+=1; continue
    if 'error' in v: stats['judge_error']+=1; continue
    j=v['verdict']; stats['judged']+=1
    if not j.get('is_functional_bug_fix'): rej[str(j.get('reject_reason'))]+=1; continue
    try: dl=int(j['defect_line']); conf=float(j.get('confidence',0))
    except Exception: stats['bad_fields']+=1; continue
    if not (c['pre_line']-1<=dl<=c['pre_end']+1) or conf<0.7: stats['line_or_conf_fail']+=1; continue
    pre=subprocess.run(['git','-C','/workspace/vh_repos/'+c['repo'],'show',f"{c['parent']}:{c['file']}"],capture_output=True,text=True,errors='replace').stdout.splitlines()
    # pre-fix text must match removed lines (re-check) 
    if c['removed'] and pre[c['pre_line']-1:c['pre_line']-1+len(c['removed'])]!=c['removed']: stats['prefix_text_mismatch']+=1; continue
    L.setdefault(c['repo'],lic(c['repo']))
    rows.append(dict(repo=c['repo'],url='https://github.com/'+c['repo'].replace('__','/',1),commit=c['commit'],parent=c['parent'],date=c['author_date'],subject=c['subject'],file=c['file'],pre_fix_line=dl,hunk_span=[c['pre_line'],c['pre_end']],pre_fix_line_text=pre[dl-1] if 0<dl<=len(pre) else None,bug_kind=j['bug_kind'],defect=j['defect'],fix=j['fix'],removed=c['removed'],added=c['added'],confidence=conf,license=L[c['repo']]))
# exclusion verification (repo url in excluded set, or jankeesvw)
bad=[r['repo'] for r in rows if r['url'] in excl or 'jankeesvw' in r['repo'].lower()]
assert not bad,bad
open('data/verified_pairs_2.jsonl','w').write(''.join(json.dumps(r)+'\n' for r in rows))
r1=[json.loads(l) for l in open('data/verified_pairs.jsonl')]
allr=r1+rows
cost2=sum(v.get('cost') or 0 for v in V.values()); cost1=sum(json.loads(l).get('cost') or 0 for l in open('data/llm_verdicts.jsonl'))
def tab(rs): return dict(verified_pairs=len(rs),verified_repos=len({r['repo'] for r in rs}),by_kind=dict(collections.Counter(r['bug_kind'] for r in rs).most_common()),by_license=dict(collections.Counter(r['license'] for r in rs).most_common()))
summ=dict(round2=dict(selected=len(cands),**stats,rejected_by_reason=dict(rej),yield_=round(len(rows)/max(1,stats['judged']),4),excluded_repo_hits=len(bad),cost_usd=round(cost2,4),**tab(rows)),
 round1=dict(judged=1400,cost_usd=round(cost1,4),**tab(r1)),
 combined=dict(judged=1400+stats['judged'],cost_usd_judging=round(cost1+cost2,4),cost_usd_incl_smoke_test=round(cost1+cost2+0.02,4),repos_in_both_rounds_overlap=len({r['repo'] for r in r1}&{r['repo'] for r in rows}),**tab(allr)))
json.dump(summ,open('data/summary.json','w'),indent=1); print(json.dumps(summ,indent=1))
