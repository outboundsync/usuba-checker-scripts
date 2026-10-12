import json,collections,os,shutil,subprocess
c=collections.Counter
S=json.load(open('sources/sources.json'))
rows=[json.loads(l) for f in ['data/train.jsonl','data/holdout.jsonl'] for l in open(f)]
usedrepos=c(r['meta']['repo'] for r in rows)
L=["| Plugin id | Repo | Commit | Stars | Commits | Author | Core contrib (commits) | Author plugins | LICENSE file (verified) | Catalog label | Manifest license | Copyright | Vendored/3p flags | Bucket | Examples |","|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for s in sorted(S,key=lambda s:-(s['stars'] or 0)):
    L.append(f"| {s['id']} | {s['repo']} | `{s['commit'][:10]}` | {s['stars']} | {s['commits']} | {s['author']} | {'yes' if s['core'] else 'no'} ({s['coreCommits']}) | {s['authorPlugins']} | {s['licenseVerified']} ({s['licenseFile']}) | {s['catalogLicense']} | {', '.join(str(x) for x in s['manifestLicense'])} | {'; '.join(s['copyright'])} | {', '.join(s['vendored']) or '-'} | {s['bucket']} | {usedrepos.get(s['repo'],0)} |")
open('sources/SOURCES.md','w').write("\n".join(L)+"\n")
shutil.rmtree('sources/licenses',ignore_errors=True); os.makedirs('sources/licenses')
N=["NOTICE — Omarchy Specialist seed dataset","","Training text is derived from the sources below. Every source's LICENSE file was read at the pinned commit; all are MIT.",
"MIT requires the copyright notice and permission notice in all copies or substantial portions: ship this file and sources/licenses/* with the dataset and with the model.","",
"- basecamp/omarchy @ 9480d1b6a98156314dbabe6bfef08f39f8b9cd07 — MIT — Copyright (c) David Heinemeier Hansson"]
shutil.copy('/tmp/omarchy-src/LICENSE','sources/licenses/basecamp-omarchy.LICENSE')
house=sorted({(r['meta']['repo'],r['meta']['commit']) for r in rows if r['meta']['origin']=='house'})
for repo,sha in house:
    n=repo.split('/')[-1]; lt=open(f'/workspace/{n}/LICENSE').read(); cr=[l for l in lt.splitlines() if l.startswith('Copyright')][0]
    N.append(f"- kenhara/{n} @ {sha} — MIT — {cr}"); shutil.copy(f'/workspace/{n}/LICENSE',f'sources/licenses/kenhara-{n}.LICENSE')
for s in sorted(S,key=lambda s:s['repo'].lower()):
    if usedrepos.get(s['repo']):
        N.append(f"- {s['repo'].replace('https://github.com/','')} @ {s['commit']} — {s['licenseVerified']} — {s['copyright'][0]}")
        shutil.copy(f"sources/repos/{s['id']}/{s['licenseFile']}",f"sources/licenses/{s['repo'].split('/')[3]}-{s['repo'].split('/')[4]}.LICENSE")
N.append("- (vendored inside mtolhuys/omacrunch) mtolhuys/omakit @ 2a3b95629518dfbdaa880bf528ce2ce495b27b45 — MIT — Copyright (c) 2026 Maarten Tolhuijs")
open('NOTICE','w').write("\n".join(N)+"\n")
tr=[r for r in rows if r['meta']['split']=='train']; ho=[r for r in rows if r['meta']['split']=='holdout']
def tab(key,multi=False):
    out=["| | train | holdout | total |","|---|---|---|---|"]
    get=(lambda r:key(r)) if multi else (lambda r:[key(r)])
    keys=c(k for r in rows for k in get(r))
    for k,v in keys.most_common(): out.append(f"| {k} | {sum(k in get(r) for r in tr)} | {sum(k in get(r) for r in ho)} | {v} |")
    return "\n".join(out)
pk=lambda r:next(k for k in ['menu','bar','overlay','panel','service','bar-widget'] if k in r['meta']['kinds'])
stats=("### By task\n"+tab(lambda r:r['task'].split(':')[0])+"\n\n### By task (detailed)\n"+tab(lambda r:r['task'])+
"\n\n### By kind (an example counts once per kind it declares)\n"+tab(lambda r:r['meta']['kinds'],True)+
"\n\n### By primary kind (rarest kind; holdout strata)\n"+tab(pk)+"\n\n### By origin\n"+tab(lambda r:r['meta']['origin'])+
"\n\n### House plugins\n"+tab(lambda r:r['meta']['repo'].split('/')[-1] if r['meta']['origin']=='house' else '(not house)')+
"\n\n### Origin × kind\n"+tab(lambda r:[r['meta']['origin']+'/'+k for k in r['meta']['kinds']],True)+
"\n\n### Full plugin vs chunked\n"+tab(lambda r:'chunked' if r['meta'].get('chunked') else 'full/fix')+
"\n\n### By complexity\n"+tab(lambda r:r['meta']['complexity']))
open('data/STATS.md','w').write(stats+"\n")
print(len(tr),len(ho),len(N)-5,'notice sources',len(os.listdir('sources/licenses')),'licenses')
print(c(s['bucket'] for s in S))
