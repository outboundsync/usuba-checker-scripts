#!/usr/bin/env python3
"""Select ~4,000 additional unjudged candidates (same filters as 03b) for round 2, diversity-first.
Seed 1. Per-repo cap CAP (default 5 new). Score = predicted-underrepresented-kind bonus + permissive-license bonus + random jitter;
repos are taken round-robin (best-scored candidate of each repo per pass) until N reached."""
import json,re,random,collections,subprocess,os
random.seed(1)
N=int(os.environ.get('N','4000')); CAP=int(os.environ.get('CAP','5'))
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'03b_prefilter.py')).read().split("cs=[")[0].replace("random.seed(0)",""))   # STRONG, SKIPF
KW={'api-compat':r'compat|deprecat|api|version|upgrade|breaking|renamed|new (hyprland|quickshell|qt)|no longer|removed in|since \d',
 'null-guard':r'null|undefined|none\b|nil\b|empty|missing|guard|check (if|for)|exist|crash',
 'shell-quoting':r'quot|escap|space|glob|expan|word.?split|\$\(|"\$',
 'missing-dependency':r'depend|require|install|missing package|pacman|yay|pip |npm |import|not found|command not found',
 'error-handling':r'error|exception|fail|catch|try|handle|fallback|retry|abort|set -e|exit',
 'missing-file':r'manifest|file not|missing file|path|\.json|plugin\.json|not found|mkdir|ENOENT',
 'security':r'secur|inject|sanitiz|token|password|secret|permission|chmod|unsafe|traversal|credential|/tmp|mktemp|eval'}
KWc={k:re.compile(v,re.I) for k,v in KW.items()}
PERM=('MIT','Apache-2.0','BSD','ISC')
def lic(repo):
    for f in ('LICENSE','LICENSE.md','LICENSE.txt','COPYING','license'):
        r=subprocess.run(['git','-C','/workspace/vh_repos/'+repo,'show','HEAD:'+f],capture_output=True,text=True,errors='replace')
        if r.returncode==0:
            t=r.stdout[:3000].lower()
            for k,n in (('mit license','MIT'),('permission is hereby granted, free of charge','MIT'),('apache license','Apache-2.0'),('gnu general public license','GPL'),('gnu lesser general','LGPL'),('gnu affero','AGPL'),('bsd','BSD'),('mozilla public','MPL-2.0'),('unlicense','Unlicense'),('isc license','ISC')):
                if k in t: return n
            return 'other-license-file'
    return 'none-found'
done={(j['repo'],j['commit']) for j in map(json.loads,open('data/llm_verdicts.jsonl'))}
seen=set(); pool={}
for l in open('data/candidates.jsonl'):
    c=json.loads(l); k=(c['commit'],c['file'],c['pre_line'])
    if k in seen: continue
    seen.add(k)
    if (c['repo'],c['commit']) in done or 'jankeesvw' in c['repo'].lower(): continue
    if not STRONG.search(c['subject']) or SKIPF.search(c['file']): continue
    n=len(c['removed'])+len(c['added'])
    if n>16 or not any(x.strip() and not x.strip().startswith(('#','//','*','/*')) for x in c['removed']+c['added']): continue
    cur=pool.get((c['repo'],c['commit']))
    if cur is None or n<len(cur['removed'])+len(cur['added']): pool[(c['repo'],c['commit'])]=c   # smallest hunk per commit
from concurrent.futures import ThreadPoolExecutor
_repos=sorted({r for r,_ in pool})
with ThreadPoolExecutor(24) as ex: LIC=dict(zip(_repos,ex.map(lic,_repos)))   # network-bound (blobless clones fetch LICENSE lazily)
excl=set(json.load(open('data/universe.json'))['excluded'])
L={}
by=collections.defaultdict(list)
for (r,_),c in pool.items():
    if 'https://github.com/'+r.replace('__','/',1) in excl: continue
    L[r]=LIC[r]
    txt=c['subject']+' '+' '.join(c['removed']+c['added'])
    hits=[k for k,p in KWc.items() if p.search(txt)]
    c['_pred']=hits
    s=len(hits)*1.0+(1.5 if L[r] in PERM else 0)+(0.3 if L[r]=='GPL' else 0)+random.random()
    by[r].append((s,c))
sel=[]
for r in by: by[r].sort(key=lambda x:-x[0])
rep=sorted(by); rnd=0
while len(sel)<N and rnd<CAP:
    layer=[by[r][rnd] for r in rep if len(by[r])>rnd]
    layer.sort(key=lambda x:-x[0]); sel+=layer[:N-len(sel)]; rnd+=1
out=[c for _,c in sel]; random.shuffle(out)
for c in out: c.pop('_pred',None)
open('data/candidates_round2.jsonl','w').write(''.join(json.dumps(c)+'\n' for c in out))
print('pool commits',len(pool),'selected',len(out),'repos',len({c['repo'] for c in out}),'permissive-license share',round(sum(L[c['repo']] in PERM for c in out)/len(out),3))
