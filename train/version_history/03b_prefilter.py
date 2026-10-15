#!/usr/bin/env python3
"""Dedup + prefilter candidate hunks for LLM judging (budget control). Deterministic (seed 0)."""
import json,re,random,collections
random.seed(0)
STRONG=re.compile(r"\b(fix(es|ed|ing)?|bug|crash(es|ed)?|error|broken|regression|hang|fail(s|ed|ure)?|doesn'?t work|not work(ing)?|wrong|incorrect|exception|leak|race|null|undefined|segfault|stuck|invalid)\b",re.I)
SKIPF=re.compile(r"(^|/)(package-lock\.json|.*\.min\.js|.*\.svg)$|(^|/)(test|tests|__tests__)/",re.I)
cs=[json.loads(l) for l in open('data/candidates.jsonl')]
seen=set(); out=[]
for c in cs:
    k=(c['commit'],c['file'],c['pre_line'])
    if k in seen: continue
    seen.add(k)
    if not STRONG.search(c['subject']): continue          # strong keyword must be in subject
    if SKIPF.search(c['file']): continue
    n=len(c['removed'])+len(c['added'])
    if n>16 or not any(x.strip() and not x.strip().startswith(('#','//','*','/*')) for x in c['removed']+c['added']): continue
    out.append(c)
# one hunk per (commit,file) first (smallest), then cap 8 commits/repo
by=collections.defaultdict(list)
for c in out: by[c['repo']].append(c)
final=[]
for r,l in by.items():
    cm=collections.OrderedDict()
    for c in sorted(l,key=lambda c:len(c['removed'])+len(c['added'])): cm.setdefault(c['commit'],c)
    final+=list(cm.values())[:8]
random.shuffle(final)
MAX=int(__import__('os').environ.get('MAXC','3200')); final=final[:MAX]
open('data/candidates_dedup.jsonl','w').write(''.join(json.dumps(c)+'\n' for c in final))
print(len(cs),'raw hunks',len(seen),'dedup',len(out),'after filter',len(final),'in',len({c['repo'] for c in final}),'repos')
