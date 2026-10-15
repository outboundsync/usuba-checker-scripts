#!/usr/bin/env python3
"""Final verification + dataset + counts + license scan. Verified = mechanical (pre-fix text at file:line == removed text, done in step 03)
AND LLM judge says functional bug fix AND judged defect_line inside [pre_line-1, pre_end+1] AND confidence>=0.7."""
import json,subprocess,collections,re,hashlib
cands={(c['repo'],c['commit'],c['file'],c['pre_line']):c for c in map(json.loads,open('data/candidates_dedup.jsonl'))}
raw=[json.loads(l) for l in open('data/candidates.jsonl')]
counts=json.load(open('data/repo_commit_counts.json'))
V=[json.loads(l) for l in open('data/llm_verdicts.jsonl')]
V={(v['repo'],v['commit'],v['file'],v['pre_line']):v for v in V}
def lic(repo):
    for f in ('LICENSE','LICENSE.md','LICENSE.txt','COPYING','license'):
        r=subprocess.run(['git','-C','/workspace/vh_repos/'+repo,'show','HEAD:'+f],capture_output=True,text=True,errors='replace')
        if r.returncode==0:
            t=r.stdout[:3000].lower()
            for k,n in (('mit license','MIT'),('permission is hereby granted, free of charge','MIT'),('apache license','Apache-2.0'),('gnu general public license','GPL'),('gnu lesser general','LGPL'),('gnu affero','AGPL'),('bsd','BSD'),('mozilla public','MPL-2.0'),('unlicense','Unlicense'),('isc license','ISC')): 
                if k in t: return n
            return 'other-license-file'
    return 'none-found'
rows=[];stats=collections.Counter();rej=collections.Counter()
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
    rows.append(dict(repo=c['repo'],url='https://github.com/'+c['repo'].replace('__','/',1),commit=c['commit'],parent=c['parent'],date=c['author_date'],subject=c['subject'],file=c['file'],pre_fix_line=dl,hunk_span=[c['pre_line'],c['pre_end']],pre_fix_line_text=pre[dl-1] if 0<dl<=len(pre) else None,bug_kind=j['bug_kind'],defect=j['defect'],fix=j['fix'],removed=c['removed'],added=c['added'],confidence=conf,license=lic(c['repo'])))
open('data/verified_pairs.jsonl','w').write(''.join(json.dumps(r)+'\n' for r in rows))
usable=[r for r,n in counts.items() if n and n>1]
cm={(c['repo'],c['commit']) for c in raw}
vc={(r['repo'],r['commit']) for r in rows}
summ=dict(repos_cloned_ok=len(counts),repos_with_history_gt1_commit=len(usable),raw_hunks=len(raw),candidate_fix_commits=len(cm),candidate_repos=len({c['repo'] for c in raw}),
 prefiltered_for_llm=len(cands),**stats,rejected_by_reason=dict(rej),verified_pairs=len(rows),verified_commits=len(vc),verified_repos=len({r['repo'] for r in rows}),
 by_kind=dict(collections.Counter(r['bug_kind'] for r in rows).most_common()),by_license=dict(collections.Counter(r['license'] for r in rows).most_common()),
 training_row_candidates_broken=len(rows),training_row_candidates_approve=len(rows),training_rows_total=2*len(rows))
json.dump(summ,open('data/summary.json','w'),indent=1); print(json.dumps(summ,indent=1))
