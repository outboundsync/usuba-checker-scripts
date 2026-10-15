#!/usr/bin/env python3
"""Find candidate bug-fix commits by message, extract single-file hunks with PRE-fix line numbers, run mechanical verification (pre-fix line exists at parent and matches removed text)."""
import json,os,re,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
R='/workspace/vh_repos'
MAXCAND=120
FIX=re.compile(r"\b(fix(es|ed|ing)?|bug(fix)?|crash(es|ed)?|error|broken|break(s|ing)?|regress(ion)?|hang(s)?|freez\w*|fail(s|ed|ure|ing)?|doesn'?t work|not work(ing)?|wrong|incorrect|exception|leak|race|null|undefined|unbound|resolve[sd]?|patch|hotfix|workaround|missing|invalid|segfault|stuck|corrupt\w*|typo in (path|command|var))\b",re.I)
SKIP=re.compile(r"^(docs?|chore|style|refactor|feat|test|ci|build|release|bump)(\(.*\))?[:!]|^merge |^bump |^release |^v?\d+\.\d+|\b(readme|changelog|license|screenshot|typo in (readme|doc))\b|^(add|update) (readme|docs)",re.I)
CODE=re.compile(r"\.(sh|bash|zsh|py|qml|js|mjs|ts|lua|rs|go|conf|toml|css|fish|rb|pl|c|cpp|h|service|desktop)$|(^|/)bin/[^/.]+$|(^|/)(install|uninstall|setup|run|start)[^/]*$",re.I)
def g(d,*a,**k): return subprocess.run(['git','-C',d]+list(a),capture_output=True,text=True,errors='replace',timeout=120,**k)
def mine(rd):
    d=R+'/'+rd; out=[]
    r=g(d,'log','--no-merges','--format=%H%x1f%P%x1f%an%x1f%aI%x1f%s%x1f%b%x1e')
    if r.returncode: return rd,None,[]
    commits=[c for c in r.stdout.split('\x1e') if c.strip()]
    n=len(commits); ncand=0
    for c in commits:
        h,par,an,ad,subj,body=(c.strip('\n').split('\x1f')+['']*6)[:6]
        if not par or ' ' in par.strip(): continue
        if SKIP.search(subj) or not FIX.search(subj+' '+body[:400]): continue
        p=par.strip()
        ncand+=1
        if ncand>MAXCAND: break   # cap per repo: huge repos (thousands of commits) are not plugin-shaped
        ns=g(d,'diff','--numstat',p,h)
        if ns.returncode: continue
        files=[l.split('\t') for l in ns.stdout.splitlines()]
        code=[f for f in files if len(f)==3 and CODE.search(f[2]) and f[0]!='-' and not re.search(r'(^|/)(node_modules|vendor|dist|\.github)/',f[2])]
        if not code or len(code)>3 or sum(int(f[0])+int(f[1]) for f in code)>60: continue
        for f in code:
            fn=f[2]
            if ' => ' in fn or '{' in fn: continue
            df=g(d,'diff','-U0','--no-renames',p,h,'--',fn).stdout
            for m in re.finditer(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*\n((?:[-+\\].*\n?)*)',df,re.M):
                os_,oc,ns_,nc,hunk=m.groups(); os_=int(os_); oc=int(oc) if oc is not None else 1; nc=int(nc) if nc is not None else 1
                rem=[l[1:] for l in hunk.splitlines() if l.startswith('-')]
                add=[l[1:] for l in hunk.splitlines() if l.startswith('+')]
                if len(rem)+len(add)>24: continue
                old=g(d,'show',f'{p}:{fn}').stdout.splitlines()
                if rem: ln=os_; verified_line=all(os_-1+i<len(old) and old[os_-1+i]==rem[i] for i in range(len(rem))); kind_hunk='modify' if add else 'delete'
                else: ln=os_+1; verified_line=ln<=len(old); kind_hunk='insert'   # pure insertion: pre-fix anchor = line after insertion point
                if not verified_line: continue
                out.append(dict(repo=rd,commit=h,parent=p,author_date=ad,subject=subj,body=body.strip()[:500],file=fn,pre_line=ln,pre_end=ln+max(len(rem),1)-1,hunk_kind=kind_hunk,removed=rem,added=add,n_commits=n))
    return rd,n,out
if __name__=='__main__':
    st=[json.loads(l) for l in open('data/clone_status.jsonl')]
    ok=sorted({s['url'].replace('https://github.com/','').replace('/','__') for s in st if s['status']=='ok' and 'jankeesvw' not in s['url'].lower()})
    stats={}
    with ThreadPoolExecutor(8) as ex, open('data/candidates.jsonl','w') as f:
        for rd,n,o in ex.map(mine,ok):
            stats[rd]=n
            for x in o: f.write(json.dumps(x)+'\n')
    json.dump(stats,open('data/repo_commit_counts.json','w'))
    print(len(ok),'repos mined')
