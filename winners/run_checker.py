import os,sys,json
sys.path.insert(0,'/workspace/usuba-runs/winners/cr2/functest')
from usuba import checks, hancore_rules_v2 as h2
import static_checks as sc
R={'akshar.radio-atlas':'aksharp5__omarchy-radio-atlas','slcode777.omagotchi':'slcode777__omagotchi','io.github.thisisgm.omapods':'thisisgm__omarchy-pods','robzolkos.github':'robzolkos__omarchy-github'}
def load(d,skip=True):
    files={}
    for r,ds,fs in os.walk(d):
        ds[:]=[x for x in ds if x not in('.git','node_modules','__pycache__')+(('tests','test') if skip else ())]
        for f in fs:
            p=os.path.relpath(os.path.join(r,f),d)
            try: files[p]=open(os.path.join(r,f),encoding='utf-8').read()
            except Exception: pass
    return files
out={}
for pid,dn in R.items():
    d='/workspace/sweep_repos/'+dn; files=load(d)
    res={}
    try:
        man=json.loads(files['manifest.json'])
    except Exception as e: man=None
    try: res['usuba_checks']=checks.check(files,man)
    except Exception as e: res['usuba_checks']='ERR '+repr(e)
    try: fa,fl=sc.check(files); res['static_checks']={'fails':fa,'flags':fl}
    except Exception as e: res['static_checks']='ERR '+repr(e)
    allf=load(d,False)
    res['h_v3_enabled']=h2.check(allf)
    res['h_all_incl_experimental']=h2.check(allf,enabled=set(h2.RULES))
    out[pid]=res
json.dump(out,open('/workspace/usuba-runs/winners/checker_results.json','w'),indent=1,default=str)
for pid,r in out.items():
    print('==',pid)
    for k,v in r.items():
        if k=='usuba_checks' and isinstance(v,list):
            print(k,len(v))
            for x in v: print('   ',x['rule'],x['severity'],x['file'],x['reason'][:200])
        elif isinstance(v,dict):
            print(k,'fails',len(v['fails']),'flags',len(v['flags']))
            for x in v['fails']+v['flags']: print('   ',str(x)[:260])
        elif isinstance(v,list):
            print(k,len(v))
            for x in v: print('   ',x['rule'],x['file'],x['line'],x['reason'][:140])
        else: print(k,v)
