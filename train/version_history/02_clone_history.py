#!/usr/bin/env python3
"""Blobless full-history bare clones (commits+trees only) of universe repos into /workspace/vh_repos."""
import json,os,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
R='/workspace/vh_repos'; os.makedirs(R,exist_ok=True)
repos=json.load(open('data/universe.json'))['repos']
def one(u):
    d=R+'/'+u.replace('https://github.com/','').replace('/','__')
    if os.path.isdir(d+'/objects'): return u,'ok'
    try:
        r=subprocess.run(['git','clone','-q','--bare','--filter=blob:none','--single-branch',u+'.git',d],capture_output=True,text=True,timeout=120,env=dict(os.environ,GIT_TERMINAL_PROMPT='0'))
        if r.returncode: subprocess.run(['rm','-rf',d]); return u,'fail:'+r.stderr.strip()[-80:]
        return u,'ok'
    except Exception as e:
        subprocess.run(['rm','-rf',d]); return u,'fail:'+type(e).__name__
with ThreadPoolExecutor(24) as ex, open('data/clone_status.jsonl','a') as f:
    for u,s in ex.map(one,repos):
        f.write(json.dumps(dict(url=u,status=s))+'\n'); f.flush()
