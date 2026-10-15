#!/usr/bin/env python3
"""LLM judge (qwen/qwen3.5-397b-a17b via OpenRouter, open weights only) for each candidate: is the pre-fix code really defective and the diff a functional bug fix? Budget-capped."""
import json,os,re,sys,urllib.request,subprocess
from concurrent.futures import ThreadPoolExecutor
KEY=os.environ['OPENROUTER_API_KEY']; MODEL='qwen/qwen3.5-397b-a17b'; BUDGET=float(os.environ.get('BUDGET','6.0'))
KINDS=['null-or-missing-guard','wrong-path-or-command','missing-dependency-or-install','shell-quoting-or-expansion','race-or-timing','process-or-resource-lifecycle','wrong-condition-or-logic','error-handling','env-or-config-assumption','syntax-or-parse-error','api-compat-change','ui-layout-or-state','security','other']
out='data/llm_verdicts.jsonl'; done=set()
if os.path.exists(out): done={(j['repo'],j['commit'],j['file'],j['pre_line']) for j in map(json.loads,open(out))}
spent=[0.0]
def ctx(c):
    r=subprocess.run(['git','-C','/workspace/vh_repos/'+c['repo'],'show',f"{c['parent']}:{c['file']}"],capture_output=True,text=True,errors='replace').stdout.splitlines()
    a=max(0,c['pre_line']-1-10); b=min(len(r),c['pre_end']+10)
    return '\n'.join(f"{i+1}: {r[i]}" for i in range(a,b))
def ask(c):
    k=(c['repo'],c['commit'],c['file'],c['pre_line'])
    if k in done or spent[0]>=BUDGET: return None
    diff='\n'.join(['- '+x for x in c['removed']]+['+ '+x for x in c['added']])
    p=f"""You judge whether a git commit hunk is a genuine FUNCTIONAL bug fix in a desktop-plugin (shell/QML/Python/JS) repo.
Commit message: {c['subject']}\n{c['body'][:300]}
File: {c['file']}  (hunk type: {c['hunk_kind']}; for pure insertions the pre-fix anchor is the line AFTER the insertion point)
PRE-FIX file excerpt (numbered):\n{ctx(c)}
Hunk (removed '-', added '+'):\n{diff[:2500]}

Answer with JSON only: {{"is_functional_bug_fix": true/false, "reject_reason": "cosmetic|refactor|feature|docs|config-tweak|unclear|null", "defect_line": <pre-fix line number of the line that contains/exhibits the defect, from the numbered excerpt>, "bug_kind": one of {KINDS}, "defect": "<=25 words: what was wrong in the pre-fix code", "fix": "<=25 words: what the change does", "confidence": 0-1}}
Say false if the change is style, renaming, a new feature, a version/dependency bump, text/label change, or you cannot see a concrete defect in the pre-fix lines."""
    body=json.dumps(dict(model=MODEL,messages=[dict(role='user',content=p)],max_tokens=350,temperature=0,reasoning=dict(enabled=False),usage=dict(include=True),response_format=dict(type='json_object')))
    for t in range(2):
        try:
            rq=urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',body.encode(),{'Authorization':'Bearer '+KEY,'Content-Type':'application/json'})
            j=json.load(urllib.request.urlopen(rq,timeout=120)); spent[0]+=j.get('usage',{}).get('cost',0) or 0
            txt=j['choices'][0]['message']['content']; m=re.search(r'\{.*\}',txt,re.S); v=json.loads(m.group(0))
            return {**{x:c[x] for x in('repo','commit','file','pre_line')},'verdict':v,'cost':j.get('usage',{}).get('cost')}
        except Exception as e: err=str(e)[:100]
    return {**{x:c[x] for x in('repo','commit','file','pre_line')},'error':err}
cands=[json.loads(l) for l in open('data/candidates_dedup.jsonl')]
if len(sys.argv)>1: cands=cands[:int(sys.argv[1])]
with ThreadPoolExecutor(32) as ex, open(out,'a') as f:
    for r in ex.map(ask,cands):
        if r: f.write(json.dumps(r)+'\n'); f.flush()
print('spent',round(spent[0],3))
