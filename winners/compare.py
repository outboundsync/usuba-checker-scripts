import json,statistics as st
C=json.load(open('corpus_profile.json')); W=json.load(open('winners_profile.json'))
def pct(f): return round(100*sum(1 for c in C if f(c))/len(C),1)
def med(f):
    v=[f(c) for c in C]; return st.median(v), round(st.quantiles(v,n=10)[8],1)
rows=[('has_license',lambda c:c['has_license']),('has_readme',lambda c:c['has_readme']),('has_tests',lambda c:c['has_tests']),('has_ci',lambda c:c['has_ci']),
('has_changelog',lambda c:c['has_changelog']),('has_agent_files',lambda c:c['has_agent_files']),('has_docs_dir',lambda c:c['has_docs_dir']),
('manifest.license',lambda c:bool(c['manifest'] and c['manifest']['license'])),('manifest.repository/homepage',lambda c:bool(c['manifest'] and c['manifest']['repository'])),
('manifest.keywords',lambda c:bool(c['manifest'] and c['manifest']['keywords'])),('barWidget.schema',lambda c:bool(c['manifest'] and c['manifest']['schema'])),
('barWidget.defaults',lambda c:bool(c['manifest'] and c['manifest']['defaults'])),('uses onExited/exitCode',lambda c:c['api']['exitCode']+c['api']['onExited']>0),
('timeouts present',lambda c:c['api']['timeout']>0),('try/catch',lambda c:c['api']['try/catch']>0),('set -e/pipefail',lambda c:c['api']['sh set -e/pipefail']>0),
('command -v dep probe',lambda c:c['api']['command -v']>0),('mktemp',lambda c:c['api']['mktemp']>0),('StdioCollector',lambda c:c['api']['StdioCollector']>0),
('FileView',lambda c:c['api']['FileView']>0),('Timer',lambda c:c['api']['Timer']>0),('IpcHandler',lambda c:c['api']['IpcHandler']>0)]
out=['| metric | corpus pct (n=%d) | %s |'%(len(C),' | '.join(W)),'|---|---|'+'---|'*len(W)]
def wv(w,n):
    m=w['manifest'] or {}
    return {'manifest.license':m.get('license'),'manifest.repository/homepage':m.get('repository'),'manifest.keywords':m.get('keywords'),'barWidget.schema':m.get('schema'),'barWidget.defaults':m.get('defaults'),
     'uses onExited/exitCode':w['api']['exitCode']+w['api']['onExited']>0,'timeouts present':w['api']['timeout']>0,'try/catch':w['api']['try/catch']>0,'set -e/pipefail':w['api']['sh set -e/pipefail']>0,
     'command -v dep probe':w['api']['command -v']>0,'mktemp':w['api']['mktemp']>0,'StdioCollector':w['api']['StdioCollector']>0,'FileView':w['api']['FileView']>0,'Timer':w['api']['Timer']>0,'IpcHandler':w['api']['IpcHandler']>0}.get(n, w.get(n))
for n,f in rows:
    out.append('| %s | %s | %s |'%(n,pct(f),' | '.join('Y' if wv(w,n) else 'n' for w in W.values())))
out.append('')
out.append('| size metric | corpus median | corpus p90 | '+' | '.join(W)+' |'); out.append('|---|---|---|'+'---|'*len(W))
for n,f in [('prod LOC',lambda c:c['prod_loc']),('test LOC',lambda c:c['test_loc']),('files',lambda c:c['files']),('bytes',lambda c:c['bytes'])]:
    m,p=med(f); out.append('| %s | %s | %s | %s |'%(n,m,p,' | '.join(str(f(w)) for w in W.values())))
# percentile rank of winners prod_loc
import bisect
pl=sorted(c['prod_loc'] for c in C)
out.append(''); out.append('winner prod-LOC percentile: '+', '.join('%s=%d%%'%(k,round(100*bisect.bisect(pl,w['prod_loc'])/len(pl))) for k,w in W.items()))
tl=sorted(c['test_loc'] for c in C)
out.append('winner test-LOC percentile: '+', '.join('%s=%d%%'%(k,round(100*bisect.bisect(tl,w['test_loc'])/len(tl))) for k,w in W.items()))
both=pct(lambda c:c['has_tests'] and c['has_ci'] and c['has_license'] and c['has_readme'])
out.append('corpus with license+readme+tests+CI: %s%%'%both)
open('comparison.md','w').write('\n'.join(out)); print('\n'.join(out))
