#!/usr/bin/env python3
"""Run PySide6 qmllint (Qt 6) on every QML file in assistant outputs. Quickshell/qs.* modules are not
installed, so import/type warnings are expected; we score SYNTAX errors only (qmllint 'syntax' category)."""
import json,subprocess,sys,tempfile,os,re,collections
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from validate import safe_join
sys.path.insert(0,os.path.dirname(__file__))
QL=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..",".venv","bin","pyside6-qmllint")
def lint(files):
    with tempfile.TemporaryDirectory() as t:
        qs=[]
        for p,c in files.items():
            try: fp=safe_join(t,p)   # `### ../../x` from model output must not write outside t (audit C3)
            except ValueError: continue
            os.makedirs(os.path.dirname(fp),exist_ok=True); open(fp,'w').write(c)
            if p.endswith('.qml'): qs.append(fp)
        if not qs: return 0,0
        bad=0
        for q in qs:
            try: r=subprocess.run([QL,'--bare','--disable-plugins','all',q],capture_output=True,text=True,timeout=30)
            except subprocess.TimeoutExpired: return len(qs),-1
            if '[syntax]' in r.stdout+r.stderr: bad+=1
        return len(qs),bad
if __name__=='__main__':
    from build_parse import parse
    tot=collections.Counter()
    for fn in sys.argv[1:]:
        for line in open(fn):
            r=json.loads(line); files=parse(r['messages'][2]['content']); n,bad=lint(files)
            tot['examples']+=1; tot['qml_files']+=n; tot['syntax_bad_files']+=max(bad,0); tot['examples_clean']+= (bad==0); tot['lint_crash']+=(bad<0)
    print(dict(tot))
